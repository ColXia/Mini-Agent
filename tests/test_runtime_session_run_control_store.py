from __future__ import annotations

import asyncio
from pathlib import Path

from mini_agent.agent_core.contracts import ApprovalWaitState, RunControlMode
from mini_agent.runtime.live_control.run_control_store import RuntimeSessionRunControlStore
from mini_agent.workspace_runtime import capture_shared_workspace_snapshot
from tests.runtime_contract_fixtures import runtime_projection_stub, runtime_session_stub, runtime_state_stub


def _session(tmp_path: Path):
    return runtime_session_stub(
        session_id="sess-run-control",
        workspace_dir=tmp_path / "workspace",
        projection=runtime_projection_stub(
            busy=False,
            active_surface="desktop",
            origin_surface="desktop",
            running_state="",
            channel_type=None,
            conversation_id=None,
            sender_id=None,
        ),
        runtime=runtime_state_stub(
            pending_approvals=[],
            pending_approval_waiters={},
        ),
    )


def test_run_control_store_tracks_active_approval_wait_and_syncs_compatibility(tmp_path: Path) -> None:
    async def _run() -> None:
        store = RuntimeSessionRunControlStore()
        session = _session(tmp_path)

        state = store.begin_turn(session)
        assert state.control_mode is RunControlMode.NORMAL
        assert isinstance(session.runtime.cancel_event, asyncio.Event)
        assert session.runtime.pending_approvals == []

        future = asyncio.get_running_loop().create_future()
        wait = store.replace_active_approval_wait(
            session,
            payload={
                "token": "approval-1",
                "tool_name": "bash",
                "arguments": {"command": "pytest -q"},
                "kind": "exec",
                "reason": "needs approval",
                "cache_key": "shell:1",
                "can_escalate": True,
                "step": 2,
            },
            future=future,
        )

        assert wait.is_pending is True
        assert store.current_control_state(session).control_mode is RunControlMode.APPROVAL_WAIT
        assert session.runtime.pending_approvals == [
            {
                "token": "approval-1",
                "tool_name": "bash",
                "arguments": {"command": "pytest -q"},
                "kind": "exec",
                "reason": "needs approval",
                "cache_key": "shell:1",
                "can_escalate": True,
                "step": 2,
            }
        ]
        assert store.pending_approval_waiter(session, token="approval-1") is future

        resolved, waiter = store.resolve_active_approval_wait(
            session,
            token="approval-1",
            approved=True,
        )

        assert resolved is not None
        assert resolved.wait_state is ApprovalWaitState.RESOLVED
        assert waiter is future
        assert store.current_control_state(session).control_mode is RunControlMode.NORMAL
        assert session.runtime.pending_approvals == []
        assert session.runtime.pending_approval_waiters == {}

    asyncio.run(_run())


def test_run_control_store_cancel_and_reset_keep_truth_then_clear_projection(tmp_path: Path) -> None:
    async def _run() -> None:
        store = RuntimeSessionRunControlStore()
        session = _session(tmp_path)
        store.begin_turn(session)

        future = asyncio.get_running_loop().create_future()
        store.replace_active_approval_wait(
            session,
            payload={"token": "approval-2", "tool_name": "shell"},
            future=future,
        )

        cancelled = store.request_cancel(session, reason="stop now", source="desktop")

        assert cancelled.control_mode is RunControlMode.CANCEL_REQUESTED
        assert cancelled.cancel_requested is True
        assert future.done() is True
        assert future.result() is None
        assert session.runtime.pending_approvals == [
            {
                "token": "approval-2",
                "tool_name": "shell",
                "arguments": {},
                "kind": None,
                "reason": None,
                "cache_key": None,
                "can_escalate": False,
                "step": 0,
            }
        ]

        store.reset_runtime_state(session, reason="runtime reset")

        assert store.current_control_state(session).control_mode is RunControlMode.TERMINAL
        wait = store.current_approval_wait(session)
        assert wait is not None
        assert wait.wait_state is ApprovalWaitState.INVALIDATED
        assert session.runtime.cancel_event is None
        assert session.runtime.pending_approvals == []
        assert session.runtime.pending_approval_waiters == {}

    asyncio.run(_run())


