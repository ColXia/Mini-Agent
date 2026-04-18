"""Direct host-backed workspace executor."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from mini_agent.workspace_runtime.boundary import WorkspaceBoundary
from mini_agent.workspace_runtime.mutation_ledger import InMemoryMutationLedger
from mini_agent.workspace_runtime.outside_zone_policy import DefaultOutsideZonePolicy
from mini_agent.workspace_runtime.permission_table import WorkspacePermissionTable
from mini_agent.workspace_runtime.runtime_modes import WorkspaceRuntimeMode
from mini_agent.workspace_runtime.workspace_executor import WorkspaceAccessScope, WorkspaceExecutor


@dataclass(slots=True)
class DirectWorkspaceExecutor(WorkspaceExecutor):
    """Direct filesystem executor rooted at one workspace boundary."""

    def __init__(
        self,
        boundary: WorkspaceBoundary | str | Path,
        *,
        scope: WorkspaceAccessScope = WorkspaceAccessScope.WORKSPACE_ONLY,
        outside_zone_policy: DefaultOutsideZonePolicy | None = None,
        permission_table: WorkspacePermissionTable | None = None,
        mutation_ledger: InMemoryMutationLedger | None = None,
    ) -> None:
        super().__init__(
            boundary=boundary,
            mode=WorkspaceRuntimeMode.DIRECT,
            scope=scope,
            outside_zone_policy=outside_zone_policy or DefaultOutsideZonePolicy(),
            permission_table=permission_table,
            mutation_ledger=mutation_ledger,
        )


__all__ = ["DirectWorkspaceExecutor"]
