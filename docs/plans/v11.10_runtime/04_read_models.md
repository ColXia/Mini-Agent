# 读模型开发文档

**模块**: runtime/read_models
**优先级**: P1
**预估时间**: 已实现，文档补全

---

## 一、功能概述

读模型负责构建查询视图：

- 会话详情视图
- 会话快照
- Run 投影
- 诊断信息

---

## 二、组件总览

| 组件 | 职责 |
|------|------|
| `SessionReadModelBuilder` | 会话读模型构建 |
| `SessionSnapshotBuilder` | 会话快照构建 |
| `RunProjectionBuilder` | Run 投影构建 |
| `SessionDiagnostics` | 会话诊断 |
| `SessionPayloadCodec` | 会话负载编解码 |
| `SessionModelIdentityCodec` | 模型身份编解码 |

---

## 三、核心组件

### 3.1 SessionReadModelBuilder

```python
# src/mini_agent/runtime/read_models/session_read_model_builder.py

class SessionReadModelBuilder:
    """Build read models for session queries."""

    def __init__(
        self,
        run_control_store: RuntimeSessionRunControlStore,
    ) -> None:
        self._store = run_control_store

    def build_session_detail(
        self,
        session: MainAgentSessionState,
        *,
        recent_limit: int = 50,
    ) -> MainAgentSessionDetail:
        """Build session detail view."""
        # 1. 基本信息
        base = self._build_base_info(session)

        # 2. 消息历史
        messages = self._build_messages(session, limit=recent_limit)

        # 3. 运行时状态
        run_state = self._build_run_state(session)

        # 4. 模型信息
        model_info = self._build_model_info(session)

        # 5. 待审批列表
        pending_approvals = self._build_pending_approvals(session)

        return MainAgentSessionDetail(
            session_id=session.session_id,
            workspace_dir=str(session.workspace_dir),
            title=session.title,
            created_at=session.created_at,
            messages=messages,
            run_state=run_state,
            model_info=model_info,
            pending_approvals=pending_approvals,
        )

    def build_session_summary(
        self,
        session: MainAgentSessionState,
    ) -> MainAgentSessionSummary:
        """Build session summary view."""
        return MainAgentSessionSummary(
            session_id=session.session_id,
            title=session.title,
            created_at=session.created_at,
            message_count=len(session.messages),
            is_running=self._is_running(session),
        )
```

### 3.2 SessionSnapshotBuilder

```python
# src/mini_agent/runtime/read_models/session_snapshot_builder.py

class SessionSnapshotBuilder:
    """Build session snapshots for persistence."""

    def build_snapshot(
        self,
        session: MainAgentSessionState,
    ) -> SessionSnapshot:
        """Build session snapshot."""
        return SessionSnapshot(
            session_id=session.session_id,
            workspace_dir=str(session.workspace_dir),
            title=session.title,
            messages=[self._serialize_message(m) for m in session.messages],
            agent_state=self._serialize_agent_state(session.agent),
            created_at=session.created_at,
            updated_at=session.updated_at,
        )

    def restore_from_snapshot(
        self,
        snapshot: SessionSnapshot,
    ) -> MainAgentSessionState:
        """Restore session from snapshot."""
        return MainAgentSessionState(
            session_id=snapshot.session_id,
            workspace_dir=Path(snapshot.workspace_dir),
            title=snapshot.title,
            messages=[self._deserialize_message(m) for m in snapshot.messages],
            created_at=snapshot.created_at,
            updated_at=snapshot.updated_at,
        )
```

### 3.3 RunProjectionBuilder

```python
# src/mini_agent/runtime/read_models/run_projection_builder.py

class RunProjectionBuilder:
    """Build run projections for queries."""

    def __init__(
        self,
        run_control_store: RuntimeSessionRunControlStore,
    ) -> None:
        self._store = run_control_store

    def build_run_view(
        self,
        run_id: str,
    ) -> RunView | None:
        """Build run view."""
        session_id = self._store.session_id_for_run_id(run_id)
        if session_id is None:
            return None

        state = self._store.current_control_state_for_run_id(run_id)
        if state is None:
            return None

        return RunView(
            run_id=run_id,
            session_id=session_id,
            state=state.state,
            surface=state.surface,
            detail=state.detail,
            started_at=state.started_at,
        )

    def build_run_list(
        self,
        *,
        workspace_dir: Path | None = None,
        state_filter: str | None = None,
    ) -> list[RunView]:
        """Build list of runs."""
        runs = []
        for run_id, state in self._store.all_states():
            if state_filter and state.state != state_filter:
                continue
            runs.append(self.build_run_view(run_id))
        return runs
```

### 3.4 SessionDiagnostics

```python
# src/mini_agent/runtime/read_models/session_diagnostics.py

class SessionDiagnostics:
    """Build session diagnostics."""

    def build_diagnostics(
        self,
        session: MainAgentSessionState,
    ) -> SessionDiagnosticsView:
        """Build session diagnostics view."""
        return SessionDiagnosticsView(
            session_id=session.session_id,
            message_count=len(session.messages),
            token_count=self._estimate_tokens(session),
            run_state=self._get_run_state(session),
            pending_approvals=len(self._get_pending_approvals(session)),
            model_info=self._get_model_info(session),
            skill_info=self._get_skill_info(session),
            memory_info=self._get_memory_info(session),
        )

    def build_health_check(
        self,
        session: MainAgentSessionState,
    ) -> HealthCheckView:
        """Build health check view."""
        issues = []

        # 检查 Agent
        if session.agent is None:
            issues.append("Agent not initialized")

        # 检查模型
        if not self._has_model_binding(session):
            issues.append("No model binding")

        # 检查 Token
        if self._is_near_token_limit(session):
            issues.append("Near token limit")

        return HealthCheckView(
            session_id=session.session_id,
            is_healthy=len(issues) == 0,
            issues=issues,
        )
```

---

## 四、视图模型

### 4.1 MainAgentSessionDetail

```python
@dataclass
class MainAgentSessionDetail:
    """Session detail view."""
    session_id: str
    workspace_dir: str
    title: str | None
    created_at: datetime
    messages: list[MessageView]
    run_state: RunStateView
    model_info: ModelInfoView
    pending_approvals: list[ApprovalView]
```

### 4.2 MainAgentSessionSummary

```python
@dataclass
class MainAgentSessionSummary:
    """Session summary view."""
    session_id: str
    title: str | None
    created_at: datetime
    message_count: int
    is_running: bool
```

### 4.3 RunView

```python
@dataclass
class RunView:
    """Run view."""
    run_id: str
    session_id: str
    state: str
    surface: str | None
    detail: str | None
    started_at: datetime | None
```

---

## 五、文件位置

```
src/mini_agent/runtime/read_models/
├── __init__.py
├── session_read_model_builder.py
├── session_snapshot_builder.py
├── run_projection_builder.py
├── session_diagnostics.py
├── session_payload_codec.py
└── session_model_identity_codec.py
```

---

## 六、验收标准

- [x] 支持会话详情构建
- [x] 支持会话快照
- [x] 支持 Run 投影
- [x] 支持诊断信息

---

## 七、依赖关系

- 依赖: live_control/
- 被依赖: handlers/