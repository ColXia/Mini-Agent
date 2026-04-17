"""User-facing workspace operations facade."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from mini_agent.application.ports.workspace_runtime_port import WorkspaceRuntimePort
from mini_agent.application.use_cases.workspace_application_service import WorkspaceApplicationService


@dataclass(slots=True)
class WorkspaceUserService:
    """Thin user-service facade for workspace queries and switching."""

    application_service: WorkspaceApplicationService | None = None
    workspace_runtime: WorkspaceRuntimePort | None = None

    def _application(self) -> WorkspaceApplicationService:
        if self.application_service is None:
            self.application_service = WorkspaceApplicationService(workspace_runtime=self.workspace_runtime)
        return self.application_service

    async def list_workspaces(self) -> Any:
        return await self._application().list_workspaces()

    async def get_workspace(self, workspace_id: str) -> Any:
        return await self._application().get_workspace(workspace_id)

    async def get_active_workspace(self) -> Any:
        return await self._application().get_active_workspace()

    async def switch_workspace(self, workspace_id: str) -> Any:
        return await self._application().switch_workspace(workspace_id)

    async def get_workspace_runtime_summary(self, workspace_id: str | None = None) -> Any:
        return await self._application().get_workspace_runtime_summary(workspace_id)


__all__ = ["WorkspaceUserService"]
