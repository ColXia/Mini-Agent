from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from mini_agent.agent_core.contracts import RunControlMode
from mini_agent.runtime.live_control.session_live_state_handler import RuntimeSessionLiveStateHandler
from tests.runtime_contract_fixtures import (
    RuntimeContractAgentStub,
    runtime_projection_stub,
    runtime_session_stub,
    runtime_state_stub,
    transcript_state_stub,
)


def _dt() -> datetime:
    return datetime(2026, 4, 16, 9, 0, 0, tzinfo=timezone.utc)


class _RecoverySnapshot:
    def __init__(self, payload: dict[str, object]) -> None:
        self._payload = dict(payload)

    def model_dump(self) -> dict[str, object]:
        return dict(self._payload)


class _PendingFuture:
    def __init__(self) -> None:
        self._done = False
        self.result_value = None

    def done(self) -> bool:
        return self._done

    def set_result(self, value) -> None:  # noqa: ANN001
        self._done = True
        self.result_value = value


def _session_for_pending() -> object:
    touch_calls: list[datetime | None] = []

    def _touch(*, now_utc=None):  # noqa: ANN001
        touch_calls.append(now_utc)

    session = runtime_session_stub(
        runtime=runtime_state_stub(
            pending_approvals=[],
            pending_approval_waiters={},
        ),
        touch=_touch,
    )
    session._touch_calls = touch_calls
    return session


def _session_for_recovery() -> object:
    touch_calls: list[datetime | None] = []
    cleared_runtime_task_memory: list[tuple[str, str]] = []

    def _touch(*, now_utc=None):  # noqa: ANN001
        touch_calls.append(now_utc)

    agent = RuntimeContractAgentStub(
        messages=[
            {"role": "system", "content": "system"},
            {"role": "user", "content": "hello"},
        ],
        api_total_tokens=33,
        prepared_context={"recent": True},
        prepared_context_diagnostics={"ctx": True},
        last_memory_automation={"ran": True},
        last_runtime_task_memory={"key": "value"},
    )

    def _reset() -> None:
        agent._reset_called = True

    agent.reset_ephemeral_runtime_state = _reset
    pending_future = _PendingFuture()
    session = runtime_session_stub(
        session_id="sess-live",
        workspace_dir="workspace-live",
        runtime=runtime_state_stub(
            agent=agent,
            cancel_event=object(),
            pending_approvals=[{"token": "tok-1", "tool_name": "shell"}],
            pending_approval_waiters={"tok-1": pending_future},
        ),
        transcript_state=transcript_state_stub(current_turn_id="turn-1"),
        projection=runtime_projection_stub(
            recovery_context_pending=True,
            recovery_state="interrupted",
            recovery_summary="resume required",
            recovery_last_activity="shell running",
            recovery_last_user_message="continue",
            recovery_last_assistant_message="working",
            recovery_pending_approvals=[{"token": "tok-1"}],
            last_prepared_context={"before": True},
            prepared_context_diagnostics={"ctx": True},
            busy=True,
            running_state="running",
            knowledge_base_enabled=False,
            memory_diagnostics={"before": True},
            sandbox_diagnostics={"backend": "none"},
        ),
        touch=_touch,
    )
    session._touch_calls = touch_calls
    session._cleared_runtime_task_memory = cleared_runtime_task_memory
    session._pending_future = pending_future
    return session


