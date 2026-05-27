# UI 架构概述开发文档

**模块**: tui, desktop, transport
**优先级**: P0
**预估时间**: 已实现，文档补全

---

## 一、架构概述

Mini-Agent 用户界面采用**分层架构**设计：

```
┌─────────────────────────────────────────────────────────────────┐
│                        Surface Layer                             │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐              │
│  │    TUI      │  │  Desktop    │  │     CLI     │              │
│  │ (prompt_    │  │ (PySide6)   │  │   (Click)   │              │
│  │  toolkit)   │  │             │  │             │              │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘              │
└─────────┼────────────────┼────────────────┼─────────────────────┘
          │                │                │
          └────────────────┼────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Transport Layer                             │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                    GatewayClient                         │   │
│  │              (HTTP/WebSocket Transport)                  │   │
│  └─────────────────────────────────────────────────────────┘   │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  Remote Clients                                          │   │
│  │  - RemoteChatClient                                      │   │
│  │  - RemoteRunClient                                       │   │
│  │  - RemoteSessionClient                                   │   │
│  │  - RemoteMemoryClient                                    │   │
│  │  - RemoteModelCatalogClient                              │   │
│  │  - RemoteProviderClient                                  │   │
│  │  - RemoteWorkspaceClient                                 │   │
│  │  - RemoteSystemClient                                    │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                     Application Layer                            │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  User Services                                           │   │
│  │  - AgentUserService                                      │   │
│  │  - WorkspaceUserService                                  │   │
│  │  - ModelUserService                                      │   │
│  │  - CommandUserService                                    │   │
│  └─────────────────────────────────────────────────────────┘   │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  Application Services                                    │   │
│  │  - AgentApplicationService                               │   │
│  │  - RunControlApplicationService                          │   │
│  │  - SessionTaskService                                    │   │
│  │  - WorkspaceApplicationService                           │   │
│  │  - ModelBindingApplicationService                        │   │
│  │  - CommandApplicationService                             │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

---

## 二、界面类型

### 2.1 TUI (Terminal User Interface)

**技术栈**: prompt_toolkit

**特点**:
- 全屏终端界面
- 实时流式输出
- 键盘快捷键
- 命令模式 (/command)

**适用场景**:
- 开发者日常使用
- 远程服务器操作
- 快速交互

### 2.2 Desktop

**技术栈**: PySide6 (Qt)

**特点**:
- 图形化界面
- 多页面布局
- 鼠标交互
- 系统托盘

**适用场景**:
- 非技术用户
- 长时间会话
- 复杂操作

### 2.3 CLI (Command Line Interface)

**技术栈**: Click

**特点**:
- 单次命令执行
- 脚本集成
- 自动化任务

**适用场景**:
- CI/CD 集成
- 批处理任务
- 快速查询

---

## 三、运行模式

### 3.1 本地模式 (Local Mode)

```
┌─────────────┐
│     TUI     │
└──────┬──────┘
       │
       ▼
┌─────────────┐
│ Local Ports │
└──────┬──────┘
       │
       ▼
┌─────────────┐
│ Agent Core  │
└─────────────┘
```

**特点**:
- 直接访问 Agent Core
- 无需 Gateway
- 低延迟

### 3.2 远程模式 (Remote Mode)

```
┌─────────────┐
│  Desktop    │
└──────┬──────┘
       │
       ▼
┌─────────────┐
│GatewayClient│
└──────┬──────┘
       │ HTTP
       ▼
┌─────────────┐
│   Gateway   │
└──────┬──────┘
       │
       ▼
