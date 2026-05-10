"""Local-session MCP reload semantics built on TUI-local agent runtime rebuilds."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from mini_agent.tools.mcp.command_service import McpReloadOutcome, build_mcp_reload_warm_prefix
from mini_agent.tui.local_agent_runtime_handler import LocalSessionAgentRuntimeHandler
from mini_agent.utils.text import safe_text


def _safe_text(value: object) -> str:
    return safe_text(value)


@dataclass(slots=True)
class LocalSessionMcpRuntimeService:
    """Own local MCP reload runtime rebuild flow for TUI local sessions."""

    agent_runtime: LocalSessionAgentRuntimeHandler

    async def reload_bindings(self, session: Any) -> McpReloadOutcome:
        outcome = await self.agent_runtime.rebuild_current_identity(
            session,
            warm_prefix=build_mcp_reload_warm_prefix(_safe_text(getattr(session, "title", ""))),
        )
        return McpReloadOutcome(
            rebuilt_runtime=True,
            active_model_label=outcome.active_model_label,
        )


__all__ = ["LocalSessionMcpRuntimeService"]
