from __future__ import annotations

from datetime import datetime, timezone

from mini_agent.runtime.session_recovery_reset_handler import RuntimeSessionRecoveryResetHandler
from tests.runtime_contract_fixtures import (
    RuntimeContractAgentStub,
    runtime_projection_stub,
    runtime_session_stub,
    runtime_state_stub,
    transcript_state_stub,
)


def _dt() -> datetime:
    return datetime(2026, 4, 14, 13, 0, 0, tzinfo=timezone.utc)


class _RecoverySnapshot:
    def __init__(self, payload: dict[str, object]) -> None:
        self._payload = dict(payload)

    def model_dump(self) -> dict[str, object]:
        return dict(self._payload)

    @property
    def state(self) -> object:
        return self._payload.get("state")

    @property
    def summary(self) -> object:
        return self._payload.get("summary")

    @property
    def last_activity(self) -> object:
        return self._payload.get("last_activity")

    @property
    def last_user_message(self) -> object:
        return self._payload.get("last_user_message")

    @property
    def last_assistant_message(self) -> object:
        return self._payload.get("last_assistant_message")

    @property
    def pending_approvals(self) -> list[object]:
        return list(self._payload.get("pending_approvals") or [])


class _PendingFuture:
    def __init__(self) -> None:
        self._done = False
        self.result_value = None

    def done(self) -> bool:
        return self._done

    def set_result(self, value) -> None:  # noqa: ANN001
        self._done = True
        self.result_value = value


class _ApprovalItem:
    def __init__(self, payload: dict[str, object]) -> None:
        self._payload = dict(payload)

    def model_dump(self) -> dict[str, object]:
        return dict(self._payload)


def _session(*, with_agent_reset_hook: bool = False):
    touch_calls: list[datetime | None] = []
    clear_calls: list[tuple[str, str]] = []

    def _touch(*, now_utc=None):  # noqa: ANN001
        touch_calls.append(now_utc)

    agent = RuntimeContractAgentStub(
        messages=[
            {"role": "system", "content": "system"},
            {"role": "user", "content": "hello"},
        ],
        api_total_tokens=77,
        prepared_context={"recent": True},
        prepared_context_diagnostics={"ok": True},
        last_memory_automation={"ran": True},
        last_runtime_task_memory={"key": "value"},
    )
    reset_calls: list[str] = []
    if with_agent_reset_hook:
        def _reset() -> None:
            reset_calls.append("called")
        agent.reset_ephemeral_runtime_state = _reset

    future = _PendingFuture()

    session = runtime_session_stub(
        session_id="sess-1",
        workspace_dir="workspace-1",
        transcript_state=transcript_state_stub(current_turn_id="turn-1"),
        runtime=runtime_state_stub(
            agent=agent,
            cancel_event=object(),
            pending_approvals=[{"token": "tok-1", "tool_name": "shell"}],
            pending_approval_waiters={"tok-1": future},
        ),
        projection=runtime_projection_stub(
            recovery_context_pending=True,
            recovery_state="interrupted",
            recovery_summary="awaiting resume",
            recovery_last_activity="shell running",
            recovery_last_user_message="continue",
            recovery_last_assistant_message="working",
            recovery_pending_approvals=[{"token": "tok-1"}],
            last_prepared_context={"history": 1},
            prepared_context_diagnostics={"ctx": True},
            busy=True,
            running_state="running",
            knowledge_base_enabled=False,
            memory_diagnostics={"before": True},
        ),
        touch=_touch,
    )
    session._touch_calls = touch_calls
    session._clear_calls = clear_calls
    session._agent_reset_calls = reset_calls
    session._future = future
    return session


def test_recovery_reset_handler_builds_recovery_turn_context() -> None:
    handler = RuntimeSessionRecoveryResetHandler(
        refresh_session_diagnostics=lambda _session: ({}, {}),
        agent_knowledge_base_enabled=lambda _agent: True,
        clear_runtime_task_memory_namespace=lambda workspace_dir, session_id: False,
        stored_recovery_snapshot_from_session=lambda _session: _RecoverySnapshot(
            {
                "state": "interrupted",
                "summary": "resume required",
                "pending_approvals": [{"token": "tok-1"}],
            }
        ),
    )

    payload = handler.build_recovery_turn_context(_session())

    assert payload is not None
    assert payload["state"] == "interrupted"
    assert payload["resume_strategy"] == "next_message"
    assert payload["continue_hint"]
    assert payload["approval_hint"]


