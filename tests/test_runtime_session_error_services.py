from __future__ import annotations

from mini_agent.runtime.live_control.session_cancel_service import SessionCancelService
from mini_agent.runtime.handlers.session_agent_control_handler import SessionControlErrorService
from mini_agent.runtime.live_control.session_pending_approval_service import SessionPendingApprovalService


def test_session_control_error_service_maps_busy_detail() -> None:
    detail = SessionControlErrorService.busy_detail()

    assert SessionControlErrorService.is_busy_detail(detail) is True
    assert SessionControlErrorService.remote_summary(detail) == "session busy"
    assert SessionControlErrorService.remote_status_text(detail) == detail


def test_session_pending_approval_service_maps_remote_detail_to_summary_and_status() -> None:
    detail = "Multiple approvals pending. Specify a token: approval-1, approval-2"

    assert SessionPendingApprovalService.error_code_from_detail(detail) == "token_required"
    assert SessionPendingApprovalService.error_summary(detail=detail) == "token required"
    assert SessionPendingApprovalService.error_status_text(detail=detail) == "Specify approval token."


def test_session_cancel_service_matches_no_running_turn_detail() -> None:
    assert SessionCancelService.is_no_running_turn_detail(
        "Session has no running turn to cancel."
    ) is True
