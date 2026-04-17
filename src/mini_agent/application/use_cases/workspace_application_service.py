"""Application service for workspace-facing queries and switching flows."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from mini_agent.application.ports.workspace_runtime_port import WorkspaceRuntimePort


def _require_workspace_runtime(runtime: WorkspaceRuntimePort | None) -> WorkspaceRuntimePort:
    if runtime is None:
        raise RuntimeError("Workspace runtime port is not configured.")
    return runtime


@dataclass(slots=True)
class WorkspaceApplicationService:
    """Owns workspace-facing application logic above the workspace runtime port."""

    workspace_runtime: WorkspaceRuntimePort | None = None

    async def list_workspaces(self) -> Any:
        return await _require_workspace_runtime(self.workspace_runtime).list_workspaces()

    async def get_workspace(self, workspace_id: str) -> Any:
        return await _require_workspace_runtime(self.workspace_runtime).get_workspace(workspace_id)

    async def get_active_workspace(self) -> Any:
        return await _require_workspace_runtime(self.workspace_runtime).get_active_workspace()

    async def switch_workspace(self, workspace_id: str) -> Any:
        return await _require_workspace_runtime(self.workspace_runtime).switch_workspace(workspace_id)

    async def get_workspace_runtime_summary(self, workspace_id: str | None = None) -> Any:
        return await _require_workspace_runtime(self.workspace_runtime).get_workspace_runtime_summary(workspace_id)


__all__ = ["WorkspaceApplicationService"]
