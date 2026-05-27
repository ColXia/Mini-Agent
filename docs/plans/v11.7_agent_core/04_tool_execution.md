# 工具执行协调器开发文档

**模块**: agent_core/execution/tool_execution_coordinator.py
**优先级**: P1
**预估时间**: 已实现，文档补全

---

## 一、功能概述

工具执行协调器负责：

- 工具调用授权
- 工具执行序列化
- 中断支持
- 审批流程

---

## 二、核心数据结构

### 2.1 ToolExecutionBatchState

```python
class ToolExecutionBatchState(str, Enum):
    """Execution states for one batch of tool calls in a planner step."""

    CONTINUE = "continue"     # 继续执行
    COMPLETE = "complete"     # 执行完成
    CANCELLED = "cancelled"   # 已取消
```

### 2.2 ToolExecutionBatchResult

```python
@dataclass(frozen=True)
class ToolExecutionBatchResult:
    """Result payload for one tool-call execution batch."""

    state: ToolExecutionBatchState
    message: str = ""
```

### 2.3 AgentToolExecutionRuntime

```python
@dataclass(frozen=True)
class AgentToolExecutionRuntime:
    """Narrow runtime contract used by the tool-execution seam."""

    cancel_event_getter: Callable[[], asyncio.Event | None]
    cancelled_checker: Callable[[], bool]
    hook_emitter: Callable[[Any, Any], Awaitable[None]]
    tool_getter: Callable[[str], Tool | None]
    invocation_builder: Callable[[str, dict[str, object]], ToolInvocation]
    tool_approval_handler_getter: Callable[[], Any]
    runtime_policy_engine_getter: Callable[[], Any]
    approval_engine_getter: Callable[[], Any]
    message_appender: Callable[[Message], None]
    event_logger: Callable[[str, dict[str, Any], str], None]
    tool_result_logger: Callable[[str, dict[str, object], bool, str | None, str | None], None]
```

---

## 三、AgentToolExecutionCoordinator

### 3.1 职责

协调器管理工具执行的完整生命周期：

1. 授权检查
2. 审批请求
3. 工具执行
4. 中断处理
5. 结果记录

### 3.2 执行流程

```
┌─────────────────────────────────────────────────────────────────┐
│                   Tool Execution Flow                            │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  1. 接收工具调用请求                                            │
│     │                                                           │
│     ▼                                                           │
│  2. 构建工具调用 (build_tool_invocation)                        │
│     │                                                           │
│     ▼                                                           │
│  3. 授权检查 (authorize_tool_invocation)                        │
│     │                                                           │
│     ├── 被拒绝 ──► 返回拒绝结果                                 │
│     │                                                           │
│     ▼                                                           │
│  4. 审批请求 (request_tool_approval)                            │
│     │                                                           │
│     ├── 需要审批 ──► 等待用户决策                               │
│     │   ├── 批准 ──► 继续                                       │
│     │   └── 拒绝 ──► 返回拒绝结果                               │
│     │                                                           │
│     ▼                                                           │
│  5. 执行工具 (execute_tool_with_interrupt_support)               │
│     │                                                           │
│     ├── 正常执行 ──► 返回结果                                   │
│     │                                                           │
│     └── 中断请求                                                │
│         ├── 尝试取消 (best_effort_cancel_tool)                  │
│         └── 返回中断结果                                        │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 3.3 核心方法

#### 工具执行

```python
async def execute_tool_with_interrupt_support(
    self,
    *,
    step: int,
    tool_name: str,
    tool: Tool,
    arguments: dict[str, object] | None = None,
    invocation: ToolInvocation | None = None,
) -> ToolResult:
    """Execute one tool call with cancel-event race handling."""
```

**执行逻辑**:
1. 创建工具执行任务
2. 创建取消等待任务
3. 竞争等待
4. 如果工具先完成，返回结果
5. 如果取消先触发，尝试取消工具

#### 中断支持

```python
async def best_effort_cancel_tool(
    self,
    *,
    step: int,
    tool_name: str,
    tool: Tool,
) -> bool:
    """Try to interrupt one running tool invocation."""
```

**取消逻辑**:
1. 检查工具是否支持 `cancel_running` 方法
2. 调用取消方法
3. 记录取消结果

#### 授权检查

```python
async def authorize_tool_invocation(
    self,
    *,
    step: int,
    invocation: ToolInvocation,
) -> ToolResult | None:
    """Check if tool invocation is allowed by policy engine."""
```

**授权逻辑**:
1. 获取策略引擎
2. 检查命令是否允许
3. 返回拒绝结果或 None

#### 审批请求

```python
async def request_tool_approval(
    self,
    *,
    step: int,
    invocation: ToolInvocation,
    reason: str,
    cache_key: str | None,
    can_escalate: bool,
) -> bool | None:
    """Request user approval for tool invocation."""
```

---

## 四、工具调用属性

### 4.1 ToolInvocation

```python
@dataclass
class ToolInvocation:
    """One prepared tool-call invocation."""

    tool_name: str
    arguments: dict[str, object]
    attributes: ToolAttributes
    tool: Tool

    async def execute(self) -> ToolResult:
        """Execute the tool invocation."""
```

### 4.2 ToolAttributes

```python
@dataclass(frozen=True)
class ToolAttributes:
    """Attributes describing tool behavior."""

    kind: ToolKind
    read_only: bool = False
    requires_approval: bool = False
    sandbox: bool = False
    timeout_seconds: float | None = None
```

### 4.3 ToolKind

```python
class ToolKind(str, Enum):
    """Tool kind classification."""

    READ = "read"
    WRITE = "write"
    EDIT = "edit"
    DELETE = "delete"
    EXECUTE = "execute"
    NETWORK = "network"
    BROWSER = "browser"
    MCP = "mcp"
    UTILITY = "utility"
```

---

## 五、审批流程

### 5.1 ToolApprovalRequest

```python
@dataclass(frozen=True)
class ToolApprovalRequest:
    """Request for user approval of a tool invocation."""

    token: str              # 唯一标识
    step: int                # 步骤号
    tool_name: str          # 工具名称
    arguments: dict[str, object]  # 参数
    kind: str                # 工具类型
    reason: str              # 审批原因
    cache_key: str | None    # 缓存键
    can_escalate: bool       # 是否可升级
```

### 5.2 审批流程

```
┌─────────────────────────────────────────────────────────────────┐
│                     Approval Flow                                │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  1. 工具调用需要审批                                            │
│     │                                                           │
│     ▼                                                           │
│  2. 创建 ToolApprovalRequest                                    │
│     │                                                           │
│     ▼                                                           │
│  3. 调用 tool_approval_handler                                  │
│     │                                                           │
│     ├── 返回 True ──► 批准执行                                  │
│     ├── 返回 False ──► 拒绝执行                                 │
│     └── 返回 None ──► 使用默认策略                              │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## 六、文件位置

```
src/mini_agent/agent_core/execution/
├── tool_execution_coordinator.py  # 协调器
├── tool_approval.py              # 审批请求
├── tools/
│   ├── attributes.py             # 工具属性
│   ├── builder.py                # 工具构建器
│   ├── invocation.py             # 工具调用
│   └── runtime_adapter.py        # 运行时适配器
└── permissions/
    ├── policy.py                 # 权限策略
    └── approval.py               # 审批引擎
```

---

## 七、验收标准

- [x] 工具执行支持中断
- [x] 支持授权检查
- [x] 支持审批流程
- [x] 支持工具属性分类

---

## 八、依赖关系

- 依赖: tools/base.py, permissions/
- 被依赖: engine.py
