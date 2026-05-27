# 门面服务开发文档

**模块**: application/facades
**优先级**: P1
**预估时间**: 已实现，文档补全

---

## 一、功能概述

门面层负责复杂流程编排：

- 跨多个用例服务的流程
- Surface 无关的交互处理
- 执行结果组装

---

## 二、门面服务总览

| 服务 | 职责 |
|------|------|
| `SurfaceChatFlowHandler` | Surface 无关的聊天流程编排 |
| `AgentTurnExecutionHandler` | 单回合 Agent 执行 |
| `AgentRouteExecutionHandler` | 路由解析与执行分发 |
| `AgentDelegationExecutionHandler` | 子 Agent 委派执行 |

---

## 三、核心门面实现

### 3.1 SurfaceChatFlowHandler

```python
# src/mini_agent/application/facades/surface_chat_flow_handler.py

@dataclass(frozen=True)
class SurfaceChatExecutionRequest:
    """Chat execution request."""
    message: str
    workspace_dir: Path
    session_id: str | None = None
    session_title_hint: str | None = None
    surface: str | None = None
    channel_type: str | None = None
    conversation_id: str | None = None
    sender_id: str | None = None
    dry_run: bool = False
    running_detail: str = ""


@dataclass(frozen=True)
class SurfaceChatExecutionResult:
    """Chat execution result."""
    reply: str
    stop_reason: str
    main_route_used: bool
    delegation_payload: dict[str, Any] | None = None
    supplemental_events: tuple[SurfaceChatStreamEvent, ...] = ()


@dataclass(slots=True)
class SurfaceChatFlowHandler:
    """Surface-neutral chat-turn orchestration for shared interaction services."""

    session_task_service: SessionTaskFlowPort
    to_utc_iso: ToUtcIsoFn
    sse_event: SseEventFn
    format_bootstrap_error: FormatBootstrapErrorFn
    stream_chunk_size: int

    async def run_chat(
        self,
        request: SurfaceChatExecutionRequest,
        *,
        execute_turn: ExecuteSurfaceChatTurnFn,
    ) -> MainAgentChatResponse:
        """Execute chat request and return response."""
        # 1. 验证工作区
        self.session_task_service.validate_workspace(request.workspace_dir)

        # 2. Dry run 模式
        if request.dry_run:
            return self._build_dry_run_response(request)

        # 3. 准备回合
        request.workspace_dir.mkdir(parents=True, exist_ok=True)
        turn = await self._prepare_turn(request)

        # 4. 执行回合
        async with turn:
            execution = await self._execute_turn(turn, request, execute_turn=execute_turn)

        # 5. 构建响应
        return MainAgentChatResponse(
            reply=execution.reply,
            stop_reason=execution.stop_reason,
        )

    async def stream_chat_events(
        self,
        request: SurfaceChatExecutionRequest,
        *,
        execute_turn: ExecuteSurfaceChatTurnFn,
    ) -> AsyncIterator[str]:
        """Stream chat events via SSE."""
        # 1. 准备回合
        turn = await self._prepare_turn(request)

        # 2. 流式执行
        async with turn:
            async for event in self._stream_turn_events(turn, request, execute_turn):
                yield self.sse_event(event.event_type, event.payload)
```

### 3.2 AgentTurnExecutionHandler

```python
# src/mini_agent/application/facades/agent_turn_execution_handler.py

@dataclass(slots=True)
class AgentTurnExecutionHandler:
    """Owns single-turn agent execution plus runtime approval/activity hooks."""

    async def run_agent_once(
        self,
        turn: ManagedSessionTurn,
        request: SurfaceChatExecutionRequest,
    ) -> TurnExecutionResult:
        """Execute one agent turn."""
        # 1. 获取 Agent
        agent = turn.agent

        # 2. 添加用户消息
        agent.add_user_message(request.message)

        # 3. 执行回合
        result = await agent.run_turn(
            cancel_event=turn.cancel_event,
            hooks=self._build_hooks(turn),
        )

        # 4. 返回结果
        return TurnExecutionResult(
            stop_reason=result.stop_reason,
            message=result.message,
        )
```

### 3.3 AgentRouteExecutionHandler

```python
# src/mini_agent/application/facades/agent_route_execution_handler.py

class AgentRouteExecutionHandler:
    """Owns route resolution, route diagnostics, and route-to-executor dispatch."""

    async def get_routing_diagnostics(self) -> MainAgentRoutingDiagnostics:
        """Get routing diagnostics."""
        ...

    async def execute_chat_turn(
        self,
        turn: ManagedSessionTurn,
        request: SurfaceChatExecutionRequest,
        *,
        emit_event: Callable[[str, dict], Awaitable[None]] | None = None,
    ) -> SurfaceChatExecutionResult:
        """Execute chat turn with routing."""
        # 1. 解析路由
        route = await self._resolve_route(turn, request)

        # 2. 执行
        if route.is_delegation:
            # 委派给子 Agent
            return await self._execute_delegation(turn, request, route)
        else:
            # 主 Agent 执行
            return await self._execute_main(turn, request, emit_event)
```

### 3.4 AgentDelegationExecutionHandler

```python
# src/mini_agent/application/facades/agent_delegation_execution_handler.py

class AgentDelegationExecutionHandler:
    """Handle delegation to sub-agents."""

    async def execute_delegation(
        self,
        turn: ManagedSessionTurn,
        request: SurfaceChatExecutionRequest,
        route: AgentRoute,
    ) -> SurfaceChatExecutionResult:
        """Execute delegation to sub-agent."""
        # 1. 创建子 Agent
        sub_agent = await self._create_sub_agent(turn, route)

        # 2. 执行子 Agent
        result = await sub_agent.run_turn()

        # 3. 返回结果
        return SurfaceChatExecutionResult(
            reply=result.message,
            stop_reason=result.stop_reason.value,
            main_route_used=False,
            delegation_payload={
                "sub_agent_id": route.target_agent_id,
            },
        )
```

---

## 四、流程图

### 4.1 聊天流程

```
┌─────────────────────────────────────────────────────────────────┐
│                      Chat Flow                                   │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  1. SurfaceChatFlowHandler.run_chat()                           │
│     │                                                           │
│     ├── 验证工作区                                              │
│     │                                                           │
│     ├── 准备回合 (SessionTaskService.prepare_chat_turn)         │
│     │                                                           │
│     ▼                                                           │
│  2. AgentRouteExecutionHandler.execute_chat_turn()              │
│     │                                                           │
│     ├── 解析路由                                                │
│     │   ├── 主路由 → AgentTurnExecutionHandler                  │
│     │   └── 委派路由 → AgentDelegationExecutionHandler          │
│     │                                                           │
│     ▼                                                           │
│  3. AgentTurnExecutionHandler.run_agent_once()                  │
│     │                                                           │
│     ├── 添加用户消息                                            │
│     │                                                           │
│     ├── 执行 Agent 回合                                         │
│     │                                                           │
│     └── 返回结果                                                │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## 五、文件位置

```
src/mini_agent/application/facades/
├── __init__.py
├── surface_chat_flow_handler.py
├── agent_turn_execution_handler.py
├── agent_route_execution_handler.py
├── agent_delegation_execution_handler.py
└── service_response_dto_adapter.py
```

---

## 六、验收标准

- [x] 支持跨服务流程编排
- [x] 支持 Surface 无关处理
- [x] 支持流式响应

---

## 七、依赖关系

- 依赖: use_cases/, support/
- 被依赖: user_services/, gateway/
