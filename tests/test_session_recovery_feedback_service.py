from __future__ import annotations

from mini_agent.session.projections import (
    SessionPendingApprovalProjection,
    SessionRecoveryProjection,
)
from mini_agent.session.recovery_feedback import SessionRecoveryFeedbackService


def test_session_recovery_feedback_service_builds_live_status_text() -> None:
    text = SessionRecoveryFeedbackService.build_remote_recovery_text(
        session_id="sess-live",
        origin_surface="qq",
        active_surface="qq",
        reply_enabled=True,
        recovery=SessionRecoveryProjection(
            state="running",
            summary="qq request running",
            last_activity="shell running | pytest -q",
            last_user_message="run the full suite",
            last_assistant_message="working on it now",
        ),
        pending_approvals=(
            SessionPendingApprovalProjection(
                token="tok-1",
                tool_name="shell",
                arguments={"command": "pytest -q"},
            ),
        ),
        pending_skill_reload=True,
        pending_skill_reload_reason="skill added",
    )

    assert "route: qq / reply" in text
    assert "state: running" in text
    assert "task: qq request running" in text
    assert "pending approvals: shell[tok-1]" in text
    assert "skills: reload pending (skill added)" in text


def test_session_recovery_feedback_service_builds_restart_resume_hint() -> None:
    text = SessionRecoveryFeedbackService.build_remote_recovery_text(
        session_id="sess-restart",
        origin_surface="tui",
        active_surface="qq",
        reply_enabled=True,
        recovery=SessionRecoveryProjection(
            state="interrupted",
            summary="interrupted after restart: approval pending for shell",
            last_activity="shell ok | pytest -q | 32 passed",
            pending_approvals=(
                SessionPendingApprovalProjection(
                    token="approval-1",
                    tool_name="shell",
                    arguments={"command": "pytest -q"},
                ),
            ),
        ),
        pending_approvals=(),
    )

    assert "route: tui->qq / reply" in text
    assert "lost approvals after restart: shell[approval-1]" in text
    assert "resume hint: send a new message to continue with recovery context" in text

