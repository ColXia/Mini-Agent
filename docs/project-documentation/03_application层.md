# Mini-Agent Application 层

## 1. 模块概述

Application 层采用**六边形架构**设计，遵循**依赖倒置原则**。所有 Port 都定义为 `Protocol`，确保接口契约与实现解耦。

### 1.1 目录结构

```
application/
├── ports/              # 端口层 - 运行时接口协议
│   ├── agent_runtime_port.py
│   ├── run_runtime_port.py
│   ├── workspace_runtime_port.py
│   ├── model_runtime_port.py
│   ├── session_agent_runtime_port.py
│   ├── session_task_port.py
│   └── session_task_runtime_port.py
│
├── use_cases/          # 用例层 - 业务逻辑编排
│   ├── command_application_service.py
│   ├── workspace_application_service.py
│   ├── agent_application_service.py
│   ├── model_binding_application_service.py
│   ├── run_control_application_service.py
│   ├── session_task_service.py
│   └── ...
│
├── facades/            # 门面层 - 复杂流程编排
│   ├── surface_chat_flow_handler.py
│   ├── agent_turn_execution_handler.py
│   ├── agent_route_execution_handler.py
│   └── agent_delegation_execution_handler.py
│
├── user_services/      # 用户服务层 - 对外暴露
│   ├── workspace_user_service.py
│   ├── command_user_service.py
│   ├── agent_user_service.py
│   ├── model_user_service.py
│   └── service_assembly.py
│
└── support/            # 支撑层
    ├── interaction_request_adapter.py
    └── managed_session_turn.py
```

---

## 2. Ports (端口定义)

### 2.1 端口总览

| 端口 | 职责 |
|------|------|
| `AgentRuntimePort` | Agent 运行时查询 |
| `RunRuntimePort` | Run 控制流管理 |
| `WorkspaceRuntimePort` | Workspace 查询与切换 |
| `ModelRuntimePort` | Model 绑定与能力查询 |
| `SessionAgentRuntimePort` | Session 级别 Agent 操作 |
| `SessionTaskPort` | Session 到 Run 的映射 |
| `SessionTaskRuntimePort` | Session 任务运行时管理 |

### 2.2 核心端口定义

#### AgentRuntimePort

```python
class AgentRuntimePort(Protocol):
    """Application-facing contract for agent runtime queries."""

    async def list_agents(self) -> Any: ...
    async def get_agent(self, agent_id: str) -> Any: ...
    async def get_active_agent(self) -> Any: ...
```

#### RunRuntimePort

```python
class RunRuntimePort(Protocol):
    """Application-facing contract for active run queries and control."""

    async def get_run(self, run_id: str) -> Any: ...
    async def interrupt_run(self, run_id: str, *, reason: str | None, source: str | None) -> Any: ...
    async def resume_run(self, run_id: str, *, resume_token: str | None, source: str | None) -> Any: ...
    async def cancel_run(self, run_id: str, *, reason: str | None, source: str | None) -> Any: ...
    async def resolve_approval_wait(self, run_id: str, *, approved: bool, token: str | None, ...) -> Any: ...
```

#### ModelRuntimePort

```python
class ModelRuntimePort(Protocol):
    """Application-facing contract for agent model selection and capability views."""

    async def list_model_bindings(self) -> Any: ...
    async def get_model_binding(self, agent_id: str | None) -> Any: ...
    async def update_model_binding(self, *, agent_id, provider_source, provider_id, model_id) -> Any: ...
    async def list_model_capabilities(self, agent_id: str | None) -> Any: ...
    async def get_model_binding_diagnostics(self, agent_id: str | None) -> Any: ...
```

---

## 3. Use Cases (用例服务)

### 3.1 用例服务总览

| 服务 | 职责 |
|------|------|
| `CommandApplicationService` | 命令发现、描述、补全、分发 |
| `WorkspaceApplicationService` | Workspace 查询与切换 |
| `AgentApplicationService` | Agent 综合服务 + Run 控制 |
| `ModelBindingApplicationService` | Model 绑定管理 |
| `RunControlApplicationService` | Run 控制专用服务 |
| `SessionTaskService` | Session 任务管理核心 |

### 3.2 核心用例定义

#### AgentApplicationService

