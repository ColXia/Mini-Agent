# 变更账本开发文档

**模块**: workspace_runtime/mutation_ledger
**优先级**: P1
**预估时间**: 已实现，文档补全

---

## 一、功能概述

变更账本负责：

- 工作空间操作记录
- 变更历史追踪
- 共享账本管理

---

## 二、变更组件总览

| 组件 | 职责 |
|------|------|
| `MutationKind` | 变更类型枚举 |
| `MutationRecord` | 变更记录 |
| `InMemoryMutationLedger` | 内存变更账本 |

---

## 三、核心变更组件

### 3.1 MutationKind

```python
# src/mini_agent/workspace_runtime/mutation_ledger.py

class MutationKind(str, Enum):
    """Baseline recorded operation kinds."""
    READ = "read"       # 读取
    WRITE = "write"     # 写入
    EDIT = "edit"       # 编辑
    DELETE = "delete"   # 删除
    EXECUTE = "execute" # 执行
```

### 3.2 MutationRecord

```python
@dataclass(frozen=True, slots=True)
class MutationRecord:
    """One recorded mutation or side-effect attempt."""
    kind: MutationKind
    path: Path | None = None
    detail: str | None = None
    inside_workspace: bool = True
    approved: bool | None = None
    created_at: datetime = field(default_factory=_utc_now)

    def __post_init__(self) -> None:
        if self.path is not None:
            object.__setattr__(self, "path", Path(self.path).expanduser().resolve(strict=False))
```

### 3.3 InMemoryMutationLedger

```python
@dataclass(slots=True)
class InMemoryMutationLedger:
    """Append-only in-memory ledger used by Stage 1 seams."""
    _records: list[MutationRecord] = field(default_factory=list)

    def append(self, record: MutationRecord) -> MutationRecord:
        """Append record to ledger."""
        self._records.append(record)
        return record

    def record(
        self,
        kind: MutationKind,
        *,
        path: str | Path | None = None,
        detail: str | None = None,
        inside_workspace: bool = True,
        approved: bool | None = None,
    ) -> MutationRecord:
        """Record mutation."""
        return self.append(
            MutationRecord(
                kind=kind,
                path=Path(path) if path is not None else None,
                detail=detail,
                inside_workspace=inside_workspace,
                approved=approved,
            )
        )

    def snapshot(self) -> list[MutationRecord]:
        """Get snapshot of all records."""
        return list(self._records)

    def clear(self) -> None:
        """Clear all records."""
        self._records.clear()

    def __len__(self) -> int:
        """Get record count."""
        return len(self._records)
```

---

## 四、共享账本管理

```python
_SHARED_MUTATION_LEDGERS: dict[str, InMemoryMutationLedger] = {}

def shared_mutation_ledger(workspace_dir: str | Path) -> InMemoryMutationLedger:
    """Return the process-local shared mutation ledger for one workspace."""
    key = _workspace_state_key(workspace_dir)
    ledger = _SHARED_MUTATION_LEDGERS.get(key)
    if ledger is None:
        ledger = InMemoryMutationLedger()
        _SHARED_MUTATION_LEDGERS[key] = ledger
    return ledger

def clear_shared_mutation_ledgers() -> None:
    """Clear all process-local shared mutation ledgers."""
    _SHARED_MUTATION_LEDGERS.clear()
```

---

## 五、变更类型

```
┌─────────────────────────────────────────────────────────────────┐
│                    Mutation Kinds                                │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌───────────┐   ┌───────────┐   ┌───────────┐                  │
│  │   READ    │   │   WRITE   │   │   EDIT    │                  │
│  │           │   │           │   │           │                  │
│  │ 读取文件  │   │ 写入文件  │   │ 编辑文件  │                  │
│  └───────────┘   └───────────┘   └───────────┘                  │
│                                                                 │
│  ┌───────────┐   ┌───────────┐                                  │
│  │  DELETE   │   │  EXECUTE  │                                  │
│  │           │   │           │                                  │
│  │ 删除文件  │   │ 执行命令  │                                  │
│  └───────────┘   └───────────┘                                  │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## 六、变更记录示例

```python
# 记录读取操作
ledger.record(
    MutationKind.READ,
    path="/workspace/src/main.py",
    detail="read source file",
    inside_workspace=True,
)

# 记录写入操作（需要审批）
ledger.record(
    MutationKind.WRITE,
    path="/workspace/config.json",
    detail="update configuration",
    inside_workspace=True,
    approved=True,
)

# 记录外部路径访问
ledger.record(
    MutationKind.READ,
    path="/etc/passwd",
    detail="read system file",
    inside_workspace=False,
    approved=False,
)
```

---

## 七、文件位置

```
src/mini_agent/workspace_runtime/
├── mutation_ledger.py           # 本文档所述组件
```

---

## 八、验收标准

- [x] 支持变更类型
- [x] 支持变更记录
- [x] 支持内存账本
- [x] 支持共享账本

---

## 九、依赖关系

- 依赖: 无
- 被依赖: permission_table.py, workspace_executor.py, snapshot_store.py