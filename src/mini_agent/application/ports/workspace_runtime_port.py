"""Runtime-facing workspace seams for application services."""

from __future__ import annotations

from typing import Any, Protocol


class WorkspaceRuntimePort(Protocol):
    """Application-facing contract for workspace queries and switching."""

    async def list_workspaces(self) -> Any: ...

    async def get_workspace(self, workspace_id: str) -> Any: ...

    async def get_active_workspace(self) -> Any: ...

    async def switch_workspace(self, workspace_id: str) -> Any: ...

    async def get_workspace_runtime_summary(self, workspace_id: str | None = None) -> Any: ...


__all__ = ["WorkspaceRuntimePort"]
