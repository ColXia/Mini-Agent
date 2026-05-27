# 会话血缘追踪开发文档

**模块**: session/lineage, agent_core/session/lineage
**优先级**: P1
**预估时间**: 已实现，文档补全

---

## 一、功能概述

会话血缘追踪负责：

- 会话派生关系追踪
- 血缘图管理
- 根会话识别
- 血缘链查询

---

## 二、血缘组件总览

| 组件 | 职责 |
|------|------|
| `SessionLineageNode` | 血缘节点 |
| `SessionLineageStore` | 血缘图存储 |
| `MainAgentSessionLineageState` | 会话血缘状态 |
| `RuntimeSessionLineageRegistry` | 运行时血缘注册表 |

---

## 三、核心血缘组件

### 3.1 SessionLineageNode

```python
# src/mini_agent/agent_core/session/lineage.py

@dataclass(frozen=True)
class SessionLineageNode:
    """One lineage node."""
    session_key: str
    parent_session_key: str | None = None
    reason: str = "root"
    created_utc: datetime = field(default_factory=_utc_now)
    metadata: dict[str, Any] = field(default_factory=dict)
```

### 3.2 SessionLineageStore

```python
class SessionLineageStore:
    """In-memory lineage graph."""

    def __init__(self) -> None:
        self._nodes: dict[str, SessionLineageNode] = {}
        self._children: dict[str, set[str]] = {}

    # === 节点操作 ===

    def add_root(
        self,
        session_key: str,
        *,
        metadata: dict[str, Any] | None = None,
    ) -> SessionLineageNode:
        """Add root session."""
        key = session_key.strip()
        if not key:
            raise ValueError("session_key must not be empty.")
        node = SessionLineageNode(
            session_key=key,
            parent_session_key=None,
            reason="root",
            metadata=dict(metadata or {}),
        )
        self._nodes[key] = node
        self._children.setdefault(key, set())
        return node

    def restore_node(self, node: SessionLineageNode) -> SessionLineageNode:
        """Restore or update one lineage node from persisted state."""
        ...

    def add_child(
        self,
        *,
        parent_session_key: str,
        child_session_key: str,
        reason: str,
        metadata: dict[str, Any] | None = None,
    ) -> SessionLineageNode:
        """Add child session."""
        ...

    # === 查询操作 ===

    def get(self, session_key: str) -> SessionLineageNode | None:
        """Get node by key."""
        return self._nodes.get(session_key)

    def parent_of(self, session_key: str) -> SessionLineageNode | None:
        """Get parent of session."""
        node = self._nodes.get(session_key)
        if node is None or node.parent_session_key is None:
            return None
        return self._nodes.get(node.parent_session_key)

    def children_of(self, session_key: str) -> list[SessionLineageNode]:
        """Get children of session."""
        child_keys = sorted(self._children.get(session_key, set()))
        return [self._nodes[item] for item in child_keys if item in self._nodes]

    def chain_to_root(self, session_key: str) -> list[SessionLineageNode]:
        """Get chain from session to root."""
        if session_key not in self._nodes:
            return []
        chain: list[SessionLineageNode] = []
        current = self._nodes[session_key]
        seen: set[str] = set()
        while True:
            if current.session_key in seen:
                raise ValueError(f"lineage cycle detected at {current.session_key}")
            seen.add(current.session_key)
            chain.append(current)
            if current.parent_session_key is None:
                break
            parent = self._nodes.get(current.parent_session_key)
            if parent is None:
                break
            current = parent
        return chain

    def all_nodes(self) -> list[SessionLineageNode]:
        """Get all nodes."""
        return [self._nodes[key] for key in sorted(self._nodes)]

    def remove(self, session_key: str) -> bool:
        """Remove session from lineage."""
        ...
```

### 3.3 MainAgentSessionLineageState

```python
# src/mini_agent/session/lineage.py

@dataclass(slots=True)
class MainAgentSessionLineageState:
    """Lineage state for main agent session."""
    parent_session_id: str | None = None
    root_session_id: str | None = None
    reason: str = "root"
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = field(default_factory=dict)
```

### 3.4 RuntimeSessionLineageRegistry

