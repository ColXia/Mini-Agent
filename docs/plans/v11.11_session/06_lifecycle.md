# 生命周期管理开发文档

**模块**: agent_core/session/lifecycle
**优先级**: P1
**预估时间**: 已实现，文档补全

---

## 一、功能概述

生命周期管理负责：

- 会话重置策略
- 活动时间追踪
- 生命周期决策
- 会话键管理

---

## 二、生命周期组件总览

| 组件 | 职责 |
|------|------|
| `SessionResetMode` | 重置模式枚举 |
| `SessionLifecyclePolicy` | 生命周期策略 |
| `SessionLifecycleState` | 生命周期状态 |
| `SessionLifecycleResult` | 生命周期结果 |
| `SessionLifecycleManager` | 生命周期管理器 |
| `AgentSessionKey` | 会话键模型 |
| `SessionKeyIndex` | 会话键索引 |

---

## 三、核心生命周期组件

### 3.1 SessionResetMode

```python
# src/mini_agent/agent_core/session/lifecycle.py

class SessionResetMode(str, Enum):
    """Reset policy modes."""
    NONE = "none"      # 不重置
    DAILY = "daily"    # 每日重置
    IDLE = "idle"      # 空闲重置
    BOTH = "both"      # 每日+空闲重置
```

### 3.2 SessionLifecyclePolicy

```python
@dataclass(frozen=True)
class SessionLifecyclePolicy:
    """Lifecycle reset policy."""
    mode: SessionResetMode = SessionResetMode.NONE
    idle_seconds: int = 1800  # 30分钟

    def normalized(self) -> "SessionLifecyclePolicy":
        """Normalize policy."""
        idle = max(1, int(self.idle_seconds))
        return SessionLifecyclePolicy(mode=self.mode, idle_seconds=idle)
```

### 3.3 SessionLifecycleState

```python
@dataclass(frozen=True)
class SessionLifecycleState:
    """Mutable session lifecycle state stored per session."""
    session_key: AgentSessionKey
    created_utc: datetime
    last_activity_utc: datetime
    revision: int = 0
```

### 3.4 SessionLifecycleResult

```python
@dataclass(frozen=True)
class SessionLifecycleResult:
    """Lifecycle decision result."""
    state: SessionLifecycleState
    reset: bool
    reason: str | None = None
```

### 3.5 SessionLifecycleManager

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
        """Check if session should reset."""
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

    def touch(
        self,
        state: SessionLifecycleState,
        *,
        now_utc: datetime | None = None,
    ) -> SessionLifecycleState:
        """Update activity timestamp."""
        now = (now_utc or _utc_now()).astimezone(timezone.utc)
        return SessionLifecycleState(
            session_key=state.session_key,
            created_utc=state.created_utc,
            last_activity_utc=now,
            revision=state.revision,
        )

    def reset(
        self,
        state: SessionLifecycleState,
        *,
        now_utc: datetime | None = None,
    ) -> SessionLifecycleState:
        """Reset session."""
        now = (now_utc or _utc_now()).astimezone(timezone.utc)
        return SessionLifecycleState(
            session_key=state.session_key,
            created_utc=now,
            last_activity_utc=now,
            revision=state.revision + 1,
        )

    def ensure_active(
        self,
        state: SessionLifecycleState,
        *,
        now_utc: datetime | None = None,
    ) -> SessionLifecycleResult:
        """Ensure session is active, reset if needed."""
        should_reset, reason = self.should_reset(state, now_utc=now_utc)
        if should_reset:
            return SessionLifecycleResult(
                state=self.reset(state, now_utc=now_utc),
                reset=True,
                reason=reason,
            )
        return SessionLifecycleResult(state=state, reset=False, reason=None)

    @staticmethod
    def bootstrap(
        session_key: AgentSessionKey,
        *,
        now_utc: datetime | None = None,
    ) -> SessionLifecycleState:
        """Bootstrap new session state."""
        now = (now_utc or _utc_now()).astimezone(timezone.utc)
        return SessionLifecycleState(
            session_key=session_key,
            created_utc=now,
            last_activity_utc=now,
            revision=0,
        )
```

---

## 四、会话键模型

### 4.1 AgentSessionKey

```python
# src/mini_agent/agent_core/session/session_key.py

