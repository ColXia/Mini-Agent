# 端口定义开发文档

**模块**: application/ports
**优先级**: P0
**预估时间**: 已实现，文档补全

---

## 一、功能概述

端口层定义 Application 层与 Runtime 层的接口契约：

- 所有 Port 定义为 `Protocol`
- 遵循依赖倒置原则
- 最小必要接口

---

## 二、端口总览

| 端口 | 职责 | 文件 |
|------|------|------|
| `AgentRuntimePort` | Agent 运行时查询 | agent_runtime_port.py |
| `RunRuntimePort` | Run 控制流管理 | run_runtime_port.py |
| `WorkspaceRuntimePort` | Workspace 查询与切换 | workspace_runtime_port.py |
| `ModelRuntimePort` | Model 绑定与能力查询 | model_runtime_port.py |
| `SessionAgentRuntimePort` | Session 级别 Agent 操作 | session_agent_runtime_port.py |
| `SessionTaskPort` | Session 到 Run 的映射 | session_task_port.py |
| `SessionTaskRuntimePort` | Session 任务运行时管理 | session_task_runtime_port.py |

---

## 三、端口定义

### 3.1 AgentRuntimePort

```python
# src/mini_agent/application/ports/agent_runtime_port.py

class AgentRuntimePort(Protocol):
    """Application-facing contract for agent runtime queries."""

    async def list_agents(self) -> Any:
        """List all agents."""
        ...

    async def get_agent(self, agent_id: str) -> Any:
        """Get agent by ID."""
        ...

    async def get_active_agent(self) -> Any:
        """Get currently active agent."""
        ...
```

### 3.2 RunRuntimePort

```python
# src/mini_agent/application/ports/run_runtime_port.py

class RunRuntimePort(Protocol):
    """Application-facing contract for active run queries and control."""

    async def get_run(self, run_id: str) -> Any:
        """Get run by ID."""
        ...

    async def interrupt_run(
        self,
        run_id: str,
        *,
        reason: str | None = None,
        source: str | None = None,
    ) -> Any:
        """Request interrupt for running task."""
        ...

    async def resume_run(
        self,
        run_id: str,
        *,
        resume_token: str | None = None,
        source: str | None = None,
    ) -> Any:
        """Request resume for paused task."""
        ...

    async def cancel_run(
        self,
        run_id: str,
        *,
        reason: str | None = None,
        source: str | None = None,
    ) -> Any:
        """Request cancel for running task."""
        ...

    async def resolve_approval_wait(
        self,
        run_id: str,
        *,
        approved: bool,
        token: str | None = None,
        source: str | None = None,
        reason: str | None = None,
    ) -> Any:
        """Resolve pending approval request."""
        ...
```

### 3.3 WorkspaceRuntimePort

```python
# src/mini_agent/application/ports/workspace_runtime_port.py

class WorkspaceRuntimePort(Protocol):
    """Application-facing contract for workspace queries."""

    async def get_workspace(self, workspace_id: str) -> Any:
        """Get workspace by ID."""
        ...

    async def list_workspaces(self) -> Any:
        """List all workspaces."""
        ...

    async def switch_workspace(self, workspace_id: str) -> Any:
        """Switch to different workspace."""
        ...
```

### 3.4 ModelRuntimePort

```python
# src/mini_agent/application/ports/model_runtime_port.py

class ModelRuntimePort(Protocol):
    """Application-facing contract for agent model selection and capability views."""

    async def list_model_bindings(self) -> Any:
        """List all model bindings."""
        ...

    async def get_model_binding(self, agent_id: str | None) -> Any:
        """Get model binding for agent."""
        ...

    async def update_model_binding(
        self,
        *,
        agent_id: str,
        provider_source: str,
        provider_id: str,
        model_id: str,
    ) -> Any:
        """Update model binding for agent."""
        ...

    async def list_model_capabilities(self, agent_id: str | None) -> Any:
        """List model capabilities for agent."""
        ...

    async def get_model_binding_diagnostics(self, agent_id: str | None) -> Any:
        """Get model binding diagnostics."""
        ...
```

### 3.5 SessionTaskPort

```python
# src/mini_agent/application/ports/session_task_port.py

class SessionTaskPort(Protocol):
    """Resolve run ownership from session task state."""

    async def resolve_run_id_for_session(self, session_id: str) -> str | None:
        """Resolve run ID for session."""
        ...
```

### 3.6 SessionTaskRuntimePort

```python
# src/mini_agent/application/ports/session_task_runtime_port.py

class SessionTaskRuntimePort(Protocol):
    """Session task runtime management."""

    async def list_sessions(self, *, workspace_dir: str, shared_only: bool) -> Any:
        """List sessions."""
        ...

    async def create_session(self, *, workspace_dir: str, title: str | None) -> Any:
        """Create new session."""
        ...

    async def get_session(self, session_id: str) -> Any:
        """Get session by ID."""
        ...

    async def delete_session(self, session_id: str) -> Any:
        """Delete session."""
        ...
```

---

## 四、端口适配器

### 4.1 本地适配器

```python
# TUI 本地模式适配
class TuiLocalRunRuntimePort:
    """RunRuntimePort implementation for TUI local mode."""

    def __init__(
        self,
        run_control_store: RuntimeSessionRunControlStore,
    ) -> None:
        self._store = run_control_store

    async def get_run(self, run_id: str) -> Any: ...
    async def interrupt_run(self, run_id: str, ...) -> Any: ...
    async def resume_run(self, run_id: str, ...) -> Any: ...
    async def cancel_run(self, run_id: str, ...) -> Any: ...
```

### 4.2 远程适配器

```python
# Desktop 远程模式适配
class RemoteRunClient:
    """RunRuntimePort implementation via Gateway."""

    def __init__(self, run_transport: GatewayClient) -> None:
        self._transport = run_transport

    async def get_run(self, run_id: str) -> Any: ...
    async def interrupt_run(self, run_id: str, ...) -> Any: ...
    async def resume_run(self, run_id: str, ...) -> Any: ...
    async def cancel_run(self, run_id: str, ...) -> Any: ...
```

---

## 五、端口使用示例

```python
# 在 Application Service 中使用 Port
@dataclass(slots=True)
class RunControlApplicationService:
    """Resolve user control actions against run truth."""

    run_runtime: RunRuntimePort
    session_run_lookup: SessionTaskPort | None = None

    async def interrupt_run(
        self,
        run_id: str,
        *,
        reason: str | None = None,
        source: str | None = None,
    ) -> Any:
        return await self.run_runtime.interrupt_run(
            run_id,
            reason=reason,
            source=source,
        )

    async def interrupt_session_run(
        self,
        session_id: str,
        *,
        reason: str | None = None,
        source: str | None = None,
    ) -> Any:
        run_id = await self._require_run_id(session_id)
        return await self.interrupt_run(run_id, reason=reason, source=source)
```

---

## 六、文件位置

```
src/mini_agent/application/ports/
├── __init__.py
├── agent_runtime_port.py
├── run_runtime_port.py
├── workspace_runtime_port.py
├── model_runtime_port.py
├── session_agent_runtime_port.py
├── session_task_port.py
└── session_task_runtime_port.py
```

---

## 七、验收标准

- [x] 所有 Port 定义为 Protocol
- [x] Port 接口最小化
- [x] 支持本地和远程适配

---

## 八、依赖关系

- 无前置依赖
- 被依赖: use_cases/, user_services/
