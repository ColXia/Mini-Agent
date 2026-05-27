# 权限表开发文档

**模块**: workspace_runtime/permission_table
**优先级**: P1
**预估时间**: 已实现，文档补全

---

## 一、功能概述

权限表负责：

- 工作空间内部权限规则
- 路径/操作权限决策
- 规则匹配与评估

---

## 二、权限组件总览

| 组件 | 职责 |
|------|------|
| `WorkspacePermissionEffect` | 权限效果枚举 |
| `WorkspacePermissionRule` | 权限规则 |
| `WorkspacePermissionDecision` | 权限决策 |
| `WorkspacePermissionTable` | 权限表 |

---

## 三、核心权限组件

### 3.1 WorkspacePermissionEffect

```python
# src/mini_agent/workspace_runtime/permission_table.py

class WorkspacePermissionEffect(str, Enum):
    """Decision effect for one workspace permission rule."""
    ALLOW = "allow"
    DENY = "deny"
```

### 3.2 WorkspacePermissionRule

```python
@dataclass(frozen=True, slots=True)
class WorkspacePermissionRule:
    """One workspace-internal path/operation permission rule."""
    effect: WorkspacePermissionEffect
    kinds: tuple[MutationKind, ...] = ()           # 操作类型
    relative_path: Path | None = None              # 相对路径
    reason: str | None = None                      # 原因

    def __post_init__(self) -> None:
        object.__setattr__(self, "relative_path", _normalize_relative_path(self.relative_path))
        normalized_kinds = tuple(kind for kind in self.kinds if isinstance(kind, MutationKind))
        object.__setattr__(self, "kinds", normalized_kinds)

    def matches(self, *, kind: MutationKind, relative_path: Path | None) -> bool:
        """Check if rule matches operation."""
        if self.kinds and kind not in self.kinds:
            return False
        if self.relative_path is None:
            return True
        if relative_path is None:
            return False
        try:
            relative_path.relative_to(self.relative_path)
            return True
        except ValueError:
            return False
```

### 3.3 WorkspacePermissionDecision

```python
@dataclass(frozen=True, slots=True)
class WorkspacePermissionDecision:
    """Evaluated result for one workspace-internal access request."""
    allowed: bool
    reason: str | None = None
    matched_rule: WorkspacePermissionRule | None = None
```

### 3.4 WorkspacePermissionTable

```python
@dataclass(slots=True)
class WorkspacePermissionTable:
    """Workspace-internal permission owner for executor-level checks."""
    rules: tuple[WorkspacePermissionRule, ...] = field(default_factory=tuple)
    default_allow: bool = True

    def decide(
        self,
        *,
        kind: MutationKind,
        relative_path: str | Path | None,
    ) -> WorkspacePermissionDecision:
        """Decide permission for operation."""
        normalized_relative_path = _normalize_relative_path(relative_path)
        for rule in self.rules:
            if not rule.matches(kind=kind, relative_path=normalized_relative_path):
                continue
            return WorkspacePermissionDecision(
                allowed=rule.effect is WorkspacePermissionEffect.ALLOW,
                reason=rule.reason,
                matched_rule=rule,
            )
        return WorkspacePermissionDecision(
            allowed=bool(self.default_allow),
            reason=None if self.default_allow else "workspace permission table denied the operation",
            matched_rule=None,
        )
```

---

## 四、权限规则示例

```python
# 允许所有操作
rule_allow_all = WorkspacePermissionRule(
    effect=WorkspacePermissionEffect.ALLOW,
)

# 拒绝删除操作
rule_deny_delete = WorkspacePermissionRule(
    effect=WorkspacePermissionEffect.DENY,
    kinds=(MutationKind.DELETE,),
    reason="Delete operations are not allowed",
)

# 拒绝访问敏感目录
rule_deny_sensitive = WorkspacePermissionRule(
    effect=WorkspacePermissionEffect.DENY,
    relative_path=Path(".secrets"),
    reason="Sensitive directory is protected",
)

# 只允许读取特定目录
rule_allow_read_docs = WorkspacePermissionRule(
    effect=WorkspacePermissionEffect.ALLOW,
    kinds=(MutationKind.READ,),
    relative_path=Path("docs"),
)
```

---

## 五、权限决策流程

```
┌─────────────────────────────────────────────────────────────────┐
│                    Permission Decision Flow                      │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  Input: kind, relative_path                                     │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  1. Normalize relative_path                              │   │
│  │     - Ensure path is workspace-relative                  │   │
│  │     - Reject absolute paths                              │   │
│  └─────────────────────────────────────────────────────────┘   │
│                              │                                   │
│                              ▼                                   │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  2. Iterate rules                                         │   │
│  │     - Check kind match                                    │   │
│  │     - Check path match                                    │   │
│  └─────────────────────────────────────────────────────────┘   │
│                              │                                   │
│              ┌───────────────┴───────────────┐                  │
│              │                               │                  │
│              ▼                               ▼                  │
│  ┌───────────────────┐              ┌───────────────────┐      │
│  │  Rule Matched     │              │  No Match         │      │
│  │  - Return rule    │              │  - Return default │      │
│  │    decision       │              │    decision       │      │
│  └───────────────────┘              └───────────────────┘      │
│                                                                 │
│  Output: WorkspacePermissionDecision                            │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## 六、辅助函数

```python
def _normalize_relative_path(value: str | Path | None) -> Path | None:
    """Normalize relative path for permission rules."""
    if value is None:
        return None
    normalized = Path(str(value).replace("\\", "/")).expanduser()
    if normalized.is_absolute():
        raise ValueError("permission rule paths must be workspace-relative")
    parts = [part for part in normalized.parts if part not in ("", ".")]
    if any(part == ".." for part in parts):
        raise ValueError("permission rule paths cannot escape the workspace root")
    if not parts:
        return None
    return Path(*parts)
```

---

## 七、文件位置

```
src/mini_agent/workspace_runtime/
├── permission_table.py          # 本文档所述组件
```

---

## 八、验收标准

- [x] 支持权限效果
- [x] 支持权限规则
- [x] 支持权限决策
- [x] 支持规则匹配

---

## 九、依赖关系

- 依赖: mutation_ledger (MutationKind)
- 被依赖: workspace_executor.py