```python
@dataclass(slots=True)
class RuntimeSessionLineageRegistry:
    """Registry for runtime session lineage."""
    store: SessionLineageStore

    def replace_store(self, store: SessionLineageStore) -> None:
        """Replace lineage store."""
        self.store = store

    def register_session(self, session: "MainAgentSessionState") -> None:
        """Register session in lineage."""
        lineage = session.lineage_state
        parent_session_id = _safe_text(lineage.parent_session_id) or None
        root_session_id = _safe_text(lineage.root_session_id) or None
        reason = _safe_text(lineage.reason) or ("child" if parent_session_id else "root")
        created_at = (lineage.created_at or session.created_at).astimezone(timezone.utc)
        metadata = dict(lineage.metadata) if isinstance(lineage.metadata, dict) else {}

        if parent_session_id is not None:
            parent_node = self.store.get(parent_session_id)
            resolved_root_session_id = (
                root_session_id
                or self._lineage_root_from_node(parent_node)
                or parent_session_id
            )
            lineage.parent_session_id = parent_session_id
            lineage.root_session_id = resolved_root_session_id
            lineage.reason = reason
            lineage.created_at = created_at
            lineage.metadata = metadata
            metadata["root_session_id"] = resolved_root_session_id
            self.store.restore_node(
                SessionLineageNode(
                    session_key=session.session_id,
                    parent_session_key=parent_session_id,
                    reason=reason,
                    created_utc=created_at,
                    metadata=metadata,
                )
            )
            return

        resolved_root_session_id = root_session_id or session.session_id
        lineage.parent_session_id = None
        lineage.root_session_id = resolved_root_session_id
        lineage.reason = "root"
        lineage.created_at = created_at
        lineage.metadata = metadata
        metadata["root_session_id"] = resolved_root_session_id
        self.store.restore_node(
            SessionLineageNode(
                session_key=session.session_id,
                parent_session_key=None,
                reason="root",
                created_utc=created_at,
                metadata=metadata,
            )
        )

    def remove_session(self, session_id: str) -> None:
        """Remove session from lineage."""
        self.store.remove(session_id)

    @staticmethod
    def _lineage_root_from_node(node: SessionLineageNode | None) -> str | None:
        """Get root session ID from node."""
        if node is None:
            return None
        root_session_id = _safe_text(node.metadata.get("root_session_id"))
        if root_session_id:
            return root_session_id
        if node.parent_session_key is None:
            return node.session_key
        return None
```

---

## 四、血缘关系图

```
┌─────────────────────────────────────────────────────────────────┐
│                    Session Lineage Graph                         │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌───────────┐                                                  │
│  │  Root     │                                                  │
│  │ Session A │                                                  │
│  └─────┬─────┘                                                  │
│        │                                                        │
│        ├──────────────────────┬──────────────────────┐          │
│        │                      │                      │          │
│        ▼                      ▼                      ▼          │
│  ┌───────────┐          ┌───────────┐          ┌───────────┐   │
│  │  Child B  │          │  Child C  │          │  Child D  │   │
│  │ (reset)   │          │ (fork)    │          │ (delegate)│   │
│  └─────┬─────┘          └───────────┘          └───────────┘   │
│        │                                                        │
│        ▼                                                        │
│  ┌───────────┐                                                  │
│  │  Child E  │                                                  │
│  │ (fork)    │                                                  │
│  └───────────┘                                                  │
│                                                                 │
│  chain_to_root(E) = [E, B, A]                                   │
│  children_of(A) = [B, C, D]                                     │
│  parent_of(E) = B                                               │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## 五、血缘原因类型

| 原因 | 描述 |
|------|------|
| `root` | 根会话 |
| `reset` | 重置派生 |
| `fork` | 分叉派生 |
| `delegate` | 委托派生 |
| `compress` | 压缩派生 |
| `child` | 通用子会话 |

---

## 六、文件位置

```
src/mini_agent/agent_core/session/
├── lineage.py                   # SessionLineageNode, SessionLineageStore

src/mini_agent/session/
├── lineage.py                   # MainAgentSessionLineageState, RuntimeSessionLineageRegistry
```

---

## 七、验收标准

- [x] 支持血缘节点存储
- [x] 支持父子关系查询
- [x] 支持根链追踪
- [x] 支持循环检测
- [x] 支持会话注册

---

## 八、依赖关系

- 依赖: store_records
- 被依赖: runtime/, persistence.py