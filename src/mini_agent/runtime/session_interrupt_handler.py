"""Session cancel / approval routing extracted from the runtime manager."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable

from fastapi import HTTPException

from mini_agent.interfaces import MainAgentSessionApprovalResponse, MainAgentSessionMutationResponse

if TYPE_CHECKING:
    import asyncio

    from mini_agent.runtime.session_state import MainAgentSessionState


def _safe_text(value: object) -> str:
    return " ".join(str(value or "").split())


_RESTART_PENDING_APPROVAL_DETAIL = (
    "Pending approval was interrupted after restart and cannot be resumed directly. "
    "Send a new message to continue with recovery context."
)


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
            raise HTTPException(status_code=409, detail="Session has no running turn to cancel.")

        cancel_event = session.runtime.cancel_event
        if cancel_event is None:
            raise HTTPException(status_code=409, detail="Session turn is not cancellable.")

        if not cancel_event.is_set():
            cancel_event.set()
        for future in list(session.runtime.pending_approval_waiters.values()):
            if not future.done():
                future.set_result(None)

        active_surface = self.normalize_surface(session.projection.active_surface or session.projection.origin_surface)
        session.projection.running_state = "cancellation requested"
        return RuntimeSessionCancelExecution(
            response=MainAgentSessionMutationResponse(
                status="cancel_requested",
                session_id=session.session_id,
                active_surface=active_surface,
            ),
            transcript_details=self._cancel_details(reason),
            transcript_summary="cancellation requested",
        )

    def execute_approval(
        self,
        session: "MainAgentSessionState",
        *,
        approved: bool,
        token: str | None,
    ) -> RuntimeSessionApprovalExecution:
        pending = self.pending_approvals_from_raw(session.runtime.pending_approvals)
        if not pending:
            if session.projection.recovery_context_pending and session.projection.recovery_pending_approvals:
                raise HTTPException(status_code=409, detail=_RESTART_PENDING_APPROVAL_DETAIL)
            raise HTTPException(status_code=409, detail="Session has no pending approval.")

        normalized_token = _safe_text(token)
        if normalized_token:
            target = next((item for item in pending if item["token"] == normalized_token), None)
            if target is None:
                raise HTTPException(status_code=404, detail=f"Pending approval not found: {normalized_token}")
        elif len(pending) == 1:
            target = pending[0]
            normalized_token = target["token"]
        else:
            available = ", ".join(item["token"] for item in pending)
            raise HTTPException(
                status_code=409,
                detail=f"Multiple approvals pending. Specify a token: {available}",
            )

        future = session.runtime.pending_approval_waiters.get(normalized_token)
        if future is None or future.done():
            raise HTTPException(
                status_code=409,
                detail="Pending approval is no longer waiting for input.",
            )

        command = "approve" if approved else "deny"
        decision = "approved" if approved else "denied"
        return RuntimeSessionApprovalExecution(
            response=MainAgentSessionApprovalResponse(
                status="resolved",
                session_id=session.session_id,
                token=normalized_token,
                tool_name=target["tool_name"],
                decision=decision,
                active_surface=self.normalize_surface(
                    session.projection.active_surface or session.projection.origin_surface
                ),
            ),
            transcript_command=command,
            transcript_summary=f"{decision} {target['tool_name']}",
            transcript_details=self._approval_details(
                command=command,
                token=normalized_token,
                tool_name=target["tool_name"],
            ),
            token=normalized_token,
            tool_name=target["tool_name"],
            waiter=future,
            decision_value=bool(approved),
        )

    @staticmethod
    def restart_pending_approval_detail() -> str:
        return _RESTART_PENDING_APPROVAL_DETAIL

    @staticmethod
    def _cancel_details(reason: str | None) -> str:
        lines = [
            "Action: cancel",
            "State: cancellation requested",
        ]
        normalized_reason = _safe_text(reason)
        if normalized_reason:
            lines.append(f"Reason: {normalized_reason}")
        return "\n".join(lines)

    @staticmethod
    def _approval_details(
        *,
        command: str,
        token: str,
        tool_name: str,
    ) -> str:
        return "\n".join(
            [
                f"Action: {command}",
                f"Token: {token}",
                f"Tool: {tool_name}",
            ]
        )


__all__ = [
    "RuntimeSessionApprovalExecution",
    "RuntimeSessionCancelExecution",
    "RuntimeSessionInterruptHandler",
]
