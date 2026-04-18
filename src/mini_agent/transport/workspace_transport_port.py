"""Transport-facing contract for remote workspace client operations."""

from __future__ import annotations

from typing import Any, Protocol


class RemoteWorkspaceTransportPort(Protocol):
    """Transport contract consumed by `RemoteWorkspaceClient`."""

    async def list_workspaces(self) -> list[dict[str, Any]]: ...

    def list_workspaces_sync(self) -> list[dict[str, Any]]: ...

    async def get_workspace(self, workspace_id: str) -> dict[str, Any]: ...

    def get_workspace_sync(self, workspace_id: str) -> dict[str, Any]: ...

    async def get_active_workspace(self) -> dict[str, Any]: ...

    def get_active_workspace_sync(self) -> dict[str, Any]: ...

    async def switch_workspace(self, workspace_id: str) -> dict[str, Any]: ...

    def switch_workspace_sync(self, workspace_id: str) -> dict[str, Any]: ...

    async def get_workspace_runtime_summary(
        self,
        *,
        workspace_id: str | None = None,
    ) -> dict[str, Any]: ...

    def get_workspace_runtime_summary_sync(
        self,
        *,
        workspace_id: str | None = None,
    ) -> dict[str, Any]: ...


__all__ = ["RemoteWorkspaceTransportPort"]
