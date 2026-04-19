"""Workspace-bound execution and path-access helpers."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any

from mini_agent.agent_core.execution.sandbox.manager import SandboxManager
from mini_agent.agent_core.execution.sandbox.network import NetworkAccessMode, NetworkDomainPolicy
from mini_agent.security.policy import RuntimePolicyEngine

from .boundary import WorkspaceBoundary
from .mutation_ledger import InMemoryMutationLedger, MutationKind, shared_mutation_ledger
from .outside_zone_policy import DefaultOutsideZonePolicy, OutsideZoneDecision, OutsideZoneOperation
from .permission_table import WorkspacePermissionTable
from .runtime_modes import WorkspaceRuntimeDescriptor, WorkspaceRuntimeMode

if TYPE_CHECKING:
    from .snapshot_store import InMemoryWorkspaceSnapshotStore, WorkspaceRuntimeSnapshot


def _clean_text(value: object) -> str:
    return " ".join(str(value or "").split())


class WorkspaceAccessScope(str, Enum):
    """How one executor should treat paths outside the workspace root."""

    WORKSPACE_ONLY = "workspace_only"
    WITH_OUTSIDE_ZONE = "with_outside_zone"


class WorkspaceAccessError(PermissionError):
    """Raised when one workspace executor rejects a path access request."""


@dataclass(frozen=True, slots=True)
class WorkspacePathAccess:
    """Resolved path-access decision for one workspace operation."""

    requested_path: str
    resolved_path: Path
    inside_workspace: bool
    mode: WorkspaceRuntimeMode
    scope: WorkspaceAccessScope
    relative_path: Path | None = None
    outside_decision: OutsideZoneDecision | None = None

    @property
    def requires_approval(self) -> bool:
        return bool(self.outside_decision and self.outside_decision.requires_approval)

    @property
    def protected(self) -> bool:
        return bool(self.outside_decision and self.outside_decision.protected)


@dataclass(slots=True)
class WorkspaceExecutor:
    """Shared workspace-bound access owner for direct execution slices."""

    boundary: WorkspaceBoundary | str | Path
    mode: WorkspaceRuntimeMode
    scope: WorkspaceAccessScope = WorkspaceAccessScope.WORKSPACE_ONLY
    outside_zone_policy: DefaultOutsideZonePolicy = field(default_factory=DefaultOutsideZonePolicy)
    permission_table: WorkspacePermissionTable | None = None
    mutation_ledger: InMemoryMutationLedger | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.boundary, WorkspaceBoundary):
            self.boundary = WorkspaceBoundary(self.boundary)

    def resolve_access(
        self,
        path: str | Path,
        *,
        kind: MutationKind,
        approved: bool | None = None,
        detail: str | None = None,
    ) -> WorkspacePathAccess:
        requested_path = str(path)
        resolved_path = self.boundary.resolve_path(path)
        relative_path = self.boundary.relative_path(resolved_path)
        if relative_path is not None:
            if self.permission_table is not None:
                permission = self.permission_table.decide(kind=kind, relative_path=relative_path)
                if not permission.allowed:
                    self._record_denied_path(
                        resolved_path,
                        kind=kind,
                        detail=detail or permission.reason,
                        approved=False,
                        inside_workspace=True,
                    )
                    raise WorkspaceAccessError(
                        permission.reason or f"Workspace permission denied: {relative_path}"
                    )
            access = WorkspacePathAccess(
                requested_path=requested_path,
                resolved_path=resolved_path,
                inside_workspace=True,
                relative_path=relative_path,
                mode=self.mode,
                scope=self.scope,
            )
            self._record_access(access, kind=kind, approved=approved, detail=detail)
            return access

        if self.scope is WorkspaceAccessScope.WORKSPACE_ONLY:
            self._record_denied_path(
                resolved_path,
                kind=kind,
                detail=detail,
                approved=False,
                inside_workspace=False,
            )
            raise WorkspaceAccessError(
                f"Path escapes workspace root: {path} (workspace: {self.boundary.root})"
            )

        decision = self.outside_zone_policy.decide(self._outside_operation_for(kind), resolved_path)
        access = WorkspacePathAccess(
            requested_path=requested_path,
            resolved_path=resolved_path,
            inside_workspace=False,
            relative_path=None,
            mode=self.mode,
            scope=self.scope,
            outside_decision=decision,
        )

        if decision.allowed:
            self._record_access(access, kind=kind, approved=approved, detail=detail or decision.reason)
            return access
        if decision.requires_approval and approved:
            self._record_access(access, kind=kind, approved=True, detail=detail or decision.reason)
            return access

        self._record_access(access, kind=kind, approved=False, detail=detail or decision.reason)
        if decision.requires_approval:
            raise WorkspaceAccessError(
                f"Outside-workspace {self._outside_operation_for(kind).value} requires approval: {resolved_path}"
            )
        raise WorkspaceAccessError(
            f"Outside-workspace {self._outside_operation_for(kind).value} denied: {resolved_path}"
        )

    @property
    def runtime_descriptor(self) -> WorkspaceRuntimeDescriptor:
        return WorkspaceRuntimeDescriptor(mode=self.mode)

    def resolve_execution_root(
        self,
        *,
        cwd: str | Path | None = None,
        approved: bool | None = None,
        detail: str | None = None,
    ) -> WorkspacePathAccess:
        target = cwd if cwd is not None else self.boundary.root
        return self.resolve_access(
            target,
            kind=MutationKind.EXECUTE,
            approved=approved,
            detail=detail or "workspace execute",
        )

    def read_text(
        self,
        path: str | Path,
        *,
        encoding: str = "utf-8",
        approved: bool | None = None,
    ) -> str:
        access = self.resolve_access(path, kind=MutationKind.READ, approved=approved, detail="read text")
        return access.resolved_path.read_text(encoding=encoding)

    def write_text(
        self,
        path: str | Path,
        content: str,
        *,
        encoding: str = "utf-8",
        approved: bool | None = None,
        create_parent: bool = True,
    ) -> Path:
        access = self.resolve_access(path, kind=MutationKind.WRITE, approved=approved, detail="write text")
        if create_parent:
            access.resolved_path.parent.mkdir(parents=True, exist_ok=True)
        access.resolved_path.write_text(content, encoding=encoding)
        return access.resolved_path

    def replace_text(
        self,
        path: str | Path,
        *,
        old_text: str,
        new_text: str,
        encoding: str = "utf-8",
        approved: bool | None = None,
    ) -> Path:
        access = self.resolve_access(path, kind=MutationKind.EDIT, approved=approved, detail="replace text")
        content = access.resolved_path.read_text(encoding=encoding)
        if old_text not in content:
            raise ValueError(f"Text not found in file: {old_text}")
        access.resolved_path.write_text(content.replace(old_text, new_text), encoding=encoding)
        return access.resolved_path

    @staticmethod
    def _outside_operation_for(kind: MutationKind) -> OutsideZoneOperation:
        if kind is MutationKind.READ:
            return OutsideZoneOperation.READ
        if kind in {MutationKind.WRITE, MutationKind.EDIT, MutationKind.EXECUTE}:
            return OutsideZoneOperation.WRITE
        return OutsideZoneOperation.DELETE

    def _record_access(
        self,
        access: WorkspacePathAccess,
        *,
        kind: MutationKind,
        approved: bool | None,
        detail: str | None,
    ) -> None:
        if self.mutation_ledger is None:
            return
        self.mutation_ledger.record(
            kind,
            path=access.resolved_path,
            detail=_clean_text(detail) or None,
            inside_workspace=access.inside_workspace,
            approved=approved,
        )

    def _record_denied_path(
        self,
        path: Path,
        *,
        kind: MutationKind,
        detail: str | None,
        approved: bool | None,
        inside_workspace: bool,
    ) -> None:
        if self.mutation_ledger is None:
            return
        self.mutation_ledger.record(
            kind,
            path=path,
            detail=_clean_text(detail) or None,
            inside_workspace=inside_workspace,
            approved=approved,
        )


@dataclass(slots=True)
class WorkspaceRuntimeBundle:
    """Composed direct workspace runtime shared by workspace-bound tools."""

    boundary: WorkspaceBoundary
    executor: WorkspaceExecutor
    sandbox_manager: SandboxManager
    scope: WorkspaceAccessScope
    outside_zone_policy: DefaultOutsideZonePolicy
    permission_table: WorkspacePermissionTable
    mutation_ledger: InMemoryMutationLedger
    snapshot_store: InMemoryWorkspaceSnapshotStore

    @property
    def workspace_dir(self) -> Path:
        return self.boundary.root

    @property
    def descriptor(self) -> WorkspaceRuntimeDescriptor:
        return self.executor.runtime_descriptor

    def capture_snapshot(
        self,
        *,
        snapshot_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> WorkspaceRuntimeSnapshot:
        return self.snapshot_store.create(
            workspace_dir=self.workspace_dir,
            mode=self.descriptor.mode,
            scope=self.scope,
            descriptor=self.descriptor,
            mutation_records=self.mutation_ledger.snapshot(),
            metadata=metadata,
            snapshot_id=snapshot_id,
        )

    def latest_snapshot(self) -> WorkspaceRuntimeSnapshot | None:
        return self.snapshot_store.latest(self.workspace_dir)

    def to_summary(self) -> dict[str, Any]:
        from .snapshot_store import workspace_runtime_snapshot_payload

        selection = self.sandbox_manager.select_initial()
        latest_snapshot = self.latest_snapshot()
        return {
            "workspace_root": str(self.workspace_dir),
            "mode": self.descriptor.mode.value,
            "scope": self.scope.value,
            "sandbox_backend": selection.backend.value,
            "sandbox_reason": selection.reason,
            "permission_rule_count": len(self.permission_table.rules),
            "mutation_count": len(self.mutation_ledger),
            "snapshot_count": len(self.snapshot_store.list(self.workspace_dir)),
            "latest_snapshot_id": latest_snapshot.snapshot_id if latest_snapshot is not None else None,
            "latest_snapshot": workspace_runtime_snapshot_payload(latest_snapshot),
        }


def _resolve_network_policy(config) -> NetworkDomainPolicy:
    security = getattr(config, "security", None)
    raw_network_mode = str(getattr(security, "network_mode", "") or "").strip().lower()
    try:
        network_mode = (
            NetworkAccessMode(raw_network_mode)
            if raw_network_mode
            else NetworkAccessMode.ALLOW_ALL
        )
    except ValueError:
        network_mode = NetworkAccessMode.ALLOW_ALL
    return NetworkDomainPolicy(
        mode=network_mode,
        allow_domains=tuple(getattr(security, "network_allow_domains", []) or ()),
        block_domains=tuple(getattr(security, "network_block_domains", []) or ()),
    ).normalized()


def build_direct_workspace_runtime_bundle(
    config,
    workspace_dir: str | Path,
    *,
    policy_engine: RuntimePolicyEngine | None = None,
    scope: WorkspaceAccessScope = WorkspaceAccessScope.WORKSPACE_ONLY,
    outside_zone_policy: DefaultOutsideZonePolicy | None = None,
    permission_table: WorkspacePermissionTable | None = None,
    mutation_ledger: InMemoryMutationLedger | None = None,
    snapshot_store: InMemoryWorkspaceSnapshotStore | None = None,
) -> WorkspaceRuntimeBundle:
    """Compose the maintained direct workspace-runtime bundle."""

    from .adapters.direct_executor import DirectWorkspaceExecutor
    from .snapshot_store import shared_workspace_snapshot_store

    active_policy = policy_engine or RuntimePolicyEngine.from_config(config)
    boundary = WorkspaceBoundary(workspace_dir)
    resolved_outside_zone_policy = outside_zone_policy or DefaultOutsideZonePolicy()
    resolved_permission_table = permission_table or WorkspacePermissionTable()
    resolved_mutation_ledger = mutation_ledger or shared_mutation_ledger(boundary.root)
    resolved_snapshot_store = snapshot_store or shared_workspace_snapshot_store(boundary.root)
    executor = DirectWorkspaceExecutor(
        boundary,
        scope=scope,
        outside_zone_policy=resolved_outside_zone_policy,
        permission_table=resolved_permission_table,
        mutation_ledger=resolved_mutation_ledger,
    )
    security = getattr(config, "security", None)
    sandbox_manager = SandboxManager(
        workspace_dir=boundary.root,
        sandbox_mode=active_policy.policy.sandbox_mode,
        network_policy=_resolve_network_policy(config),
        max_processes=getattr(security, "sandbox_max_processes", None),
        max_process_memory_mb=getattr(security, "sandbox_max_process_memory_mb", None),
    )
    return WorkspaceRuntimeBundle(
        boundary=boundary,
        executor=executor,
        sandbox_manager=sandbox_manager,
        scope=scope,
        outside_zone_policy=resolved_outside_zone_policy,
        permission_table=resolved_permission_table,
        mutation_ledger=resolved_mutation_ledger,
        snapshot_store=resolved_snapshot_store,
    )


__all__ = [
    "WorkspaceAccessError",
    "WorkspaceAccessScope",
    "WorkspaceExecutor",
    "WorkspacePathAccess",
    "WorkspaceRuntimeBundle",
    "build_direct_workspace_runtime_bundle",
]
