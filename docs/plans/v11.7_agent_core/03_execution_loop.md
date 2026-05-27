# 执行循环开发文档

**模块**: agent_core/execution
**优先级**: P0
**预估时间**: 已实现，文档补全

---

## 一、功能概述

执行循环负责：

- TurnScheduler - 回合调度器
- AgentLoop - 提交循环
- 状态机管理
- 事件发布

---

## 二、核心数据结构

### 2.1 SchedulerState

```python
class SchedulerState(str, Enum):
    """Scheduler states for one turn lifecycle."""

    VALIDATING = "validating"   # 验证中
    SCHEDULED = "scheduled"     # 已调度
    EXECUTING = "executing"     # 执行中
    COMPLETED = "completed"     # 已完成
    ERRORED = "errored"         # 错误
    INTERRUPTED = "interrupted" # 已中断
```

### 2.2 SchedulerResult

```python
@dataclass(frozen=True)
class SchedulerResult:
    """Result payload for one scheduler execution."""

    state: SchedulerState
    turn_context: TurnContext
    stop_reason: str | None = None
    message: str = ""
    error: str | None = None
```

### 2.3 SubmissionEvent

```python
class SubmissionEventType(str, Enum):
    """Submission-loop event types."""

    USER_INPUT = "user_input"
    INTERRUPT = "interrupt"
    EXEC_APPROVAL = "exec_approval"
    COMPACT = "compact"
    DROP_MEMORIES = "drop_memories"
    LOOP_STOP = "loop_stop"


@dataclass(frozen=True)
class SubmissionEvent:
    """One queued submission-loop event."""

    event_id: str
    event_type: SubmissionEventType
    payload: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=_utc_now)
```

---

## 三、TurnScheduler

### 3.1 职责

TurnScheduler 驱动单个回合的执行：

1. 验证用户输入
2. 应用回合策略
3. 执行 Agent 回合
4. 返回执行结果

### 3.2 状态机

```
┌─────────────────────────────────────────────────────────────────┐
│                     TurnScheduler State Machine                  │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌───────────┐                                                  │
│  │ VALIDATING│  ← 验证用户输入                                  │
│  └─────┬─────┘                                                  │
│        │                                                        │
│        ├── 空输入 ──► ERRORED                                   │
│        ├── 无效 Agent ──► ERRORED                               │
│        │                                                        │
│        ▼                                                        │
│  ┌───────────┐                                                  │
│  │ SCHEDULED │  ← 已调度，准备执行                               │
│  └─────┬─────┘                                                  │
│        │                                                        │
│        ▼                                                        │
│  ┌───────────┐                                                  │
│  │ EXECUTING │  ← 执行 Agent 回合                               │
│  └─────┬─────┘                                                  │
│        │                                                        │
│        ├── 成功 ──► COMPLETED                                   │
│        ├── 错误 ──► ERRORED                                     │
│        └── 中断 ──► INTERRUPTED                                 │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 3.3 实现

```python
class TurnScheduler:
    """Minimal scheduler driving one turn with explicit states."""

    async def run(
        self,
        *,
        agent: Any,
        turn_context: TurnContext,
        cancel_event: Any | None = None,
        hooks: Any | None = None,
    ) -> SchedulerResult:
        # 1. 验证
        user_input = turn_context.user_input.strip()
        if not user_input:
            return SchedulerResult(
                state=SchedulerState.ERRORED,
                turn_context=turn_context,
                message="Empty user input is not allowed.",
                error="empty_user_input",
            )

        # 2. 检查 Agent 合约
        if not hasattr(agent, "add_user_message") or not hasattr(agent, "run_turn"):
            return SchedulerResult(
                state=SchedulerState.ERRORED,
                turn_context=turn_context,
                message="Agent is missing required methods.",
                error="invalid_agent_contract",
            )

        # 3. 添加用户消息
        agent.add_user_message(user_input)

        try:
            # 4. 应用回合策略
            with _turn_policy_override(agent, turn_context.policy):
                # 5. 执行回合
                result = await agent.run_turn(
                    cancel_event=cancel_event,
                    hooks=hooks,
                )

                # 6. 返回结果
                return SchedulerResult(
                    state=SchedulerState.COMPLETED,
                    turn_context=turn_context,
                    stop_reason=result.stop_reason.value,
                    message=result.message,
                )

        except Exception as exc:
            return SchedulerResult(
                state=SchedulerState.ERRORED,
                turn_context=turn_context,
                message=str(exc),
                error="execution_error",
            )