```python
@dataclass(slots=True)
class AgentApplicationService:
    """Owns agent-facing application logic above runtime ports and control services."""

    agent_runtime: AgentRuntimePort | None = None
    run_control: RunControlApplicationService | None = None
    interaction_service: AgentInteractionApplicationService | None = None

    async def list_agents(self) -> Any: ...
    async def get_agent(self, agent_id: str) -> Any: ...
    async def get_active_agent(self) -> Any: ...
    async def submit_message(self, request: MainAgentChatRequest) -> MainAgentChatResponse: ...
    async def interrupt_run(self, run_id: str, *, reason, source) -> Any: ...
    async def resume_run(self, run_id: str, *, resume_token, source) -> Any: ...
    async def cancel_run(self, run_id: str, *, reason, source) -> Any: ...
```

#### SessionTaskService

```python
class SessionTaskService:
    """Owns session/task application behavior during the v11.1 transition."""

    async def list_sessions(self, *, workspace_dir, shared_only) -> list[MainAgentSessionSummary]: ...
    async def create_session(self, request, *, workspace_dir) -> MainAgentSessionDetail: ...
    async def ensure_default_session(self, request, *, workspace_dir) -> MainAgentSessionDetail: ...
    async def get_session_detail(self, session_id: str, *, recent_limit) -> MainAgentSessionDetail: ...
    async def delete_session(self, session_id: str) -> MainAgentSessionMutationResponse: ...
    async def prepare_chat_turn(self, *, workspace_dir, message, ...) -> ManagedSessionTurn: ...
```

---

## 4. Facades (门面服务)

### 4.1 SurfaceChatFlowHandler

```python
@dataclass(slots=True)
class SurfaceChatFlowHandler:
    """Surface-neutral chat-turn orchestration."""

    async def run_chat(self, request, *, execute_turn) -> MainAgentChatResponse: ...
    async def stream_chat_events(self, request, *, execute_turn) -> AsyncIterator[str]: ...
```

### 4.2 AgentTurnExecutionHandler

```python
@dataclass(slots=True)
class AgentTurnExecutionHandler:
    """Owns single-turn agent execution plus runtime approval/activity hooks."""

    async def run_agent_once(self, turn: ManagedSessionTurn, request) -> TurnExecutionResult: ...
```

### 4.3 AgentRouteExecutionHandler

```python
class AgentRouteExecutionHandler:
    """Owns route resolution, route diagnostics, and route-to-executor dispatch."""

    async def get_routing_diagnostics(self) -> MainAgentRoutingDiagnostics: ...
    async def execute_chat_turn(self, turn, request, ...) -> SurfaceChatExecutionResult: ...
```

---

## 5. User Services (用户服务)

### 5.1 服务总览

| 服务 | 职责 |
|------|------|
| `WorkspaceUserService` | Workspace 用户服务门面 |
| `CommandUserService` | Command 用户服务门面 |
| `AgentUserService` | Agent 用户服务门面 |
| `ModelUserService` | Model 用户服务门面 |

### 5.2 服务组装

```python
@dataclass(frozen=True, slots=True)
class UserServiceAssembly:
    """Explicit Stage 3 assembly of user services."""
    session_task_service: SessionTaskService
    run_control_service: RunControlApplicationService
    agent_service: AgentUserService
    model_service: ModelUserService
    workspace_service: WorkspaceUserService | None = None
    command_service: CommandUserService | None = None

def assemble_typed_user_services(...) -> UserServiceAssembly: ...
```

---

## 6. 依赖关系

```
┌─────────────────────────────────────────────────────────────┐
│                      User Services Layer                     │
│  (WorkspaceUserService, AgentUserService, ModelUserService)  │
└─────────────────────────────┬───────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                      Use Cases Layer                         │
│  (WorkspaceApplicationService, AgentApplicationService,     │
│   SessionTaskService, RunControlApplicationService)         │
└─────────────────────────────┬───────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                        Ports Layer                           │
│  (WorkspaceRuntimePort, AgentRuntimePort, RunRuntimePort,   │
│   SessionTaskRuntimePort, ModelRuntimePort)                 │
└─────────────────────────────────────────────────────────────┘
```

---

## 7. 设计原则

1. **依赖倒置**: 上层依赖 Port 协议，而非具体实现
2. **单一职责**: 每个服务专注于单一领域
3. **开闭原则**: 通过 Port 扩展，不修改现有代码
4. **接口隔离**: Port 定义最小必要接口
5. **延迟初始化**: User Service 支持按需创建 Application Service