def test_live_state_handler_compat_pending_approval_wrappers_use_default_support_owner() -> None:
    handler = RuntimeSessionLiveStateHandler()
    session = _session_for_pending()

    async def _run() -> None:
        future = asyncio.get_running_loop().create_future()
        normalized = handler.record_pending_approval(
            session,
            payload={"token": "tok-1", "tool_name": "shell", "step": 2},
            future=future,
            now_utc=_dt(),
        )

        assert normalized == {
            "token": "tok-1",
            "tool_name": "shell",
            "arguments": {},
            "kind": None,
            "reason": None,
            "cache_key": None,
            "can_escalate": False,
            "step": 2,
        }
        assert session.runtime.pending_approvals == [normalized]
        assert session.runtime.pending_approval_waiters["tok-1"] is future

        handler.clear_pending_approval(session, token="tok-1")
        assert session.runtime.pending_approvals == []
        assert session.runtime.pending_approval_waiters == {}

    asyncio.run(_run())

    assert RuntimeSessionLiveStateHandler.normalize_pending_approval({"token": "tok-2"}) == {
        "token": "tok-2",
        "tool_name": "tool",
        "arguments": {},
        "kind": None,
        "reason": None,
        "cache_key": None,
        "can_escalate": False,
        "step": 0,
    }
    assert RuntimeSessionLiveStateHandler.pending_approvals_from_raw(
        [{"token": "tok-3", "tool_name": "bash"}, {"tool_name": "missing-token"}]
    ) == [
        {
            "token": "tok-3",
            "tool_name": "bash",
            "arguments": {},
            "kind": None,
            "reason": None,
            "cache_key": None,
            "can_escalate": False,
            "step": 0,
        }
    ]
    assert session._touch_calls == [_dt(), None]


def test_live_state_handler_compat_legacy_recovery_wiring_builds_and_clears_context() -> None:
    session = _session_for_recovery()
    handler = RuntimeSessionLiveStateHandler(
        stored_recovery_snapshot_from_session=lambda _session: _RecoverySnapshot(
            {
                "state": "interrupted",
                "summary": "resume required",
                "pending_approvals": [{"token": "tok-1"}],
            }
        ),
    )

    payload = handler.build_recovery_turn_context(session)
    handler.clear_recovery_context(session, now_utc=_dt())

    assert payload is not None
    assert payload["state"] == "interrupted"
    assert payload["resume_strategy"] == "next_message"
    assert payload["approval_hint"]
    assert session.projection.recovery_context_pending is False
    assert session.projection.recovery_state == ""
    assert session.projection.recovery_summary == ""
    assert session.projection.recovery_pending_approvals == []
    assert session._touch_calls == [_dt()]


def test_live_state_handler_compat_legacy_recovery_wiring_resets_runtime_state() -> None:
    session = _session_for_recovery()
    cleared_runtime_task_memory = session._cleared_runtime_task_memory
    handler = RuntimeSessionLiveStateHandler(
        build_memory_diagnostics_for_session=lambda target: {"rebuilt_for": target.session_id},
        agent_knowledge_base_enabled=lambda _agent: True,
        clear_runtime_task_memory_namespace=lambda workspace_dir, session_id: cleared_runtime_task_memory.append(
            (workspace_dir, session_id)
        ) or True,
        stored_recovery_snapshot_from_session=lambda _session: None,
    )

    handler.reset_runtime_state(session, clear_runtime_task_memory=True)

    assert session.runtime.agent.messages == [{"role": "system", "content": "system"}]
    assert session.runtime.agent.api_total_tokens == 0
    assert session.runtime.agent._reset_called is True
    assert cleared_runtime_task_memory == [("workspace-live", "sess-live")]
    assert session.transcript_state.current_turn_id is None
    assert session.runtime.cancel_event is None
    assert session.runtime.pending_approvals == []
    assert session.runtime.pending_approval_waiters == {}
    assert session._pending_future.done() is True
    assert session._pending_future.result_value is None
    assert session.projection.recovery_context_pending is False
    assert session.projection.recovery_state == ""
    assert session.projection.recovery_summary == ""
    assert session.projection.last_prepared_context == {}
    assert session.projection.prepared_context_diagnostics == {}
    assert session.projection.busy is False
    assert session.projection.running_state == ""
    assert session.projection.knowledge_base_enabled is True
    assert session.projection.memory_diagnostics == {"rebuilt_for": "sess-live"}
    assert session.projection.sandbox_diagnostics == {"backend": "none"}


