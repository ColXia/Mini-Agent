"""Typed client-side remote workspace client over the shared gateway transport."""

from __future__ import annotations

from mini_agent.interfaces import (
    MainAgentWorkspaceRuntimeSummary,
    MainAgentWorkspaceSummary,
    MainAgentWorkspaceSwitchRequest,
)

from .workspace_transport_port import RemoteWorkspaceTransportPort


class RemoteWorkspaceClient:
    """Typed client-side facade over the shared remote workspace transport."""

    def __init__(self, *, workspace_transport: RemoteWorkspaceTransportPort) -> None:
        self._workspace_transport = workspace_transport

    @staticmethod
    def _summary_model(payload: object) -> MainAgentWorkspaceSummary:
        return MainAgentWorkspaceSummary.model_validate(payload)

    @staticmethod
    def _runtime_summary_model(payload: object) -> MainAgentWorkspaceRuntimeSummary:
        return MainAgentWorkspaceRuntimeSummary.model_validate(payload)

    async def list_workspaces(self) -> list[MainAgentWorkspaceSummary]:
        payload = await self._workspace_transport.list_workspaces()
        return [
            MainAgentWorkspaceSummary.model_validate(item)
            for item in payload
            if isinstance(item, dict)
        ]

    def list_workspaces_sync(self) -> list[MainAgentWorkspaceSummary]:
        payload = self._workspace_transport.list_workspaces_sync()
        return [
            MainAgentWorkspaceSummary.model_validate(item)
            for item in payload
            if isinstance(item, dict)
        ]

    async def get_workspace(self, workspace_id: str) -> MainAgentWorkspaceSummary:
        payload = await self._workspace_transport.get_workspace(workspace_id)
        return self._summary_model(payload)

    def get_workspace_sync(self, workspace_id: str) -> MainAgentWorkspaceSummary:
        payload = self._workspace_transport.get_workspace_sync(workspace_id)
        return self._summary_model(payload)

    async def get_active_workspace(self) -> MainAgentWorkspaceSummary:
        payload = await self._workspace_transport.get_active_workspace()
        return self._summary_model(payload)

    def get_active_workspace_sync(self) -> MainAgentWorkspaceSummary:
        payload = self._workspace_transport.get_active_workspace_sync()
        return self._summary_model(payload)

    async def switch_workspace(
        self,
        request: MainAgentWorkspaceSwitchRequest,
    ) -> MainAgentWorkspaceSummary:
        payload = await self._workspace_transport.switch_workspace(request.workspace_id)
        return self._summary_model(payload)

    def switch_workspace_sync(
        self,
        request: MainAgentWorkspaceSwitchRequest,
    ) -> MainAgentWorkspaceSummary:
        payload = self._workspace_transport.switch_workspace_sync(request.workspace_id)
        return self._summary_model(payload)

    async def get_workspace_runtime_summary(
        self,
        *,
        workspace_id: str | None = None,
    ) -> MainAgentWorkspaceRuntimeSummary:
        payload = await self._workspace_transport.get_workspace_runtime_summary(workspace_id=workspace_id)
        return self._runtime_summary_model(payload)

    def get_workspace_runtime_summary_sync(
        self,
        *,
        workspace_id: str | None = None,
    ) -> MainAgentWorkspaceRuntimeSummary:
        payload = self._workspace_transport.get_workspace_runtime_summary_sync(workspace_id=workspace_id)
        return self._runtime_summary_model(payload)


__all__ = ["RemoteWorkspaceClient"]
