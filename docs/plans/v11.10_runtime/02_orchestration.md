# 编排服务开发文档

**模块**: runtime/orchestration
**优先级**: P0
**预估时间**: 已实现，文档补全

---

## 一、功能概述

编排服务负责复杂流程的编排：

- 会话生命周期管理
- 会话恢复与重置
- 运行时策略协调

---

## 二、编排服务总览

| 服务 | 职责 |
|------|------|
| `SessionHydrationCoordinator` | 会话初始化协调 |
| `SessionRuntimeLifecycleHandler` | 会话生命周期管理 |
| `SessionRestoreHandler` | 会话恢复处理 |
| `SessionRuntimePolicyCoordinator` | 运行时策略协调 |

---

## 三、核心编排服务

### 3.1 SessionHydrationCoordinator

```python
# src/mini_agent/runtime/orchestration/session_hydration_coordinator.py

class SessionHydrationCoordinator:
    """Coordinate session hydration (initialization)."""

    async def hydrate_session(
        self,
        session: MainAgentSessionState,
    ) -> HydratedSession:
        """Initialize session with all required components."""
        # 1. 加载配置
        config = self._load_runtime_config()

        # 2. 构建 Agent
        agent = await self._build_agent(session, config)

        # 3. 加载技能
        skills = await self._load_skills(session)

        # 4. 加载记忆
        memories = await self._load_memories(session)

        # 5. 加载 MCP 工具
        mcp_tools = await self._load_mcp_tools(session)

        # 6. 组装
        return HydratedSession(
            session=session,
            agent=agent,
            skills=skills,
            memories=memories,
            mcp_tools=mcp_tools,
        )
```

### 3.2 SessionRuntimeLifecycleHandler

```python
# src/mini_agent/runtime/orchestration/session_runtime_lifecycle_handler.py

class SessionRuntimeLifecycleHandler:
    """Manage session runtime lifecycle."""

    async def start_session(
        self,
        session: MainAgentSessionState,
    ) -> None:
        """Start session runtime."""
        # 1. 初始化运行时状态
        self._run_control_store.begin_turn(session, surface="lifecycle")

        # 2. 启动 Agent
        await self._start_agent(session)

        # 3. 注册事件监听
        self._register_event_handlers(session)

    async def stop_session(
        self,
        session: MainAgentSessionState,
    ) -> None:
        """Stop session runtime."""
        # 1. 取消正在执行的任务
        self._run_control_store.request_cancel(session, source="lifecycle")

        # 2. 等待任务完成
        await self._wait_for_completion(session)

        # 3. 清理资源
        self._cleanup_session(session)

    async def pause_session(
        self,
        session: MainAgentSessionState,
    ) -> None:
        """Pause session runtime."""
        self._run_control_store.request_interrupt(session, source="lifecycle")

    async def resume_session(
        self,
        session: MainAgentSessionState,
    ) -> None:
        """Resume session runtime."""
        self._run_control_store.request_resume(session, source="lifecycle")
```

### 3.3 SessionRestoreHandler

```python
# src/mini_agent/runtime/orchestration/session_restore_handler.py

class SessionRestoreHandler:
    """Handle session restore from checkpoint."""

    async def restore_session(
        self,
        *,
        session_id: str,
        checkpoint_id: str | None = None,
    ) -> MainAgentSessionDetail:
        """Restore session from checkpoint."""
        # 1. 加载会话状态
        session = self._load_session_state(session_id)

        # 2. 加载检查点
        checkpoint = self._load_checkpoint(checkpoint_id or session.checkpoint_head_id)

        # 3. 恢复消息历史
        messages = self._restore_messages(checkpoint)

        # 4. 恢复 Agent 状态
        agent = await self._restore_agent(session, checkpoint)

        # 5. 更新会话
        session.agent = agent
        session.messages = messages

        return self._build_session_detail(session)

    async def reset_session(
        self,
        session_id: str,
    ) -> MainAgentSessionDetail:
        """Reset session to initial state."""
        session = self._get_session(session_id)

        # 清除消息历史
        session.messages = [Message(role="system", content=session.system_prompt)]

        # 重置 Agent
        session.agent = await self._build_agent(session)

        return self._build_session_detail(session)
```

