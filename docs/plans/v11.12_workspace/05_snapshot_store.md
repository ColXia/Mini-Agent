# 快照存储开发文档

**模块**: workspace_runtime/snapshot_store
**优先级**: P1
**预估时间**: 已实现，文档补全

---

## 一、功能概述

快照存储负责：

- 工作空间运行时状态捕获
- 快照持久化与恢复
- 共享快照管理

---

## 二、快照组件总览

| 组件 | 职责 |
|------|------|
| `WorkspaceRuntimeSnapshot` | 运行时快照 |
| `InMemoryWorkspaceSnapshotStore` | 内存快照存储 |

---

## 三、核心快照组件

### 3.1 WorkspaceRuntimeSnapshot

```python
# src/mini_agent/workspace_runtime/snapshot_store.py

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
```

### 3.2 InMemoryWorkspaceSnapshotStore

```python
@dataclass(slots=True)
class InMemoryWorkspaceSnapshotStore:
    """Append-only in-memory snapshot store for workspace-runtime state."""
    _snapshots: list[WorkspaceRuntimeSnapshot] = field(default_factory=list)

    def save(self, snapshot: WorkspaceRuntimeSnapshot) -> WorkspaceRuntimeSnapshot:
        """Save snapshot."""
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
        """Create and save snapshot."""
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
        """Get snapshot by ID."""
        normalized = _normalize_snapshot_id(snapshot_id)
        for snapshot in reversed(self._snapshots):
            if snapshot.snapshot_id == normalized:
                return snapshot
        return None

    def latest(self, workspace_dir: str | Path | None = None) -> WorkspaceRuntimeSnapshot | None:
        """Get latest snapshot."""
        if workspace_dir is None:
            return self._snapshots[-1] if self._snapshots else None
        normalized_workspace = _normalize_path(workspace_dir)
        for snapshot in reversed(self._snapshots):
            if snapshot.workspace_dir == normalized_workspace:
                return snapshot
        return None

    def list(self, workspace_dir: str | Path | None = None) -> list[WorkspaceRuntimeSnapshot]:
        """List snapshots."""
        if workspace_dir is None:
            return list(self._snapshots)
        normalized_workspace = _normalize_path(workspace_dir)
        return [snapshot for snapshot in self._snapshots if snapshot.workspace_dir == normalized_workspace]

    def clear(self) -> None:
        """Clear all snapshots."""
        self._snapshots.clear()

    def __len__(self) -> int:
        """Get snapshot count."""
        return len(self._snapshots)
```

---

## 四、共享快照管理

```python
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
    ...
```

---

## 五、快照序列化

```python
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
    ...

def restore_shared_workspace_snapshot(
    payload: Any,
    *,
    workspace_dir: str | Path | None = None,
) -> WorkspaceRuntimeSnapshot | None:
    """Restore one persisted snapshot payload into the shared workspace snapshot store."""
    ...
```

---

## 六、快照结构

```
┌─────────────────────────────────────────────────────────────────┐
│                    WorkspaceRuntimeSnapshot                      │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  snapshot_id: str              # 快照唯一标识                   │
│  workspace_dir: Path           # 工作空间目录                   │
│  created_at: datetime          # 创建时间                       │
│  mode: WorkspaceRuntimeMode    # 运行时模式                     │
│  scope: WorkspaceAccessScope   # 访问范围                       │
│  descriptor: WorkspaceRuntimeDescriptor  # 运行时描述符         │
│  mutation_records: tuple[MutationRecord, ...]  # 变更记录       │
│  metadata: dict[str, Any]      # 元数据                         │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## 七、文件位置

```
src/mini_agent/workspace_runtime/
├── snapshot_store.py            # 本文档所述组件
```

---

## 八、验收标准

- [x] 支持快照创建
- [x] 支持快照存储
- [x] 支持快照查询
- [x] 支持快照序列化
- [x] 支持共享快照

---

## 九、依赖关系

- 依赖: mutation_ledger, runtime_modes, workspace_executor
- 被依赖: workspace_executor.py, session/persistence.py