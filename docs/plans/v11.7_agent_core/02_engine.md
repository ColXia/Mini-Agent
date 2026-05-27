# Agent 引擎核心开发文档

**模块**: agent_core/engine.py
**优先级**: P0
**预估时间**: 已实现，文档补全

---

## 一、功能概述

Agent 引擎是 Mini-Agent 的核心运行时，负责：

- 执行循环管理 (run_turn, run)
- 消息历史管理
- Token 限制与上下文压缩
- 工具调用协调
- 钩子系统
- 错误处理与恢复

---

## 二、核心数据结构

### 2.1 AgentExecutionPolicy

```python
@dataclass(frozen=True)
class AgentExecutionPolicy:
    """Policy controls for one Agent run loop."""

    max_steps: int                      # 最大步数
    max_tool_calls_per_step: int | None = None  # 每步最大工具调用数

    def normalized(self) -> "AgentExecutionPolicy":
        """Normalize and validate policy values."""
```

### 2.2 StepExecutionState

```python
@dataclass
class StepExecutionState:
    """Per-step execution counters used by run loops and telemetry."""

    step: int
    requested_tool_calls: int = 0    # 请求的工具调用数
    truncated_tool_calls: int = 0    # 被截断的工具调用数
    executed_tool_calls: int = 0     # 实际执行的工具调用数
```

### 2.3 StepPlan

```python
@dataclass
class StepPlan:
    """Planner output for a single step."""

    step: int
    response_content: str              # LLM 响应内容
    response_thinking: str | None      # 思考过程 (如果支持)
    planned_tool_calls: list[ToolCall] # 计划的工具调用
    step_state: StepExecutionState
```

### 2.4 StepTransition

```python
class StepTransition(str, Enum):
    """Step transition decisions for the run state machine."""

    CONTINUE = "continue"   # 继续执行
    COMPLETE = "complete"   # 执行完成
    CANCELLED = "cancelled" # 被取消
    FAILED = "failed"       # 执行失败
```

### 2.5 StepOutcome

```python
@dataclass
class StepOutcome:
    """Executor output that drives run-level state transitions."""

    transition: StepTransition
    message: str
    failure: StepFailureEnvelope | None = None
```

### 2.6 StepFailureEnvelope

```python
@dataclass(frozen=True)
class StepFailureEnvelope:
    """Structured step failure details for observability and recovery policy."""

    step: int
    phase: str              # planner / executor
    error_type: str
    recoverable: bool       # 是否可恢复
    retryable: bool         # 是否可重试
    message: str
    details: dict[str, object] = field(default_factory=dict)
```

### 2.7 RunExecutionMetrics

```python
@dataclass
class RunExecutionMetrics:
    """Per-run counters emitted in terminal run events."""

    steps_started: int = 0
    steps_completed: int = 0
    steps_failed: int = 0
    steps_cancelled: int = 0
    tool_calls_requested: int = 0
    tool_calls_truncated: int = 0
    tool_calls_executed: int = 0
    failures_by_type: dict[str, int] = field(default_factory=dict)
```

---

## 三、Agent 类核心实现

### 3.1 构造函数

```python
class Agent:
    """Single agent with basic tools and MCP support."""

    def __init__(
        self,
        llm_client: LLMClient,
        system_prompt: str,
        tools: list[Tool],
        max_steps: int = 50,
        max_tool_calls_per_step: int | None = None,
        workspace_dir: str = "./workspace",
        token_limit: int = 80000,
        logger: AgentLogger | None = None,
        console_output: bool = True,
        presenter: AgentRuntimePresenter | None = None,
        approval_engine: ApprovalEngine | None = None,
        tool_approval_handler: Callable[[ToolApprovalRequest], Awaitable[bool | None] | bool | None] | None = None,
        runtime_policy_engine: Any | None = None,
        sandbox_manager: Any | None = None,
        context_compactor: LayeredContextCompactor | None = None,
        turn_context_providers: list[Any] | None = None,
        turn_context_max_items: int = 4,
        turn_context_max_items_per_source: int = 1,
        turn_context_max_total_chars: int = 2400,
        turn_memory_automation: TurnMemoryAutomation | None = None,
        turn_runtime_task_memory: TurnRuntimeTaskMemory | None = None,
    ):
```

**参数说明**:

