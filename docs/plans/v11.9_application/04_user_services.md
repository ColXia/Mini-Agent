# 用户服务开发文档

**模块**: application/user_services
**优先级**: P0
**预估时间**: 已实现，文档补全

---

## 一、功能概述

用户服务层负责对外暴露：

- 服务门面
- 服务组装
- 延迟初始化

---

## 二、用户服务总览

| 服务 | 职责 |
|------|------|
| `AgentUserService` | Agent 用户服务门面 |
| `WorkspaceUserService` | Workspace 用户服务门面 |
| `ModelUserService` | Model 用户服务门面 |
| `CommandUserService` | Command 用户服务门面 |

---

## 三、服务组装

### 3.1 UserServiceAssembly

```python
# src/mini_agent/application/user_services/service_assembly.py

@dataclass(frozen=True, slots=True)
class UserServiceAssembly:
    """Explicit Stage 3 assembly of user services."""

    session_task_service: SessionTaskService
    run_control_service: RunControlApplicationService
    agent_service: AgentUserService
    model_service: ModelUserService
    workspace_service: WorkspaceUserService | None = None
    command_service: CommandUserService | None = None


def assemble_typed_user_services(
    *,
    session_task_runtime: SessionTaskRuntimePort | None = None,
    run_runtime: RunRuntimePort | None = None,
    session_agent_runtime: SessionAgentRuntimePort | None = None,
    workspace_runtime: WorkspaceRuntimePort | None = None,
    model_runtime: ModelRuntimePort | None = None,
    workspace_service: WorkspaceUserService | None = None,
    command_service: CommandUserService | None = None,
) -> UserServiceAssembly:
    """Assemble user services with explicit runtime bindings."""
    # 1. 创建 SessionTaskService
    session_task_service = SessionTaskService(
        session_task_runtime=session_task_runtime,
    )

    # 2. 创建 RunControlApplicationService
    run_control_service = RunControlApplicationService(
        run_runtime=run_runtime,
        session_run_lookup=session_task_runtime,
    )

    # 3. 创建 AgentUserService
    agent_service = AgentUserService(
        session_agent_runtime=session_agent_runtime,
        run_control_service=run_control_service,
    )

    # 4. 创建 ModelUserService
    model_service = ModelUserService(
        model_runtime=model_runtime,
    )

    # 5. 组装
    return UserServiceAssembly(
        session_task_service=session_task_service,
        run_control_service=run_control_service,
        agent_service=agent_service,
        model_service=model_service,
        workspace_service=workspace_service,
        command_service=command_service,
    )
```

---

## 四、用户服务实现

### 4.1 AgentUserService

```python
# src/mini_agent/application/user_services/agent_user_service.py

@dataclass(slots=True)
class AgentUserService:
    """User-facing agent service facade."""

    session_agent_runtime: SessionAgentRuntimePort
    run_control_service: RunControlApplicationService | None = None

    async def list_agents(self) -> Any:
        """List all agents."""
        return await self.session_agent_runtime.list_agents()

    async def get_agent(self, agent_id: str) -> Any:
        """Get agent by ID."""
        return await self.session_agent_runtime.get_agent(agent_id)

    async def get_active_agent(self) -> Any:
        """Get active agent."""
        return await self.session_agent_runtime.get_active_agent()

    async def interrupt_run(
        self,
        run_id: str,
        *,
        reason: str | None = None,
        source: str | None = None,
    ) -> Any:
        """Interrupt running task."""
        if self.run_control_service:
            return await self.run_control_service.interrupt_run(
                run_id,
                reason=reason,
                source=source,
            )

    async def cancel_run(
        self,
        run_id: str,
        *,
        reason: str | None = None,
        source: str | None = None,
    ) -> Any:
        """Cancel running task."""
        if self.run_control_service:
            return await self.run_control_service.cancel_run(
                run_id,
                reason=reason,
                source=source,
            )
```

### 4.2 WorkspaceUserService

