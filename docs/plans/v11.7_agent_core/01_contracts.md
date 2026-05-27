# 合约系统开发文档

**模块**: agent_core/contracts
**优先级**: P0
**预估时间**: 已实现，文档补全

---

## 一、功能概述

合约系统定义 Agent 运行的核心数据结构：

- **AgentProfile** - Agent 静态配置（持久化）
- **AgentInstance** - Agent 运行时实例（有状态）
- **Run** - 执行单元（一次完整执行）
- **Checkpoint** - 检查点（可恢复锚点）
- **ExecutionJournal** - 执行日志（追加写入）

---

## 二、数据结构

### 2.1 AgentProfile

**用途**: 定义 Agent 的静态身份和内置能力

```python
@dataclass(frozen=True, slots=True)
class AgentProfile:
    """Static agent identity and built-in capability definition."""

    agent_profile_id: str           # 唯一标识
    role: str | None = None         # 角色描述
    identity_label: str | None = None  # 身份标签

    # 内置能力
    built_in_tool_names: tuple[str, ...] = ()
    built_in_internal_skill_names: tuple[str, ...] = ()

    # 模型路由
    default_model_routing_intent: str | None = None

    # 策略提示
    static_policy_hints: dict[str, Any] | None = None
    stable_behavior_defaults: dict[str, Any] | None = None
    capability_hints: tuple[str, ...] = ()

    # 时间戳
    created_at: datetime | None = None
    updated_at: datetime | None = None
```

**设计要点**:
- `frozen=True` - 不可变，确保配置一致性
- `slots=True` - 内存优化
- 内置工具/技能在 Profile 定义，运行时不可变

**方法**:
- `has_tool(tool_name)` - 检查是否包含指定工具
- `has_internal_skill(skill_name)` - 检查是否包含指定技能

---

### 2.2 AgentInstance

**用途**: Agent 运行时实例，管理生命周期状态

```python
class AgentInstanceLifecycleState(str, Enum):
    """Lifecycle states for one durable agent instance."""

    COLD = "cold"         # 未初始化
    READY = "ready"       # 就绪
    ATTACHED = "attached" # 已绑定 Workspace/Session
    RUNNING = "running"   # 执行中
    WAITING = "waiting"  # 等待（审批/输入）
    PAUSED = "paused"    # 暂停
    MIGRATING = "migrating"  # 迁移中
    ERRORED = "errored"   # 错误
    RETIRED = "retired"   # 已退役


@dataclass(frozen=True, slots=True)
class AgentInstance:
    """Persistent execution subject for the kernel."""

    agent_instance_id: str
    agent_profile_id: str
    lifecycle_state: AgentInstanceLifecycleState = AgentInstanceLifecycleState.COLD

    # 运行时绑定
    active_run_id: str | None = None
    current_workspace_id: str | None = None
    current_session_id: str | None = None
    current_workspace_attachment_id: str | None = None
    current_session_attachment_id: str | None = None

    # 检查点
    checkpoint_head_id: str | None = None
    journal_head_seq: int = 0

    # 中断控制
    interrupt_requested: bool = False
    cancel_requested: bool = False
    pending_wait_kind: RunWaitKind = RunWaitKind.NONE
    pending_wait_id: str | None = None

    # 恢复信息
    restored_from_checkpoint_id: str | None = None

    # 时间戳
    created_at: datetime | None = None
    updated_at: datetime | None = None
    retired_at: datetime | None = None
```

**生命周期状态机**:

```
                    ┌──────────────────────────────────────┐
                    │                                      │
                    ▼                                      │
┌──────┐  init   ┌───────┐  attach  ┌──────────┐  start  ┌────────┐
│ COLD │ ───────►│ READY │ ────────►│ ATTACHED │ ───────►│ RUNNING │
└──────┘         └───────┘          └──────────┘         └────────┘
                     │                    │                    │
                     │                    │                    │
                     │                    │      pause         │
                     │                    │◄───────────────────┤
                     │                    │                    │
                     │                    ▼                    │
                     │               ┌────────┐               │
                     │               │ PAUSED │               │
                     │               └────────┘               │
                     │                    │                   │
                     │                    │ resume            │
                     │                    └──────────────────►│
                     │                                        │
                     │                    wait                │
                     │                   ◄────────────────────┤
                     │                                        │
                     │                    ▼                   │
                     │               ┌─────────┐             │
                     │               │ WAITING │             │
                     │               └─────────┘             │
                     │                    │                   │
                     │                    │ resume            │
                     │                    └──────────────────►│
                     │                                        │
                     │  error                                │
                     │◄───────────────────────────────────────┤
                     ▼                                        │
                ┌──────────┐                                  │
                │ ERRORED  │                                  │
                └──────────┘                                  │
                     │                                        │
                     │  retire                                │
                     ▼                                        │
                ┌──────────┐                                  │
                │ RETIRED  │◄─────────────────────────────────┘
                └──────────┘
```

