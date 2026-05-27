# 实时控制开发文档

**模块**: runtime/live_control
**优先级**: P0
**预估时间**: 已实现，文档补全

---

## 一、功能概述

实时控制负责运行时状态管理：

- Run 控制状态
- 中断/恢复/取消
- 审批等待管理
- 内核状态注册

---

## 二、组件总览

| 组件 | 职责 |
|------|------|
| `RuntimeSessionRunControlStore` | Run 控制存储门面 |
| `RuntimeKernelStateRegistry` | 内核状态注册表 |
| `SessionInterruptHandler` | 中断处理 |
| `SessionCancelService` | 取消服务 |
| `SessionPendingApprovalService` | 审批等待服务 |
| `SessionTurnScopeHandler` | 回合作用域处理 |
| `SessionTranscriptStateHandler` | 转录状态处理 |

---

## 三、核心组件

### 3.1 RuntimeSessionRunControlStore

```python
# src/mini_agent/runtime/live_control/run_control_store.py

class RuntimeSessionRunControlStore:
    """Thin facade that delegates run truth mutations to the kernel-state registry."""

    def __init__(
        self,
        *,
        selected_model_identity_for_session: Callable | None = None,
    ) -> None:
        self._registry = RuntimeKernelStateRegistry(
            selected_model_identity_for_session=selected_model_identity_for_session,
        )

    # === Run ID 映射 ===

    @staticmethod
    def run_id_for_session(session_id: str) -> str:
        """Generate run ID for session."""
        return f"session:{session_id}"

    @staticmethod
    def session_id_for_run_id(run_id: str) -> str | None:
        """Extract session ID from run ID."""
        if not run_id.startswith("session:"):
            return None
        return run_id[8:]

    # === 状态查询 ===

    def current_control_state(
        self,
        session: MainAgentSessionState,
    ) -> RunControlState:
        """Get current run control state."""
        return self._registry.current_control_state(session)

    def current_approval_wait(
        self,
        session: MainAgentSessionState,
    ) -> ApprovalWait | None:
        """Get current approval wait."""
        return self._registry.current_approval_wait(session)

    def pending_approval_payloads(
        self,
        session: MainAgentSessionState,
    ) -> list[dict[str, Any]]:
        """Get pending approval payloads."""
        return self._registry.pending_approval_payloads(session)

    # === 控制操作 ===

    def begin_turn(
        self,
        session: MainAgentSessionState,
        *,
        surface: str | None = None,
        detail: str | None = None,
    ) -> RunControlState:
        """Begin a new turn."""
        record = self._registry.begin_turn(session, surface=surface, detail=detail)
        self._registry.sync_session_runtime(session)
        return record.run_control

    def finish_turn(
        self,
        session: MainAgentSessionState,
    ) -> RunControlState:
        """Finish current turn."""
        record = self._registry.finish_turn(session)
        self._registry.sync_session_runtime(session)
        return record.run_control

    def request_interrupt(
        self,
        session: MainAgentSessionState,
        *,
        source: str | None = None,
        reason: str | None = None,
    ) -> RunControlState:
        """Request interrupt."""
        record = self._registry.request_interrupt(session, source=source, reason=reason)
        return record.run_control

    def request_cancel(
        self,
        session: MainAgentSessionState,
        *,
        source: str | None = None,
        reason: str | None = None,
    ) -> RunControlState:
        """Request cancel."""
        record = self._registry.request_cancel(session, source=source, reason=reason)
        return record.run_control

    def request_resume(
        self,
        session: MainAgentSessionState,
        *,
        source: str | None = None,
        resume_token: str | None = None,
    ) -> RunControlState:
        """Request resume."""
        record = self._registry.request_resume(session, source=source, resume_token=resume_token)
        return record.run_control

    # === 审批操作 ===

    def resolve_approval(
        self,
        session: MainAgentSessionState,
        *,
        approved: bool,
        token: str | None = None,
    ) -> RunControlState:
        """Resolve pending approval."""
        record = self._registry.resolve_approval(session, approved=approved, token=token)
        return record.run_control
```

### 3.2 RuntimeKernelStateRegistry

