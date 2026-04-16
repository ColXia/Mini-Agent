"""Session cancel / approval routing extracted from the runtime manager."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable

from fastapi import HTTPException

from mini_agent.interfaces import MainAgentSessionApprovalResponse, MainAgentSessionMutationResponse
from mini_agent.runtime.session_cancel_service import SessionCancelService
from mini_agent.runtime.session_pending_approval_service import (
    PendingApprovalResolutionError,
    SessionPendingApprovalService,
)

if TYPE_CHECKING:
    import asyncio

    from mini_agent.runtime.session_state import MainAgentSessionState


def _safe_text(value: object) -> str:
    return " ".join(str(value or "").split())


@dataclass(slots=True)
class RuntimeSessionCancelExecution:
    response: MainAgentSessionMutationResponse
    transcript_details: str
    transcript_summary: str


@dataclass(slots=True)
class RuntimeSessionApprovalExecution:
    response: MainAgentSessionApprovalResponse
    transcript_command: str
    transcript_summary: str
    transcript_details: str
    token: str
    tool_name: str
    waiter: "asyncio.Future[bool | None]"
    decision_value: bool

    def finalize(self) -> None:
        if not self.waiter.done():
            self.waiter.set_result(self.decision_value)


@dataclass(slots=True)
class RuntimeSessionInterruptHandler:
    normalize_surface: Callable[[str | None], str | None]
    pending_approvals_from_raw: Callable[[Any], list[dict[str, Any]]]

    def execute_cancel(
        self,
        session: "MainAgentSessionState",
        *,
        reason: str | None,
    ) -> RuntimeSessionCancelExecution:
        if not session.projection.busy:
            raise HTTPException(status_code=409, detail=SessionCancelService.no_running_turn_detail())

        cancel_event = session.runtime.cancel_event
        if cancel_event is None:
            raise HTTPException(status_code=409, detail=SessionCancelService.not_cancellable_detail())

        if not cancel_event.is_set():
            cancel_event.set()
        for future in list(session.runtime.pending_approval_waiters.values()):
            if not future.done():
                future.set_result(None)

        active_surface = self.normalize_surface(session.projection.active_surface or session.projection.origin_surface)
        session.projection.running_state = SessionCancelService.REQUESTED_STATE
        return RuntimeSessionCancelExecution(
            response=MainAgentSessionMutationResponse(
                status=SessionCancelService.CANCEL_REQUESTED_STATUS,
                session_id=session.session_id,
                active_surface=active_surface,
            ),
            transcript_details=SessionCancelService.transcript_details(reason=reason),
            transcript_summary=SessionCancelService.requested_summary(),
        )

    def execute_approval(
        self,
        session: "MainAgentSessionState",
        *,
        approved: bool,
        token: str | None,
    ) -> RuntimeSessionApprovalExecution:
        pending = self.pending_approvals_from_raw(session.runtime.pending_approvals)
        try:
            target = SessionPendingApprovalService.resolve_target(
                pending=pending,
                token=token,
                recovery_context_pending=bool(session.projection.recovery_context_pending),
                recovery_pending_approvals=list(session.projection.recovery_pending_approvals or []),
            )
        except PendingApprovalResolutionError as exc:
            raise HTTPException(
                status_code=exc.status_code,
                detail=exc.detail,
            ) from exc

        future = session.runtime.pending_approval_waiters.get(target.token)
        try:
            SessionPendingApprovalService.ensure_waiter(future)
        except PendingApprovalResolutionError as exc:
            raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc

        resolution = SessionPendingApprovalService.build_decision(
            approved=approved,
            token=target.token,
            tool_name=target.tool_name,
        )
        return RuntimeSessionApprovalExecution(
            response=MainAgentSessionApprovalResponse(
                status="resolved",
                session_id=session.session_id,
                token=target.token,
                tool_name=target.tool_name,
                decision=resolution.decision,
                active_surface=self.normalize_surface(
                    session.projection.active_surface or session.projection.origin_surface
                ),
            ),
            transcript_command=resolution.command,
            transcript_summary=resolution.summary,
            transcript_details=resolution.transcript_details,
            token=target.token,
            tool_name=target.tool_name,
            waiter=future,
            decision_value=bool(approved),
        )

    @staticmethod
    def restart_pending_approval_detail() -> str:
        return SessionPendingApprovalService.restart_pending_approval_detail()

__all__ = [
    "RuntimeSessionApprovalExecution",
    "RuntimeSessionCancelExecution",
    "RuntimeSessionInterruptHandler",
]
