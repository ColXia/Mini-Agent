from __future__ import annotations

from mini_agent.tui.session_turn_outcome_coordinator import TuiSessionTurnOutcomeCoordinator


def test_tui_turn_outcome_coordinator_resolves_local_turn_outcomes() -> None:
    coordinator = TuiSessionTurnOutcomeCoordinator()

    success = coordinator.resolve_local_completion(
        session_title="Session 1",
        state="completed",
        stop_reason="",
        message="done",
        error="",
    )
    assert success.kind == "success"
    assert success.task_status == "completed"
    assert success.task_stop_reason == "end_turn"
    assert success.task_note == "ok"
    assert success.activity_detail == "response ready"
    assert success.status_text == "Completed turn for Session 1."
    assert success.system_message is None

    cancelled = coordinator.resolve_local_completion(
        session_title="Session 1",
        state="interrupted",
        stop_reason="",
        message="",
        error="",
    )
    assert cancelled.kind == "cancelled"
    assert cancelled.task_status == "cancelled"
    assert cancelled.task_stop_reason == "interrupted"
    assert cancelled.task_note == "cancelled"
    assert cancelled.activity_detail == "cancelled"
    assert cancelled.status_text == "Cancelled turn for Session 1."
    assert cancelled.system_message == "Task cancelled by user."

    limited = coordinator.resolve_local_completion(
        session_title="Session 1",
        state="completed",
        stop_reason="max_turn_requests",
        message="",
        error="",
    )
    assert limited.kind == "limit"
    assert limited.task_status == "completed"
    assert limited.task_stop_reason == "max_turn_requests"
    assert limited.task_note == "max_turn_requests"
    assert limited.activity_detail == "turn limit reached"
    assert limited.status_text == "Turn reached limits for Session 1."
    assert limited.system_message == "Turn reached max request limit."

    failure = coordinator.resolve_local_completion(
        session_title="Session 1",
        state="failed",
        stop_reason="",
        message="",
        error="tool exploded",
    )
    assert failure.kind == "failure"
    assert failure.task_status == "completed"
    assert failure.task_stop_reason == "failed"
    assert failure.task_note == "tool exploded"
    assert failure.activity_detail == "run failed"
    assert failure.status_text == "Turn failed for Session 1."
    assert failure.system_message == "tool exploded"

    exception = coordinator.resolve_local_exception(detail="boom")
    assert exception.kind == "exception"
    assert exception.task_status == "completed"
    assert exception.task_stop_reason == "exception"
    assert exception.task_note == "boom"
    assert exception.activity_detail == "exception raised"
    assert exception.status_text == "Turn failed: boom"
    assert exception.system_message == "Turn failed: boom"


def test_tui_turn_outcome_coordinator_resolves_remote_turn_outcomes() -> None:
    coordinator = TuiSessionTurnOutcomeCoordinator()

    success = coordinator.resolve_remote_completion(
        session_title="Remote Session",
        stop_reason="end_turn",
        reply_text="remote done",
    )
    assert success.kind == "success"
    assert success.task_status == "completed"
    assert success.task_stop_reason == "end_turn"
    assert success.task_note == "ok"
    assert success.activity_detail == "response ready"
    assert success.status_text == "Completed remote turn for Remote Session."
    assert success.system_message is None

    cancelled = coordinator.resolve_remote_completion(
        session_title="Remote Session",
        stop_reason="cancelled",
        reply_text="",
    )
    assert cancelled.kind == "cancelled"
    assert cancelled.task_status == "cancelled"
    assert cancelled.task_stop_reason == "cancelled"
    assert cancelled.task_note == "cancelled"
    assert cancelled.activity_detail == "cancelled"
    assert cancelled.status_text == "Cancelled remote turn for Remote Session."
    assert cancelled.system_message == "Task cancelled by user."

    limited = coordinator.resolve_remote_completion(
        session_title="Remote Session",
        stop_reason="max_turn_requests",
        reply_text="",
    )
    assert limited.kind == "limit"
    assert limited.task_status == "completed"
    assert limited.task_stop_reason == "max_turn_requests"
    assert limited.task_note == "max_turn_requests"
    assert limited.activity_detail == "turn limit reached"
    assert limited.status_text == "Remote turn reached limits for Remote Session."
    assert limited.system_message == "Turn reached max request limit."

    failure = coordinator.resolve_remote_completion(
        session_title="Remote Session",
        stop_reason="refused",
        reply_text="",
    )
    assert failure.kind == "failure"
    assert failure.task_status == "completed"
    assert failure.task_stop_reason == "refused"
    assert failure.task_note == "refusal_or_failure"
    assert failure.activity_detail == "run failed"
    assert failure.status_text == "Remote turn failed for Remote Session."
    assert failure.system_message == "Remote turn ended with refusal."

    exception = coordinator.resolve_remote_exception(
        session_title="Remote Session",
        detail="upstream stream exploded",
    )
    assert exception.kind == "exception"
    assert exception.task_status == "completed"
    assert exception.task_stop_reason == "exception"
    assert exception.task_note == "upstream stream exploded"
    assert exception.activity_detail == "exception raised"
    assert exception.status_text == "Remote turn failed for Remote Session: upstream stream exploded"
    assert exception.system_message == "Remote turn failed: upstream stream exploded"
