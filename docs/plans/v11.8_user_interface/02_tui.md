# TUI 终端用户界面开发文档

**模块**: tui
**优先级**: P0
**预估时间**: 已实现，文档补全

---

## 一、功能概述

TUI (Terminal User Interface) 提供：

- 全屏终端界面
- 实时流式输出
- 命令模式
- 键盘快捷键
- 会话管理

---

## 二、技术栈

- **prompt_toolkit** - 终端 UI 框架
- **asyncio** - 异步执行
- **rich** - 富文本格式化

---

## 三、核心组件

### 3.1 TUI 应用结构

```python
# src/mini_agent/tui/app.py

class MiniAgentTuiApp:
    """Full-screen terminal UI for Mini-Agent."""

    def __init__(
        self,
        workspace_dir: Path,
        config: Config,
        *,
        session_id: str | None = None,
        approval_profile: str | None = None,
    ) -> None:
        self.workspace_dir = workspace_dir
        self.config = config
        self.session_id = session_id

        # UI 组件
        self.layout: Layout
        self.key_bindings: KeyBindings
        self.style: Style

        # 状态
        self.messages: list[Message]
        self.is_running: bool = False
        self.current_input: str = ""

        # 服务
        self.agent: Agent | None = None
        self.session_state: MainAgentSessionState | None = None
```

### 3.2 布局结构

```
┌─────────────────────────────────────────────────────────────────┐
│ Header: Session Info, Model, Status                              │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│                                                                 │
│                      Message History                             │
│                                                                 │
│                                                                 │
│                                                                 │
├─────────────────────────────────────────────────────────────────┤
│ Activity: Tool calls, Progress indicators                        │
├─────────────────────────────────────────────────────────────────┤
│ Input: User input field                                          │
├─────────────────────────────────────────────────────────────────┤
│ Status: Keybindings, Mode indicators                             │
└─────────────────────────────────────────────────────────────────┘
```

### 3.3 键盘快捷键

| 快捷键 | 功能 |
|--------|------|
| `Enter` | 发送消息 |
| `Esc` | 中断/取消 |
| `Ctrl+C` | 退出 |
| `Ctrl+D` | 切换命令模式 |
| `Ctrl+L` | 清屏 |
| `Ctrl+P` | 上翻 |
| `Ctrl+N` | 下翻 |
| `Tab` | 自动补全 |

---

## 四、命令模式

### 4.1 命令格式

```
/command [args...] [options...]
```

### 4.2 内置命令

| 命令 | 说明 |
|------|------|
| `/help` | 显示帮助 |
| `/clear` | 清除消息 |
| `/model` | 模型管理 |
| `/session` | 会话管理 |
| `/skill` | 技能管理 |
| `/memory` | 记忆管理 |
| `/context` | 上下文管理 |
| `/mcp` | MCP 管理 |
| `/approval` | 审批管理 |
| `/exit` | 退出应用 |

### 4.3 命令解析

```python
# src/mini_agent/commands/parser.py

class CommandDispatcher:
    """Dispatch parsed commands to handlers."""

    def parse(self, text: str) -> CommandParseResult:
        """Parse command text into structured result."""
        if not text.startswith("/"):
            return CommandParseResult(type="chat", content=text)

        parts = text[1:].split()
        if not parts:
            return CommandParseResult(type="unknown", error="Empty command")

        command = parts[0].lower()
        args = parts[1:]

        return CommandParseResult(
            type="command",
            command=command,
            args=args,
        )
```

---

## 五、消息显示

### 5.1 消息类型

```python
class MessageType(Enum):
    USER = "user"           # 用户消息
    ASSISTANT = "assistant" # 助手消息
    SYSTEM = "system"       # 系统消息
    TOOL = "tool"           # 工具调用
    ERROR = "error"         # 错误消息
```

### 5.2 消息格式化

```python
def format_message(message: Message) -> list[str]:
    """Format message for display."""
    if message.role == "user":
        return format_user_message(message)
    elif message.role == "assistant":
        return format_assistant_message(message)
    elif message.role == "tool":
        return format_tool_message(message)
    else:
        return format_system_message(message)
```

### 5.3 流式输出

