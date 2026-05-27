# Mini-Agent Agent Core 模块

## 1. 模块概述

`agent_core` 是 Mini-Agent 的核心运行时模块，负责 Agent 的执行、状态管理、上下文处理、技能系统、安全控制等关键功能。

### 1.1 目录结构

```
agent_core/
├── __init__.py              # 模块标记
├── kernel.py                # Agent 内核构建器
├── engine.py                # 核心 Agent 类
├── routing.py               # Agent 路由表
├── delegation.py            # 子 Agent 委派
├── presentation.py         # 运行时呈现器
├── runtime_bindings.py      # 运行时绑定
├── post_turn.py            # 回合后副作用
│
├── contracts/              # 核心合约定义
│   ├── agent_profile.py    # Agent 配置档案
│   ├── agent_instance.py   # Agent 实例合约
│   ├── run.py              # 运行合约
│   ├── checkpoint.py       # 检查点合约
│   ├── execution_journal.py # 执行日志
│   └── attachments.py      # 附件管理
│
├── execution/              # 执行引擎
│   ├── agent_loop.py       # 提交循环
│   ├── coordinator.py      # 多 Agent 协调
│   ├── tool_execution_coordinator.py
│   ├── permissions/        # 权限系统
│   ├── sandbox/            # 沙箱执行
│   └── tools/              # 工具系统
│
├── context/                # 上下文管理
│   ├── turn_context.py     # 回合上下文
│   ├── context_compaction.py # 上下文压缩
│   └── context_assembler.py # 上下文组装
│
├── session/                # 会话管理
│   ├── lifecycle.py        # 生命周期
│   └── lineage.py          # 血缘追踪
│
├── skills/                 # 技能系统
│   ├── registry.py         # 技能注册表
│   └── loader.py           # 技能加载器
│
├── browser/                # 浏览器集成
├── cron/                   # 定时任务
├── security/               # 安全模块
└── history/                # 历史记录
```

---

## 2. 核心类定义

### 2.1 Agent 类 (engine.py)

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
        ...
    ):

    # 核心方法
    async def run(self, cancel_event: Optional[asyncio.Event] = None) -> str
    async def run_turn(...) -> TurnExecutionResult
    def add_user_message(self, content: str)
    def compact_context(self, *, reason: str | None = None) -> dict[str, Any]
```

### 2.2 执行策略

```python
@dataclass(frozen=True)
class AgentExecutionPolicy:
    """Policy controls for one Agent run loop."""
    max_steps: int
    max_tool_calls_per_step: int | None = None

class StepTransition(str, Enum):
    """Step transition decisions."""
    CONTINUE = "continue"
    COMPLETE = "complete"
    CANCELLED = "cancelled"
    FAILED = "failed"
```

---

## 3. 合约系统 (contracts/)

### 3.1 AgentProfile

```python
@dataclass(frozen=True, slots=True)
class AgentProfile:
    """Agent 静态配置 - 持久化"""
    agent_profile_id: str
    name: str
    description: str = ""
    default_model_preference: str | None = None
    tool_policy: dict[str, Any] = field(default_factory=dict)
    skill_preferences: dict[str, Any] = field(default_factory=dict)
```

### 3.2 AgentInstance

```python
class AgentInstanceLifecycleState(str, Enum):
    COLD = "cold"
    READY = "ready"
    ATTACHED = "attached"
    RUNNING = "running"
    WAITING = "waiting"
    PAUSED = "paused"
    ERRORED = "errored"
    RETIRED = "retired"

@dataclass(frozen=True, slots=True)
class AgentInstance:
    """Agent 运行时实例 - 有状态"""
    agent_instance_id: str
    agent_profile_id: str
    lifecycle_state: AgentInstanceLifecycleState
    active_run_id: str | None = None
    current_workspace_id: str | None = None
    current_session_id: str | None = None
```

### 3.3 Run

```python
class RunStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    WAITING = "waiting"
    PAUSED = "paused"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"