┌─────────────┐
│ Agent Core  │
└─────────────┘
```

**特点**:
- 通过 Gateway 访问
- 支持多客户端
- 需要网络连接

---

## 四、传输协议

### 4.1 HTTP REST

用于常规请求：

```
POST /api/chat          # 发送消息
GET  /api/sessions      # 列出会话
POST /api/sessions      # 创建会话
GET  /api/models        # 列出模型
POST /api/run/interrupt # 中断执行
```

### 4.2 Server-Sent Events (SSE)

用于流式响应：

```
GET /api/chat/stream    # 流式聊天响应
```

**事件类型**:
- `content_delta` - 内容增量
- `tool_call_start` - 工具调用开始
- `tool_call_result` - 工具调用结果
- `step_complete` - 步骤完成
- `turn_complete` - 回合完成

---

## 五、端口适配

### 5.1 本地端口适配

```python
class TuiLocalRunRuntimePort:
    """RunRuntimePort implementation for TUI local mode.

    Adapts RuntimeSessionRunControlStore to the RunRuntimePort protocol.
    """

    def __init__(
        self,
        run_control_store: RuntimeSessionRunControlStore | None = None,
        session_resolver: callable | None = None,
    ) -> None:
        self._store = run_control_store or RuntimeSessionRunControlStore()
        self._session_resolver = session_resolver

    async def get_run(self, run_id: str) -> Any: ...
    async def interrupt_run(self, run_id: str, *, reason, source) -> Any: ...
    async def resume_run(self, run_id: str, *, resume_token, source) -> Any: ...
    async def cancel_run(self, run_id: str, *, reason, source) -> Any: ...
```

### 5.2 远程端口适配

```python
class RemoteRunClient:
    """Remote client for run operations via Gateway."""

    def __init__(self, run_transport: GatewayClient) -> None:
        self._transport = run_transport

    async def get_run(self, run_id: str) -> Any: ...
    async def interrupt_run(self, run_id: str, *, reason, source) -> Any: ...
    async def resume_run(self, run_id: str, *, resume_token, source) -> Any: ...
    async def cancel_run(self, run_id: str, *, reason, source) -> Any: ...
```

---

## 六、会话协调器

### 6.1 协调器类型

| 协调器 | 职责 |
|--------|------|
| `SessionTurnStateCoordinator` | 回合状态管理 |
| `SessionTurnOutcomeCoordinator` | 回合结果处理 |
| `SessionModelCommandCoordinator` | 模型命令处理 |
| `SessionSkillCommandCoordinator` | 技能命令处理 |
| `SessionMemoryCommandCoordinator` | 记忆命令处理 |
| `SessionContextCommandCoordinator` | 上下文命令处理 |
| `SessionMcpCommandCoordinator` | MCP 命令处理 |
| `SessionApprovalCommandCoordinator` | 审批命令处理 |
| `SessionRuntimePolicyCommandCoordinator` | 运行时策略命令 |
| `SessionKbCommandCoordinator` | 知识库命令处理 |

### 6.2 协调器模式

```python
class SessionCommandCoordinator:
    """Base pattern for session command coordinators."""

    def __init__(
        self,
        session_state: MainAgentSessionState,
        transport_binding: TransportBinding,
    ) -> None:
        self._session = session_state
        self._transport = transport_binding

    async def execute(self, request: CommandRequest) -> CommandResult:
        """Execute command and return result."""
        pass
```

---

## 七、文件位置

```
src/mini_agent/
├── tui/
│   ├── app.py                    # TUI 主应用
│   ├── user_service_ports.py     # 本地端口适配
│   ├── gateway_transport_binding.py
│   └── session_*_coordinator.py  # 会话协调器
│
├── desktop/
│   ├── app.py                    # Desktop 启动
│   ├── window.py                 # 主窗口
│   ├── gateway_supervisor.py     # Gateway 监管
│   ├── gateway_transport_binding.py
│   └── session_actions.py        # 会话操作
│
├── transport/
│   ├── gateway_client.py         # Gateway 客户端
│   ├── gateway_error.py          # 错误处理
│   └── remote_*_client.py        # 远程客户端
│
└── commands/
    ├── cli.py                    # CLI 入口
    ├── parser.py                 # 命令解析
    └── execution.py              # 命令执行
```

---

## 八、验收标准

- [x] TUI 支持本地模式
- [x] Desktop 支持远程模式
- [x] 传输层支持 HTTP 和 SSE
- [x] 支持多种会话协调器

---

## 九、依赖关系

- 依赖: application/, agent_core/
- 被依赖: 用户交互
