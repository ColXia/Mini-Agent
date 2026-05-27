# 外部区域策略开发文档

**模块**: workspace_runtime/outside_zone_policy
**优先级**: P1
**预估时间**: 已实现，文档补全

---

## 一、功能概述

外部区域策略负责：

- 工作空间外部路径访问控制
- 保护系统关键路径
- 外部操作审批决策

---

## 二、外部区域组件总览

| 组件 | 职责 |
|------|------|
| `OutsideZoneOperation` | 外部操作类型 |
| `OutsideZoneDecision` | 外部区域决策 |
| `DefaultOutsideZonePolicy` | 默认外部区域策略 |

---

## 三、核心外部区域组件

### 3.1 OutsideZoneOperation

```python
# src/mini_agent/workspace_runtime/outside_zone_policy.py

class OutsideZoneOperation(str, Enum):
    """Baseline operations evaluated outside the workspace root."""
    READ = "read"       # 读取
    WRITE = "write"     # 写入
    DELETE = "delete"   # 删除
```

### 3.2 OutsideZoneDecision

```python
@dataclass(frozen=True, slots=True)
class OutsideZoneDecision:
    """Result of evaluating one outside-workspace operation."""
    allowed: bool               # 是否允许
    requires_approval: bool     # 是否需要审批
    reason: str                 # 原因
    protected: bool = False     # 是否受保护

    @property
    def denied(self) -> bool:
        """Check if operation is denied."""
        return not self.allowed and not self.requires_approval
```

### 3.3 DefaultOutsideZonePolicy

```python
@dataclass(frozen=True, slots=True)
class DefaultOutsideZonePolicy:
    """Outside-zone default policy aligned with the v11.1 baseline."""
    protected_roots: tuple[Path, ...] = field(default_factory=_default_protected_roots)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "protected_roots",
            tuple(_normalize_path(root) for root in self.protected_roots),
        )

    def is_protected(self, value: str | Path) -> bool:
        """Check if path is in protected roots."""
        candidate = _normalize_path(value)
        return any(_is_relative_to(candidate, root) for root in self.protected_roots)

    def decide(self, operation: OutsideZoneOperation, path: str | Path) -> OutsideZoneDecision:
        """Decide outside-zone operation."""
        candidate = _normalize_path(path)
        protected = self.is_protected(candidate)

        # 受保护路径
        if protected:
            if operation is OutsideZoneOperation.READ:
                return OutsideZoneDecision(
                    allowed=True,
                    requires_approval=False,
                    reason="protected outside path is read-only",
                    protected=True,
                )
            return OutsideZoneDecision(
                allowed=False,
                requires_approval=False,
                reason="protected outside path cannot be modified",
                protected=True,
            )

        # 非保护路径
        if operation is OutsideZoneOperation.READ:
            return OutsideZoneDecision(
                allowed=True,
                requires_approval=False,
                reason="outside-workspace read is allowed",
            )

        if operation is OutsideZoneOperation.WRITE:
            return OutsideZoneDecision(
                allowed=False,
                requires_approval=True,
                reason="outside-workspace write requires approval",
            )

        return OutsideZoneDecision(
            allowed=False,
            requires_approval=False,
            reason="outside-workspace delete is denied",
        )
```

---

## 四、保护路径

```python
def _default_protected_roots() -> tuple[Path, ...]:
    """Get default protected roots based on OS."""
    if os.name == "nt":
        values = (
            os.environ.get("SystemRoot"),
            os.environ.get("ProgramFiles"),
            os.environ.get("ProgramFiles(x86)"),
            os.environ.get("ProgramData"),
        )
    else:
        values = ("/bin", "/etc", "/sbin", "/usr", "/var")
    roots = []
    for value in values:
        if value:
            roots.append(_normalize_path(value))
    return tuple(dict.fromkeys(roots))
```

---

## 五、决策矩阵

```
┌─────────────────────────────────────────────────────────────────┐
│                    Outside Zone Decision Matrix                  │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  Path Type    │ READ           │ WRITE          │ DELETE        │
│  ─────────────┼────────────────┼────────────────┼───────────────│
│  Protected    │ Allow          │ Deny           │ Deny          │
│               │ (read-only)    │                │               │
│  ─────────────┼────────────────┼────────────────┼───────────────│
│  Non-protected│ Allow          │ Require        │ Deny          │
│               │                │ Approval       │               │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## 六、决策流程

```
┌─────────────────────────────────────────────────────────────────┐
│                    Outside Zone Decision Flow                    │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  Input: operation, path                                         │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  1. Normalize path                                       │   │
│  └─────────────────────────────────────────────────────────┘   │
│                              │                                   │
│                              ▼                                   │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  2. Check if protected                                   │   │
│  │     - Compare against protected_roots                    │   │
│  └─────────────────────────────────────────────────────────┘   │
│                              │                                   │
│              ┌───────────────┴───────────────┐                  │
│              │                               │                  │
│              ▼                               ▼                  │
│  ┌───────────────────┐              ┌───────────────────┐      │
│  │  Protected        │              │  Non-protected    │      │
│  │  - READ: Allow    │              │  - READ: Allow    │      │
│  │  - WRITE: Deny    │              │  - WRITE: Approve │      │
│  │  - DELETE: Deny   │              │  - DELETE: Deny   │      │
│  └───────────────────┘              └───────────────────┘      │
│                                                                 │
│  Output: OutsideZoneDecision                                    │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## 七、文件位置

```
src/mini_agent/workspace_runtime/
├── outside_zone_policy.py       # 本文档所述组件
```

---

## 八、验收标准

- [x] 支持外部操作类型
- [x] 支持外部区域决策
- [x] 支持保护路径
- [x] 支持审批决策

---

## 九、依赖关系

- 依赖: 无
- 被依赖: workspace_executor.py