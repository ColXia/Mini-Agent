# 请求处理器开发文档

**模块**: runtime/handlers
**优先级**: P0
**预估时间**: 已实现，文档补全

---

## 一、功能概述

请求处理器负责处理各类运行时请求：

- 会话创建与管理
- Run 控制
- Agent 运行时
- 记忆与技能

---

## 二、处理器总览

| 处理器 | 职责 |
|--------|------|
| `SessionCreationHandler` | 会话创建 |
| `SessionRunControlHandler` | Run 控制 |
| `SessionAgentRuntimeHandler` | Agent 运行时 |
| `SessionMemoryHandler` | 记忆管理 |
| `SessionSkillHandler` | 技能管理 |
| `SessionMcpControlHandler` | MCP 控制 |
| `SessionContextPolicyHandler` | 上下文策略 |
| `SessionRuntimePolicyHandler` | 运行时策略 |
| `SessionCommandCoordinator` | 命令协调 |

---

## 三、核心处理器

### 3.1 SessionCreationHandler

```python
# src/mini_agent/runtime/handlers/session_creation_handler.py

class SessionCreationHandler:
    """Handle session creation requests."""

    async def create_session(
        self,
        *,
        workspace_dir: Path,
        title: str | None = None,
        surface: str = "tui",
        shared: bool = False,
    ) -> MainAgentSessionDetail:
        """Create new session."""
        # 1. 生成会话 ID
        session_id = self._generate_session_id()

        # 2. 创建会话状态
        session = MainAgentSessionState(
            session_id=session_id,
            workspace_dir=workspace_dir,
            title=title,
            surface=surface,
            shared=shared,
        )

        # 3. 初始化 Agent
        agent = await self._build_agent(session)
        session.agent = agent

        # 4. 注册到运行时
        self._runtime_manager.register_session(session)

        return self._build_session_detail(session)

    async def ensure_default_session(
        self,
        *,
        workspace_dir: Path,
    ) -> MainAgentSessionDetail:
        """Ensure default session exists."""
        # 查找或创建默认会话
        existing = self._find_default_session(workspace_dir)
        if existing:
            return existing

        return await self.create_session(
            workspace_dir=workspace_dir,
            title="Default Session",
        )
```

### 3.2 SessionRunControlHandler

```python
# src/mini_agent/runtime/handlers/session_run_control_handler.py

class SessionRunControlHandler:
    """Handle run control requests."""

    def __init__(
        self,
        run_control_store: RuntimeSessionRunControlStore,
    ) -> None:
        self._store = run_control_store

    async def get_run(self, run_id: str) -> RunView:
        """Get run by ID."""
        state = self._store.current_control_state_for_run_id(run_id)
        if state is None:
            raise NotFoundError(f"Run not found: {run_id}")
        return self._build_run_view(state)

    async def interrupt_run(
        self,
        run_id: str,
        *,
        reason: str | None = None,
        source: str | None = None,
    ) -> InterruptResult:
        """Interrupt running task."""
        session_id = self._store.session_id_for_run_id(run_id)
        if session_id is None:
            raise NotFoundError(f"Invalid run ID: {run_id}")

        session = self._get_session(session_id)
        state = self._store.request_interrupt(session, source=source, reason=reason)

        return InterruptResult(
            run_id=run_id,
            requested=True,
            state=state.state,
        )

    async def cancel_run(
        self,
        run_id: str,
        *,
        reason: str | None = None,
        source: str | None = None,
    ) -> CancelResult:
        """Cancel running task."""
        session_id = self._store.session_id_for_run_id(run_id)
        session = self._get_session(session_id)
        state = self._store.request_cancel(session, source=source, reason=reason)

        return CancelResult(
            run_id=run_id,
            requested=True,
            state=state.state,
        )

    async def resume_run(
        self,
        run_id: str,
        *,
        resume_token: str | None = None,
        source: str | None = None,
    ) -> ResumeResult:
        """Resume paused task."""
        session_id = self._store.session_id_for_run_id(run_id)
        session = self._get_session(session_id)
        state = self._store.request_resume(session, source=source, resume_token=resume_token)

        return ResumeResult(
            run_id=run_id,
            requested=True,
            state=state.state,
        )
```

### 3.3 SessionAgentRuntimeHandler

```python
# src/mini_agent/runtime/handlers/session_agent_runtime_handler.py

class SessionAgentRuntimeHandler:
    """Handle agent runtime requests."""

    async def submit_message(
        self,
        *,
        session_id: str,
        message: str,
        surface: str = "tui",
    ) -> ChatResponse:
        """Submit chat message."""
        # 1. 获取会话
        session = self._get_session(session_id)

        # 2. 开始回合
        self._run_control_store.begin_turn(session, surface=surface)

        try:
            # 3. 执行 Agent
            agent = session.agent
            result = await agent.run_turn()

            # 4. 返回结果
            return ChatResponse(
                reply=result.message,
                stop_reason=result.stop_reason.value,
            )
        finally:
            # 5. 结束回合
            self._run_control_store.finish_turn(session)

    async def stream_message(
        self,
        *,
        session_id: str,
        message: str,
        surface: str = "tui",
    ) -> AsyncIterator[StreamEvent]:
        """Stream chat response."""
        session = self._get_session(session_id)
        self._run_control_store.begin_turn(session, surface=surface)

        try:
            agent = session.agent
            async for event in agent.stream_turn():
                yield self._convert_event(event)
        finally:
            self._run_control_store.finish_turn(session)
```

### 3.4 SessionMemoryHandler

```python
# src/mini_agent/runtime/handlers/session_memory_handler.py

class SessionMemoryHandler:
    """Handle memory requests."""

    async def list_memories(
        self,
        *,
        session_id: str,
        limit: int = 50,
    ) -> list[MemoryView]:
        """List session memories."""
        session = self._get_session(session_id)
        return await self._memory_service.list_memories(
            workspace_dir=session.workspace_dir,
            session_id=session_id,
            limit=limit,
        )

    async def create_memory(
        self,
        *,
        session_id: str,
        content: str,
        metadata: dict | None = None,
    ) -> MemoryView:
        """Create new memory."""
        session = self._get_session(session_id)
        return await self._memory_service.create_memory(
            workspace_dir=session.workspace_dir,
            session_id=session_id,
            content=content,
            metadata=metadata,
        )

    async def search_memories(
        self,
        *,
        session_id: str,
        query: str,
        limit: int = 10,
    ) -> list[MemoryView]:
        """Search memories."""
        session = self._get_session(session_id)
        return await self._memory_service.search_memories(
            workspace_dir=session.workspace_dir,
            query=query,
            limit=limit,
        )
```

---

## 四、文件位置

```
src/mini_agent/runtime/handlers/
├── __init__.py
├── session_creation_handler.py
├── session_run_control_handler.py
├── session_agent_runtime_handler.py
├── session_agent_control_handler.py
├── session_memory_handler.py
├── session_memory_command_handler.py
├── session_skill_handler.py
├── session_mcp_control_handler.py
├── session_context_policy_handler.py
├── session_runtime_policy_handler.py
├── session_command_coordinator.py
├── session_control_command_handler.py
├── session_access_handler.py
├── session_catalog_handler.py
├── session_registry_handler.py
├── session_admin_handler.py
└── main_agent_runtime_public_api_mixin.py
```

---

## 五、验收标准

- [x] 支持会话创建与管理
- [x] 支持 Run 控制
- [x] 支持 Agent 运行时
- [x] 支持记忆与技能

---

## 六、依赖关系

- 依赖: orchestration/, live_control/
- 被依赖: gateway/, tui/, desktop/