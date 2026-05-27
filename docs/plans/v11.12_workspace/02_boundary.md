# 边界管理开发文档

**模块**: workspace_runtime/boundary
**优先级**: P0
**预估时间**: 已实现，文档补全

---

## 一、功能概述

边界管理负责：

- 工作空间根目录管理
- 路径解析与验证
- 边界检查
- 工作空间运行时适配

---

## 二、边界组件总览

| 组件 | 职责 |
|------|------|
| `WorkspaceBoundary` | 工作空间边界 |
| `MainAgentWorkspaceRuntimeAdapter` | 工作空间运行时适配器 |

---

## 三、核心边界组件

### 3.1 WorkspaceBoundary

```python
# src/mini_agent/workspace_runtime/boundary.py

@dataclass(frozen=True, slots=True)
class WorkspaceBoundary:
    """Normalized workspace root and containment checks."""
    root: Path

    def __post_init__(self) -> None:
        object.__setattr__(self, "root", _normalize_path(self.root))

    def resolve_path(self, value: str | Path) -> Path:
        """Resolve path relative to workspace root."""
        candidate = Path(value).expanduser()
        if not candidate.is_absolute():
            candidate = self.root / candidate
        return candidate.resolve(strict=False)

    def contains_path(self, value: str | Path) -> bool:
        """Check if path is within workspace boundary."""
        return _is_relative_to(self.resolve_path(value), self.root)

    def relative_path(self, value: str | Path) -> Path | None:
        """Get relative path from workspace root."""
        resolved = self.resolve_path(value)
        if not _is_relative_to(resolved, self.root):
            return None
        return resolved.relative_to(self.root)
```

### 3.2 MainAgentWorkspaceRuntimeAdapter

```python
@dataclass(slots=True)
class MainAgentWorkspaceRuntimeAdapter:
    """Expose workspace-oriented runtime facts above the session host runtime."""
    runtime_manager: Any
    config_loader: Callable[[], Any]
    repo_root: Path
    _selected_workspace_dir: Path | None = field(default=None, init=False, repr=False)

    # === 工作空间查询 ===

    async def list_workspaces(self) -> list[dict[str, Any]]:
        """List all workspaces."""
        workspaces = await self._collect_workspaces()
        return sorted(
            workspaces,
            key=lambda item: (
                not bool(item.get("active")),
                not bool(item.get("default")),
                str(item.get("workspace_dir", "")).lower(),
            ),
        )

    async def get_workspace(self, workspace_id: str) -> dict[str, Any]:
        """Get workspace by ID."""
        descriptor = await self._resolve_workspace_descriptor(workspace_id)
        if descriptor is None:
            raise LookupError(f"Workspace not found: {workspace_id}")
        return descriptor

    async def get_active_workspace(self) -> dict[str, Any]:
        """Get active workspace."""
        return await self._resolve_active_workspace_descriptor()

    # === 工作空间切换 ===

    async def switch_workspace(self, workspace_id: str) -> dict[str, Any]:
        """Switch to workspace."""
        target = await self._resolve_workspace_path(workspace_id)
        validator = getattr(self.runtime_manager, "validate_workspace", None)
        if callable(validator):
            validator(target)
        self._selected_workspace_dir = target
        return await self._descriptor_for_path(target)

    # === 运行时摘要 ===

    async def get_workspace_runtime_summary(
        self,
        workspace_id: str | None = None,
    ) -> dict[str, Any]:
        """Get workspace runtime summary."""
        ...
```

---

## 四、边界检查流程

```
┌─────────────────────────────────────────────────────────────────┐
│                    Boundary Check Flow                           │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  Input: path                                                    │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  1. Normalize path                                       │   │
│  │     - Expand user (~)                                    │   │
│  │     - Resolve to absolute path                           │   │
│  └─────────────────────────────────────────────────────────┘   │
│                              │                                   │
│                              ▼                                   │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  2. Check containment                                    │   │
│  │     - Is path relative to workspace root?                │   │
│  └─────────────────────────────────────────────────────────┘   │
│                              │                                   │
│              ┌───────────────┴───────────────┐                  │
│              │                               │                  │
│              ▼                               ▼                  │
│  ┌───────────────────┐              ┌───────────────────┐      │
│  │  Inside           │              │  Outside          │      │
│  │  - Allow/Check    │              │  - Check policy   │      │
│  │    permission     │              │  - May require    │      │
│  │                   │              │    approval       │      │
│  └───────────────────┘              └───────────────────┘      │
│                                                                 │
│  Output: WorkspacePathAccess                                    │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## 五、辅助函数

```python
def _normalize_path(value: str | Path) -> Path:
    """Normalize path for comparison."""
    return Path(value).expanduser().resolve(strict=False)

def _is_relative_to(candidate: Path, root: Path) -> bool:
    """Check if candidate is relative to root."""
    try:
        candidate.relative_to(root)
        return True
    except ValueError:
        return False
```

---

## 六、文件位置

```
src/mini_agent/workspace_runtime/
├── boundary.py                 # 本文档所述组件
```

---

## 七、验收标准

- [x] 支持路径解析
- [x] 支持边界检查
- [x] 支持工作空间列表
- [x] 支持工作空间切换

---

## 八、依赖关系

- 依赖: workspace/domain, runtime/support/workspace_path_utils
- 被依赖: workspace_executor.py