| 参数 | 类型 | 说明 |
|------|------|------|
| llm_client | LLMClient | LLM 客户端 |
| system_prompt | str | 系统提示词 |
| tools | list[Tool] | 工具列表 |
| max_steps | int | 最大执行步数 |
| max_tool_calls_per_step | int \| None | 每步最大工具调用数 |
| workspace_dir | str | 工作目录 |
| token_limit | int | Token 限制阈值 |
| logger | AgentLogger | 日志记录器 |
| console_output | bool | 是否输出到控制台 |
| presenter | AgentRuntimePresenter | 运行时呈现器 |
| approval_engine | ApprovalEngine | 审批引擎 |
| tool_approval_handler | Callable | 工具审批处理器 |
| runtime_policy_engine | Any | 运行时策略引擎 |
| sandbox_manager | Any | 沙箱管理器 |
| context_compactor | LayeredContextCompactor | 上下文压缩器 |
| turn_context_providers | list | 回合上下文提供者 |
| turn_memory_automation | TurnMemoryAutomation | 记忆自动化 |
| turn_runtime_task_memory | TurnRuntimeTaskMemory | 运行时任务记忆 |

### 3.2 核心属性

```python
# LLM 相关
self.llm: LLMClient                    # LLM 客户端
self.messages: list[Message]           # 消息历史
self.system_prompt: str                # 系统提示词

# 工具相关
self.tools: dict[str, Tool]            # 工具字典
self.declarative_tools: dict           # 声明式工具注册表

# 执行策略
self.execution_policy: AgentExecutionPolicy
self.max_steps: int
self.max_tool_calls_per_step: int | None
self.token_limit: int

# 取消控制
self.cancel_event: asyncio.Event | None

# 运行时绑定
self._runtime_bindings: AgentRuntimeBindings
self._runtime_services: AgentRuntimeServices

# 工具执行
self.tool_execution_coordinator: AgentToolExecutionCoordinator

# 上下文管理
self.context_compactor: LayeredContextCompactor | None
self.turn_context_preparation_service: AgentPreparedTurnContextService

# Token 追踪
self.api_total_tokens: int = 0
self._skip_next_token_check: bool = False
```

### 3.3 核心方法

#### 消息管理

```python
def add_user_message(self, content: str) -> None:
    """Add a user message to history."""
```

#### 上下文压缩

```python
def compact_context(self, *, reason: str | None = None) -> dict[str, Any]:
    """Compact message history with the layered context compactor."""

def drop_memories(self, *, reason: str | None = None) -> dict[str, Any]:
    """Drop older conversational memory and keep only the freshest turn context."""
```

#### 工具管理

```python
def is_tool_enabled(self, tool_name: str) -> bool:
    """Check if a tool is enabled."""

def set_tool_enabled(self, tool_name: str, enabled: bool) -> bool:
    """Enable or disable a tool."""
```

#### 运行时绑定

```python
def set_runtime_bindings(
    self,
    *,
    runtime_route: Any = UNSET_RUNTIME_VALUE,
    skill_runtime: Any = UNSET_RUNTIME_VALUE,
    skill_catalog_loader: Any = UNSET_RUNTIME_VALUE,
    kernel_diagnostics: Any = UNSET_RUNTIME_VALUE,
) -> AgentRuntimeBindings:
    """Update runtime bindings."""

def set_runtime_services(
    self,
    *,
    runtime_policy_engine: Any = UNSET_RUNTIME_VALUE,
    approval_engine: ApprovalEngine | None = UNSET_RUNTIME_VALUE,
    sandbox_manager: Any = UNSET_RUNTIME_VALUE,
    tool_approval_handler: Any = UNSET_RUNTIME_VALUE,
) -> AgentRuntimeServices:
    """Update runtime services."""
```

#### 上下文管理器

```python
@contextmanager
def override_execution_policy(self, policy: Any):
    """Temporarily override execution policy."""

@contextmanager
def override_tool_approval_handler(
    self,
    handler: Callable[[ToolApprovalRequest], Awaitable[bool | None] | bool | None] | None,
):
    """Temporarily override tool approval handler."""
```

---

## 四、执行流程

### 4.1 执行循环状态机