### 3.4 SessionRuntimePolicyCoordinator

```python
# src/mini_agent/runtime/orchestration/session_runtime_policy_coordinator.py

@dataclass
class MainAgentRuntimePolicy:
    """Runtime policy configuration."""

    max_concurrent_sessions: int = 10
    session_ttl_seconds: int = 3600
    auto_compact_threshold: float = 0.8
    enable_auto_recovery: bool = True


class SessionRuntimePolicyCoordinator:
    """Coordinate runtime policy enforcement."""

    def __init__(
        self,
        policy: MainAgentRuntimePolicy,
    ) -> None:
        self._policy = policy

    async def enforce_policy(
        self,
        session: MainAgentSessionState,
    ) -> PolicyEnforcementResult:
        """Enforce runtime policy on session."""
        results = []

        # 1. 检查 TTL
        if self._should_expire(session):
            results.append("session_expired")
            await self._expire_session(session)

        # 2. 检查上下文大小
        if self._should_compact(session):
            results.append("context_compact")
            await self._compact_context(session)

        # 3. 检查并发限制
        if self._exceeds_concurrent_limit():
            results.append("concurrent_limit")

        return PolicyEnforcementResult(
            session_id=session.session_id,
            actions=results,
        )

    def _should_expire(self, session: MainAgentSessionState) -> bool:
        """Check if session should expire."""
        age = time.time() - session.created_at.timestamp()
        return age > self._policy.session_ttl_seconds

    def _should_compact(self, session: MainAgentSessionState) -> bool:
        """Check if context should be compacted."""
        if session.agent is None:
            return False
        usage_ratio = session.agent.api_total_tokens / session.agent.token_limit
        return usage_ratio > self._policy.auto_compact_threshold
```

---

## 四、生命周期流程

```
┌─────────────────────────────────────────────────────────────────┐
│                    Session Lifecycle                             │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                    Creation                              │   │
│  │  SessionCreationHandler.create_session()                │   │
│  └─────────────────────────────────────────────────────────┘   │
│                              │                                   │
│                              ▼                                   │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                   Hydration                              │   │
│  │  SessionHydrationCoordinator.hydrate_session()          │   │
│  │  - Build Agent                                          │   │
│  │  - Load Skills                                          │   │
│  │  - Load Memories                                        │   │
│  │  - Load MCP Tools                                       │   │
│  └─────────────────────────────────────────────────────────┘   │
│                              │                                   │
│                              ▼                                   │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                     Start                                │   │
│  │  SessionRuntimeLifecycleHandler.start_session()         │   │
│  └─────────────────────────────────────────────────────────┘   │
│                              │                                   │
│                              ▼                                   │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                    Running                               │   │
│  │  - Policy Enforcement                                   │   │
│  │  - Context Management                                   │   │
│  │  - Run Control                                          │   │
│  └─────────────────────────────────────────────────────────┘   │
│                              │                                   │
│                              ▼                                   │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                     Stop                                 │   │
│  │  SessionRuntimeLifecycleHandler.stop_session()          │   │
│  └─────────────────────────────────────────────────────────┘   │
│                              │                                   │
│                              ▼                                   │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                   Cleanup                                │   │
│  │  - Drop from registry                                   │   │
│  │  - Release resources                                    │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## 五、文件位置

```
src/mini_agent/runtime/orchestration/
├── __init__.py
├── session_hydration_coordinator.py
├── session_runtime_lifecycle_handler.py
├── session_restore_handler.py
├── session_runtime_policy_coordinator.py
└── main_agent_runtime_assembly_mixin.py
```

---

## 六、验收标准

- [x] 支持会话初始化
- [x] 支持生命周期管理
- [x] 支持会话恢复
- [x] 支持策略协调

---

## 七、依赖关系

- 依赖: live_control/, handlers/
- 被依赖: handlers/