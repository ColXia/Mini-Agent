"""User-facing workspace operations facade."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from mini_agent.application.ports.workspace_runtime_port import WorkspaceRuntimePort


@dataclass(slots=True)
class WorkspaceUserService:
    """Thin user-service facade for workspace queries and switching."""

    workspace_runtime: WorkspaceRuntimePort

    async def list_workspaces(self) -> Any:
        return await self.workspace_runtime.list_workspaces()

    async def get_workspace(self, workspace_id: str) -> Any:
        return await self.workspace_runtime.get_workspace(workspace_id)

    async def get_active_workspace(self) -> Any:
        return await self.workspace_runtime.get_active_workspace()

    async def switch_workspace(self, workspace_id: str) -> Any:
        return await self.workspace_runtime.switch_workspace(workspace_id)

    async def get_workspace_runtime_summary(self, workspace_id: str | None = None) -> Any:
        return await self.workspace_runtime.get_workspace_runtime_summary(workspace_id)


__all__ = ["WorkspaceUserService"]
