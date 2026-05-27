# 会话管理开发文档

**模块**: agent_core/session
**优先级**: P2
**预估时间**: 已实现，文档补全

---

## 一、功能概述

会话管理负责：

- SessionLifecycle - 生命周期管理
- SessionLineage - 血缘追踪
- 会话重置策略

---

## 二、核心数据结构

### 2.1 SessionResetMode

```python
class SessionResetMode(str, Enum):
    """Reset policy modes."""

    NONE = "none"     # 不重置
    DAILY = "daily"   # 每日重置
    IDLE = "idle"     # 空闲重置
    BOTH = "both"     # 每日或空闲都重置
```

### 2.2 SessionLifecyclePolicy

```python
@dataclass(frozen=True)
class SessionLifecyclePolicy:
    """Lifecycle reset policy."""

    mode: SessionResetMode = SessionResetMode.NONE
    idle_seconds: int = 1800  # 30 分钟

    def normalized(self) -> "SessionLifecyclePolicy":
        """Normalize policy values."""
```

### 2.3 SessionLifecycleState

```python
@dataclass(frozen=True)
class SessionLifecycleState:
    """Mutable session lifecycle state stored per session."""

    session_key: AgentSessionKey
    created_utc: datetime
    last_activity_utc: datetime
    revision: int = 0
```

### 2.4 SessionLifecycleResult

```python
@dataclass(frozen=True)
class SessionLifecycleResult:
    """Lifecycle decision result."""

    state: SessionLifecycleState
    reset: bool
    reason: str | None = None
```

### 2.5 SessionLineageNode

```python
@dataclass(frozen=True)
class SessionLineageNode:
    """One lineage node."""

    session_key: str
    parent_session_key: str | None = None
    reason: str = "root"
    created_utc: datetime = field(default_factory=_utc_now)
    metadata: dict[str, Any] = field(default_factory=dict)
```

---

## 三、SessionLifecycleManager

### 3.1 职责

生命周期管理器决定会话是否需要重置：

- 检查每日重置条件
- 检查空闲超时条件
- 返回重置决策

### 3.2 实现

```python
class SessionLifecycleManager:
    """Apply lifecycle reset policy for one session."""

    def __init__(self, policy: SessionLifecyclePolicy):
        self.policy = policy.normalized()

    def should_reset(
        self,
        state: SessionLifecycleState,
        *,
        now_utc: datetime | None = None,
    ) -> tuple[bool, str | None]:
        """Check if session should be reset."""
        now = (now_utc or _utc_now()).astimezone(timezone.utc)
        mode = self.policy.mode

        if mode == SessionResetMode.NONE:
            return False, None

        day_changed = now.date() != state.created_utc.astimezone(timezone.utc).date()
        idle_elapsed = (
            now - state.last_activity_utc.astimezone(timezone.utc)
        ).total_seconds() >= self.policy.idle_seconds

        if mode == SessionResetMode.DAILY:
            return (day_changed, "daily" if day_changed else None)

        if mode == SessionResetMode.IDLE:
            return (idle_elapsed, "idle" if idle_elapsed else None)

        if mode == SessionResetMode.BOTH:
            if day_changed:
                return True, "daily"
            if idle_elapsed:
                return True, "idle"

        return False, None

    def touch(self, state: SessionLifecycleState) -> SessionLifecycleState:
        """Update last activity timestamp."""
        return SessionLifecycleState(
            session_key=state.session_key,
            created_utc=state.created_utc,
            last_activity_utc=_utc_now(),
            revision=state.revision + 1,
        )

    def reset(self, state: SessionLifecycleState) -> SessionLifecycleState:
        """Reset session state."""
        return SessionLifecycleState(
            session_key=state.session_key,
            created_utc=_utc_now(),
            last_activity_utc=_utc_now(),
            revision=state.revision + 1,
        )
```

---

## 四、SessionLineageStore

### 4.1 职责

血缘存储追踪会话的父子关系：

