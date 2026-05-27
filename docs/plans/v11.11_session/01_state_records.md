# 会话状态记录开发文档

**模块**: session/store_records
**优先级**: P0
**预估时间**: 已实现，文档补全

---

## 一、功能概述

会话状态记录定义了运行时会话的核心数据结构：

- 会话主状态
- 投影状态
- 运行时宿主状态
- 转录状态

---

## 二、状态记录总览

| 记录类型 | 职责 |
|----------|------|
| `MainAgentSessionState` | 会话主状态 |
| `MainAgentSessionProjectionState` | 投影状态 |
| `MainAgentSessionRuntimeHostState` | 运行时宿主状态 |
| `MainAgentSessionTranscriptState` | 转录状态 |
| `MainAgentSessionTranscriptEntry` | 转录条目 |
| `MainAgentSessionLineageState` | 血缘状态 |

---

## 三、核心状态记录

### 3.1 MainAgentSessionState

```python
# src/mini_agent/session/store_records.py

@dataclass(slots=True)
class MainAgentSessionState:
    """Main agent session state record."""
    session_id: str
    workspace_dir: Path
    lifecycle_state: SessionLifecycleState
    runtime: MainAgentSessionRuntimeHostState
    lineage_state: MainAgentSessionLineageState = field(default_factory=MainAgentSessionLineageState)
    projection: MainAgentSessionProjectionState = field(default_factory=MainAgentSessionProjectionState)
    transcript_state: MainAgentSessionTranscriptState = field(default_factory=MainAgentSessionTranscriptState)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def touch(self, *, now_utc: datetime | None = None) -> None:
        """Update timestamp."""
        self.updated_at = (now_utc or datetime.now(timezone.utc)).astimezone(timezone.utc)

    @property
    def agent(self) -> Agent:
        """Get attached agent."""
        return self.runtime.agent

    @property
    def cancel_event(self) -> asyncio.Event | None:
        """Get cancel event."""
        return self.runtime.cancel_event

    @property
    def active_surface(self) -> str:
        """Get active surface."""
        return self.projection.active_surface

    @property
    def origin_surface(self) -> str:
        """Get origin surface."""
        return self.projection.origin_surface

    @property
    def busy(self) -> bool:
        """Check if session is busy."""
        return bool(self.projection.busy)

    @property
    def running_state(self) -> str:
        """Get running state."""
        return self.projection.running_state

    @running_state.setter
    def running_state(self, value: str) -> None:
        """Set running state."""
        self.projection.running_state = str(value or "")

    @property
    def pending_approvals(self) -> list[dict[str, Any]]:
        """Get pending approvals."""
        return list(self.runtime.pending_approvals)

    @property
    def token_usage(self) -> int:
        """Get token usage."""
        return _agent_token_usage(self.runtime.agent)

    @property
    def message_count(self) -> int:
        """Get message count."""
        return _agent_message_count(self.runtime.agent)
```

### 3.2 MainAgentSessionProjectionState

```python
@dataclass(slots=True)
class MainAgentSessionProjectionState:
    """Projection state for session views."""
    title: str = ""
    origin_surface: str = ""
    active_surface: str = ""
    reply_enabled: bool = False
    busy: bool = False
    running_state: str = ""
    is_default: bool = False
    channel_type: str | None = None
    conversation_id: str | None = None
    sender_id: str | None = None
    shared: bool = False
    knowledge_base_enabled: bool = True

    # Model identity
    selected_model_source: str | None = None
    selected_provider_id: str | None = None
    selected_model_id: str | None = None
    pending_model_source: str | None = None
    pending_provider_id: str | None = None
    pending_model_id: str | None = None

    # Skill reload
    pending_skill_reload: bool = False
    pending_skill_reload_reason: str = ""

    # Recovery
    recovery_context_pending: bool = False
    recovery_state: str = ""
    recovery_summary: str = ""
    recovery_last_activity: str | None = None
    recovery_last_user_message: str | None = None
    recovery_last_assistant_message: str | None = None
    recovery_pending_approvals: list[dict[str, Any]] = field(default_factory=list)

    # Context policy
    context_policy: dict[str, Any] = field(default_factory=dict)
    last_prepared_context: dict[str, Any] = field(default_factory=dict)
    prepared_context_diagnostics: dict[str, Any] = field(default_factory=dict)

    # Diagnostics
    memory_diagnostics: dict[str, Any] = field(default_factory=dict)
    sandbox_diagnostics: dict[str, Any] = field(default_factory=dict)
```

