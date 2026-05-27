# 工作空间执行器开发文档

**模块**: workspace_runtime/workspace_executor
**优先级**: P0
**预估时间**: 已实现，文档补全

---

## 一、功能概述

工作空间执行器负责：

- 路径访问控制
- 文件操作封装
- 运行时包组装

---

## 二、执行器组件总览

| 组件 | 职责 |
|------|------|
| `WorkspaceAccessScope` | 访问范围枚举 |
| `WorkspaceAccessError` | 访问错误 |
| `WorkspacePathAccess` | 路径访问决策 |
| `WorkspaceExecutor` | 工作空间执行器 |
| `WorkspaceRuntimeBundle` | 运行时包 |

---

## 三、核心执行器组件

### 3.1 WorkspaceAccessScope

```python
# src/mini_agent/workspace_runtime/workspace_executor.py

class WorkspaceAccessScope(str, Enum):
    """How one executor should treat paths outside the workspace root."""
    WORKSPACE_ONLY = "workspace_only"       # 仅限工作空间
    WITH_OUTSIDE_ZONE = "with_outside_zone" # 允许外部区域
```

### 3.2 WorkspaceAccessError

```python
class WorkspaceAccessError(PermissionError):
    """Raised when one workspace executor rejects a path access request."""
```

### 3.3 WorkspacePathAccess

```python
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
        """Check if approval is required."""
        return bool(self.outside_decision and self.outside_decision.requires_approval)

    @property
    def protected(self) -> bool:
        """Check if path is protected."""
        return bool(self.outside_decision and self.outside_decision.protected)
```

### 3.4 WorkspaceExecutor

```python
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

    # === 路径访问 ===

    def resolve_access(
        self,
        path: str | Path,
        *,
        kind: MutationKind,
        approved: bool | None = None,
        detail: str | None = None,
    ) -> WorkspacePathAccess:
        """Resolve path access."""
        requested_path = str(path)
        resolved_path = self.boundary.resolve_path(path)
        relative_path = self.boundary.relative_path(resolved_path)

        # 工作空间内部
        if relative_path is not None:
            if self.permission_table is not None:
                permission = self.permission_table.decide(kind=kind, relative_path=relative_path)
                if not permission.allowed:
                    self._record_denied_path(...)
                    raise WorkspaceAccessError(...)
            access = WorkspacePathAccess(...)
            self._record_access(access, kind=kind, approved=approved, detail=detail)
            return access

        # 工作空间外部
        if self.scope is WorkspaceAccessScope.WORKSPACE_ONLY:
            raise WorkspaceAccessError(...)

        decision = self.outside_zone_policy.decide(self._outside_operation_for(kind), resolved_path)
        ...

    # === 文件操作 ===

    def read_text(
        self,
        path: str | Path,
        *,
        encoding: str = "utf-8",
        approved: bool | None = None,
    ) -> str:
        """Read text file."""
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
        """Write text file."""
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
        """Replace text in file."""
        ...
```

### 3.5 WorkspaceRuntimeBundle

```python
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
        """Get workspace directory."""
        return self.boundary.root

    @property
    def descriptor(self) -> WorkspaceRuntimeDescriptor:
        """Get runtime descriptor."""
        return self.executor.runtime_descriptor

    def capture_snapshot(
        self,
        *,
        snapshot_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> WorkspaceRuntimeSnapshot:
        """Capture snapshot."""
        return self.snapshot_store.create(...)

    def latest_snapshot(self) -> WorkspaceRuntimeSnapshot | None:
        """Get latest snapshot."""
        return self.snapshot_store.latest(self.workspace_dir)

    def to_summary(self) -> dict[str, Any]:
        """Get summary."""
        ...
```

---

## 四、运行时包构建

```python
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
```

---

## 五、访问控制流程

```
┌─────────────────────────────────────────────────────────────────┐
│                    Access Control Flow                           │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  Input: path, kind, approved                                    │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  1. Resolve path                                         │   │
│  │     - Normalize to absolute path                         │   │
│  │     - Get relative path from workspace root              │   │
│  └─────────────────────────────────────────────────────────┘   │
│                              │                                   │
│              ┌───────────────┴───────────────┐                  │
│              │                               │                  │
│              ▼                               ▼                  │
│  ┌───────────────────┐              ┌───────────────────┐      │
│  │  Inside Workspace │              │  Outside Workspace│      │
│  └─────────┬─────────┘              └─────────┬─────────┘      │
│            │                                  │                  │
│            ▼                                  ▼                  │
│  ┌───────────────────┐              ┌───────────────────┐      │
│  │ Check Permission  │              │ Check Scope       │      │
│  │ Table             │              │                   │      │
│  └─────────┬─────────┘              └─────────┬─────────┘      │
│            │                                  │                  │
│            ▼                        ┌─────────┴─────────┐      │
│  ┌───────────────────┐              │                   │      │
│  │ Allow/Deny        │              ▼                   ▼      │
│  └───────────────────┘    ┌───────────────┐   ┌───────────────┐│
│                           │ WORKSPACE_ONLY│   │WITH_OUTSIDE  ││
│                           │   → Deny      │   │   → Check    ││
│                           └───────────────┘   │     Policy   ││
│                                               └───────────────┘│
│                                                                 │
│  Output: WorkspacePathAccess                                    │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## 六、文件位置

```
src/mini_agent/workspace_runtime/
├── workspace_executor.py        # 本文档所述组件
└── adapters/
    └── direct_executor.py       # 直接执行器适配
```

---

## 七、验收标准

- [x] 支持路径访问控制
- [x] 支持文件操作封装
- [x] 支持运行时包组装
- [x] 支持权限检查

---

## 八、依赖关系

- 依赖: boundary, permission_table, mutation_ledger, snapshot_store, runtime_modes, outside_zone_policy
- 被依赖: runtime/, tools/