```
┌─────────────────────────────────────────────────────────────────┐
│                        Agent Execution Loop                       │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌─────────┐                                                    │
│  │  START  │                                                    │
│  └────┬────┘                                                    │
│       │                                                         │
│       ▼                                                         │
│  ┌─────────────────┐                                            │
│  │ Prepare Context │  ← 准备回合上下文                          │
│  └────────┬────────┘                                            │
│           │                                                     │
│           ▼                                                     │
│  ┌─────────────────┐                                            │
│  │  Plan Step      │  ← LLM 生成响应和工具调用                  │
│  │  (LLM Call)     │                                            │
│  └────────┬────────┘                                            │
│           │                                                     │
│           ▼                                                     │
│  ┌─────────────────┐     No      ┌─────────────────┐           │
│  │ Tool Calls?     │────────────►│ COMPLETE        │           │
│  └────────┬────────┘              └─────────────────┘           │
│           │ Yes                                                 │
│           ▼                                                     │
│  ┌─────────────────┐                                            │
│  │ Execute Tools   │  ← 执行工具调用                            │
│  └────────┬────────┘                                            │
│           │                                                     │
│           ▼                                                     │
│  ┌─────────────────┐     Yes     ┌─────────────────┐           │
│  │ Cancelled?      │────────────►│ CANCELLED       │           │
│  └────────┬────────┘              └─────────────────┘           │
│           │ No                                                  │
│           ▼                                                     │
│  ┌─────────────────┐     Yes     ┌─────────────────┐           │
│  │ Max Steps?      │────────────►│ MAX_STEPS       │           │
│  └────────┬────────┘              └─────────────────┘           │
│           │ No                                                  │
│           ▼                                                     │
│  ┌─────────────────┐                                            │
│  │ Check Tokens    │  ← 检查 Token 限制                         │
│  └────────┬────────┘                                            │
│           │                                                     │
│           ▼                                                     │
│  ┌─────────────────┐     Yes     ┌─────────────────┐           │
│  │ Token Limit?    │────────────►│ Compact Context │──┐        │
│  └────────┬────────┘              └─────────────────┘  │        │
│           │ No                                        │        │
│           │                                           │        │
│           ◄───────────────────────────────────────────┘        │
│           │                                                     │
│           ▼                                                     │
│  ┌─────────────────┐                                            │
│  │ Next Step       │  ← 返回 Plan Step                          │
│  └─────────────────┘                                            │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 4.2 错误恢复流程

```
┌─────────────────────────────────────────────────────────────────┐
│                     Error Recovery Flow                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  1. LLM 调用失败                                                │
│     │                                                           │
│     ▼                                                           │
│  2. 分类错误 (classify_provider_error)                          │
│     │                                                           │
│     ├── context_window_exceeded ──► 上下文溢出恢复              │
│     │   ├── 压缩上下文 (compact_context)                        │
│     │   ├── 丢弃记忆 (drop_memories)                            │
│     │   └── 学习 Token 限制                                     │
│     │                                                           │
│     ├── retryable ──► 重试                                      │
│     │                                                           │
│     └── non_retryable ──► 返回失败                              │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## 五、钩子系统

### 5.1 钩子类型

```python
StepPlanHook = Callable[[StepPlan], Awaitable[None] | None]
LLMEventHook = Callable[[int, LLMStreamEvent], Awaitable[None] | None]
ToolCallStartHook = Callable[[int, ToolCall], Awaitable[None] | None]
ToolCallResultHook = Callable[[int, ToolCall, ToolResult], Awaitable[None] | None]


@dataclass
class PlannerExecutorHooks:
    """Optional callbacks emitted by the planner/executor loop."""

    on_step_plan: StepPlanHook | None = None
    on_llm_event: LLMEventHook | None = None
    on_tool_call_start: ToolCallStartHook | None = None
    on_tool_call_result: ToolCallResultHook | None = None
```

### 5.2 钩子触发时机

| 钩子 | 触发时机 |
|------|---------|
| on_step_plan | LLM 响应解析完成后 |
| on_llm_event | 每个 LLM 流事件 |
| on_tool_call_start | 工具调用开始前 |
| on_tool_call_result | 工具调用完成后 |

---

## 六、Token 管理

### 6.1 Token 限制检查

```python
def _should_check_tokens(self) -> bool:
    """Check if token limit should be evaluated."""

def _estimate_tokens(self) -> int:
    """Estimate current token count."""
```

### 6.2 上下文压缩策略

```python
def _build_context_compactor(self, *, aggressive: bool = False) -> LayeredContextCompactor:
    """Build context compactor with appropriate budget."""
```

**压缩策略**:
- **普通压缩**: 保留 65% Token 预算，保留最近 2 条工具消息
- **激进压缩**: 保留 35% Token 预算，保留最近 1 条工具消息

### 6.3 上下文溢出恢复

```python
async def _recover_from_context_overflow(
    self,
    *,
    step: int,
    exc: Exception,
) -> bool:
    """Recover from context window overflow error."""
```

**恢复步骤**:
1. 分类错误类型
2. 学习 Token 限制
3. 压缩上下文
4. 如果压缩不足，丢弃记忆
5. 返回是否成功恢复

---

## 七、文件位置

```
src/mini_agent/agent_core/
├── engine.py                # Agent 类核心实现
├── runtime_bindings.py      # 运行时绑定
├── presentation.py          # 运行时呈现器
└── post_turn.py             # 回合后副作用
```

---

## 八、验收标准

- [x] Agent 类支持完整执行循环
- [x] 支持工具调用协调
- [x] 支持上下文压缩
- [x] 支持错误恢复
- [x] 支持钩子系统
- [x] 支持取消控制

---

## 九、依赖关系

- 依赖: contracts/, context/, execution/
- 被依赖: TUI, Desktop, Gateway