```python
# src/mini_agent/application/user_services/workspace_user_service.py

@dataclass(slots=True)
class WorkspaceUserService:
    """User-facing workspace service facade."""

    workspace_runtime: WorkspaceRuntimePort

    async def get_workspace(self, workspace_id: str) -> Any:
        """Get workspace by ID."""
        return await self.workspace_runtime.get_workspace(workspace_id)

    async def list_workspaces(self) -> Any:
        """List all workspaces."""
        return await self.workspace_runtime.list_workspaces()

    async def switch_workspace(self, workspace_id: str) -> Any:
        """Switch to different workspace."""
        return await self.workspace_runtime.switch_workspace(workspace_id)
```

### 4.3 ModelUserService

```python
# src/mini_agent/application/user_services/model_user_service.py

@dataclass(slots=True)
class ModelUserService:
    """User-facing model service facade."""

    model_runtime: ModelRuntimePort

    async def list_model_bindings(self) -> Any:
        """List all model bindings."""
        return await self.model_runtime.list_model_bindings()

    async def get_model_binding(self, agent_id: str | None) -> Any:
        """Get model binding for agent."""
        return await self.model_runtime.get_model_binding(agent_id)

    async def update_model_binding(
        self,
        *,
        agent_id: str,
        provider_source: str,
        provider_id: str,
        model_id: str,
    ) -> Any:
        """Update model binding."""
        return await self.model_runtime.update_model_binding(
            agent_id=agent_id,
            provider_source=provider_source,
            provider_id=provider_id,
            model_id=model_id,
        )

    async def list_model_capabilities(self, agent_id: str | None) -> Any:
        """List model capabilities."""
        return await self.model_runtime.list_model_capabilities(agent_id)
```

### 4.4 CommandUserService

```python
# src/mini_agent/application/user_services/command_user_service.py

@dataclass(slots=True)
class CommandUserService:
    """User-facing command service facade."""

    command_application_service: CommandApplicationService | None = None

    async def discover_commands(self) -> Any:
        """Discover available commands."""
        if self.command_application_service:
            return await self.command_application_service.discover_commands()

    async def get_command_description(self, command: str) -> Any:
        """Get command description."""
        if self.command_application_service:
            return await self.command_application_service.get_command_description(command)

    async def get_command_completions(self, prefix: str) -> Any:
        """Get command completions."""
        if self.command_application_service:
            return await self.command_application_service.get_command_completions(prefix)
```

---

## 五、服务依赖图

```
┌─────────────────────────────────────────────────────────────────┐
│                    UserServiceAssembly                           │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐ │
│  │ AgentUserService │  │ModelUserService │  │WorkspaceUserSvc │ │
│  └────────┬────────┘  └────────┬────────┘  └────────┬────────┘ │
│           │                    │                    │          │
│           │                    │                    │          │
│           ▼                    ▼                    ▼          │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐ │
│  │RunControlAppSvc │  │ ModelRuntimePort│  │WorkspaceRuntime │ │
│  └────────┬────────┘  └─────────────────┘  │     Port        │ │
│           │                                 └─────────────────┘ │
│           ▼                                                       │
│  ┌─────────────────┐                                             │
│  │  RunRuntimePort │                                             │
│  └─────────────────┘                                             │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                SessionTaskService                        │   │
│  │  ┌─────────────────────────────────────────────────┐   │   │
│  │  │           SessionTaskRuntimePort                 │   │   │
│  │  └─────────────────────────────────────────────────┘   │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## 六、文件位置

```
src/mini_agent/application/user_services/
├── __init__.py
├── agent_user_service.py
├── workspace_user_service.py
├── model_user_service.py
├── command_user_service.py
├── model_runtime_adapter.py
└── service_assembly.py
```

---

## 七、验收标准

- [x] 支持服务组装
- [x] 支持延迟初始化
- [x] 支持依赖注入

---

## 八、依赖关系

- 依赖: ports/, use_cases/
- 被依赖: tui/, desktop/, gateway/