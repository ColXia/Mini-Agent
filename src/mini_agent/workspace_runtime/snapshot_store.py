"""Workspace-runtime snapshot store primitives."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from uuid import uuid4

from .mutation_ledger import MutationRecord, shared_mutation_ledger
from .runtime_modes import WorkspaceRuntimeDescriptor, WorkspaceRuntimeMode
from .workspace_executor import WorkspaceAccessScope


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _normalize_path(value: str | Path) -> Path:
    return Path(value).expanduser().resolve(strict=False)


def _normalize_snapshot_id(value: str | None) -> str:
    text = " ".join(str(value or "").split())
    return text or uuid4().hex


def _to_utc_iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(timezone.utc).isoformat()


def _from_utc_iso(value: object, fallback: datetime | None = None) -> datetime:
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc)
    raw = " ".join(str(value or "").split())
    if raw:
        try:
            parsed = datetime.fromisoformat(raw)
            if parsed.tzinfo is None:
                return parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc)
        except Exception:
            pass
    return fallback or _utc_now()


def _safe_int(value: Any, *, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return int(default)


def _effective_mutation_count(snapshot: WorkspaceRuntimeSnapshot) -> int:
    if snapshot.mutation_records:
        return len(snapshot.mutation_records)
    return max(0, _safe_int(snapshot.metadata.get("recorded_mutation_count"), default=0))


@dataclass(frozen=True, slots=True)
class WorkspaceRuntimeSnapshot:
    """One workspace-runtime state capture."""

    snapshot_id: str
    workspace_dir: Path
    created_at: datetime = field(default_factory=_utc_now)
    mode: WorkspaceRuntimeMode = WorkspaceRuntimeMode.DIRECT
    scope: WorkspaceAccessScope = WorkspaceAccessScope.WORKSPACE_ONLY
    descriptor: WorkspaceRuntimeDescriptor | None = None
    mutation_records: tuple[MutationRecord, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "snapshot_id", _normalize_snapshot_id(self.snapshot_id))
        object.__setattr__(self, "workspace_dir", _normalize_path(self.workspace_dir))
        object.__setattr__(self, "metadata", dict(self.metadata or {}))
        object.__setattr__(self, "mutation_records", tuple(self.mutation_records or ()))


@dataclass(slots=True)
class InMemoryWorkspaceSnapshotStore:
    """Append-only in-memory snapshot store for workspace-runtime state."""

    _snapshots: list[WorkspaceRuntimeSnapshot] = field(default_factory=list)

    def save(self, snapshot: WorkspaceRuntimeSnapshot) -> WorkspaceRuntimeSnapshot:
        self._snapshots.append(snapshot)
        return snapshot

    def create(
        self,
        *,
        workspace_dir: str | Path,
        mode: WorkspaceRuntimeMode,
        scope: WorkspaceAccessScope,
        descriptor: WorkspaceRuntimeDescriptor | None = None,
        mutation_records: Iterable[MutationRecord] = (),
        metadata: dict[str, Any] | None = None,
        snapshot_id: str | None = None,
    ) -> WorkspaceRuntimeSnapshot:
        return self.save(
            WorkspaceRuntimeSnapshot(
                snapshot_id=snapshot_id or uuid4().hex,
                workspace_dir=workspace_dir,
                mode=mode,
                scope=scope,
                descriptor=descriptor,
                mutation_records=tuple(mutation_records),
                metadata=dict(metadata or {}),
            )
        )

    def get(self, snapshot_id: str) -> WorkspaceRuntimeSnapshot | None:
        normalized = _normalize_snapshot_id(snapshot_id)
        for snapshot in reversed(self._snapshots):
            if snapshot.snapshot_id == normalized:
                return snapshot
        return None

    def latest(self, workspace_dir: str | Path | None = None) -> WorkspaceRuntimeSnapshot | None:
        if workspace_dir is None:
            return self._snapshots[-1] if self._snapshots else None
        normalized_workspace = _normalize_path(workspace_dir)
        for snapshot in reversed(self._snapshots):
            if snapshot.workspace_dir == normalized_workspace:
                return snapshot
        return None

    def list(self, workspace_dir: str | Path | None = None) -> list[WorkspaceRuntimeSnapshot]:
        if workspace_dir is None:
            return list(self._snapshots)
        normalized_workspace = _normalize_path(workspace_dir)
        return [snapshot for snapshot in self._snapshots if snapshot.workspace_dir == normalized_workspace]

    def clear(self) -> None:
        self._snapshots.clear()

    def __len__(self) -> int:
        return len(self._snapshots)


_SHARED_WORKSPACE_SNAPSHOT_STORES: dict[str, InMemoryWorkspaceSnapshotStore] = {}


def shared_workspace_snapshot_store(workspace_dir: str | Path) -> InMemoryWorkspaceSnapshotStore:
    """Return the process-local shared snapshot store for one workspace."""

    key = str(_normalize_path(workspace_dir))
    store = _SHARED_WORKSPACE_SNAPSHOT_STORES.get(key)
    if store is None:
        store = InMemoryWorkspaceSnapshotStore()
        _SHARED_WORKSPACE_SNAPSHOT_STORES[key] = store
    return store


def clear_shared_workspace_snapshot_stores() -> None:
    """Clear all process-local shared workspace snapshot stores."""

    _SHARED_WORKSPACE_SNAPSHOT_STORES.clear()


def capture_shared_workspace_snapshot(
    workspace_dir: str | Path,
    *,
    mode: WorkspaceRuntimeMode | None = None,
    scope: WorkspaceAccessScope | None = None,
    descriptor: WorkspaceRuntimeDescriptor | None = None,
    mutation_records: Iterable[MutationRecord] | None = None,
    metadata: dict[str, Any] | None = None,
    snapshot_id: str | None = None,
) -> WorkspaceRuntimeSnapshot:
    """Capture one shared workspace-runtime snapshot using shared process-local state."""

    store = shared_workspace_snapshot_store(workspace_dir)
    latest = store.latest(workspace_dir)
    resolved_mode = mode or (latest.mode if latest is not None else WorkspaceRuntimeMode.DIRECT)
    resolved_scope = scope or (
        latest.scope if latest is not None else WorkspaceAccessScope.WORKSPACE_ONLY
    )
    resolved_descriptor = descriptor or (
        latest.descriptor
        if latest is not None and latest.descriptor is not None
        else WorkspaceRuntimeDescriptor(mode=resolved_mode)
    )
    resolved_records = (
        tuple(mutation_records)
        if mutation_records is not None
        else tuple(shared_mutation_ledger(workspace_dir).snapshot())
    )
    return store.create(
        workspace_dir=workspace_dir,
        mode=resolved_mode,
        scope=resolved_scope,
        descriptor=resolved_descriptor,
        mutation_records=resolved_records,
        metadata=metadata,
        snapshot_id=snapshot_id,
    )


def workspace_runtime_snapshot_payload(
    snapshot: WorkspaceRuntimeSnapshot | None,
) -> dict[str, Any] | None:
    """Serialize one workspace-runtime snapshot into a transport-safe payload."""

    if snapshot is None:
        return None
    return {
        "snapshot_id": snapshot.snapshot_id,
        "workspace_dir": str(snapshot.workspace_dir),
        "created_at": _to_utc_iso(snapshot.created_at),
        "mode": snapshot.mode.value,
        "scope": snapshot.scope.value,
        "descriptor_mode": snapshot.descriptor.mode.value if snapshot.descriptor is not None else None,
        "mutation_count": _effective_mutation_count(snapshot),
        "metadata": dict(snapshot.metadata),
    }


def workspace_runtime_snapshot_from_payload(
    payload: Any,
    *,
    default_workspace_dir: str | Path | None = None,
) -> WorkspaceRuntimeSnapshot | None:
    """Rehydrate one snapshot object from a persisted payload."""

    if not isinstance(payload, dict):
        return None
    workspace_dir = payload.get("workspace_dir") or default_workspace_dir
    if not workspace_dir:
        return None
    raw_mode = " ".join(str(payload.get("mode") or "").split()).lower()
    raw_scope = " ".join(str(payload.get("scope") or "").split()).lower()
    raw_descriptor_mode = " ".join(str(payload.get("descriptor_mode") or "").split()).lower()
    try:
        mode = WorkspaceRuntimeMode(raw_mode) if raw_mode else WorkspaceRuntimeMode.DIRECT
    except ValueError:
        mode = WorkspaceRuntimeMode.DIRECT
    try:
        scope = (
            WorkspaceAccessScope(raw_scope)
            if raw_scope
            else WorkspaceAccessScope.WORKSPACE_ONLY
        )
    except ValueError:
        scope = WorkspaceAccessScope.WORKSPACE_ONLY
    try:
        descriptor = (
            WorkspaceRuntimeDescriptor(mode=WorkspaceRuntimeMode(raw_descriptor_mode))
            if raw_descriptor_mode
            else WorkspaceRuntimeDescriptor(mode=mode)
        )
    except ValueError:
        descriptor = WorkspaceRuntimeDescriptor(mode=mode)
    metadata = dict(payload.get("metadata")) if isinstance(payload.get("metadata"), dict) else {}
    metadata.setdefault(
        "recorded_mutation_count",
        max(0, _safe_int(payload.get("mutation_count"), default=0)),
    )
    return WorkspaceRuntimeSnapshot(
        snapshot_id=str(payload.get("snapshot_id") or ""),
        workspace_dir=workspace_dir,
        created_at=_from_utc_iso(payload.get("created_at")),
        mode=mode,
        scope=scope,
        descriptor=descriptor,
        mutation_records=(),
        metadata=metadata,
    )


def restore_shared_workspace_snapshot(
    payload: Any,
    *,
    workspace_dir: str | Path | None = None,
) -> WorkspaceRuntimeSnapshot | None:
    """Restore one persisted snapshot payload into the shared workspace snapshot store."""

    snapshot = workspace_runtime_snapshot_from_payload(
        payload,
        default_workspace_dir=workspace_dir,
    )
    if snapshot is None:
        return None
    store = shared_workspace_snapshot_store(snapshot.workspace_dir)
    existing = store.get(snapshot.snapshot_id)
    if existing is not None:
        return existing
    return store.save(snapshot)


__all__ = [
    "capture_shared_workspace_snapshot",
    "clear_shared_workspace_snapshot_stores",
    "InMemoryWorkspaceSnapshotStore",
    "WorkspaceRuntimeSnapshot",
    "restore_shared_workspace_snapshot",
    "shared_workspace_snapshot_store",
    "workspace_runtime_snapshot_from_payload",
    "workspace_runtime_snapshot_payload",
]