### 3.3 MainAgentSessionRuntimeHostState

```python
@dataclass(slots=True)
class MainAgentSessionRuntimeHostState:
    """Runtime host state for agent execution."""
    agent: Agent
    cancel_event: asyncio.Event | None = None
    pending_approvals: list[dict[str, Any]] = field(default_factory=list)
    pending_approval_waiters: dict[str, asyncio.Future[bool | None]] = field(default_factory=dict)
    kernel_state_payload: dict[str, Any] | None = None
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
```

### 3.4 MainAgentSessionTranscriptState

```python
@dataclass(slots=True)
class MainAgentSessionTranscriptState:
    """Transcript state for message history."""
    transcript: list["MainAgentSessionTranscriptEntry"] = field(default_factory=list)
    next_transcript_index: int = 1
    current_turn_id: str | None = None
```

### 3.5 MainAgentSessionTranscriptEntry

```python
@dataclass
class MainAgentSessionTranscriptEntry:
    """Single transcript entry."""
    index: int
    role: str
    content: str
    surface: str
    created_at: datetime
    channel_type: str | None = None
    conversation_id: str | None = None
    sender_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
```

---

## 四、状态层次结构

```
┌─────────────────────────────────────────────────────────────────┐
│                    MainAgentSessionState                         │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │              RuntimeHostState                            │   │
│  │  - agent: Agent                                          │   │
│  │  - cancel_event: asyncio.Event                           │   │
│  │  - pending_approvals: list[dict]                         │   │
│  │  - pending_approval_waiters: dict[str, Future]           │   │
│  │  - kernel_state_payload: dict | None                     │   │
│  │  - lock: asyncio.Lock                                    │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │              ProjectionState                             │   │
│  │  - title, surfaces, shared status                        │   │
│  │  - model identity (selected/pending)                     │   │
│  │  - skill reload state                                    │   │
│  │  - recovery state                                        │   │
│  │  - context policy                                        │   │
│  │  - diagnostics                                           │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │              TranscriptState                             │   │
│  │  - transcript: list[TranscriptEntry]                     │   │
│  │  - next_transcript_index: int                            │   │
│  │  - current_turn_id: str | None                           │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │              LineageState                                │   │
│  │  - parent_session_id: str | None                         │   │
│  │  - root_session_id: str | None                           │   │
│  │  - reason: str                                           │   │
│  │  - created_at: datetime                                  │   │
│  │  - metadata: dict                                        │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │              LifecycleState                              │   │
│  │  - session_key: AgentSessionKey                          │   │
│  │  - created_utc: datetime                                 │   │
│  │  - last_activity_utc: datetime                           │   │
│  │  - revision: int                                         │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## 五、辅助函数

### 5.1 Token 计算

```python
def _agent_messages(agent: Any | None) -> list[Any]:
    """Get messages from agent."""
    messages = getattr(agent, "messages", None)
    return list(messages) if isinstance(messages, list) else []

def _agent_message_count(agent: Any | None) -> int:
    """Get message count from agent."""
    return len(_agent_messages(agent))

def _agent_token_usage(agent: Any | None) -> int:
    """Get token usage from agent."""
    live = _normalize_nonnegative_int(getattr(agent, "api_total_tokens", 0))
    if live > 0:
        return live
    messages = _agent_messages(agent)
    if not messages:
        return 0
    try:
        return _normalize_nonnegative_int(estimate_tokens(messages))
    except Exception:
        return 0
```

---

## 六、文件位置

```
src/mini_agent/session/
├── store_records.py             # 本文档所述组件
```

---

## 七、验收标准

- [x] 支持会话主状态
- [x] 支持投影状态
- [x] 支持运行时宿主状态
- [x] 支持转录状态
- [x] 支持 Agent 属性访问

---

## 八、依赖关系

- 依赖: agent_core/engine, agent_core/session/lifecycle
- 被依赖: runtime/, persistence.py