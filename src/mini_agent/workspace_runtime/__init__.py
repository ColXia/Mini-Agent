"""Workspace-runtime baseline exports."""

from .adapters import DirectWorkspaceExecutor
from .boundary import WorkspaceBoundary
from .mutation_ledger import (
    InMemoryMutationLedger,
    MutationKind,
    MutationRecord,
    clear_shared_mutation_ledgers,
    shared_mutation_ledger,
)
from .outside_zone_policy import DefaultOutsideZonePolicy, OutsideZoneDecision, OutsideZoneOperation
from .permission_table import (
    WorkspacePermissionDecision,
    WorkspacePermissionEffect,
    WorkspacePermissionRule,
    WorkspacePermissionTable,
)
from .runtime_bundle import WorkspaceRuntimeBundle, build_direct_workspace_runtime_bundle
from .runtime_modes import WorkspaceRuntimeDescriptor, WorkspaceRuntimeMode
from .snapshot_store import (
    InMemoryWorkspaceSnapshotStore,
    WorkspaceRuntimeSnapshot,
    capture_shared_workspace_snapshot,
    clear_shared_workspace_snapshot_stores,
    restore_shared_workspace_snapshot,
    shared_workspace_snapshot_store,
    workspace_runtime_snapshot_from_payload,
    workspace_runtime_snapshot_payload,
)
from .workspace_executor import WorkspaceAccessError, WorkspaceAccessScope, WorkspaceExecutor, WorkspacePathAccess

__all__ = [
    "capture_shared_workspace_snapshot",
    "clear_shared_mutation_ledgers",
    "clear_shared_workspace_snapshot_stores",
    "DefaultOutsideZonePolicy",
    "DirectWorkspaceExecutor",
    "InMemoryMutationLedger",
    "InMemoryWorkspaceSnapshotStore",
    "MutationKind",
    "MutationRecord",
    "OutsideZoneDecision",
    "OutsideZoneOperation",
    "WorkspacePermissionDecision",
    "WorkspacePermissionEffect",
    "WorkspacePermissionRule",
    "WorkspacePermissionTable",
    "WorkspaceRuntimeBundle",
    "WorkspaceAccessError",
    "WorkspaceAccessScope",
    "WorkspaceBoundary",
    "WorkspaceExecutor",
    "WorkspacePathAccess",
    "WorkspaceRuntimeDescriptor",
    "WorkspaceRuntimeMode",
    "WorkspaceRuntimeSnapshot",
    "build_direct_workspace_runtime_bundle",
    "restore_shared_workspace_snapshot",
    "shared_mutation_ledger",
    "shared_workspace_snapshot_store",
    "workspace_runtime_snapshot_from_payload",
    "workspace_runtime_snapshot_payload",
]
