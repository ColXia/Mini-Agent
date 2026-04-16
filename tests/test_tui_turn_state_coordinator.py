from __future__ import annotations

from types import SimpleNamespace

from mini_agent.tui.session_turn_state_coordinator import TuiSessionTurnStateCoordinator


def _session():
    return SimpleNamespace(
        projection=SimpleNamespace(
            busy=False,
            active_surface="remote",
            reply_enabled=True,
            running_state="idle",
            pending_approvals=[{"token": "tok-1"}],
        ),
        runtime=SimpleNamespace(
            active_task_id=None,
            cancel_event=object(),
        ),
        view=SimpleNamespace(
            active_activity_message_index=4,
        ),
    )


def test_tui_turn_state_coordinator_manages_local_turn_state() -> None:
    session = _session()
    coordinator = TuiSessionTurnStateCoordinator()

    coordinator.begin_local_turn(session, task_id="task-1", resuming=False)
    assert session.projection.busy is True
    assert session.runtime.active_task_id == "task-1"
    assert session.runtime.cancel_event is None
    assert session.projection.running_state == "starting run"
    assert session.projection.pending_approvals == []

    session.projection.pending_approvals = [{"token": "tok-2"}]
    coordinator.finish_local_turn(session)
    assert session.runtime.active_task_id is None
    assert session.projection.busy is False
    assert session.runtime.cancel_event is None
    assert session.projection.running_state == ""
    assert session.view.active_activity_message_index is None
    assert session.projection.pending_approvals == []


def test_tui_turn_state_coordinator_manages_resume_and_remote_turn_state() -> None:
    session = _session()
    coordinator = TuiSessionTurnStateCoordinator()

    coordinator.begin_local_turn(session, task_id="task-2", resuming=True)
    assert session.projection.running_state == "resuming after restart"

    coordinator.begin_remote_turn(session, task_id="task-remote")
    assert session.projection.busy is True
    assert session.runtime.active_task_id == "task-remote"
    assert session.projection.active_surface == "tui"
    assert session.projection.reply_enabled is False
    assert session.projection.running_state == "gateway request running"
    assert session.projection.pending_approvals == []

    session.projection.pending_approvals = [{"token": "tok-r"}]
    coordinator.finish_remote_turn(session)
    assert session.runtime.active_task_id is None
    assert session.projection.busy is False
    assert session.projection.running_state == ""
    assert session.projection.pending_approvals == [{"token": "tok-r"}]
