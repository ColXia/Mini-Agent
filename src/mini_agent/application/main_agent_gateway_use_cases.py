"""Application-layer use cases for Studio Gateway main-agent endpoints."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, AsyncIterator, Callable
from uuid import uuid4

from fastapi import HTTPException

from mini_agent.interfaces import (
    MainAgentChatRequest,
    MainAgentChatResponse,
    MainAgentSessionMutationResponse,
    MainAgentSessionSummary,
)
from mini_agent.runtime.main_agent_runtime_manager import MainAgentRuntimeManager, MainAgentSessionState


ResolveWorkspaceDirFn = Callable[[str | None], Path]
ToUtcIsoFn = Callable[[datetime], str]
SseEventFn = Callable[[str, dict[str, Any]], str]
FormatBootstrapErrorFn = Callable[[Exception], HTTPException]


class MainAgentGatewayUseCases:
    """Main-agent orchestration use cases for chat and session flows."""

    def __init__(
        self,
        *,
        runtime_manager: MainAgentRuntimeManager,
        resolve_workspace_dir: ResolveWorkspaceDirFn,
        to_utc_iso: ToUtcIsoFn,
        sse_event: SseEventFn,
        format_bootstrap_error: FormatBootstrapErrorFn,
        stream_chunk_size: int,
    ) -> None:
        self._runtime_manager = runtime_manager
        self._resolve_workspace_dir = resolve_workspace_dir
        self._to_utc_iso = to_utc_iso
        self._sse_event = sse_event
        self._format_bootstrap_error = format_bootstrap_error
        self._stream_chunk_size = max(1, int(stream_chunk_size))

    async def run_chat(self, request: MainAgentChatRequest) -> MainAgentChatResponse:
        resolved_workspace = self._resolve_workspace_dir(request.workspace_dir)
        self._runtime_manager.validate_workspace(resolved_workspace)

        if request.dry_run:
            now = datetime.now(timezone.utc)
            return MainAgentChatResponse(
                session_id=request.session_id or "dry-run-session",
                reply=f"[Dry Run] Received task: {request.message}",
                message_count=1,
                token_usage=0,
                workspace_dir=str(resolved_workspace),
                updated_at=self._to_utc_iso(now),
            )

        workspace_dir = resolved_workspace
        workspace_dir.mkdir(parents=True, exist_ok=True)
        try:
            session = await self._runtime_manager.get_or_create_session(request.session_id, workspace_dir)
        except HTTPException:
            raise
        except Exception as exc:
            raise self._format_bootstrap_error(exc) from exc
        async with session.lock:
            session.agent.add_user_message(request.message)
            try:
                reply = await session.agent.run()
            except Exception as exc:
                raise HTTPException(status_code=500, detail=f"Agent execution failed: {exc}") from exc
            session.touch()
            return MainAgentChatResponse(
                session_id=session.session_id,
                reply=reply,
                message_count=len(session.agent.messages),
                token_usage=session.agent.api_total_tokens,
                workspace_dir=str(session.workspace_dir),
                updated_at=self._to_utc_iso(session.updated_at),
            )

    async def list_sessions(self) -> list[MainAgentSessionSummary]:
        return await self._runtime_manager.list_sessions()

    async def delete_session(self, session_id: str) -> MainAgentSessionMutationResponse:
        await self._runtime_manager.delete_session(session_id)
        return MainAgentSessionMutationResponse(status="deleted", session_id=session_id)

    async def reset_session(self, session_id: str) -> MainAgentSessionMutationResponse:
        await self._runtime_manager.reset_session(session_id)
        return MainAgentSessionMutationResponse(status="reset", session_id=session_id)

    async def stream_chat_events(
        self,
        *,
        message: str,
        session_id: str | None = None,
        workspace_dir: str | None = None,
        dry_run: bool = False,
    ) -> AsyncIterator[str]:
        resolved_workspace = self._resolve_workspace_dir(workspace_dir)
        self._runtime_manager.validate_workspace(resolved_workspace)
        resolved_workspace.mkdir(parents=True, exist_ok=True)

        if dry_run:
            now = self._to_utc_iso(datetime.now(timezone.utc))
            sid = session_id or "dry-run-session"
            assistant_id = uuid4().hex
            yield self._sse_event("session", {"session_id": sid, "workspace_dir": str(resolved_workspace)})
            yield self._sse_event("status", {"stage": "running", "at": now})
            text = f"[Dry Run] Received task: {message}"
            for index in range(0, len(text), self._stream_chunk_size):
                chunk = text[index : index + self._stream_chunk_size]
                yield self._sse_event("delta", {"assistant_id": assistant_id, "chunk": chunk})
                await asyncio.sleep(0)
            yield self._sse_event(
                "done",
                {
                    "session_id": sid,
                    "assistant_id": assistant_id,
                    "reply": text,
                    "token_usage": 0,
                    "message_count": 1,
                    "updated_at": now,
                },
            )
            return

        try:
            session = await self._runtime_manager.get_or_create_session(session_id, resolved_workspace)
        except HTTPException:
            raise
        except Exception as exc:
            raise self._format_bootstrap_error(exc) from exc
        assistant_id = uuid4().hex
        yield self._sse_event("session", {"session_id": session.session_id, "workspace_dir": str(session.workspace_dir)})
        yield self._sse_event("status", {"stage": "running", "at": self._to_utc_iso(datetime.now(timezone.utc))})

        async with session.lock:
            task = asyncio.create_task(self._run_agent_once(session, message))
            while not task.done():
                yield self._sse_event("heartbeat", {"at": self._to_utc_iso(datetime.now(timezone.utc))})
                await asyncio.sleep(0.9)

            try:
                reply = task.result()
            except Exception as exc:
                yield self._sse_event("error", {"message": f"Agent execution failed: {exc}"})
                return

            for index in range(0, len(reply), self._stream_chunk_size):
                chunk = reply[index : index + self._stream_chunk_size]
                yield self._sse_event("delta", {"assistant_id": assistant_id, "chunk": chunk})
                await asyncio.sleep(0)

            yield self._sse_event(
                "done",
                {
                    "session_id": session.session_id,
                    "assistant_id": assistant_id,
                    "reply": reply,
                    "token_usage": session.agent.api_total_tokens,
                    "message_count": len(session.agent.messages),
                    "updated_at": self._to_utc_iso(session.updated_at),
                },
            )

    async def _run_agent_once(self, session: MainAgentSessionState, message: str) -> str:
        session.agent.add_user_message(message)
        reply = await session.agent.run()
        session.touch()
        return reply
