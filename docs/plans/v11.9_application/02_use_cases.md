# 用例服务开发文档

**模块**: application/use_cases
**优先级**: P0
**预估时间**: 已实现，文档补全

---

## 一、功能概述

用例层负责业务逻辑编排：

- 组合多个 Port 完成业务操作
- 实现应用级事务
- 协调领域对象

---

## 二、用例服务总览

| 服务 | 职责 |
|------|------|
| `AgentApplicationService` | Agent 综合服务 + Run 控制 |
| `RunControlApplicationService` | Run 控制专用服务 |
| `SessionTaskService` | Session 任务管理核心 |
| `WorkspaceApplicationService` | Workspace 查询与切换 |
| `ModelBindingApplicationService` | Model 绑定管理 |
| `CommandApplicationService` | 命令发现、描述、补全、分发 |
| `AgentInteractionApplicationService` | Agent 交互服务 |

---

## 三、核心用例实现

### 3.1 AgentApplicationService

```python
# src/mini_agent/application/use_cases/agent_application_service.py

@dataclass(slots=True)
class AgentApplicationService:
    """Owns agent-facing application logic above runtime ports and control services."""

    agent_runtime: AgentRuntimePort | None = None
    run_control: RunControlApplicationService | None = None
    interaction_service: AgentInteractionApplicationService | None = None

    # === Agent 查询 ===

    async def list_agents(self) -> Any:
        """List all agents."""
        return await self.agent_runtime.list_agents()

    async def get_agent(self, agent_id: str) -> Any:
        """Get agent by ID."""
        return await self.agent_runtime.get_agent(agent_id)

    async def get_active_agent(self) -> Any:
        """Get currently active agent."""
        return await self.agent_runtime.get_active_agent()

    # === 消息提交 ===

    async def submit_message(self, request: MainAgentChatRequest) -> MainAgentChatResponse:
        """Submit chat message."""
        return await self.interaction_service.submit_message(request)

    def stream_message(self, **kwargs: Any) -> AsyncIterator[str]:
        """Stream chat response."""
        return self.interaction_service.stream_message(**kwargs)

    # === Run 控制 ===

    async def get_run(self, run_id: str) -> Any:
        """Get run by ID."""
        return await self.run_control.get_run(run_id)

    async def interrupt_run(
        self,
        run_id: str,
        *,
        reason: str | None = None,
        source: str | None = None,
    ) -> Any:
        """Interrupt running task."""
        return await self.run_control.interrupt_run(run_id, reason=reason, source=source)

    async def resume_run(
        self,
        run_id: str,
        *,
        resume_token: str | None = None,
        source: str | None = None,
    ) -> Any:
        """Resume paused task."""
        return await self.run_control.resume_run(run_id, resume_token=resume_token, source=source)

    async def cancel_run(
        self,
        run_id: str,
        *,
        reason: str | None = None,
        source: str | None = None,
    ) -> Any:
        """Cancel running task."""
        return await self.run_control.cancel_run(run_id, reason=reason, source=source)

    # === 审批 ===

    async def approve_wait(
        self,
        run_id: str,
        *,
        token: str | None = None,
        source: str | None = None,
        reason: str | None = None,
    ) -> Any:
        """Approve pending wait."""
        return await self.run_control.approve_wait(run_id, token=token, source=source, reason=reason)

    async def deny_wait(
        self,
        run_id: str,
        *,
        token: str | None = None,
        source: str | None = None,
        reason: str | None = None,
    ) -> Any:
        """Deny pending wait."""
        return await self.run_control.deny_wait(run_id, token=token, source=source, reason=reason)
```

### 3.2 RunControlApplicationService