def test_run_control_store_interrupt_projection_stays_distinct_from_cancel(tmp_path: Path) -> None:
    async def _run() -> None:
        store = RuntimeSessionRunControlStore()
        session = _session(tmp_path)
        session.projection.busy = True

        store.begin_turn(session)
        interrupted = store.request_interrupt(session, reason="pause", source="desktop")
        projection = store.build_active_run_projection(session)

        assert interrupted.control_mode is RunControlMode.INTERRUPT_REQUESTED
        assert interrupted.interrupt_requested is True
        assert interrupted.cancel_requested is False
        assert session.runtime.cancel_event is not None
        assert session.runtime.cancel_event.is_set() is True
        assert projection["status"] == "interrupt_requested"
        assert projection["phase"] == "interrupting"
        assert projection["control_mode"] == "interrupt_requested"
        assert projection["interrupt_requested"] is True
        assert projection["cancel_requested"] is False

    asyncio.run(_run())


def test_run_control_store_pause_turn_acknowledges_interrupt_and_clears_waiters(tmp_path: Path) -> None:
    async def _run() -> None:
        store = RuntimeSessionRunControlStore()
        session = _session(tmp_path)
        session.projection.busy = True
        store.begin_turn(session)

        future = asyncio.get_running_loop().create_future()
        store.replace_active_approval_wait(
            session,
            payload={"token": "approval-pause", "tool_name": "shell"},
            future=future,
        )
        store.request_interrupt(session, reason="pause", source="desktop")

        paused = store.pause_turn(session, reason="safe boundary")

        assert paused.control_mode is RunControlMode.PAUSED
        assert paused.interrupt_requested is False
        assert paused.cancel_requested is False
        assert paused.last_pause_reason == "safe boundary"
        assert future.done() is True
        assert future.result() is None
        assert session.runtime.cancel_event is None
        assert session.runtime.pending_approvals == []
        assert session.runtime.pending_approval_waiters == {}
        wait = store.current_approval_wait(session)
        assert wait is not None
        assert wait.wait_state is ApprovalWaitState.INVALIDATED

    asyncio.run(_run())


def test_run_control_store_active_projection_exposes_checkpoint_summary(tmp_path: Path) -> None:
    store = RuntimeSessionRunControlStore()
    session = _session(tmp_path)
    store.begin_turn(session)

    capture_shared_workspace_snapshot(
        session.workspace_dir,
        snapshot_id="live-snap-1",
        metadata={"trigger": "test"},
    )

    projection = store.build_active_run_projection(session)

    assert projection["checkpoint"] is not None
    assert projection["checkpoint"]["checkpoint_id"] == "live-snap-1"
    assert projection["checkpoint"]["kind"] == "workspace_runtime_snapshot"
    assert projection["checkpoint"]["source"] == "live_workspace_runtime"
    assert projection["checkpoint"]["workspace_dir"] == str(session.workspace_dir.resolve())
    assert projection["checkpoint"]["runtime_mode"] == "direct"
    assert projection["checkpoint"]["access_scope"] == "workspace_only"


def test_run_control_store_persisted_projection_exposes_checkpoint_summary(tmp_path: Path) -> None:
    run_id = RuntimeSessionRunControlStore.run_id_for_session("sess-persisted-run")
    record = {
        "session_id": "sess-persisted-run",
        "workspace_runtime_snapshot": {
            "snapshot_id": "persisted-snap-1",
            "created_at": "2026-04-18T09:15:00+00:00",
            "workspace_dir": str((tmp_path / "workspace").resolve()),
            "mode": "direct",
            "scope": "workspace_only",
            "mutation_count": 4,
        },
    }

    projection = RuntimeSessionRunControlStore.build_persisted_run_projection(run_id=run_id, record=record)

    assert projection["checkpoint"] is not None
    assert projection["checkpoint"]["checkpoint_id"] == "persisted-snap-1"
    assert projection["checkpoint"]["kind"] == "workspace_runtime_snapshot"
    assert projection["checkpoint"]["source"] == "persisted_workspace_runtime"
    assert projection["checkpoint"]["mutation_count"] == 4
