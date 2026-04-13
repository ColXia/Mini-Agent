"""Surface-neutral chat-turn orchestration for shared interaction services."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, AsyncIterator, Awaitable, Callable, TYPE_CHECKING
from uuid import uuid4

from fastapi import HTTPException

from mini_agent.application.session_service import ManagedSessionTurn, SessionApplicationService
from mini_agent.interfaces import MainAgentChatResponse

if TYPE_CHECKING:
    from mini_agent.application.surface_service_types import FormatBootstrapErrorFn, SseEventFn, ToUtcIsoFn


@dataclass(frozen=True)
class SurfaceChatExecutionRequest:
    message: str
    workspace_dir: Path
    session_id: str | None = None
    session_title_hint: str | None = None
    surface: str | None = None
    channel_type: str | None = None
    conversation_id: str | None = None
    sender_id: str | None = None
    dry_run: bool = False
    running_detail: str = ""


@dataclass(frozen=True)
class SurfaceChatStreamEvent:
    event_type: str
    payload: dict[str, Any]


@dataclass(frozen=True)
class SurfaceChatExecutionResult:
    reply: str
    stop_reason: str
    main_route_used: bool
    delegation_payload: dict[str, Any] | None = None
    supplemental_events: tuple[SurfaceChatStreamEvent, ...] = field(default_factory=tuple)


ExecuteSurfaceChatTurnFn = Callable[
    [ManagedSessionTurn, SurfaceChatExecutionRequest, Callable[[str, dict[str, Any]], Awaitable[None] | None] | None],
    Awaitable[SurfaceChatExecutionResult],
]


@dataclass(slots=True)
class SurfaceChatFlowHandler:
    session_service: SessionApplicationService
    to_utc_iso: "ToUtcIsoFn"
    sse_event: "SseEventFn"
    format_bootstrap_error: "FormatBootstrapErrorFn"
    stream_chunk_size: int

    async def run_chat(
        self,
        request: SurfaceChatExecutionRequest,
        *,
        execute_turn: ExecuteSurfaceChatTurnFn,
    ) -> MainAgentChatResponse:
        self.session_service.validate_workspace(request.workspace_dir)
        if request.dry_run:
            return self._build_dry_run_response(request)

        request.workspace_dir.mkdir(parents=True, exist_ok=True)
        turn = await self._prepare_turn(request)

        async with turn:
            execution = await self._execute_turn(turn, request, execute_turn=execute_turn)
            self._finalize_turn(turn, request=request, execution=execution)
            return MainAgentChatResponse(
                session_id=turn.session_id,
                reply=execution.reply,
                message_count=turn.message_count,
                token_usage=turn.token_usage,
                workspace_dir=str(turn.workspace_dir),
                updated_at=self.to_utc_iso(turn.updated_at),
                **(
                    {"delegation": dict(execution.delegation_payload)}
                    if isinstance(execution.delegation_payload, dict)
                    else {}
                ),
            )

    async def stream_chat_events(
        self,
        request: SurfaceChatExecutionRequest,
        *,
        execute_turn: ExecuteSurfaceChatTurnFn,
    ) -> AsyncIterator[str]:
        self.session_service.validate_workspace(request.workspace_dir)
        if request.dry_run:
            async for item in self._stream_dry_run_events(request):
                yield item
            return

        request.workspace_dir.mkdir(parents=True, exist_ok=True)
        turn = await self._prepare_turn(request)
        assistant_id = uuid4().hex
        yield self.sse_event("session", {"session_id": turn.session_id, "workspace_dir": str(turn.workspace_dir)})
        yield self.sse_event("status", {"stage": "running", "at": self.to_utc_iso(datetime.now(timezone.utc))})

        async with turn:
            stream_events: asyncio.Queue[tuple[str, dict[str, Any]]] = asyncio.Queue()

            async def _emit_stream_event(event_type: str, payload: dict[str, Any]) -> None:
                await stream_events.put((event_type, dict(payload)))

            task = asyncio.create_task(
                self._execute_turn(
                    turn,
                    request,
                    execute_turn=execute_turn,
                    activity_emitter=_emit_stream_event,
                )
            )
            try:
                while not task.done():
                    try:
                        event_type, payload = await asyncio.wait_for(stream_events.get(), timeout=0.9)
                        yield self.sse_event(event_type, payload)
                    except asyncio.TimeoutError:
                        yield self.sse_event("heartbeat", {"at": self.to_utc_iso(datetime.now(timezone.utc))})
                while not stream_events.empty():
                    event_type, payload = await stream_events.get()
                    yield self.sse_event(event_type, payload)
                execution = task.result()
            except HTTPException as exc:
                yield self.sse_event("error", {"message": str(exc.detail or "Request rejected.")})
                return
            except Exception as exc:
                yield self.sse_event("error", {"message": f"Agent execution failed: {exc}"})
                return

            for event in execution.supplemental_events:
                yield self.sse_event(event.event_type, dict(event.payload))

            self._finalize_turn(turn, request=request, execution=execution)
            for index in range(0, len(execution.reply), self.stream_chunk_size):
                chunk = execution.reply[index : index + self.stream_chunk_size]
                yield self.sse_event("delta", {"assistant_id": assistant_id, "chunk": chunk})
                await asyncio.sleep(0)

            yield self.sse_event(
                "done",
                {
                    "session_id": turn.session_id,
                    "assistant_id": assistant_id,
                    "reply": execution.reply,
                    "stop_reason": execution.stop_reason,
                    "token_usage": turn.token_usage,
                    "message_count": turn.message_count,
                    "updated_at": self.to_utc_iso(turn.updated_at),
                },
            )

    async def _prepare_turn(self, request: SurfaceChatExecutionRequest) -> ManagedSessionTurn:
        try:
            return await self.session_service.prepare_chat_turn(
                workspace_dir=request.workspace_dir,
                message=request.message,
                session_id=request.session_id,
                session_title_hint=request.session_title_hint,
                surface=request.surface,
                channel_type=request.channel_type,
                conversation_id=request.conversation_id,
                sender_id=request.sender_id,
                running_detail=request.running_detail,
            )
        except HTTPException:
            raise
        except Exception as exc:
            raise self.format_bootstrap_error(exc) from exc

    @staticmethod
    def _finalize_turn(
        turn: ManagedSessionTurn,
        *,
        request: SurfaceChatExecutionRequest,
        execution: SurfaceChatExecutionResult,
    ) -> None:
        if execution.main_route_used:
            turn.capture_prepared_context_state()
            if turn.recovery_context is not None:
                turn.clear_recovery_context()
        turn.record_message(
            role="assistant",
            content=execution.reply,
            surface=request.surface,
            channel_type=request.channel_type,
            conversation_id=request.conversation_id,
            sender_id=request.sender_id,
        )
        turn.touch()

    @staticmethod
    async def _execute_turn(
        turn: ManagedSessionTurn,
        request: SurfaceChatExecutionRequest,
        *,
        execute_turn: ExecuteSurfaceChatTurnFn,
        activity_emitter: Callable[[str, dict[str, Any]], Awaitable[None] | None] | None = None,
    ) -> SurfaceChatExecutionResult:
        try:
            return await execute_turn(turn, request, activity_emitter)
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Agent execution failed: {exc}") from exc

    def _build_dry_run_response(self, request: SurfaceChatExecutionRequest) -> MainAgentChatResponse:
        now = datetime.now(timezone.utc)
        return MainAgentChatResponse(
            session_id=request.session_id or "dry-run-session",
            reply=f"[Dry Run] Received task: {request.message}",
            message_count=1,
            token_usage=0,
            workspace_dir=str(request.workspace_dir),
            updated_at=self.to_utc_iso(now),
        )

    async def _stream_dry_run_events(self, request: SurfaceChatExecutionRequest) -> AsyncIterator[str]:
        now = self.to_utc_iso(datetime.now(timezone.utc))
        sid = request.session_id or "dry-run-session"
        assistant_id = uuid4().hex
        yield self.sse_event("session", {"session_id": sid, "workspace_dir": str(request.workspace_dir)})
        yield self.sse_event("status", {"stage": "running", "at": now})
        text = f"[Dry Run] Received task: {request.message}"
        for index in range(0, len(text), self.stream_chunk_size):
            chunk = text[index : index + self.stream_chunk_size]
            yield self.sse_event("delta", {"assistant_id": assistant_id, "chunk": chunk})
            await asyncio.sleep(0)
        yield self.sse_event(
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


GatewayChatExecutionRequest = SurfaceChatExecutionRequest
GatewayChatExecutionResult = SurfaceChatExecutionResult
GatewayChatFlowHandler = SurfaceChatFlowHandler
GatewayChatStreamEvent = SurfaceChatStreamEvent
ExecuteGatewayChatTurnFn = ExecuteSurfaceChatTurnFn

__all__ = [
    "ExecuteSurfaceChatTurnFn",
    "SurfaceChatExecutionRequest",
    "SurfaceChatExecutionResult",
    "SurfaceChatFlowHandler",
    "SurfaceChatStreamEvent",
    "ExecuteGatewayChatTurnFn",
    "GatewayChatExecutionRequest",
    "GatewayChatExecutionResult",
    "GatewayChatFlowHandler",
    "GatewayChatStreamEvent",
]