```python
# src/mini_agent/application/use_cases/run_control_application_service.py

@dataclass(slots=True)
class RunControlApplicationService:
    """Resolve user control actions against run truth."""

    run_runtime: RunRuntimePort
    session_run_lookup: SessionTaskPort | None = None

    async def get_run(self, run_id: str) -> Any:
        """Get run by ID."""
        return await self.run_runtime.get_run(run_id)

    async def interrupt_run(
        self,
        run_id: str,
        *,
        reason: str | None = None,
        source: str | None = None,
    ) -> Any:
        """Interrupt running task."""
        return await self.run_runtime.interrupt_run(run_id, reason=reason, source=source)

    async def resume_run(
        self,
        run_id: str,
        *,
        resume_token: str | None = None,
        source: str | None = None,
    ) -> Any:
        """Resume paused task."""
        return await self.run_runtime.resume_run(run_id, resume_token=resume_token, source=source)

    async def cancel_run(
        self,
        run_id: str,
        *,
        reason: str | None = None,
        source: str | None = None,
    ) -> Any:
        """Cancel running task."""
        return await self.run_runtime.cancel_run(run_id, reason=reason, source=source)

    async def approve_wait(
        self,
        run_id: str,
        *,
        token: str | None = None,
        source: str | None = None,
        reason: str | None = None,
    ) -> Any:
        """Approve pending wait."""
        return await self.run_runtime.resolve_approval_wait(
            run_id,
            approved=True,
            token=token,
            source=source,
            reason=reason,
        )

    async def deny_wait(
        self,
        run_id: str,
        *,
        token: str | None = None,
        source: str | None = None,
        reason: str | None = None,
    ) -> Any:
        """Deny pending wait."""
        return await self.run_runtime.resolve_approval_wait(
            run_id,
            approved=False,
            token=token,
            source=source,
            reason=reason,
        )

    # === Session 级别操作 ===

    async def interrupt_session_run(
        self,
        session_id: str,
        *,
        reason: str | None = None,
        source: str | None = None,
    ) -> Any:
        """Interrupt session's running task."""
        run_id = await self._require_run_id(session_id)
        return await self.interrupt_run(run_id, reason=reason, source=source)

    async def resume_session_run(
        self,
        session_id: str,
        *,
        resume_token: str | None = None,
        source: str | None = None,
    ) -> Any:
        """Resume session's paused task."""
        run_id = await self._require_run_id(session_id)
        return await self.resume_run(run_id, resume_token=resume_token, source=source)

    async def cancel_session_run(
        self,
        session_id: str,
        *,
        reason: str | None = None,
        source: str | None = None,
    ) -> Any:
        """Cancel session's running task."""
        run_id = await self._require_run_id(session_id)
        return await self.cancel_run(run_id, reason=reason, source=source)
```

### 3.3 SessionTaskService

```python
# src/mini_agent/application/use_cases/session_task_service.py

class SessionTaskService:
    """Owns session/task application behavior during the v11.1 transition."""

    async def list_sessions(
        self,
        *,
        workspace_dir: Path,
        shared_only: bool = False,
    ) -> list[MainAgentSessionSummary]:
        """List sessions in workspace."""
        ...

    async def create_session(
        self,
        request: MainAgentSessionCreateRequest,
        *,
        workspace_dir: Path,
    ) -> MainAgentSessionDetail:
        """Create new session."""
        ...

    async def ensure_default_session(
        self,
        request: MainAgentDefaultSessionRequest,
        *,
        workspace_dir: Path,
    ) -> MainAgentSessionDetail:
        """Ensure default session exists."""
        ...

    async def get_session_detail(
        self,
        session_id: str,
        *,
        recent_limit: int = 50,
    ) -> MainAgentSessionDetail:
        """Get session details."""
        ...

    async def delete_session(
        self,
        session_id: str,
    ) -> MainAgentSessionMutationResponse:
        """Delete session."""
        ...

    async def prepare_chat_turn(
        self,
        *,
        workspace_dir: Path,
        message: str,
        session_id: str | None = None,
        ...
    ) -> ManagedSessionTurn:
        """Prepare chat turn for execution."""
        ...
```

---

## 四、用例服务组合

```
┌─────────────────────────────────────────────────────────────────┐
│                    AgentApplicationService                       │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                    组合关系                              │   │
│  │  - AgentRuntimePort (查询)                              │   │
│  │  - RunControlApplicationService (控制)                  │   │
│  │  - AgentInteractionApplicationService (交互)            │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                RunControlApplicationService                      │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                    组合关系                              │   │
│  │  - RunRuntimePort (Run 控制)                            │   │
│  │  - SessionTaskPort (Session → Run 映射)                 │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                    SessionTaskService                            │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                    组合关系                              │   │
│  │  - SessionTaskRuntimePort (Session 管理)                │   │
│  │  - WorkspaceRuntimePort (Workspace 查询)                │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

---

## 五、文件位置

```
src/mini_agent/application/use_cases/
├── __init__.py
├── agent_application_service.py
├── run_control_application_service.py
├── session_task_service.py
├── workspace_application_service.py
├── model_binding_application_service.py
├── command_application_service.py
├── agent_interaction_application_service.py
├── operations_path_policy.py
├── operations_memory_use_cases.py
├── operations_provider_use_cases.py
└── channel_ingress_use_cases.py
```

---

## 六、验收标准

- [x] 用例服务组合多个 Port
- [x] 实现业务逻辑编排
- [x] 支持依赖注入

---

## 七、依赖关系

- 依赖: ports/
- 被依赖: user_services/, facades/