@dataclass(frozen=True)
class AgentSessionKey:
    """Canonical agent-core session key."""
    agent_id: str
    channel: str
    peer_kind: str
    peer_id: str
    thread_id: str | None = None

    def __post_init__(self) -> None:
        for field_name in ("agent_id", "channel", "peer_kind", "peer_id"):
            value = getattr(self, field_name)
            if not str(value).strip():
                raise SessionKeyError(f"{field_name} must not be empty.")

    def base_key(self) -> str:
        """Get base key without thread."""
        return f"agent:{self.agent_id}:{self.channel}:{self.peer_kind}:{self.peer_id}"

    def to_key(self) -> str:
        """Get full key."""
        if self.thread_id:
            return f"{self.base_key()}:thread:{self.thread_id}"
        return self.base_key()

    def with_thread(self, thread_id: str) -> "AgentSessionKey":
        """Create key with thread."""
        normalized = thread_id.strip()
        if not normalized:
            raise SessionKeyError("thread_id must not be empty.")
        return AgentSessionKey(
            agent_id=self.agent_id,
            channel=self.channel,
            peer_kind=self.peer_kind,
            peer_id=self.peer_id,
            thread_id=normalized,
        )

    def slug(self, *, length: int = 10) -> str:
        """Get short slug."""
        length = max(6, min(int(length), 32))
        digest = hashlib.sha256(self.to_key().encode("utf-8")).hexdigest()
        return digest[:length]

    @staticmethod
    def parse(raw: str) -> "AgentSessionKey":
        """Parse session key from string."""
        ...
```

### 4.2 SessionKeyIndex

```python
class SessionKeyIndex:
    """Index for full/partial/slug session-key lookup."""

    def __init__(self) -> None:
        self._keys: dict[str, AgentSessionKey] = {}

    def add(self, key: AgentSessionKey) -> None:
        """Add key to index."""
        self._keys[key.to_key()] = key

    def remove(self, raw_key: str) -> bool:
        """Remove key from index."""
        return self._keys.pop(raw_key, None) is not None

    def list(self) -> tuple[AgentSessionKey, ...]:
        """List all keys."""
        return tuple(self._keys.values())

    def resolve(self, query: str) -> AgentSessionKey:
        """Resolve key by query (full/partial/slug)."""
        matches = self._matches(query)
        if not matches:
            raise SessionKeyError(f"session key not found: {query}")
        if len(matches) > 1:
            samples = ", ".join(item.to_key() for item in matches[:3])
            raise AmbiguousSessionKeyError(
                f"session key query '{query}' is ambiguous ({len(matches)} matches): {samples}"
            )
        return matches[0]
```

---

## 五、会话键格式

```
base_key = "agent:{agent_id}:{channel}:{peer_kind}:{peer_id}"
full_key = "agent:{agent_id}:{channel}:{peer_kind}:{peer_id}:thread:{thread_id}"

示例:
- "agent:main:tui:user:nlin"
- "agent:main:slack:user:U12345:thread:C789"
- "agent:assistant:discord:guild:G456"
```

---

## 六、生命周期流程

```
┌─────────────────────────────────────────────────────────────────┐
│                    Lifecycle Flow                                │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  Bootstrap                                               │   │
│  │  SessionLifecycleManager.bootstrap(session_key)          │   │
│  └─────────────────────────────────────────────────────────┘   │
│                              │                                   │
│                              ▼                                   │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  Active Session                                          │   │
│  │  - touch() on each activity                              │   │
│  │  - track last_activity_utc                               │   │
│  └─────────────────────────────────────────────────────────┘   │
│                              │                                   │
│                              ▼                                   │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  Check Reset                                             │   │
│  │  should_reset(state, now_utc)                            │   │
│  │  - DAILY: day_changed?                                   │   │
│  │  - IDLE: idle_elapsed?                                   │   │
│  │  - BOTH: day_changed OR idle_elapsed?                    │   │
│  └─────────────────────────────────────────────────────────┘   │
│                              │                                   │
│              ┌───────────────┴───────────────┐                  │
│              │                               │                  │
│              ▼                               ▼                  │
│  ┌───────────────────┐              ┌───────────────────┐      │
│  │  No Reset         │              │  Reset            │      │
│  │  Continue         │              │  revision += 1    │      │
│  │                   │              │  created_utc = now│      │
│  └───────────────────┘              └───────────────────┘      │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## 七、错误类型

```python
class SessionKeyError(ValueError):
    """Base session-key parsing error."""

class AmbiguousSessionKeyError(SessionKeyError):
    """Raised when a partial key matches multiple sessions."""
```

---

## 八、文件位置

```
src/mini_agent/agent_core/session/
├── lifecycle.py                 # SessionLifecycleManager, SessionLifecyclePolicy
├── session_key.py               # AgentSessionKey, SessionKeyIndex
```

---

## 九、验收标准

- [x] 支持重置策略
- [x] 支持活动追踪
- [x] 支持会话键模型
- [x] 支持键索引查询

---

## 十、依赖关系

- 依赖: 无
- 被依赖: session/store_records, runtime/