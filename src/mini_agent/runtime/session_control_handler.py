"""Session control routing extracted from the runtime manager."""

from __future__ import annotations

import inspect
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Awaitable, Callable

from fastapi import HTTPException

from mini_agent.interfaces import MainAgentSessionControlResponse

if TYPE_CHECKING:
    from mini_agent.runtime.session_state import MainAgentSessionState


def _safe_text(value: object) -> str:
    return " ".join(str(value or "").split())


SUPPORTED_SESSION_CONTROL_ACTIONS = frozenset(
    {
        "compact",
        "drop_memories",
        "kb_on",
        "kb_off",
        "mcp_status",
        "mcp_list",
        "mcp_reload",
    }
)


@dataclass(frozen=True, slots=True)
class RuntimeSessionControlCommand:
    action: str
    reason: str | None = None


@dataclass(slots=True)
class RuntimeSessionControlExecution:
    response: MainAgentSessionControlResponse
    transcript_summary: str
    transcript_details: str


@dataclass(slots=True)
class RuntimeSessionControlHandler:
    normalize_surface: Callable[[str | None], str | None]
    apply_agent_knowledge_base_enabled: Callable[[Any, bool], bool]
    load_runtime_config: Callable[[], Any]
    collect_mcp_operator_snapshot: Callable[[Any], Any]
    format_mcp_status: Callable[[Any], str]
    format_mcp_server_list: Callable[[Any], str]

    @staticmethod
    def normalize_action(action: str) -> str:
        return _safe_text(action).lower().replace("-", "_")

    def validate_action(self, action: str) -> str:
        normalized = self.normalize_action(action)
        if normalized not in SUPPORTED_SESSION_CONTROL_ACTIONS:
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
        normalized_action = self.validate_action(command.action)
        normalized_reason = _safe_text(command.reason) or None

        if session.projection.busy and normalized_action not in {"mcp_status", "mcp_list"}:
            raise HTTPException(status_code=409, detail="Session is busy. Wait for the current turn to finish.")

        active_surface = self.normalize_surface(session.projection.active_surface or session.projection.origin_surface)

        if normalized_action in {"mcp_status", "mcp_list", "mcp_reload"}:
            response = await self._execute_mcp_action(
                session,
                action=normalized_action,
                active_surface=active_surface,
                cleanup_mcp_connections=cleanup_mcp_connections,
                rebuild_session_agent=rebuild_session_agent,
            )
        elif normalized_action in {"kb_on", "kb_off"}:
            desired_enabled = normalized_action == "kb_on"
            previous_enabled = bool(session.projection.knowledge_base_enabled)
            effective_enabled = self.apply_agent_knowledge_base_enabled(
                session.runtime.agent,
                desired_enabled,
            )
            session.projection.knowledge_base_enabled = effective_enabled
            response = MainAgentSessionControlResponse(
                status="controlled",
                session_id=session.session_id,
                action=normalized_action,
                applied=(previous_enabled != effective_enabled),
                active_surface=active_surface,
                reason=normalized_reason,
                knowledge_base_enabled=effective_enabled,
            )
        else:
            response = await self._execute_context_action(
                session,
                action=normalized_action,
                reason=normalized_reason,
                active_surface=active_surface,
            )

        return RuntimeSessionControlExecution(
            response=response,
            transcript_summary=self._control_summary(
                normalized_action,
                applied=response.applied,
                response=response,
            ),
            transcript_details=self._control_details(response),
        )

    async def _execute_mcp_action(
        self,
        session: "MainAgentSessionState",
        *,
        action: str,
        active_surface: str | None,
        cleanup_mcp_connections: Callable[[], Awaitable[None]],
        rebuild_session_agent: Callable[[], Awaitable[None]],
    ) -> MainAgentSessionControlResponse:
        try:
            config = self.load_runtime_config()
        except Exception as exc:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to load config for MCP inspection: {exc}",
            ) from exc

        if action == "mcp_reload":
            try:
                await cleanup_mcp_connections()
                await rebuild_session_agent()
            except Exception as exc:
                raise HTTPException(
                    status_code=500,
                    detail=f"MCP reload failed: {exc}",
                ) from exc

        snapshot = self.collect_mcp_operator_snapshot(config)
        summary, details = self._mcp_control_output(action, snapshot=snapshot)
        return MainAgentSessionControlResponse(
            status="controlled",
            session_id=session.session_id,
            action=action,
            applied=action == "mcp_reload",
            active_surface=active_surface,
            knowledge_base_enabled=bool(session.projection.knowledge_base_enabled),
            stats={
                "summary": summary,
                "details": details,
                "configured_total": int(getattr(snapshot, "configured_total", 0) or 0),
                "discoverable_total": int(getattr(snapshot, "discoverable_total", 0) or 0),
                "disabled_total": int(getattr(snapshot, "disabled_total", 0) or 0),
                "active_total": int(getattr(snapshot, "active_total", 0) or 0),
                "tool_total": int(getattr(snapshot, "tool_total", 0) or 0),
            },
        )

    async def _execute_context_action(
        self,
        session: "MainAgentSessionState",
        *,
        action: str,
        reason: str | None,
        active_surface: str | None,
    ) -> MainAgentSessionControlResponse:
        control_method = (
            getattr(session.runtime.agent, "compact_context", None)
            if action == "compact"
            else getattr(session.runtime.agent, "drop_memories", None)
        )
        if control_method is None:
            raise HTTPException(status_code=400, detail=f"Session control not supported: {action}")

        result = control_method(reason=reason)
        if inspect.isawaitable(result):
            result = await result
        if not isinstance(result, dict):
            result = {"applied": bool(result)}

        return MainAgentSessionControlResponse(
            status="controlled",
            session_id=session.session_id,
            action=action,
            applied=bool(result.get("applied", False)),
            active_surface=active_surface,
            reason=reason,
            message_count_before=max(0, int(result.get("message_count_before") or 0)),
            message_count_after=max(0, int(result.get("message_count_after") or 0)),
            token_count_before=max(0, int(result.get("token_count_before") or 0)),
            token_count_after=max(0, int(result.get("token_count_after") or 0)),
            knowledge_base_enabled=bool(session.projection.knowledge_base_enabled),
            stats=dict(result.get("stats")) if isinstance(result.get("stats"), dict) else None,
        )

    def _mcp_control_output(self, action: str, *, snapshot: Any) -> tuple[str, str]:
        if action == "mcp_status":
            return (
                f"{int(getattr(snapshot, 'active_total', 0) or 0)} active server(s) | "
                f"{int(getattr(snapshot, 'tool_total', 0) or 0)} tool(s)",
                self.format_mcp_status(snapshot),
            )
        details = f"{self.format_mcp_status(snapshot)}\n\n{self.format_mcp_server_list(snapshot)}"
        if action == "mcp_list":
            return (
                f"{int(getattr(snapshot, 'configured_total', 0) or 0)} configured server(s) | "
                f"{int(getattr(snapshot, 'active_total', 0) or 0)} active",
                details,
            )
        return (
            f"reloaded MCP | {int(getattr(snapshot, 'active_total', 0) or 0)} active server(s) | "
            f"{int(getattr(snapshot, 'tool_total', 0) or 0)} tool(s)",
            details,
        )

    @staticmethod
    def _control_summary(
        action: str,
        *,
        applied: bool,
        response: MainAgentSessionControlResponse,
    ) -> str:
        if action in {"mcp_status", "mcp_list", "mcp_reload"}:
            stats = response.stats if isinstance(response.stats, dict) else {}
            summary = str(stats.get("summary") or "").strip()
            if summary:
                return summary
            if action == "mcp_reload":
                return "reloaded MCP bindings"
            return "MCP status shown" if action == "mcp_status" else "MCP server list shown"
        if action == "compact":
            return "context compacted" if applied else "context already compact"
        if action == "kb_on":
            return "knowledge base enabled" if applied else "knowledge base already enabled"
        if action == "kb_off":
            return "knowledge base disabled" if applied else "knowledge base already disabled"
        return "older memories dropped" if applied else "no older memories to drop"

    @staticmethod
    def _control_details(response: MainAgentSessionControlResponse) -> str:
        normalized = _safe_text(response.action).lower().replace("-", "_")
        if normalized in {"mcp_status", "mcp_list", "mcp_reload"}:
            stats = response.stats if isinstance(response.stats, dict) else {}
            details = str(stats.get("details") or "").strip()
            if details:
                return details
            return f"Action: {response.action}"
        if normalized in {"kb_on", "kb_off"}:
            lines = [
                f"Action: {response.action}",
                f"Knowledge Base: {'enabled' if bool(response.knowledge_base_enabled) else 'disabled'}",
            ]
            if response.reason:
                lines.append(f"Reason: {response.reason}")
            return "\n".join(lines)
        lines = [
            f"Action: {response.action}",
            f"Messages: {response.message_count_before} -> {response.message_count_after}",
            f"Tokens: {response.token_count_before} -> {response.token_count_after}",
        ]
        if response.reason:
            lines.append(f"Reason: {response.reason}")
        if isinstance(response.stats, dict):
            lines.append(
                "Stats: "
                f"masked={int(response.stats.get('masked_messages') or 0)}, "
                f"snipped={int(response.stats.get('snipped_messages') or 0)}, "
                f"merged={int(response.stats.get('merged_messages') or 0)}"
            )
        return "\n".join(lines)


__all__ = [
    "RuntimeSessionControlCommand",
    "RuntimeSessionControlExecution",
    "RuntimeSessionControlHandler",
    "SUPPORTED_SESSION_CONTROL_ACTIONS",
]
