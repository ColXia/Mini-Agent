# 工作空间域模型开发文档

**模块**: workspace/domain
**优先级**: P0
**预估时间**: 已实现，文档补全

---

## 一、功能概述

工作空间域模型定义了工作空间的核心概念：

- 工作空间类型
- 工作空间清单
- 工作空间记录

---

## 二、域模型总览

| 模型 | 职责 |
|------|------|
| `WorkspaceKind` | 工作空间类型枚举 |
| `WorkspaceManifest` | 工作空间清单 |
| `WorkspaceRecord` | 工作空间运行时记录 |

---

## 三、核心域模型

### 3.1 WorkspaceKind

```python
# src/mini_agent/workspace/domain.py

class WorkspaceKind(str, Enum):
    """Workspace type classification."""
    DEFAULT = "default"    # 默认工作空间
    PROJECT = "project"    # 项目工作空间
```

### 3.2 WorkspaceManifest

```python
@dataclass(frozen=True, slots=True)
class WorkspaceManifest:
    """Stable identity and manifest metadata for one workspace world."""
    workspace_id: str
    title: str
    root_dir: Path
    kind: WorkspaceKind
    runtime_policy: dict[str, Any] = field(default_factory=dict)
    permission_policy: dict[str, Any] = field(default_factory=dict)
    rag_config: dict[str, Any] = field(default_factory=dict)
    created_at: str | None = None
    updated_at: str | None = None

    @classmethod
    def default_workspace(
        cls,
        root_dir: str | Path,
        *,
        title: str | None = None,
        created_at: str | None = None,
        updated_at: str | None = None,
    ) -> "WorkspaceManifest":
        """Create default workspace manifest."""
        return cls.from_root_dir(
            root_dir,
            kind=WorkspaceKind.DEFAULT,
            title=title,
            created_at=created_at,
            updated_at=updated_at,
        )

    @classmethod
    def project_workspace(
        cls,
        root_dir: str | Path,
        *,
        title: str | None = None,
        created_at: str | None = None,
        updated_at: str | None = None,
    ) -> "WorkspaceManifest":
        """Create project workspace manifest."""
        return cls.from_root_dir(
            root_dir,
            kind=WorkspaceKind.PROJECT,
            title=title,
            created_at=created_at,
            updated_at=updated_at,
        )

    @classmethod
    def from_root_dir(
        cls,
        root_dir: str | Path,
        *,
        kind: WorkspaceKind,
        title: str | None = None,
        created_at: str | None = None,
        updated_at: str | None = None,
        runtime_policy: Mapping[str, Any] | None = None,
        permission_policy: Mapping[str, Any] | None = None,
        rag_config: Mapping[str, Any] | None = None,
    ) -> "WorkspaceManifest":
        """Create manifest from root directory."""
        resolved_root = Path(root_dir).expanduser().resolve()
        return cls(
            workspace_id=_workspace_path_key(resolved_root),
            title=(title or resolved_root.name or str(resolved_root)).strip() or str(resolved_root),
            root_dir=resolved_root,
            kind=kind,
            runtime_policy=dict(runtime_policy or {}),
            permission_policy=dict(permission_policy or {}),
            rag_config=dict(rag_config or {}),
            created_at=created_at,
            updated_at=updated_at,
        )

    def to_summary_dict(self) -> dict[str, Any]:
        """Convert to summary dict."""
        return {
            "workspace_id": self.workspace_id,
            "workspace_dir": str(self.root_dir),
            "title": self.title,
            "kind": self.kind.value,
        }
```

### 3.3 WorkspaceRecord

```python
@dataclass(frozen=True, slots=True)
class WorkspaceRecord:
    """Runtime-facing workspace summary derived from one manifest plus live state."""
    manifest: WorkspaceManifest
    default: bool = False
    active: bool = False
    switched: bool = False
    session_count: int = 0
    default_session_count: int = 0
    shared_session_count: int = 0
    busy_session_count: int = 0
    last_updated_at: str | None = None

    @classmethod
    def from_manifest(
        cls,
        manifest: WorkspaceManifest,
        *,
        default: bool = False,
        active: bool = False,
        switched: bool = False,
    ) -> "WorkspaceRecord":
        """Create record from manifest."""
        return cls(
            manifest=manifest,
            default=default,
            active=active,
            switched=switched,
        )

    def mark_active(self, *, switched: bool = False) -> "WorkspaceRecord":
        """Mark as active."""
        return replace(
            self,
            active=True,
            switched=self.switched or switched,
        )

    def observe_session(
        self,
        *,
        shared: bool = False,
        busy: bool = False,
        is_default: bool = False,
        updated_at: str | None = None,
    ) -> "WorkspaceRecord":
        """Observe session activity."""
        return replace(
            self,
            session_count=self.session_count + (0 if is_default else 1),
            default_session_count=self.default_session_count + (1 if is_default else 0),
            shared_session_count=self.shared_session_count + (1 if shared else 0),
            busy_session_count=self.busy_session_count + (1 if busy else 0),
            last_updated_at=_latest_timestamp(self.last_updated_at, updated_at),
        )

    def to_summary_dict(self) -> dict[str, Any]:
        """Convert to summary dict."""
        payload = self.manifest.to_summary_dict()
        payload.update({
            "default": self.default,
            "session_count": self.session_count,
            "default_session_count": self.default_session_count,
            "shared_session_count": self.shared_session_count,
            "busy_session_count": self.busy_session_count,
            "last_updated_at": self.last_updated_at,
            "active": self.active,
            "switched": self.switched,
        })
        return payload

    def to_runtime_summary_dict(
        self,
        *,
        runtime_policy: Mapping[str, Any] | None = None,
        runtime: Mapping[str, Any] | None = None,
        runtime_error: str | None = None,
    ) -> dict[str, Any]:
        """Convert to runtime summary dict."""
        payload = self.to_summary_dict()
        payload["runtime_policy"] = dict(runtime_policy or {})
        payload["runtime"] = dict(runtime) if runtime is not None else None
        payload["runtime_error"] = runtime_error
        return payload
```

---

## 四、工作空间类型

```
┌─────────────────────────────────────────────────────────────────┐
│                    Workspace Types                               │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  DEFAULT                                                 │   │
│  │  - 主工作空间                                            │   │
│  │  - 通常与仓库根目录关联                                  │   │
│  │  - 自动创建                                              │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  PROJECT                                                 │   │
│  │  - 项目工作空间                                          │   │
│  │  - 可以有多个                                            │   │
│  │  - 显式创建或切换                                        │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## 五、辅助函数

```python
def _workspace_path_key(path: Path) -> str:
    """Generate workspace key from path."""
    resolved = Path(path).expanduser().resolve()
    normalized = str(resolved)
    return normalized.lower() if os.name == "nt" else normalized

def _latest_timestamp(left: str | None, right: str | None) -> str | None:
    """Get latest timestamp."""
    if not right:
        return left
    if not left or right > left:
        return right
    return left
```

---

## 六、文件位置

```
src/mini_agent/workspace/
├── domain.py                   # 本文档所述组件
```

---

## 七、验收标准

- [x] 支持工作空间类型
- [x] 支持工作空间清单
- [x] 支持工作空间记录
- [x] 支持会话观察

---

## 八、依赖关系

- 依赖: 无
- 被依赖: workspace_runtime/, session/