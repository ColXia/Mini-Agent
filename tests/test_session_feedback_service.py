from __future__ import annotations

from mini_agent.session import SessionFeedbackService


def test_session_feedback_service_builds_share_status() -> None:
    feedback = SessionFeedbackService.mutation_feedback(
        status="shared",
        title="Session 1",
        shared=True,
    )

    assert feedback.summary == "shared"
    assert feedback.status_text == "Shared Session 1 to remote surfaces."


def test_session_feedback_service_builds_unshare_status() -> None:
    feedback = SessionFeedbackService.mutation_feedback(
        status="unshared",
        title="Session 1",
        shared=False,
    )

    assert feedback.summary == "unshared"
    assert feedback.status_text == "Unshared Session 1."


def test_session_feedback_service_builds_rename_delete_and_reset_status() -> None:
    renamed = SessionFeedbackService.mutation_feedback(status="renamed", title="Focus")
    deleted = SessionFeedbackService.mutation_feedback(status="deleted", title="Focus")
    reset = SessionFeedbackService.mutation_feedback(status="reset", title="Focus")

    assert renamed.status_text == "Renamed session to Focus."
    assert deleted.status_text == "Deleted session Focus."
    assert reset.status_text == "Reset remote session Focus."


def test_session_feedback_service_builds_create_and_derived_create_status() -> None:
    created = SessionFeedbackService.creation_feedback(title="Session 2")
    derived = SessionFeedbackService.creation_feedback(title="Task Branch", derived=True)

    assert created.summary == "created"
    assert created.status_text == "Created Session 2."
    assert derived.summary == "created"
    assert derived.status_text == "Created derived session Task Branch."


def test_session_feedback_service_builds_fork_status() -> None:
    feedback = SessionFeedbackService.fork_feedback(
        title="Task: clean up service layer",
        parent_title="Session 1",
    )

    assert feedback.summary == "forked"
    assert feedback.status_text == "Forked Task: clean up service layer from Session 1."