class RunPhase(str, Enum):
    CREATED = "created"
    BINDING = "binding"
    PLANNING = "planning"
    AWAITING_APPROVAL = "awaiting_approval"
    EXECUTING_TOOLS = "executing_tools"
    TERMINAL = "terminal"

@dataclass(frozen=True, slots=True)
class Run:
    """One formal execution unit."""
    run_id: str
    agent_instance_id: str
    status: RunStatus = RunStatus.QUEUED
    phase: RunPhase = RunPhase.CREATED
```

---

## 4. 执行系统 (execution/)

### 4.1 工具执行协调器

```python
class AgentToolExecutionCoordinator:
    """Own tool authorization and execution sequencing."""

    async def execute_tool_calls(...) -> ToolExecutionBatchResult
    async def authorize_tool_invocation(...) -> ToolResult | None
    async def request_tool_approval(...) -> bool | None
```

### 4.2 权限系统

```python
class PermissionDecision(str, Enum):
    ALLOW = "allow"
    DENY = "deny"
    ASK = "ask"

class ApprovalEngine:
    """Policy + cache based approval decision engine."""
    def evaluate(invocation) -> ApprovalOutcome
    def record_user_decision(invocation, decision) -> ApprovalOutcome
```

---

## 5. 上下文系统 (context/)

### 5.1 ContextAssembler

```python
@dataclass(slots=True)
class ContextAssembler:
    """Assembler for agent context from multiple sources."""

    def add_system_prompt(self, content: str) -> ContextSection
    def add_skill_context(self, skill_name: str, instructions: str) -> ContextSection
    def add_memory_context(self, content: str) -> ContextSection
    def add_workspace_context(self, content: str) -> ContextSection
    def add_session_context(self, content: str) -> ContextSection
    def add_user_context(self, content: str) -> ContextSection

    def assemble(self, *, workspace_id, session_id, run_id) -> AssembledContext
```

### 5.2 上下文压缩

```python
class LayeredContextCompactor:
    """Small, strong context compactor for agent execution turns."""

    def compact(self, messages, *, query, enable_masking) -> ContextCompressionResult
```

---

## 6. 技能系统 (skills/)

### 6.1 技能注册表

```python
class SkillRegistry:
    """Registry resolving duplicate skills by source priority."""

    def register(self, skill: AgentSkill) -> None
    def get(self, name: str) -> AgentSkill | None
    def list(self, *, eligible_only: bool = False) -> list[AgentSkill]
```

### 6.2 技能加载器

```python
class AgentSkillLoader:
    """Load skills from builtin/workspace/plugin/remote sources."""

    def discover() -> list[SkillTier1Metadata]
    def get_skill(name: str) -> AgentSkill | None
    def load_tier2(name: str) -> str | None
```

---

## 7. 会话系统 (session/)

### 7.1 生命周期管理

```python
class SessionResetMode(str, Enum):
    NONE = "none"
    DAILY = "daily"
    IDLE = "idle"
    BOTH = "both"

class SessionLifecycleManager:
    def should_reset(state) -> tuple[bool, str | None]
    def touch(state) -> SessionLifecycleState
    def reset(state) -> SessionLifecycleState
```

### 7.2 血缘追踪

```python
class SessionLineageStore:
    """In-memory lineage graph."""

    def add_root(session_key) -> SessionLineageNode
    def add_child(parent, child, reason) -> SessionLineageNode
    def chain_to_root(session_key) -> list[SessionLineageNode]
```

---

## 8. 设计模式

| 模式 | 应用位置 |
|------|---------|
| 状态机 | Agent 执行流程、Run 生命周期 |
| 策略模式 | 权限策略、技能资格检查 |
| 责任链 | 工具审批流程 |
| 工厂模式 | Agent 内核构建 |
| 观察者模式 | 事件发布、进度通知 |
| 仓储模式 | 技能注册表、会话血缘存储 |
| 不可变数据类 | 所有合约定义 |
