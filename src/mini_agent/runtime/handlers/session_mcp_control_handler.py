"""Session MCP inspection and reload controls."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Awaitable, Callable

from fastapi import HTTPException

from mini_agent.interfaces.agent import MainAgentSessionControlResponse
from mini_agent.runtime.handlers.session_agent_control_handler import (
    RuntimeSessionControlCommand,
    RuntimeSessionControlExecution,
    normalize_session_control_action,
)
from mini_agent.tools.mcp.command_service import McpCommandError, McpCommandService

if TYPE_CHECKING:
    from mini_agent.session.store_records import MainAgentSessionState


SESSION_MCP_CONTROL_ACTIONS = frozenset(
    {
        "mcp_status",
        "mcp_list",
        "mcp_reload",
    }
)


@dataclass(slots=True)
class RuntimeSessionMcpControlHandler:
    normalize_surface: Callable[[str | None], str | None]
    load_runtime_config: Callable[[], Any]
    collect_mcp_operator_snapshot: Callable[[Any], Any]
    format_mcp_status: Callable[[Any], str]
    format_mcp_server_list: Callable[[Any], str]

    def validate_action(self, action: str) -> str:
        normalized = normalize_session_control_action(action)
        if normalized not in SESSION_MCP_CONTROL_ACTIONS:
            raise HTTPException(status_code=400, detail=f"Unsupported session control action: {action}")
        return normalized

    async def execute(
        self,
        session: "MainAgentSessionState",
        command: RuntimeSessionControlCommand,
        *,
        cleanup_mcp_connections: Callable[[], Awaitable[None]],
        rebuild_session_agent: Callable[[], Awaitable[None]],
    ) -> RuntimeSessionControlExecution:
        action = self.validate_action(command.action)
        service = McpCommandService(
            load_config=self.load_runtime_config,
            snapshot_loader=self.collect_mcp_operator_snapshot,
            status_formatter=self.format_mcp_status,
            server_list_formatter=self.format_mcp_server_list,
        )
        try:
            result = await service.execute(
                action=action,
                busy=bool(session.projection.busy),
                cleanup_connections=cleanup_mcp_connections,
                reload_callback=rebuild_session_agent,
            )
        except McpCommandError as exc:
            raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc

        response = MainAgentSessionControlResponse(
            status="controlled",
            session_id=session.session_id,
            action=action,
            applied=result.applied,
            active_surface=self.normalize_surface(session.projection.active_surface or session.projection.origin_surface),
            knowledge_base_enabled=bool(session.projection.knowledge_base_enabled),
            stats={
                "summary": result.summary,
                "details": result.details,
                "configured_total": int(getattr(result.snapshot, "configured_total", 0) or 0),
                "discoverable_total": int(getattr(result.snapshot, "discoverable_total", 0) or 0),
                "disabled_total": int(getattr(result.snapshot, "disabled_total", 0) or 0),
                "active_total": int(getattr(result.snapshot, "active_total", 0) or 0),
                "tool_total": int(getattr(result.snapshot, "tool_total", 0) or 0),
            },
        )
        return RuntimeSessionControlExecution(
            response=response,
            transcript_summary=result.summary,
            transcript_details=result.details,
        )


__all__ = [
    "SESSION_MCP_CONTROL_ACTIONS",
    "RuntimeSessionMcpControlHandler",
]