**关键方法**:
- `transition_lifecycle(state)` - 状态转换
- `attach(workspace_id, session_id)` - 绑定 Workspace/Session
- `activate_run(run_id)` - 激活执行
- `mark_waiting(wait_kind)` - 标记等待
- `mark_paused()` - 标记暂停
- `request_interrupt()` / `request_cancel()` - 请求中断/取消
- `record_checkpoint(checkpoint_id)` - 记录检查点
- `clear_active_run()` - 清除活跃执行

---

### 2.3 Run

**用途**: 一次完整执行单元

```python
class RunStatus(str, Enum):
    """Status values for one formal execution unit."""

    QUEUED = "queued"       # 排队中
    RUNNING = "running"     # 执行中
    WAITING = "waiting"     # 等待
    PAUSED = "paused"       # 暂停
    COMPLETED = "completed" # 完成
    CANCELLED = "cancelled" # 取消
    FAILED = "failed"       # 失败


class RunPhase(str, Enum):
    """Pipeline phases for one formal execution unit."""

    CREATED = "created"
    BINDING = "binding"
    RESOLVING_CAPABILITIES = "resolving_capabilities"
    PREPARING_CONTEXT = "preparing_context"
    PLANNING = "planning"
    AWAITING_APPROVAL = "awaiting_approval"
    EXECUTING_TOOLS = "executing_tools"
    COMMITTING_EFFECTS = "committing_effects"
    WRITING_REPLY = "writing_reply"
    POST_TURN = "post_turn"
    TERMINAL = "terminal"


class RunInterruptState(str, Enum):
    """Interrupt lifecycle markers for one run."""

    NONE = "none"
    REQUESTED = "requested"
    ACKNOWLEDGED = "acknowledged"
    RESUMING = "resuming"


@dataclass(frozen=True, slots=True)
class Run:
    """One formal execution unit."""

    run_id: str
    agent_instance_id: str
    agent_profile_id: str
    workspace_id: str
    session_id: str
    trigger_source: str

    status: RunStatus = RunStatus.QUEUED
    phase: RunPhase = RunPhase.CREATED
    step_index: int = 0

    # 等待信息
    waiting_reason: str | None = None
    interrupt_state: RunInterruptState = RunInterruptState.NONE

    # 终止信息
    terminal_reason: str | None = None

    # 附件
    workspace_attachment_id: str | None = None
    session_attachment_id: str | None = None
    capability_snapshot_id: str | None = None

    # 检查点
    active_checkpoint_id: str | None = None
    last_checkpoint_seq: int = 0

    # 日志
    journal_stream_id: str | None = None

    # 可恢复性
    restorable: bool = True

    # 时间戳
    created_at: datetime | None = None
    started_at: datetime | None = None
    updated_at: datetime | None = None
    ended_at: datetime | None = None

    # 错误追踪
    last_error_code: str | None = None
    last_error_summary: str | None = None
    last_model_request_id: str | None = None
    last_tool_batch_id: str | None = None
    last_mutation_ledger_seq: int | None = None
```

**Status/Phase 有效组合**:

| Status | Phase |
|--------|-------|
| QUEUED | CREATED |
| RUNNING | BINDING, RESOLVING_CAPABILITIES, PREPARING_CONTEXT, PLANNING, EXECUTING_TOOLS, COMMITTING_EFFECTS, WRITING_REPLY, POST_TURN |
| WAITING | AWAITING_APPROVAL |
| PAUSED | PLANNING, EXECUTING_TOOLS |
| COMPLETED/CANCELLED/FAILED | TERMINAL |

**关键方法**:
- `transition(status, phase)` - 状态转换
- `bind_attachments(...)` - 绑定附件
- `attach_capability_snapshot(snapshot_id)` - 附加能力快照
- `activate_checkpoint(checkpoint_id)` - 激活检查点
- `advance_step()` - 推进步骤

---

