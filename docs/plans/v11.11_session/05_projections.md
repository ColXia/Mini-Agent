# 读模型投影开发文档

**模块**: session/projections
**优先级**: P1
**预估时间**: 已实现，文档补全

---

## 一、功能概述

读模型投影负责构建会话查询视图：

- 会话摘要投影
- 会话详情投影
- 消息投影
- 审批投影
- 恢复投影

---

## 二、投影组件总览

| 组件 | 职责 |
|------|------|
| `SessionSummaryProjection` | 会话摘要投影 |
| `SessionDetailProjection` | 会话详情投影 |
| `SessionMessageProjection` | 消息投影 |
| `SessionPendingApprovalProjection` | 审批投影 |
| `SessionRecoveryProjection` | 恢复投影 |

---

## 三、核心投影组件

### 3.1 SessionSummaryProjection

```python
# src/mini_agent/session/projections.py

@dataclass(frozen=True)
class SessionSummaryProjection:
    """Session summary projection for list views."""
    session_id: str
    workspace_dir: str
    created_at: str
    updated_at: str
    title: str | None = None
    message_count: int = 0
    origin_surface: str = "tui"
    active_surface: str = "tui"
    reply_enabled: bool = False
    busy: bool = False
    running_state: str | None = None
    is_default: bool = False
    channel_type: str | None = None
    conversation_id: str | None = None
    sender_id: str | None = None
    token_usage: int = 0
    token_limit: int = 0
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
    pending_skill_reload_reason: str | None = None

    # Approvals and recovery
    pending_approvals: tuple[SessionPendingApprovalProjection, ...] = ()
    recovery: SessionRecoveryProjection | None = None
    remote_recovery_text: str | None = None

    # Diagnostics
    memory_diagnostics: dict[str, Any] = field(default_factory=dict)
    sandbox_diagnostics: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_transport_payload(cls, payload: Any) -> SessionSummaryProjection | None:
        """Build from transport payload."""
        ...

    def to_transport(self) -> MainAgentSessionSummary:
        """Convert to transport model."""
        ...
```

### 3.2 SessionDetailProjection

```python
@dataclass(frozen=True)
class SessionDetailProjection(SessionSummaryProjection):
    """Session detail projection with full context."""
    context_policy: dict[str, Any] = field(default_factory=dict)
    last_prepared_context: dict[str, Any] = field(default_factory=dict)
    prepared_context_diagnostics: dict[str, Any] = field(default_factory=dict)
    workspace_runtime_snapshot: dict[str, Any] = field(default_factory=dict)
    recent_messages: tuple[SessionMessageProjection, ...] = ()

    @classmethod
    def from_summary(
        cls,
        summary: SessionSummaryProjection,
        *,
        context_policy: Mapping[str, Any] | None = None,
        last_prepared_context: Mapping[str, Any] | None = None,
        prepared_context_diagnostics: Mapping[str, Any] | None = None,
        workspace_runtime_snapshot: Mapping[str, Any] | None = None,
        recent_messages: Sequence[SessionMessageProjection] | None = None,
    ) -> SessionDetailProjection:
        """Build from summary with additional context."""
        ...

    @classmethod
    def from_transport_payload(cls, payload: Any) -> SessionDetailProjection | None:
        """Build from transport payload."""
        ...

    def to_transport(self) -> MainAgentSessionDetail:
        """Convert to transport model."""
        ...
```

### 3.3 SessionMessageProjection

```python
@dataclass(frozen=True)
class SessionMessageProjection:
    """Message projection for transcript views."""
    index: int
    role: str
    content: str
    surface: str
    created_at: str
    channel_type: str | None = None
    conversation_id: str | None = None
    sender_id: str | None = None
    metadata: dict[str, Any] | None = None

    @classmethod
    def from_payload(cls, payload: Any) -> SessionMessageProjection | None:
        """Build from payload."""
        ...

    @classmethod
    def from_payloads(cls, items: Sequence[Any] | None) -> tuple[SessionMessageProjection, ...]:
        """Build multiple from payloads."""
        ...

    def to_transport(self) -> MainAgentSessionMessage:
        """Convert to transport model."""
        ...
```

### 3.4 SessionPendingApprovalProjection