```python
async def stream_response(
    self,
    events: AsyncIterator[LLMStreamEvent],
) -> None:
    """Stream LLM response to UI."""
    async for event in events:
        if event.type == "content_delta":
            self.append_to_current_message(event.delta)
        elif event.type == "tool_call_start":
            self.show_tool_call_start(event.tool_call)
        elif event.type == "tool_call_result":
            self.show_tool_call_result(event.tool_call, event.result)
        elif event.type == "turn_complete":
            self.finalize_message()
```

---

## 六、会话管理

### 6.1 会话状态

```python
@dataclass
class SessionState:
    """TUI session state."""

    session_id: str
    workspace_dir: Path
    messages: list[Message]
    model_binding: ModelBindingView | None
    active_run_id: str | None
    pending_approvals: list[ApprovalRequest]
```

### 6.2 会话操作

```python
class SessionOperations:
    """Session operations for TUI."""

    async def create_session(self, title: str | None) -> SessionState:
        """Create new session."""

    async def switch_session(self, session_id: str) -> SessionState:
        """Switch to existing session."""

    async def fork_session(self, session_id: str) -> SessionState:
        """Fork session."""

    async def delete_session(self, session_id: str) -> None:
        """Delete session."""

    async def compact_session(self) -> dict[str, Any]:
        """Compact session context."""
```

---

## 七、审批流程

### 7.1 审批请求处理

```python
async def handle_approval_request(
    self,
    request: ApprovalRequest,
) -> bool:
    """Handle approval request from agent."""
    # 显示审批提示
    self.show_approval_prompt(request)

    # 等待用户输入
    while True:
        key = await self.read_key()
        if key == "y":
            return True
        elif key == "n":
            return False
        elif key == "a":
            # 显示更多详情
            self.show_approval_details(request)
```

### 7.2 审批 UI

```
┌─────────────────────────────────────────────────────────────────┐
│ ⚠ Approval Required                                              │
├─────────────────────────────────────────────────────────────────┤
│ Tool: bash                                                       │
│ Command: rm -rf ./temp                                           │
│ Reason: Destructive operation                                    │
├─────────────────────────────────────────────────────────────────┤
│ [Y] Approve  [N] Deny  [A] Details  [E] Escalate                │
└─────────────────────────────────────────────────────────────────┘
```

---

## 八、本地运行时

### 8.1 本地 Agent 处理

```python
# src/mini_agent/tui/local_agent_runtime_handler.py

class LocalAgentRuntimeHandler:
    """Handle local agent execution for TUI."""

    def __init__(
        self,
        workspace_dir: Path,
        config: Config,
    ) -> None:
        self.workspace_dir = workspace_dir
        self.config = config

    async def create_agent(
        self,
        session_state: SessionState,
    ) -> Agent:
        """Create local agent instance."""
        return build_agent_kernel(
            AgentKernelBuildOptions(
                llm_client=self._create_llm_client(),
                system_prompt=self._build_system_prompt(),
                tools=self._load_tools(),
                workspace_dir=self.workspace_dir,
            )
        )

    async def run_turn(
        self,
        message: str,
        *,
        hooks: PlannerExecutorHooks | None = None,
    ) -> TurnExecutionResult:
        """Run one turn of the agent."""
```

---

## 九、文件位置

```
src/mini_agent/tui/
├── __init__.py
├── app.py                            # TUI 主应用
├── user_service_ports.py             # 本地端口适配
├── local_agent_runtime_handler.py    # 本地 Agent 处理
├── local_mcp_runtime_service.py      # 本地 MCP 服务
├── gateway_transport_binding.py      # Gateway 传输绑定
├── session_projection.py             # 会话投影
├── session_remote_projector.py       # 远程投影
├── session_remote_turn_stream_coordinator.py
├── session_turn_state_coordinator.py
├── session_turn_outcome_coordinator.py
├── session_model_command_coordinator.py
├── session_skill_command_coordinator.py
├── session_memory_command_coordinator.py
├── session_context_command_coordinator.py
├── session_mcp_command_coordinator.py
├── session_approval_command_coordinator.py
├── session_runtime_policy_command_coordinator.py
└── session_kb_command_coordinator.py
```

---

## 十、验收标准

- [x] 支持全屏终端界面
- [x] 支持流式输出
- [x] 支持命令模式
- [x] 支持键盘快捷键
- [x] 支持审批流程
- [x] 支持本地模式

---

## 十一、依赖关系

- 依赖: transport/, commands/, agent_core/
- 被依赖: 用户交互
