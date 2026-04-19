"""Behavior tests for DesktopUI session/run action helpers."""

from __future__ import annotations

from typing import Any

from mini_agent.desktop.window import (
    desktop_run_can_cancel,
    desktop_run_can_interrupt,
    desktop_run_can_resume,
    perform_desktop_pending_approval_resolution,
    perform_desktop_run_cancel,
    perform_desktop_run_interrupt,
    perform_desktop_run_resume,
    perform_desktop_session_compact,
    perform_desktop_session_creation,
    perform_desktop_session_fork,
    perform_desktop_session_rename,
    perform_desktop_share_toggle,
)


class _FakeSessionClient:
    def __init__(self) -> None:
        self.share_calls: list[tuple[str, Any]] = []
        self.fork_calls: list[tuple[str, Any]] = []
        self.rename_calls: list[tuple[str, Any]] = []
        self.control_calls: list[tuple[str, Any]] = []
        self.create_calls: list[Any] = []
        self.approval_calls: list[tuple[str, Any]] = []

    def set_session_shared_sync(self, session_id: str, request: Any) -> dict[str, Any]:
        self.share_calls.append((session_id, request))
        return {
            "status": "shared" if request.shared else "unshared",
            "title": "Desk Session",
            "shared": bool(request.shared),
        }

    def create_derived_session_sync(self, session_id: str, request: Any) -> dict[str, Any]:
        self.fork_calls.append((session_id, request))
        return {
            "session_id": "sess-derived",
            "title": "Desk Session Copy",
        }

    def rename_session_sync(self, session_id: str, request: Any) -> dict[str, Any]:
        self.rename_calls.append((session_id, request))
        return {
            "status": "renamed",
            "title": request.title,
        }

    def control_session_sync(self, session_id: str, request: Any) -> dict[str, Any]:
        self.control_calls.append((session_id, request))
        return {
            "applied": True,
            "message_count_before": 18,
            "message_count_after": 7,
        }

    def create_session_sync(self, request: Any) -> dict[str, Any]:
        self.create_calls.append(request)
        return {
            "session_id": "sess-new",
            "title": "Fresh Session",
        }

    def respond_to_approval_sync(self, session_id: str, request: Any) -> dict[str, Any]:
        self.approval_calls.append((session_id, request))
        return {
            "session_id": session_id,
            "decision": "denied",
            "tool_name": "shell",
        }


class _FakeRunClient:
    def __init__(self) -> None:
        self.approval_calls: list[tuple[str, Any]] = []
        self.cancel_calls: list[tuple[str, Any]] = []
        self.interrupt_calls: list[tuple[str, Any]] = []
        self.resume_calls: list[tuple[str, Any]] = []

    def respond_to_approval_sync(self, run_id: str, request: Any) -> dict[str, Any]:
        self.approval_calls.append((run_id, request))
        return {
            "run_id": run_id,
            "decision": "approved",
            "tool_name": "shell",
            "phase": "awaiting_approval",
        }

    def cancel_run_sync(self, run_id: str, request: Any) -> dict[str, Any]:
        self.cancel_calls.append((run_id, request))
        return {
            "run_id": run_id,
            "busy": True,
            "cancel_requested": True,
            "phase": "running",
        }

    def interrupt_run_sync(self, run_id: str, request: Any) -> dict[str, Any]:
        self.interrupt_calls.append((run_id, request))
        return {
            "run_id": run_id,
            "busy": True,
            "interrupt_requested": True,
            "phase": "running",
        }

    def resume_run_sync(self, run_id: str, request: Any) -> dict[str, Any]:
        self.resume_calls.append((run_id, request))
        return {
            "run_id": run_id,
            "busy": True,
            "waiting_on_approval": False,
            "phase": "executing_tools",
        }


def test_perform_desktop_share_toggle_normalizes_feedback_and_target_session() -> None:
    session_client = _FakeSessionClient()

    feedback = perform_desktop_share_toggle(
        session_client=session_client,
        session_id="sess-1",
        selected_session_detail={"shared": False, "title": "Desk Session"},
    )

    assert len(session_client.share_calls) == 1
    session_id, request = session_client.share_calls[0]
    assert session_id == "sess-1"
    assert request.shared is True
    assert feedback.status_text == "Shared Desk Session to remote surfaces."
    assert feedback.activity_message == feedback.status_text
    assert feedback.preferred_session_id == "sess-1"


