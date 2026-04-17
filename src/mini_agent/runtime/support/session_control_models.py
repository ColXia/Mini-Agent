"""Shared models and action routing for session control commands."""

from __future__ import annotations

from dataclasses import dataclass

from mini_agent.interfaces import MainAgentSessionControlResponse


def _safe_text(value: object) -> str:
    return " ".join(str(value or "").split())


SESSION_AGENT_CONTROL_ACTIONS = frozenset(
    {
        "compact",
        "drop_memories",
        "kb_on",
        "kb_off",
    }
)

SESSION_MCP_CONTROL_ACTIONS = frozenset(
    {
        "mcp_status",
        "mcp_list",
        "mcp_reload",
    }
)

SUPPORTED_SESSION_CONTROL_ACTIONS = SESSION_AGENT_CONTROL_ACTIONS | SESSION_MCP_CONTROL_ACTIONS


def normalize_session_control_action(action: str) -> str:
    return _safe_text(action).lower().replace("-", "_")


@dataclass(frozen=True, slots=True)
class RuntimeSessionControlCommand:
    action: str
    reason: str | None = None


@dataclass(slots=True)
class RuntimeSessionControlExecution:
    response: MainAgentSessionControlResponse
    transcript_summary: str
    transcript_details: str


__all__ = [
    "RuntimeSessionControlCommand",
    "RuntimeSessionControlExecution",
    "SESSION_AGENT_CONTROL_ACTIONS",
    "SESSION_MCP_CONTROL_ACTIONS",
    "SUPPORTED_SESSION_CONTROL_ACTIONS",
    "normalize_session_control_action",
]
