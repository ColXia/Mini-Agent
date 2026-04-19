"""Desktop session/run action helpers extracted from the main window surface."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from mini_agent.interfaces.agent import (
    MainAgentRunApprovalRequest,
    MainAgentRunCancelRequest,
    MainAgentRunInterruptRequest,
    MainAgentRunResumeRequest,
    MainAgentSessionApprovalRequest,
    MainAgentSessionControlRequest,
    MainAgentSessionCreateRequest,
    MainAgentSessionForkRequest,
    MainAgentSessionRenameRequest,
    MainAgentSessionShareRequest,
)
from mini_agent.interfaces.surface_payload_adapter import surface_payload_from_dto
from mini_agent.runtime.live_control.session_pending_approval_service import SessionPendingApprovalService
from mini_agent.session.recovery_feedback import SessionFeedbackService
from mini_agent.transport.gateway_error import extract_gateway_error_info


@dataclass(frozen=True, slots=True)
class DesktopSessionActionFeedback:
    """Normalized feedback emitted by desktop session/run actions."""

    status_text: str
    activity_message: str
    activity_kind: str = "session"
    preferred_session_id: str | None = None
    activity_detail: str | None = None
    response_payload: dict[str, Any] = field(default_factory=dict)
    updated_run_summary: dict[str, Any] | None = None


def _compact_text(value: Any) -> str:
    return " ".join(str(value or "").split())


def _first_pending_approval(
    detail: dict[str, Any] | None,
    run_summary: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    run_wait = (run_summary or {}).get("approval_wait") if isinstance(run_summary, dict) else None
    if isinstance(run_wait, dict):
        token = _compact_text(run_wait.get("approval_token"))
        tool_name = _compact_text(run_wait.get("tool_name"))
        if token or tool_name:
            return {
                "token": token or None,
                "tool_name": tool_name or "tool",
                "arguments": (
                    dict(run_wait.get("tool_arguments_summary") or {})
                    if isinstance(run_wait.get("tool_arguments_summary"), dict)
                    else {}
                ),
                "kind": _compact_text(run_wait.get("approval_kind")) or None,
                "reason": _compact_text(run_wait.get("policy_reason")) or None,
                "cache_key": _compact_text(run_wait.get("cache_key")) or None,
                "can_escalate": bool(run_wait.get("can_escalate")),
                "wait_id": _compact_text(run_wait.get("wait_id")) or None,
            }
    items = list((detail or {}).get("pending_approvals") or [])
    if not items:
        return None
    item = items[0]
    return item if isinstance(item, dict) else None


def desktop_error_detail(exc: Exception) -> str:
    """Normalize desktop-visible gateway/remote exception detail."""

    return _compact_text(extract_gateway_error_info(exc).detail) or _compact_text(exc) or "request failed"


def format_desktop_approval_failure(exc: Exception) -> tuple[str, str]:
    """Normalize remote approval failures for desktop activity/status surfaces."""

    detail = desktop_error_detail(exc) or "Approval failed."
    summary = SessionPendingApprovalService.error_summary(detail=detail)
    title = f"Approval failed: {detail}" if summary == "approval failed" else f"Approval {summary}: {detail}"
    status = SessionPendingApprovalService.error_status_text(detail=detail)
    return title, status


def perform_desktop_share_toggle(
    *,
    session_client: Any,
    session_id: str,
    selected_session_detail: dict[str, Any] | None,
) -> DesktopSessionActionFeedback:
    """Execute the desktop share toggle and normalize user-facing feedback."""

    detail = selected_session_detail if isinstance(selected_session_detail, dict) else {}
    next_shared = not bool(detail.get("shared"))
    response = session_client.set_session_shared_sync(
        session_id,
        MainAgentSessionShareRequest(shared=next_shared),
    )
    response_payload = surface_payload_from_dto(response)
    shared = bool(response_payload.get("shared"))
    title = _compact_text(response_payload.get("title")) or _compact_text(detail.get("title")) or session_id
    feedback = SessionFeedbackService.mutation_feedback(
        status=str(response_payload.get("status") or ("shared" if shared else "unshared")),
        title=title,
        shared=shared,
    )
    return DesktopSessionActionFeedback(
        status_text=feedback.status_text,
        activity_message=feedback.status_text,
        preferred_session_id=session_id,
        response_payload=response_payload,
    )


def perform_desktop_session_fork(
    *,
    session_client: Any,
    session_id: str,
    parent_title: str | None,
    requested_title: str | None,
) -> DesktopSessionActionFeedback:
    """Create a derived desktop session and normalize the resulting feedback."""

    response = session_client.create_derived_session_sync(
        session_id,
        MainAgentSessionForkRequest(
            title=_compact_text(requested_title) or None,
            surface="desktop",
        ),
    )
    response_payload = surface_payload_from_dto(response)
    created_id = _compact_text(response_payload.get("session_id"))
    created_title = _compact_text(response_payload.get("title")) or created_id or "derived session"
    feedback = SessionFeedbackService.fork_feedback(
        title=created_title,
        parent_title=_compact_text(parent_title) or session_id,
    )
    return DesktopSessionActionFeedback(
        status_text=feedback.status_text,
        activity_message=feedback.status_text,
        preferred_session_id=created_id or session_id,
        response_payload=response_payload,
    )


def perform_desktop_session_rename(
    *,
    session_client: Any,
    session_id: str,
    requested_title: str,
    fallback_title: str | None = None,
) -> DesktopSessionActionFeedback:
    """Rename the active desktop session and normalize the resulting feedback."""

    response = session_client.rename_session_sync(
        session_id,
        MainAgentSessionRenameRequest(title=_compact_text(requested_title)),
    )
    response_payload = surface_payload_from_dto(response)
    applied_title = _compact_text(response_payload.get("title")) or _compact_text(requested_title)
    applied_title = applied_title or _compact_text(fallback_title) or session_id
    feedback = SessionFeedbackService.mutation_feedback(
        status=str(response_payload.get("status") or "renamed"),
        title=applied_title,
        shared=(response_payload.get("shared") if isinstance(response_payload.get("shared"), bool) else None),
    )
    return DesktopSessionActionFeedback(
        status_text=feedback.status_text,
        activity_message=feedback.status_text,
        preferred_session_id=session_id,
        response_payload=response_payload,
    )


def perform_desktop_session_compact(
    *,
    session_client: Any,
    session_id: str,
    selected_session_title: str | None,
) -> DesktopSessionActionFeedback:
    """Compact the active desktop session and normalize the resulting feedback."""

    response = session_client.control_session_sync(
        session_id,
        MainAgentSessionControlRequest(
            action="compact",
            reason="desktop compact request",
            surface="desktop",
        ),
    )
    response_payload = surface_payload_from_dto(response)
    applied = bool(response_payload.get("applied"))
    before = int(response_payload.get("message_count_before") or 0)
    after = int(response_payload.get("message_count_after") or 0)
    title = _compact_text(selected_session_title) or session_id
    status_text = f"Compacted {title}." if applied else f"{title} was already compact."
    return DesktopSessionActionFeedback(
        status_text=status_text,
        activity_message=status_text,
        activity_kind="session",
        preferred_session_id=session_id,
        activity_detail=f"Messages: {before} -> {after}",
        response_payload=response_payload,
    )


def perform_desktop_session_creation(
    *,
    session_client: Any,
    workspace_dir: str,
    current_session_id: str | None,
) -> DesktopSessionActionFeedback:
    """Create a desktop session or a derived follow-up session."""

    if current_session_id:
        created = session_client.create_derived_session_sync(
            current_session_id,
            MainAgentSessionForkRequest(
                title="Session",
                surface="desktop",
            ),
        )
    else:
        created = session_client.create_session_sync(
            MainAgentSessionCreateRequest(
                workspace_dir=workspace_dir,
                surface="desktop",
                shared=False,
            )
        )

    created_payload = surface_payload_from_dto(created)
    session_id = _compact_text(created_payload.get("session_id"))
    created_title = _compact_text(created_payload.get("title")) or session_id or "unknown"
    create_feedback = SessionFeedbackService.creation_feedback(
        title=created_title,
        derived=bool(current_session_id),
    )
    return DesktopSessionActionFeedback(
        status_text=create_feedback.status_text,
        activity_message=create_feedback.status_text,
        activity_kind="session",
        preferred_session_id=session_id or current_session_id,
        response_payload=created_payload,
    )


def perform_desktop_pending_approval_resolution(
    *,
    run_client: Any,
    session_client: Any,
    session_id: str,
    run_id: str | None,
    selected_session_detail: dict[str, Any] | None,
    selected_run_summary: dict[str, Any] | None,
    approved: bool,
) -> DesktopSessionActionFeedback:
    """Resolve the current desktop approval against run truth when available."""

    pending = _first_pending_approval(selected_session_detail, selected_run_summary)
    token = _compact_text((pending or {}).get("token"))
    if not token:
        raise ValueError("No pending approval token is available.")

    if run_id:
        response = run_client.respond_to_approval_sync(
            run_id,
            MainAgentRunApprovalRequest(
                approved=approved,
                token=token,
                surface="desktop",
            ),
        )
    else:
        response = session_client.respond_to_approval_sync(
            session_id,
            MainAgentSessionApprovalRequest(
                approved=approved,
                token=token,
                surface="desktop",
            ),
        )

    response_payload = surface_payload_from_dto(response)
    decision = _compact_text(response_payload.get("decision")) or ("approved" if approved else "denied")
    tool_name = _compact_text(response_payload.get("tool_name")) or _compact_text((pending or {}).get("tool_name")) or "tool"
    updated_run_summary = response_payload if _compact_text(response_payload.get("run_id")) else None
    status_text = f"Approval {decision}: {tool_name}"
    return DesktopSessionActionFeedback(
        status_text=status_text,
        activity_message=status_text,
        activity_kind="approval",
        response_payload=response_payload,
        updated_run_summary=updated_run_summary,
    )


def desktop_run_can_cancel(
    run_summary: dict[str, Any] | None,
    *,
    send_busy: bool = False,
) -> bool:
    """Return whether the desktop surface should expose run-cancel affordance."""

    if send_busy:
        return True
    summary = run_summary if isinstance(run_summary, dict) else {}
    return bool(summary.get("busy") or summary.get("waiting_on_approval"))


def desktop_run_can_interrupt(
    run_summary: dict[str, Any] | None,
    *,
    send_busy: bool = False,
) -> bool:
    """Return whether the desktop surface should expose run-interrupt affordance."""

    if send_busy:
        return True
    summary = run_summary if isinstance(run_summary, dict) else {}
    return bool(
        summary.get("busy")
        and not bool(summary.get("waiting_on_approval"))
        and not bool(summary.get("interrupt_requested"))
        and not bool(summary.get("cancel_requested"))
    )


def desktop_run_can_resume(run_summary: dict[str, Any] | None) -> bool:
    """Return whether the desktop surface should expose run-resume affordance."""

    summary = run_summary if isinstance(run_summary, dict) else {}
    return bool(summary.get("resumable")) and not bool(summary.get("cancel_requested"))


def perform_desktop_run_cancel(
    *,
    run_client: Any,
    run_id: str,
    reason: str | None = None,
) -> DesktopSessionActionFeedback:
    """Request cancellation for the active desktop run."""

    response = run_client.cancel_run_sync(
        run_id,
        MainAgentRunCancelRequest(
            reason=_compact_text(reason) or "desktop cancel request",
            surface="desktop",
        ),
    )
    response_payload = surface_payload_from_dto(response)
    status_text = "Cancel requested for current turn."
    if not bool(response_payload.get("cancel_requested")) and not bool(response_payload.get("busy")):
        status_text = "Current turn is already idle."
    return DesktopSessionActionFeedback(
        status_text=status_text,
        activity_message=status_text,
        activity_kind="status",
        response_payload=response_payload,
        updated_run_summary=response_payload,
    )


def perform_desktop_run_interrupt(
    *,
    run_client: Any,
    run_id: str,
    reason: str | None = None,
) -> DesktopSessionActionFeedback:
    """Request interruption for the active desktop run."""

    response = run_client.interrupt_run_sync(
        run_id,
        MainAgentRunInterruptRequest(
            reason=_compact_text(reason) or "desktop interrupt request",
            surface="desktop",
        ),
    )
    response_payload = surface_payload_from_dto(response)
    status_text = "Interrupt requested for current turn."
    if not bool(response_payload.get("interrupt_requested")) and not bool(response_payload.get("busy")):
        status_text = "Current turn is already idle."
    return DesktopSessionActionFeedback(
        status_text=status_text,
        activity_message=status_text,
        activity_kind="status",
        response_payload=response_payload,
        updated_run_summary=response_payload,
    )


def perform_desktop_run_resume(
    *,
    run_client: Any,
    run_id: str,
    selected_run_summary: dict[str, Any] | None,
) -> DesktopSessionActionFeedback:
    """Resume the active desktop run through the run-level contract."""

    summary = selected_run_summary if isinstance(selected_run_summary, dict) else {}
    run_wait = summary.get("approval_wait") if isinstance(summary.get("approval_wait"), dict) else {}
    resume_token = _compact_text(run_wait.get("approval_token")) or None
    response = run_client.resume_run_sync(
        run_id,
        MainAgentRunResumeRequest(
            resume_token=resume_token,
            surface="desktop",
        ),
    )
    response_payload = surface_payload_from_dto(response)
    status_text = "Resume requested for current turn."
    if not bool(response_payload.get("busy")) and not bool(response_payload.get("waiting_on_approval")):
        status_text = "Current turn is already idle."
    return DesktopSessionActionFeedback(
        status_text=status_text,
        activity_message=status_text,
        activity_kind="status",
        response_payload=response_payload,
        updated_run_summary=response_payload,
    )


__all__ = [
    "DesktopSessionActionFeedback",
    "desktop_error_detail",
    "desktop_run_can_cancel",
    "desktop_run_can_interrupt",
    "desktop_run_can_resume",
    "format_desktop_approval_failure",
    "perform_desktop_pending_approval_resolution",
    "perform_desktop_run_cancel",
    "perform_desktop_run_interrupt",
    "perform_desktop_run_resume",
    "perform_desktop_session_compact",
    "perform_desktop_session_creation",
    "perform_desktop_session_fork",
    "perform_desktop_session_rename",
    "perform_desktop_share_toggle",
]