```python
@dataclass(frozen=True)
class SessionPendingApprovalProjection:
    """Pending approval projection."""
    token: str
    tool_name: str
    arguments: dict[str, Any] = field(default_factory=dict)
    kind: str | None = None
    reason: str | None = None
    cache_key: str | None = None
    can_escalate: bool = False
    step: int | None = None

    @classmethod
    def from_payload(cls, payload: Any) -> SessionPendingApprovalProjection | None:
        """Build from payload."""
        ...

    @classmethod
    def from_payloads(cls, items: Sequence[Any] | None) -> tuple[SessionPendingApprovalProjection, ...]:
        """Build multiple from payloads."""
        ...

    def to_transport(self) -> MainAgentSessionPendingApproval:
        """Convert to transport model."""
        ...
```

### 3.5 SessionRecoveryProjection

```python
@dataclass(frozen=True)
class SessionRecoveryProjection:
    """Recovery state projection."""
    state: str
    summary: str
    last_activity: str | None = None
    last_user_message: str | None = None
    last_assistant_message: str | None = None
    pending_approvals: tuple[SessionPendingApprovalProjection, ...] = ()

    @classmethod
    def from_payload(cls, payload: Any) -> SessionRecoveryProjection | None:
        """Build from payload."""
        ...

    def to_transport(self) -> MainAgentSessionRecoverySnapshot:
        """Convert to transport model."""
        ...
```

---

## 四、投影层次结构

```
┌─────────────────────────────────────────────────────────────────┐
│                    Projection Hierarchy                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │              SessionSummaryProjection                    │   │
│  │  - session_id, workspace_dir                             │   │
│  │  - title, message_count                                  │   │
│  │  - surfaces (origin, active)                             │   │
│  │  - model identity                                        │   │
│  │  - pending_approvals                                     │   │
│  │  - recovery                                              │   │
│  │  - diagnostics                                           │   │
│  └─────────────────────────────────────────────────────────┘   │
│                              │                                   │
│                              ▼                                   │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │              SessionDetailProjection                     │   │
│  │  (extends SessionSummaryProjection)                      │   │
│  │  + context_policy                                        │   │
│  │  + last_prepared_context                                 │   │
│  │  + prepared_context_diagnostics                          │   │
│  │  + workspace_runtime_snapshot                            │   │
│  │  + recent_messages                                       │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │              SessionMessageProjection                    │   │
│  │  - index, role, content                                  │   │
│  │  - surface, created_at                                   │   │
│  │  - channel_type, conversation_id, sender_id              │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │              SessionPendingApprovalProjection            │   │
│  │  - token, tool_name, arguments                           │   │
│  │  - kind, reason, cache_key                               │   │
│  │  - can_escalate, step                                    │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │              SessionRecoveryProjection                   │   │
│  │  - state, summary                                        │   │
│  │  - last_activity                                         │   │
│  │  - last_user_message, last_assistant_message             │   │
│  │  - pending_approvals                                     │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## 五、转换方法

每个投影都提供两个转换方法：

```python
# 从传输负载构建
@classmethod
def from_transport_payload(cls, payload: Any) -> Projection | None:
    """Build from transport payload."""
    ...

# 转换到传输模型
def to_transport(self) -> TransportModel:
    """Convert to transport model."""
    ...
```

---

## 六、辅助函数

```python
def _safe_text(value: object | None) -> str:
    """Safely convert to text."""
    return safe_text(value)

def _safe_multiline_text(value: object | None) -> str:
    """Safely convert to multiline text."""
    return str(value or "").strip()

def _nonnegative_int(value: Any, *, default: int = 0) -> int:
    """Safely convert to non-negative int."""
    try:
        return max(0, int(value))
    except Exception:
        return max(0, int(default))

def _payload_dict(payload: Any) -> dict[str, Any]:
    """Extract dict from payload."""
    if payload is None:
        return {}
    if hasattr(payload, "model_dump"):
        dumped = payload.model_dump()
        if isinstance(dumped, dict):
            return dumped
    if isinstance(payload, Mapping):
        return dict(payload)
    return {}

def _copy_dict(value: Any) -> dict[str, Any]:
    """Copy dict if mapping."""
    if isinstance(value, Mapping):
        return dict(value)
    return {}
```

---

## 七、文件位置

```
src/mini_agent/session/
├── projections.py               # 本文档所述组件
```

---

## 八、验收标准

- [x] 支持会话摘要投影
- [x] 支持会话详情投影
- [x] 支持消息投影
- [x] 支持审批投影
- [x] 支持恢复投影
- [x] 支持传输模型转换

---

## 九、依赖关系

- 依赖: interfaces/agent, utils/text
- 被依赖: runtime/read_models, transport/