```

---

## 四、AgentLoop

### 4.1 职责

AgentLoop 管理提交循环：

- 接收用户输入
- 调度回合执行
- 发布事件
- 处理中断

### 4.2 进度记录

```python
@dataclass
class _TurnProgressRecorder:
    """Records turn progress for UI updates."""

    submission_id: str
    activity_items: list[dict[str, Any]] = field(default_factory=list)
    running_state: str = ""
    pending_approvals: dict[str, dict[str, Any]] = field(default_factory=dict)

    def record_step_plan(self, step_plan: Any) -> dict[str, Any]:
        """Record step planning progress."""

    def record_tool_call_start(self, step: int, tool_call: Any) -> dict[str, Any]:
        """Record tool call start."""

    def record_tool_call_result(self, step: int, tool_call: Any, result: Any) -> dict[str, Any]:
        """Record tool call result."""

    def record_approval_requested(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Record approval request."""

    def record_approval_resolved(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Record approval resolution."""

    def record_llm_event(self, step: int, event: Any) -> dict[str, Any]:
        """Record LLM event."""
```

### 4.3 事件总线

```python
class InMemoryLoopMessageBus:
    """Simple in-memory message bus for loop events and tests."""

    def __init__(self):
        self.events: list[dict[str, Any]] = []
        self._lock = asyncio.Lock()

    async def publish(self, event_type: str, payload: dict[str, Any]) -> None:
        async with self._lock:
            self.events.append({
                "event_type": str(event_type),
                "payload": dict(payload),
                "timestamp": _utc_now().astimezone(timezone.utc).isoformat(),
            })
```

---

## 五、执行流程

### 5.1 完整执行流程

```
┌─────────────────────────────────────────────────────────────────┐
│                     Complete Execution Flow                       │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  1. 用户输入                                                    │
│     │                                                           │
│     ▼                                                           │
│  2. AgentLoop 接收                                              │
│     │                                                           │
│     ▼                                                           │
│  3. 创建 TurnContext                                            │
│     │                                                           │
│     ▼                                                           │
│  4. TurnScheduler.run()                                         │
│     │                                                           │
│     ├── VALIDATING                                              │
│     ├── SCHEDULED                                               │
│     └── EXECUTING                                               │
│           │                                                     │
│           ▼                                                     │
│  5. Agent.run_turn()                                            │
│     │                                                           │
│     ├── 准备上下文                                              │
│     ├── LLM 调用                                                │
│     ├── 工具执行                                                │
│     └── 后处理                                                  │
│           │                                                     │
│           ▼                                                     │
│  6. SchedulerResult                                             │
│     │                                                           │
│     ▼                                                           │
│  7. 发布事件                                                    │
│     │                                                           │
│     ▼                                                           │
│  8. 返回结果                                                    │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 5.2 回合策略覆盖

```python
@contextmanager
def _turn_policy_override(agent: Any, policy: TurnPolicySnapshot) -> Iterator[None]:
    """Apply one turn-scoped execution policy and restore after completion."""
    # 保存原始值
    prev_max_steps = getattr(agent, "max_steps", None)
    prev_max_tool_calls = getattr(agent, "max_tool_calls_per_step", None)

    try:
        # 应用新策略
        if hasattr(agent, "max_steps"):
            setattr(agent, "max_steps", policy.max_steps)
        if hasattr(agent, "max_tool_calls_per_step"):
            setattr(agent, "max_tool_calls_per_step", policy.max_tool_calls_per_step)
        yield
    finally:
        # 恢复原始值
        if hasattr(agent, "max_steps"):
            setattr(agent, "max_steps", prev_max_steps)
        if hasattr(agent, "max_tool_calls_per_step"):
            setattr(agent, "max_tool_calls_per_step", prev_max_tool_calls)
```

---

## 六、文件位置

```
src/mini_agent/agent_core/execution/
├── agent_loop.py            # 提交循环
├── scheduler.py             # TurnScheduler
├── coordinator.py           # 协调器
├── tool_execution_coordinator.py  # 工具执行协调
├── minimal_workflow.py      # 最小工作流
└── mcp_tools.py             # MCP 工具
```

---

## 七、验收标准

- [x] TurnScheduler 支持状态机
- [x] AgentLoop 支持事件发布
- [x] 支持回合策略覆盖
- [x] 支持进度记录

---

## 八、依赖关系

- 依赖: contracts/, context/
- 被依赖: engine.py