def test_live_state_handler_mark_turn_finished_pauses_interrupt_requested_runs() -> None:
    session = _session_for_pending()
    session.projection.busy = True
    session.projection.running_state = "step 2: running shell"
    handler = RuntimeSessionLiveStateHandler()

    async def _run() -> None:
        future = asyncio.get_running_loop().create_future()
        handler.mark_turn_started(session, surface="desktop", detail="desktop request running")
        handler.record_pending_approval(
            session,
            payload={"token": "tok-pause", "tool_name": "shell"},
            future=future,
        )
        handler._run_control_store().request_interrupt(session, reason="pause", source="desktop")
        session.projection.running_state = "step 2: running shell"

        handler.mark_turn_finished(session, now_utc=_dt())

        assert future.done() is True
        assert future.result() is None
        state = handler._run_control_store().current_control_state(session)
        assert state.control_mode is RunControlMode.PAUSED
        assert session.projection.busy is False
        assert session.projection.running_state == ""
        assert session.projection.recovery_context_pending is True
        assert session.projection.recovery_state == "interrupted"
        assert session.projection.recovery_summary == "interrupted after pause request: approval pending for shell"
        assert session.projection.recovery_pending_approvals == [
            {
                "token": "tok-pause",
                "tool_name": "shell",
                "arguments": {},
                "kind": None,
                "reason": None,
                "cache_key": None,
                "can_escalate": False,
                "step": 0,
            }
        ]

    asyncio.run(_run())


def test_live_state_handler_compat_prefers_injected_support_owners() -> None:
    class _PendingState:
        def __init__(self) -> None:
            self.record_calls: list[tuple[object, dict[str, object]]] = []
            self.clear_calls: list[tuple[object, str | None]] = []

        def record_pending_approval(self, session, *, payload, future, now_utc=None):  # noqa: ANN001, ANN003
            self.record_calls.append((session, dict(payload)))
            return {"token": "delegated", "tool_name": "shell"}

        def clear_pending_approval(self, session, *, token=None, now_utc=None):  # noqa: ANN001, ANN003
            self.clear_calls.append((session, token))

    class _RecoveryReset:
        def __init__(self) -> None:
            self.clear_calls: list[tuple[object, datetime | None]] = []
            self.reset_calls: list[tuple[object, bool]] = []

        def build_recovery_turn_context(self, session):  # noqa: ANN001
            return {"session_id": session.session_id, "resume_strategy": "delegated"}

        def clear_recovery_context(self, session, *, now_utc=None):  # noqa: ANN001, ANN003
            self.clear_calls.append((session, now_utc))

        def reset_runtime_state(self, session, *, clear_runtime_task_memory):  # noqa: ANN001, ANN003
            self.reset_calls.append((session, clear_runtime_task_memory))

    pending_state = _PendingState()
    recovery_reset = _RecoveryReset()
    handler = RuntimeSessionLiveStateHandler(
        pending_approval_state=pending_state,
        recovery_reset=recovery_reset,
    )
    session = _session_for_pending()

    async def _run() -> None:
        future = asyncio.get_running_loop().create_future()
        normalized = handler.record_pending_approval(
            session,
            payload={"token": "tok-9", "tool_name": "shell"},
            future=future,
        )
        assert normalized == {"token": "delegated", "tool_name": "shell"}

    asyncio.run(_run())

    assert handler.build_recovery_turn_context(session) == {
        "session_id": session.session_id,
        "resume_strategy": "delegated",
    }
    handler.clear_pending_approval(session, token="tok-9")
    handler.clear_recovery_context(session, now_utc=_dt())
    handler.reset_runtime_state(session, clear_runtime_task_memory=False)

    assert pending_state.record_calls == [(session, {"token": "tok-9", "tool_name": "shell"})]
    assert pending_state.clear_calls == [(session, "tok-9")]
    assert recovery_reset.clear_calls == [(session, _dt())]
    assert recovery_reset.reset_calls == [(session, False)]
