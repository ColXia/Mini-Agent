"""Session control command ownership for managed runtime sessions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Awaitable, Callable

from mini_agent.interfaces.agent import MainAgentSessionControlResponse
from mini_agent.runtime.handlers.session_agent_control_handler import (
    RuntimeSessionAgentControlHandler,
    RuntimeSessionControlCommand,
    RuntimeSessionControlExecution,
    normalize_session_control_action,
)
from mini_agent.runtime.handlers.session_command_coordinator import (
    RuntimeSessionCommandCoordinator,
    RuntimeSessionCommandTranscript,
)
from mini_agent.runtime.handlers.session_mcp_control_handler import (
    SESSION_MCP_CONTROL_ACTIONS,
    RuntimeSessionMcpControlHandler,
)

if TYPE_CHECKING:
    from mini_agent.runtime.handlers.session_agent_runtime_handler import RuntimeSessionAgentRuntimeHandler
    from mini_agent.session.store_records import MainAgentSessionState


def _safe_text(value: object) -> str:
    return " ".join(str(value or "").split())


@dataclass(slots=True)
class RuntimeSessionControlCommandHandler:
    session_commands: RuntimeSessionCommandCoordinator
    session_agent_control: RuntimeSessionAgentControlHandler
    session_mcp_control: RuntimeSessionMcpControlHandler
    session_agent_runtime: "RuntimeSessionAgentRuntimeHandler"
    selected_model_identity: Callable[["MainAgentSessionState"], tuple[str, str, str] | None]
    cleanup_mcp_connections: Callable[[], Awaitable[None]]

    async def control_session(
        self,
        session: "MainAgentSessionState",
        *,
        action: str,
        reason: str | None = None,
        surface: str | None = None,
        channel_type: str | None = None,
        conversation_id: str | None = None,
        sender_id: str | None = None,
    ) -> MainAgentSessionControlResponse:
        command = RuntimeSessionControlCommand(
            action=action,
            reason=_safe_text(reason) or None,
        )
        normalized_action = normalize_session_control_action(command.action)
        execution = await self.session_commands.execute_locked(
            session,
            operation=lambda: self._execute_session_control(
                session,
                command=command,
                normalized_action=normalized_action,
            ),
            transcript_builder=lambda execution: RuntimeSessionCommandTranscript(
                command=self._session_control_command_name(normalized_action),
                summary=execution.transcript_summary,
                content=execution.transcript_details,
                threads_visible=False if normalized_action.startswith("mcp_") else None,
            ),
            surface=self._active_surface(session, surface),
            channel_type=channel_type,
            conversation_id=conversation_id,
            sender_id=sender_id,
        )
        return execution.response

    async def _execute_session_control(
        self,
        session: "MainAgentSessionState",
        *,
        command: RuntimeSessionControlCommand,
        normalized_action: str,
    ) -> RuntimeSessionControlExecution:
        if normalized_action in SESSION_MCP_CONTROL_ACTIONS:
            return await self.session_mcp_control.execute(
                session,
                command,
                cleanup_mcp_connections=self.cleanup_mcp_connections,
                rebuild_session_agent=lambda: self.session_agent_runtime.rebuild_agent_with_identity(
                    session,
                    self.selected_model_identity(session),
                ),
            )
        return await self.session_agent_control.execute(
            session,
            command,
        )

    @staticmethod
    def _session_control_command_name(action: str) -> str:
        normalized = normalize_session_control_action(action)
        if normalized.startswith("mcp_"):
            return normalized.replace("_", " ")
        return normalized

    @staticmethod
    def _active_surface(
        session: "MainAgentSessionState",
        surface: str | None,
    ) -> str | None:
        return surface or session.projection.active_surface or session.projection.origin_surface


__all__ = ["RuntimeSessionControlCommandHandler"]
