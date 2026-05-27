# 会话协调器开发文档

**模块**: tui/session_coordinators
**优先级**: P0
**预估时间**: 已实现，文档补全

---

## 一、功能概述

会话协调器负责：

- 命令分发
- 状态同步
- UI 更新

---

## 二、协调器列表

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

---

## 三、协调器模式

### 3.1 基础模式

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
        try:
            result = await self._do_execute(request)
            return CommandResult(success=True, data=result)
        except Exception as e:
            return CommandResult(success=False, error=str(e))

    async def _do_execute(self, request: CommandRequest) -> Any:
        """Actual implementation."""
        raise NotImplementedError
```

### 3.2 协调器注册

```python
class SessionCoordinatorRegistry:
    """Registry for session coordinators."""

    def __init__(self) -> None:
        self._coordinators: dict[str, type[SessionCommandCoordinator]] = {}

    def register(
        self,
        command: str,
        coordinator_class: type[SessionCommandCoordinator],
    ) -> None:
        self._coordinators[command] = coordinator_class

    def get(
        self,
        command: str,
    ) -> type[SessionCommandCoordinator] | None:
        return self._coordinators.get(command)
```

---

## 四、回合状态协调器

### 4.1 SessionTurnStateCoordinator

```python
class SessionTurnStateCoordinator:
    """Manage turn state for TUI session."""

    def __init__(
        self,
        session_state: MainAgentSessionState,
        run_control_store: RuntimeSessionRunControlStore,
    ) -> None:
        self._session = session_state
        self._run_control_store = run_control_store

    async def get_turn_state(self) -> TurnState:
        """Get current turn state."""
        return TurnState(
            session_id=self._session.session_id,
            is_running=self._session.is_running,
            pending_approvals=self._session.pending_approvals,
        )

    async def request_interrupt(self, *, reason: str | None) -> None:
        """Request interrupt for current turn."""
        self._run_control_store.request_interrupt(
            self._session,
            source="tui",
            reason=reason,
        )

    async def request_cancel(self, *, reason: str | None) -> None:
        """Request cancel for current turn."""
        self._run_control_store.request_cancel(
            self._session,
            source="tui",
            reason=reason,
        )
```

### 4.2 回合状态

```python
@dataclass
class TurnState:
    """Current turn state."""

    session_id: str
    is_running: bool
    pending_approvals: list[ApprovalRequest]
    can_interrupt: bool = False
    can_cancel: bool = False
    can_resume: bool = False
```

---

## 五、模型命令协调器

### 5.1 SessionModelCommandCoordinator

```python
class SessionModelCommandCoordinator:
    """Handle model commands for TUI session."""

    async def list_models(self) -> list[ModelOptionView]:
        """List available models."""
        return await self._transport.model_client.list_models()

    async def get_current_binding(self) -> ModelBindingView:
        """Get current model binding."""
        return await self._transport.model_client.get_binding(
            agent_id=self._session.agent_id,
        )

    async def switch_model(
        self,
        *,
        model_id: str,
        provider_id: str | None = None,
    ) -> ModelBindingView:
        """Switch to different model."""
        return await self._transport.model_client.update_binding(
            agent_id=self._session.agent_id,
            model_id=model_id,
            provider_id=provider_id,
        )

    async def probe_capabilities(
        self,
        *,
        model_id: str,
        provider_id: str,
    ) -> ModelCapabilitiesView:
        """Probe model capabilities."""
        return await self._transport.model_client.probe_capabilities(
            model_id=model_id,
            provider_id=provider_id,
        )
```

---

## 六、技能命令协调器

### 6.1 SessionSkillCommandCoordinator

```python
class SessionSkillCommandCoordinator:
    """Handle skill commands for TUI session."""

    async def list_skills(
        self,
        *,
        eligible_only: bool = False,
    ) -> list[SkillView]:
        """List available skills."""
        return await self._transport.skill_client.list_skills(
            eligible_only=eligible_only,
        )

    async def get_skill(self, skill_name: str) -> SkillView:
        """Get skill details."""
        return await self._transport.skill_client.get_skill(skill_name)

    async def enable_skill(self, skill_name: str) -> None:
        """Enable skill for session."""
        await self._transport.skill_client.enable_skill(
            session_id=self._session.session_id,
            skill_name=skill_name,
        )

    async def disable_skill(self, skill_name: str) -> None:
        """Disable skill for session."""
        await self._transport.skill_client.disable_skill(
            session_id=self._session.session_id,
            skill_name=skill_name,
        )
```

---

## 七、记忆命令协调器

### 7.1 SessionMemoryCommandCoordinator

```python
class SessionMemoryCommandCoordinator:
    """Handle memory commands for TUI session."""

    async def list_memories(
        self,
        *,
        limit: int = 50,
    ) -> list[MemoryView]:
        """List session memories."""
        return await self._transport.memory_client.list_memories(
            session_id=self._session.session_id,
            limit=limit,
        )

    async def create_memory(
        self,
        *,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> MemoryView:
        """Create new memory."""
        return await self._transport.memory_client.create_memory(
            session_id=self._session.session_id,
            content=content,
            metadata=metadata,
        )

    async def search_memories(
        self,
        *,
        query: str,
        limit: int = 10,
    ) -> list[MemoryView]:
        """Search memories."""
        return await self._transport.memory_client.search_memories(
            session_id=self._session.session_id,
            query=query,
            limit=limit,
        )
```

---

## 八、审批命令协调器

### 8.1 SessionApprovalCommandCoordinator

```python
class SessionApprovalCommandCoordinator:
    """Handle approval commands for TUI session."""

    async def get_pending_approvals(self) -> list[ApprovalRequest]:
        """Get pending approval requests."""
        return self._session.pending_approvals

    async def resolve_approval(
        self,
        *,
        token: str,
        approved: bool,
    ) -> None:
        """Resolve pending approval."""
        await self._transport.run_client.resolve_approval(
            run_id=self._session.active_run_id,
            approved=approved,
            token=token,
        )

    async def get_approval_policy(self) -> ApprovalPolicyView:
        """Get current approval policy."""
        return await self._transport.approval_client.get_policy(
            session_id=self._session.session_id,
        )

    async def set_approval_policy(
        self,
        *,
        mode: str,
    ) -> ApprovalPolicyView:
        """Set approval policy."""
        return await self._transport.approval_client.set_policy(
            session_id=self._session.session_id,
            mode=mode,
        )
```

---

## 九、文件位置

```
src/mini_agent/tui/
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

- [x] 支持多种命令协调器
- [x] 支持命令分发
- [x] 支持状态同步
- [x] 支持错误处理

---

## 十一、依赖关系

- 依赖: transport/, session/
- 被依赖: app.py
