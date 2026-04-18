"""Workspace-bound execution and path-access helpers."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from .boundary import WorkspaceBoundary
from .mutation_ledger import InMemoryMutationLedger, MutationKind
from .outside_zone_policy import DefaultOutsideZonePolicy, OutsideZoneDecision, OutsideZoneOperation
from .permission_table import WorkspacePermissionTable
from .runtime_modes import WorkspaceRuntimeDescriptor, WorkspaceRuntimeMode


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


__all__ = [
    "WorkspaceAccessError",
    "WorkspaceAccessScope",
    "WorkspaceExecutor",
    "WorkspacePathAccess",
]
