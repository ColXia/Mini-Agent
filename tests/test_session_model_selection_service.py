from __future__ import annotations

from mini_agent.model_manager.session_selection_service import SessionModelSelectionService


def test_session_model_selection_service_builds_queued_feedback() -> None:
    feedback = SessionModelSelectionService.queued_feedback(
        model_label="openai/gpt-5.3",
        session_title="Session 1",
    )

    assert feedback.status_text == "Queued openai/gpt-5.3 for Session 1; it will apply after the current turn."
    assert feedback.compact_text == "Model queued: openai/gpt-5.3"


def test_session_model_selection_service_builds_applied_feedback() -> None:
    feedback = SessionModelSelectionService.applied_feedback(
        model_label="openai/gpt-5.3",
        session_title="Session 1",
    )

    assert feedback.status_text == "Applied openai/gpt-5.3 to Session 1."
    assert feedback.compact_text == "Model applied: openai/gpt-5.3"


def test_session_model_selection_service_builds_already_selected_and_already_queued_feedback() -> None:
    already_selected = SessionModelSelectionService.already_selected_feedback(
        model_label="openai/gpt-5.3",
        session_title="Session 1",
    )
    already_queued = SessionModelSelectionService.already_queued_feedback(
        model_label="openai/gpt-5.3",
        session_title="Session 1",
    )

    assert already_selected.status_text == "Session 1 is already using openai/gpt-5.3."
    assert already_selected.compact_text == "Model already selected: openai/gpt-5.3"
    assert already_queued.status_text == "openai/gpt-5.3 is already queued for Session 1."
    assert already_queued.compact_text == "Model already queued: openai/gpt-5.3"
