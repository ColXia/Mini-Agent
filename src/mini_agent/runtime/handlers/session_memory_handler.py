"""Session memory command ownership for managed runtime sessions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable

from fastapi import HTTPException

from mini_agent.interfaces.agent import MainAgentSessionMemoryResponse
from mini_agent.memory.command_service import MemoryCommandRequest
from mini_agent.runtime.handlers.session_agent_control_handler import SessionControlErrorService
from mini_agent.runtime.handlers.session_command_coordinator import (
    RuntimeSessionCommandCoordinator,
    RuntimeSessionCommandTranscript,
)
from mini_agent.runtime.handlers.session_memory_command_handler import (
    RuntimeSessionMemoryCommandExecution,
    RuntimeSessionMemoryCommandHandler,
)

if TYPE_CHECKING:
    from mini_agent.session.store_records import MainAgentSessionState


def _safe_text(value: object) -> str:
    return " ".join(str(value or "").split())


@dataclass(slots=True)
class RuntimeSessionMemoryHandler:
    normalize_surface: Callable[[str | None], str]
    session_commands: RuntimeSessionCommandCoordinator
    session_memory_commands: RuntimeSessionMemoryCommandHandler
    persist_session: Callable[["MainAgentSessionState"], None]

    async def manage_memory(
        self,
        session: "MainAgentSessionState",
        *,
        action: str,
        engram_id: str | None = None,
        content: str | None = None,
        query: str | None = None,
        day: str | None = None,
        export_format: str | None = None,
        detail_mode: str | None = None,
        surface: str | None = None,
        channel_type: str | None = None,
        conversation_id: str | None = None,
        sender_id: str | None = None,
    ) -> MainAgentSessionMemoryResponse:
        normalized_detail_mode = _safe_text(detail_mode).lower() or "full"
        if normalized_detail_mode not in {"brief", "full"}:
            raise HTTPException(status_code=400, detail="detail_mode must be brief or full.")
        command = MemoryCommandRequest(
            action=_safe_text(action).lower().replace("-", "_"),
            engram_id=_safe_text(engram_id) or None,
            content=_safe_text(content) or None,
            query=_safe_text(query) or None,
            day=_safe_text(day) or None,
            export_format=_safe_text(export_format).lower() or None,
            detail_mode=normalized_detail_mode,
        )
        self.session_memory_commands.validate_action(command.action)

        if not self.session_memory_commands.is_mutating_action(command.action):
            execution = self.session_memory_commands.execute(session, command)
            self.persist_session(session)
            return self._build_session_memory_response(
                session=session,
                action=command.action,
                execution=execution,
            )

        execution = await self.session_commands.execute_locked(
            session,
            operation=lambda: self._execute_mutating_memory_command(session, command),
            transcript_builder=lambda execution: RuntimeSessionCommandTranscript(
                command=f"memory {command.action}",
                summary=str(execution.result.get("summary") or "memory command"),
                content=str(execution.result.get("details") or ""),
                threads_visible=False,
                metadata=(
                    {"engram_id": str(execution.result.get("engram_id") or command.engram_id)}
                    if (execution.result.get("engram_id") or command.engram_id)
                    else None
                ),
            ),
            surface=self._active_surface(session, surface),
            channel_type=channel_type,
            conversation_id=conversation_id,
            sender_id=sender_id,
        )
        return self._build_session_memory_response(
            session=session,
            action=command.action,
            execution=execution,
        )

    def _build_session_memory_response(
        self,
        *,
        session: "MainAgentSessionState",
        action: str,
        execution: RuntimeSessionMemoryCommandExecution,
    ) -> MainAgentSessionMemoryResponse:
        return MainAgentSessionMemoryResponse(
            status="ok",
            session_id=session.session_id,
            action=action,
            active_surface=self.normalize_surface(
                session.projection.active_surface or session.projection.origin_surface
            ),
            memory_diagnostics=dict(execution.memory_diagnostics),
            result=execution.result,
        )

    def _execute_mutating_memory_command(
        self,
        session: "MainAgentSessionState",
        command: MemoryCommandRequest,
    ) -> RuntimeSessionMemoryCommandExecution:
        if session.projection.busy:
            raise HTTPException(status_code=409, detail=SessionControlErrorService.busy_detail())
        return self.session_memory_commands.execute(session, command)

    @staticmethod
    def _active_surface(
        session: "MainAgentSessionState",
        surface: str | None,
    ) -> str | None:
        return surface or session.projection.active_surface or session.projection.origin_surface


__all__ = ["RuntimeSessionMemoryHandler"]