def test_recovery_reset_handler_applies_stored_recovery_fields() -> None:
    session = _session()
    handler = RuntimeSessionRecoveryResetHandler(
        refresh_session_diagnostics=lambda _session: ({}, {}),
        agent_knowledge_base_enabled=lambda _agent: True,
        clear_runtime_task_memory_namespace=lambda workspace_dir, session_id: False,
        stored_recovery_snapshot_from_session=lambda _session: None,
    )

    handler.apply_stored_recovery(
        session,
        _RecoverySnapshot(
            {
                "state": "handoff",
                "summary": "resume on next message",
                "last_activity": "shell finished",
                "last_user_message": "continue task",
                "last_assistant_message": "waiting",
                "pending_approvals": [_ApprovalItem({"token": "tok-2", "tool_name": "shell"})],
            }
        ),
    )

    assert session.projection.recovery_context_pending is True
    assert session.projection.recovery_state == "handoff"
    assert session.projection.recovery_summary == "resume on next message"
    assert session.projection.recovery_last_activity == "shell finished"
    assert session.projection.recovery_last_user_message == "continue task"
    assert session.projection.recovery_last_assistant_message == "waiting"
    assert session.projection.recovery_pending_approvals == [{"token": "tok-2", "tool_name": "shell"}]


def test_recovery_reset_handler_applies_interrupted_recovery_projection() -> None:
    session = _session()
    handler = RuntimeSessionRecoveryResetHandler(
        refresh_session_diagnostics=lambda _session: ({}, {}),
        agent_knowledge_base_enabled=lambda _agent: True,
        clear_runtime_task_memory_namespace=lambda workspace_dir, session_id: False,
        stored_recovery_snapshot_from_session=lambda _session: None,
    )

    handler.apply_interrupted_recovery(
        session,
        summary="interrupted after pause request: shell running",
        last_activity="shell running",
        pending_approvals=[{"token": "tok-3", "tool_name": "shell"}],
        now_utc=_dt(),
    )

    assert session.projection.recovery_context_pending is True
    assert session.projection.recovery_state == "interrupted"
    assert session.projection.recovery_summary == "interrupted after pause request: shell running"
    assert session.projection.recovery_last_activity == "shell running"
    assert session.projection.recovery_last_user_message == "continue"
    assert session.projection.recovery_last_assistant_message == "working"
    assert session.projection.recovery_pending_approvals == [{"token": "tok-3", "tool_name": "shell"}]
    assert session._touch_calls == [_dt()]


def test_recovery_reset_handler_clears_runtime_state_and_recovery_fields() -> None:
    session = _session(with_agent_reset_hook=True)
    cleared: list[tuple[str, str]] = []
    refreshed: list[str] = []

    def _refresh_session_diagnostics(target) -> tuple[dict[str, object], dict[str, object]]:  # noqa: ANN001
        target.projection.memory_diagnostics = {"rebuilt_for": target.session_id}
        target.projection.sandbox_diagnostics = {"approval_profile": "build"}
        refreshed.append(target.session_id)
        return target.projection.memory_diagnostics, target.projection.sandbox_diagnostics

    handler = RuntimeSessionRecoveryResetHandler(
        refresh_session_diagnostics=_refresh_session_diagnostics,
        agent_knowledge_base_enabled=lambda _agent: True,
        clear_runtime_task_memory_namespace=lambda workspace_dir, session_id: cleared.append(
            (workspace_dir, session_id)
        ) or True,
        stored_recovery_snapshot_from_session=lambda _session: None,
    )

    handler.reset_runtime_state(session, clear_runtime_task_memory=True)

    assert session.runtime.agent.messages == [{"role": "system", "content": "system"}]
    assert session.runtime.agent.api_total_tokens == 0
    assert session._agent_reset_calls == ["called"]
    assert cleared == [("workspace-1", "sess-1")]
    assert session.transcript_state.current_turn_id is None
    assert session.runtime.cancel_event is None
    assert session.runtime.pending_approvals == []
    assert session.runtime.pending_approval_waiters == {}
    assert session._future.done() is True
    assert session._future.result_value is None
    assert session.projection.recovery_context_pending is False
    assert session.projection.recovery_state == ""
    assert session.projection.recovery_summary == ""
    assert session.projection.recovery_last_activity is None
    assert session.projection.recovery_pending_approvals == []
    assert session.projection.last_prepared_context == {}
    assert session.projection.prepared_context_diagnostics == {}
    assert session.projection.busy is False
    assert session.projection.running_state == ""
    assert session.projection.knowledge_base_enabled is True
    assert refreshed == ["sess-1"]
    assert session.projection.memory_diagnostics == {"rebuilt_for": "sess-1"}
    assert session.projection.sandbox_diagnostics == {"approval_profile": "build"}


def test_recovery_reset_handler_clear_recovery_context_touches_session() -> None:
    session = _session()
    handler = RuntimeSessionRecoveryResetHandler(
        refresh_session_diagnostics=lambda _session: ({}, {}),
        agent_knowledge_base_enabled=lambda _agent: True,
        clear_runtime_task_memory_namespace=lambda workspace_dir, session_id: False,
        stored_recovery_snapshot_from_session=lambda _session: None,
    )

    handler.clear_recovery_context(session, now_utc=_dt())

    assert session.projection.recovery_context_pending is False
    assert session.projection.recovery_state == ""
    assert session._touch_calls == [_dt()]
