"""Session cancel / approval routing extracted from the runtime manager."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable

from fastapi import HTTPException

from mini_agent.interfaces.agent import MainAgentSessionApprovalResponse, MainAgentSessionMutationResponse
from mini_agent.runtime.live_control.session_cancel_service import SessionCancelService
from mini_agent.runtime.live_control.session_pending_approval_service import (
    PendingApprovalResolutionError,
    SessionPendingApprovalService,
)
from mini_agent.runtime.live_control.run_control_store import RuntimeSessionRunControlStore

if TYPE_CHECKING:
    import asyncio

    from mini_agent.session.store_records import MainAgentSessionState


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
    run_control_store: RuntimeSessionRunControlStore | None = None

    def execute_cancel(
        self,
        session: "MainAgentSessionState",
        *,
        reason: str | None,
    ) -> RuntimeSessionCancelExecution:
        if not session.projection.busy:
            raise HTTPException(status_code=409, detail=SessionCancelService.no_running_turn_detail())

        store = self._store()
        cancel_event = getattr(session.runtime, "cancel_event", None)
        if cancel_event is None:
            raise HTTPException(status_code=409, detail=SessionCancelService.not_cancellable_detail())

        store.request_cancel(
            session,
            source=session.projection.active_surface or session.projection.origin_surface,
            reason=reason,
        )

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
        store = self._store()
        pending = store.pending_approval_payloads(session)
        if not pending:
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

        future = store.pending_approval_waiter(session, token=target.token)
        if future is None:
            future = session.runtime.pending_approval_waiters.get(target.token)
        try:
            SessionPendingApprovalService.ensure_waiter(future)
        except PendingApprovalResolutionError as exc:
            raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
        store.resolve_active_approval_wait(
            session,
            token=target.token,
            approved=approved,
        )

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

    def _store(self) -> RuntimeSessionRunControlStore:
        if self.run_control_store is None:
            self.run_control_store = RuntimeSessionRunControlStore()
        return self.run_control_store


__all__ = [
    "RuntimeSessionApprovalExecution",
    "RuntimeSessionCancelExecution",
    "RuntimeSessionInterruptHandler",
]