### 2.4 Checkpoint

**用途**: 可恢复的执行锚点

```python
class CheckpointType(str, Enum):
    """Checkpoint classes recognized by v11.1."""

    BOOTSTRAP = "bootstrap"           # 启动点
    PRE_SIDE_EFFECT = "pre_side_effect"   # 副作用前
    POST_SIDE_EFFECT = "post_side_effect" # 副作用后
    WAITING = "waiting"               # 等待点
    TERMINAL = "terminal"             # 终止点


@dataclass(frozen=True, slots=True)
class Checkpoint:
    """Recoverable kernel anchor for one run."""

    checkpoint_id: str
    run_id: str
    agent_instance_id: str
    checkpoint_seq: int
    checkpoint_type: CheckpointType

    # 执行状态快照
    status: RunStatus
    phase: RunPhase
    step_index: int

    # 附件引用
    workspace_attachment_id: str
    session_attachment_id: str
    capability_snapshot_hash: str

    # 日志偏移
    journal_offset: int

    # 恢复信息
    waiting_reason: str | None = None
    resume_token: str | None = None
    recoverable: bool = True

    # 引用
    last_model_turn_ref: str | None = None
    last_tool_batch_ref: str | None = None
    last_mutation_ledger_seq: int | None = None
    recovery_context_ref: str | None = None
    error_ref: str | None = None

    # 元数据
    schema_version: str = "v11.1"
    created_at: datetime | None = None
```

---

### 2.5 ExecutionJournal

**用途**: 追加写入的执行日志

```python
@dataclass(frozen=True, slots=True)
class ExecutionJournalEvent:
    """One append-only execution fact."""

    event_seq: int
    event_type: str
    run_id: str
    agent_instance_id: str
    workspace_id: str
    session_id: str

    status: RunStatus
    phase: RunPhase
    step_index: int

    event_ts: datetime | None = None
    correlation_id: str | None = None
    causation_id: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ExecutionJournal:
    """Append-only execution fact stream for one run."""

    journal_stream_id: str
    run_id: str
    agent_instance_id: str
    workspace_id: str
    session_id: str

    events: tuple[ExecutionJournalEvent, ...] = ()

    created_at: datetime | None = None
    closed_at: datetime | None = None
```

**关键方法**:
- `append(event_type, status, phase, ...)` - 追加事件
- `close()` - 关闭日志

---

## 三、关系图

```
┌─────────────────────────────────────────────────────────────────┐
│                        Contract Relationships                    │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌──────────────┐                                               │
│  │ AgentProfile │  (1:N)                                        │
│  │   (静态)     │──────────────┐                                │
│  └──────────────┘              │                                │
│                                ▼                                │
│                         ┌──────────────┐                        │
│                         │AgentInstance │  (1:N)                │
│                         │   (实例)     │────────────┐          │
│                         └──────────────┘            │          │
│                                                     ▼          │
│                                              ┌──────────┐       │
│                                              │   Run    │ (1:N) │
│                                              │ (执行)   │───────┤
│                                              └──────────┘       │
│                                                     │          │
│                                    ┌────────────────┼──────────┤
│                                    │                │          │
│                                    ▼                ▼          │
│                             ┌────────────┐  ┌───────────────┐  │
│                             │ Checkpoint │  │ExecutionJournal│  │
│                             │  (检查点)  │  │   (日志)      │  │
│                             └────────────┘  └───────────────┘  │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## 四、文件位置

```
src/mini_agent/agent_core/contracts/
├── __init__.py
├── _common.py              # 公共工具函数
├── agent_profile.py        # AgentProfile
├── agent_instance.py       # AgentInstance
├── run.py                  # Run
├── run_control_state.py    # RunWaitKind
├── checkpoint.py           # Checkpoint
├── execution_journal.py    # ExecutionJournal
├── attachments.py          # WorkspaceAttachment, SessionAttachment
├── capability_snapshot.py  # CapabilitySnapshot
└── approval_wait.py        # ApprovalWait
```

---

## 五、验收标准

- [x] AgentProfile 支持静态配置
- [x] AgentInstance 支持生命周期状态机
- [x] Run 支持 Status/Phase 组合验证
- [x] Checkpoint 支持多种类型
- [x] ExecutionJournal 支持追加写入
- [x] 所有合约使用 frozen dataclass

---

## 六、依赖关系

- 无前置依赖
- 被依赖: Engine, Execution, Session