- 记录会话创建原因
- 追踪会话派生关系
- 检测循环依赖

### 4.2 实现

```python
class SessionLineageStore:
    """In-memory lineage graph."""

    def __init__(self) -> None:
        self._nodes: dict[str, SessionLineageNode] = {}
        self._children: dict[str, set[str]] = {}

    def add_root(
        self,
        session_key: str,
        *,
        metadata: dict[str, Any] | None = None,
    ) -> SessionLineageNode:
        """Add a root session node."""
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

    def add_child(
        self,
        parent: str,
        child: str,
        *,
        reason: str = "child",
        metadata: dict[str, Any] | None = None,
    ) -> SessionLineageNode:
        """Add a child session node."""
        parent_key = parent.strip()
        child_key = child.strip()

        if not parent_key or not child_key:
            raise ValueError("parent and child keys must not be empty.")
        if parent_key == child_key:
            raise ValueError("parent and child keys must differ.")
        if self._creates_cycle(parent_key, child_key):
            raise ValueError(f"lineage cycle detected.")

        if parent_key not in self._nodes:
            self.add_root(parent_key)

        node = SessionLineageNode(
            session_key=child_key,
            parent_session_key=parent_key,
            reason=reason.strip() or "child",
            metadata=dict(metadata or {}),
        )
        self._nodes[child_key] = node
        self._children.setdefault(parent_key, set()).add(child_key)
        self._children.setdefault(child_key, set())
        return node

    def chain_to_root(self, session_key: str) -> list[SessionLineageNode]:
        """Get the chain from root to this session."""
        chain = []
        current = session_key.strip()
        visited = set()

        while current and current not in visited:
            visited.add(current)
            node = self._nodes.get(current)
            if node is None:
                break
            chain.append(node)
            current = node.parent_session_key

        return list(reversed(chain))
```

---

## 五、会话血缘图

```
┌─────────────────────────────────────────────────────────────────┐
│                    Session Lineage Graph                         │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌─────────────┐                                                │
│  │ Root Session│                                                │
│  │   (root)    │                                                │
│  └──────┬──────┘                                                │
│         │                                                       │
│         ├── reset ──────────────────┐                           │
│         │                           ▼                           │
│         │                    ┌─────────────┐                    │
│         │                    │ Reset Child │                    │
│         │                    │  (reset)    │                    │
│         │                    └─────────────┘                    │
│         │                                                       │
│         ├── delegation ─────────────┐                           │
│         │                           ▼                           │
│         │                    ┌─────────────┐                    │
│         │                    │ Delegated   │                    │
│         │                    │  (delegation)│                   │
│         │                    └──────┬──────┘                    │
│         │                           │                           │
│         │                           └── compression ───┐        │
│         │                                               ▼        │
│         │                                        ┌──────────┐   │
│         │                                        │Compressed│   │
│         │                                        │(compress)│   │
│         │                                        └──────────┘   │
│         │                                                       │
│         └── fork ─────────────────────┐                         │
│                                       ▼                         │
│                                ┌─────────────┐                  │
│                                │ Forked      │                  │
│                                │  (fork)     │                  │
│                                └─────────────┘                  │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## 六、重置策略

| 模式 | 说明 | 触发条件 |
|------|------|---------|
| NONE | 不重置 | 无 |
| DAILY | 每日重置 | 日期变更 |
| IDLE | 空闲重置 | 空闲超过阈值 |
| BOTH | 组合重置 | 日期变更或空闲超时 |

---

## 七、文件位置

```
src/mini_agent/agent_core/session/
├── __init__.py
├── session_key.py           # AgentSessionKey
├── lifecycle.py             # SessionLifecycleManager
└── lineage.py               # SessionLineageStore
```

---

## 八、验收标准

- [x] SessionLifecycleManager 支持多种重置模式
- [x] SessionLineageStore 支持血缘追踪
- [x] 支持循环检测
- [x] 支持链式查询

---

## 九、依赖关系

- 无前置依赖
- 被依赖: engine.py, context/
