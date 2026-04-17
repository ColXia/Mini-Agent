"""Runtime-facing agent ownership seams for application services."""

from __future__ import annotations

from typing import Any, Protocol


class AgentRuntimePort(Protocol):
    """Application-facing contract for agent runtime queries."""

    async def list_agents(self) -> Any: ...

    async def get_agent(self, agent_id: str) -> Any: ...

    async def get_active_agent(self) -> Any: ...


__all__ = ["AgentRuntimePort"]