def test_perform_desktop_session_fork_uses_desktop_surface_and_created_session_target() -> None:
    session_client = _FakeSessionClient()

    feedback = perform_desktop_session_fork(
        session_client=session_client,
        session_id="sess-1",
        parent_title="Desk Session",
        requested_title="Desk Session Copy",
    )

    assert len(session_client.fork_calls) == 1
    session_id, request = session_client.fork_calls[0]
    assert session_id == "sess-1"
    assert request.surface == "desktop"
    assert request.title == "Desk Session Copy"
    assert feedback.status_text == "Forked Desk Session Copy from Desk Session."
    assert feedback.preferred_session_id == "sess-derived"


def test_perform_desktop_session_rename_normalizes_feedback_and_keeps_selected_session() -> None:
    session_client = _FakeSessionClient()

    feedback = perform_desktop_session_rename(
        session_client=session_client,
        session_id="sess-1",
        requested_title="Renamed Session",
        fallback_title="Desk Session",
    )

    assert len(session_client.rename_calls) == 1
    session_id, request = session_client.rename_calls[0]
    assert session_id == "sess-1"
    assert request.title == "Renamed Session"
    assert feedback.status_text == "Renamed session to Renamed Session."
    assert feedback.preferred_session_id == "sess-1"


def test_perform_desktop_session_compact_normalizes_counts_into_activity_detail() -> None:
    session_client = _FakeSessionClient()

    feedback = perform_desktop_session_compact(
        session_client=session_client,
        session_id="sess-1",
        selected_session_title="Desk Session",
    )

    assert len(session_client.control_calls) == 1
    session_id, request = session_client.control_calls[0]
    assert session_id == "sess-1"
    assert request.action == "compact"
    assert request.reason == "desktop compact request"
    assert request.surface == "desktop"
    assert feedback.status_text == "Compacted Desk Session."
    assert feedback.activity_detail == "Messages: 18 -> 7"
    assert feedback.preferred_session_id == "sess-1"


def test_perform_desktop_session_creation_creates_fresh_workspace_session_without_parent() -> None:
    session_client = _FakeSessionClient()

    feedback = perform_desktop_session_creation(
        session_client=session_client,
        workspace_dir="D:/file/Mini-Agent",
        current_session_id=None,
    )

    assert len(session_client.create_calls) == 1
    request = session_client.create_calls[0]
    assert request.workspace_dir == "D:/file/Mini-Agent"
    assert request.surface == "desktop"
    assert request.shared is False
    assert feedback.status_text == "Created Fresh Session."
    assert feedback.preferred_session_id == "sess-new"


def test_perform_desktop_session_creation_uses_derived_session_when_parent_exists() -> None:
    session_client = _FakeSessionClient()

    feedback = perform_desktop_session_creation(
        session_client=session_client,
        workspace_dir="D:/ignored",
        current_session_id="sess-parent",
    )

    assert session_client.create_calls == []
    assert len(session_client.fork_calls) == 1
    session_id, request = session_client.fork_calls[0]
    assert session_id == "sess-parent"
    assert request.title == "Session"
    assert request.surface == "desktop"
    assert feedback.status_text == "Created derived session Desk Session Copy."
    assert feedback.preferred_session_id == "sess-derived"


def test_desktop_run_can_cancel_when_busy_or_waiting_or_local_send_busy() -> None:
    assert desktop_run_can_cancel({}, send_busy=True) is True
    assert desktop_run_can_cancel({"busy": True}, send_busy=False) is True
    assert desktop_run_can_cancel({"waiting_on_approval": True}, send_busy=False) is True
    assert desktop_run_can_cancel({"busy": False, "waiting_on_approval": False}, send_busy=False) is False


def test_desktop_run_can_interrupt_requires_active_nonapproval_run() -> None:
    assert desktop_run_can_interrupt({}, send_busy=True) is True
    assert desktop_run_can_interrupt({"busy": True}, send_busy=False) is True
    assert desktop_run_can_interrupt({"busy": True, "waiting_on_approval": True}, send_busy=False) is False
    assert desktop_run_can_interrupt({"busy": True, "interrupt_requested": True}, send_busy=False) is False
    assert desktop_run_can_interrupt({"busy": True, "cancel_requested": True}, send_busy=False) is False
    assert desktop_run_can_interrupt({"busy": False}, send_busy=False) is False