```python
# src/mini_agent/runtime/live_control/kernel_state_registry.py

class RuntimeKernelStateRegistry:
    """Registry for kernel state records."""

    def __init__(
        self,
        *,
        selected_model_identity_for_session: Callable | None = None,
    ) -> None:
        self._records: dict[str, AgentKernelStateRecord] = {}
        self._selected_model_identity_for_session = selected_model_identity_for_session

    def current_record(
        self,
        session: MainAgentSessionState,
    ) -> AgentKernelStateRecord:
        """Get or create kernel state record."""
        session_id = session.session_id
        if session_id not in self._records:
            self._records[session_id] = self._create_record(session)
        return self._records[session_id]

    def begin_turn(
        self,
        session: MainAgentSessionState,
        *,
        surface: str | None = None,
        detail: str | None = None,
    ) -> AgentKernelStateRecord:
        """Begin turn for session."""
        record = self.current_record(session)
        return record.begin_turn(surface=surface, detail=detail)

    def finish_turn(
        self,
        session: MainAgentSessionState,
    ) -> AgentKernelStateRecord:
        """Finish turn for session."""
        record = self.current_record(session)
        return record.finish_turn()

    def request_interrupt(
        self,
        session: MainAgentSessionState,
        *,
        source: str | None = None,
        reason: str | None = None,
    ) -> AgentKernelStateRecord:
        """Request interrupt."""
        record = self.current_record(session)
        return record.request_interrupt(source=source, reason=reason)

    def drop_session(self, session_id: str) -> None:
        """Drop session from registry."""
        self._records.pop(session_id, None)

    def clear(self) -> None:
        """Clear all records."""
        self._records.clear()
```

### 3.3 SessionPendingApprovalService

```python
# src/mini_agent/runtime/live_control/session_pending_approval_service.py

class SessionPendingApprovalService:
    """Manage pending approvals for session."""

    def __init__(
        self,
        run_control_store: RuntimeSessionRunControlStore,
    ) -> None:
        self._store = run_control_store

    def get_pending_approvals(
        self,
        session: MainAgentSessionState,
    ) -> list[ApprovalRequest]:
        """Get pending approval requests."""
        payloads = self._store.pending_approval_payloads(session)
        return [self._build_approval_request(p) for p in payloads]

    async def resolve_approval(
        self,
        session: MainAgentSessionState,
        *,
        token: str,
        approved: bool,
    ) -> ApprovalResult:
        """Resolve pending approval."""
        state = self._store.resolve_approval(
            session,
            approved=approved,
            token=token,
        )

        return ApprovalResult(
            session_id=session.session_id,
            token=token,
            approved=approved,
            state=state.state,
        )

    def wait_for_approval(
        self,
        session: MainAgentSessionState,
        *,
        token: str,
    ) -> asyncio.Event:
        """Wait for approval resolution."""
        return self._store.pending_approval_waiter(session, token=token)
```

---

## 四、状态机

### 4.1 RunControlState

```
┌─────────────────────────────────────────────────────────────────┐
│                    Run Control State                             │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌───────────┐                                                  │
│  │   IDLE    │                                                  │
│  └─────┬─────┘                                                  │
│        │ begin_turn                                             │
│        ▼                                                         │
│  ┌───────────┐                                                  │
│  │  RUNNING  │◄──────────────────────────────┐                 │
│  └─────┬─────┘                                │                 │
│        │                                      │                 │
│        ├── request_interrupt ──►┌───────────┐│                 │
│        │                        │ INTERRUPT ││                 │
│        │                        └─────┬─────┘│                 │
│        │                              │      │                 │
│        │                              │ resume                 │
│        │                              └──────┘                 │
│        │                                                         │
│        ├── request_cancel ──────►┌───────────┐                 │
│        │                         │  CANCEL   │                 │
│        │                         └───────────┘                 │
│        │                                                         │
│        │ finish_turn                                             │
│        ▼                                                         │
│  ┌───────────┐                                                  │
│  │   IDLE    │                                                  │
│  └───────────┘                                                  │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## 五、文件位置

```
src/mini_agent/runtime/live_control/
├── __init__.py
├── run_control_store.py
├── kernel_state_registry.py
├── run_control_constants.py
├── session_interrupt_handler.py
├── session_cancel_service.py
├── session_pending_approval_service.py
├── session_pending_approval_state_handler.py
├── session_turn_scope_handler.py
├── session_transcript_state_handler.py
├── session_recovery_reset_handler.py
```

---

## 六、验收标准

- [x] 支持 Run 控制状态管理
- [x] 支持中断/恢复/取消
- [x] 支持审批等待管理
- [x] 支持内核状态注册

---

## 七、依赖关系

- 依赖: agent_core/contracts/
- 被依赖: handlers/, orchestration/