def test_desktop_run_can_resume_requires_resumable_noncancelled_run() -> None:
    assert desktop_run_can_resume({"resumable": True}) is True
    assert desktop_run_can_resume({"resumable": True, "cancel_requested": True}) is False
    assert desktop_run_can_resume({"resumable": False}) is False


def test_perform_desktop_run_cancel_routes_through_run_contract() -> None:
    run_client = _FakeRunClient()

    feedback = perform_desktop_run_cancel(
        run_client=run_client,
        run_id="run:sess-1",
    )

    assert len(run_client.cancel_calls) == 1
    run_id, request = run_client.cancel_calls[0]
    assert run_id == "run:sess-1"
    assert request.reason == "desktop cancel request"
    assert request.surface == "desktop"
    assert feedback.status_text == "Cancel requested for current turn."
    assert feedback.updated_run_summary == {
        "run_id": "run:sess-1",
        "busy": True,
        "cancel_requested": True,
        "phase": "running",
    }


def test_perform_desktop_run_interrupt_routes_through_run_contract() -> None:
    run_client = _FakeRunClient()

    feedback = perform_desktop_run_interrupt(
        run_client=run_client,
        run_id="run:sess-1",
    )

    assert len(run_client.interrupt_calls) == 1
    run_id, request = run_client.interrupt_calls[0]
    assert run_id == "run:sess-1"
    assert request.reason == "desktop interrupt request"
    assert request.surface == "desktop"
    assert feedback.status_text == "Interrupt requested for current turn."
    assert feedback.updated_run_summary == {
        "run_id": "run:sess-1",
        "busy": True,
        "interrupt_requested": True,
        "phase": "running",
    }


def test_perform_desktop_run_resume_routes_through_run_contract_with_wait_token() -> None:
    run_client = _FakeRunClient()

    feedback = perform_desktop_run_resume(
        run_client=run_client,
        run_id="run:sess-1",
        selected_run_summary={
            "approval_wait": {
                "approval_token": "approval-1",
            }
        },
    )

    assert len(run_client.resume_calls) == 1
    run_id, request = run_client.resume_calls[0]
    assert run_id == "run:sess-1"
    assert request.resume_token == "approval-1"
    assert request.surface == "desktop"
    assert feedback.status_text == "Resume requested for current turn."
    assert feedback.updated_run_summary == {
        "run_id": "run:sess-1",
        "busy": True,
        "waiting_on_approval": False,
        "phase": "executing_tools",
    }


def test_perform_desktop_pending_approval_resolution_prefers_run_truth_when_available() -> None:
    session_client = _FakeSessionClient()
    run_client = _FakeRunClient()

    feedback = perform_desktop_pending_approval_resolution(
        run_client=run_client,
        session_client=session_client,
        session_id="sess-1",
        run_id="run:sess-1",
        selected_session_detail={
            "pending_approvals": [{"token": "session-token", "tool_name": "bash"}],
        },
        selected_run_summary={
            "approval_wait": {
                "approval_token": "run-token",
                "tool_name": "shell",
                "approval_kind": "tool",
                "policy_reason": "needs manual approval",
            }
        },
        approved=True,
    )

    assert len(run_client.approval_calls) == 1
    run_id, request = run_client.approval_calls[0]
    assert run_id == "run:sess-1"
    assert request.token == "run-token"
    assert request.approved is True
    assert request.surface == "desktop"
    assert session_client.approval_calls == []
    assert feedback.status_text == "Approval approved: shell"
    assert feedback.updated_run_summary == {
        "run_id": "run:sess-1",
        "decision": "approved",
        "tool_name": "shell",
        "phase": "awaiting_approval",
    }


def test_perform_desktop_pending_approval_resolution_falls_back_to_session_path_without_run_id() -> None:
    session_client = _FakeSessionClient()
    run_client = _FakeRunClient()

    feedback = perform_desktop_pending_approval_resolution(
        run_client=run_client,
        session_client=session_client,
        session_id="sess-2",
        run_id=None,
        selected_session_detail={
            "pending_approvals": [{"token": "session-token", "tool_name": "shell"}],
        },
        selected_run_summary={},
        approved=False,
    )

    assert run_client.approval_calls == []
    assert len(session_client.approval_calls) == 1
    session_id, request = session_client.approval_calls[0]
    assert session_id == "sess-2"
    assert request.token == "session-token"
    assert request.approved is False
    assert request.surface == "desktop"
    assert feedback.status_text == "Approval denied: shell"
    assert feedback.updated_run_summary is None
