"""Shared session pending-approval resolution semantics."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


def _safe_text(value: object) -> str:
    return " ".join(str(value or "").split())


_RESTART_PENDING_APPROVAL_DETAIL = (
    "Pending approval was interrupted after restart and cannot be resumed directly. "
    "Send a new message to continue with recovery context."
)


@dataclass(frozen=True, slots=True)
class PendingApprovalResolutionError(Exception):
    code: str
    detail: str

    @property
    def status_code(self) -> int:
        if self.code == "token_not_found":
            return 404
        return 409


@dataclass(frozen=True, slots=True)
class PendingApprovalTarget:
    token: str
    tool_name: str
    payload: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class PendingApprovalDecision:
    command: str
    decision: str
    summary: str
    transcript_details: str


class SessionPendingApprovalService:
    """Own token resolution and decision formatting for pending approvals."""

    @staticmethod
    def restart_pending_approval_detail() -> str:
        return _RESTART_PENDING_APPROVAL_DETAIL

    @classmethod
    def error_code_from_detail(cls, detail: str) -> str:
        normalized = _safe_text(detail)
        if normalized.startswith("Pending approval not found:"):
            return "token_not_found"
        if normalized.startswith("Multiple approvals pending."):
            return "token_required"
        if normalized == "Session has no pending approval.":
            return "nothing_pending"
        if "cannot be resumed directly" in normalized:
            return "restart_pending"
        if normalized == "Pending approval is no longer waiting for input.":
            return "not_waiting"
        return "failed"

    @classmethod
    def error_summary(cls, *, code: str | None = None, detail: str | None = None) -> str:
        resolved = _safe_text(code) or cls.error_code_from_detail(detail or "")
        if resolved == "token_not_found":
            return "token not found"
        if resolved == "token_required":
            return "token required"
        if resolved == "nothing_pending":
            return "nothing pending"
        if resolved == "restart_pending":
            return "recovery required"
        if resolved == "not_waiting":
            return "approval unavailable"
        return "approval failed"

    @classmethod
    def error_status_text(cls, *, code: str | None = None, detail: str | None = None) -> str:
        resolved = _safe_text(code) or cls.error_code_from_detail(detail or "")
        normalized = _safe_text(detail)
        if resolved == "token_required":
            return "Specify approval token."
        if resolved == "nothing_pending":
            return "No pending approval request."
        return normalized or "Remote approval failed."

    @classmethod
    def resolve_target(
        cls,
        *,
        pending: list[dict[str, Any]],
        token: str | None,
        recovery_context_pending: bool = False,
        recovery_pending_approvals: list[Any] | None = None,
    ) -> PendingApprovalTarget:
        if not pending:
            if recovery_context_pending and list(recovery_pending_approvals or []):
                raise PendingApprovalResolutionError(
                    code="restart_pending",
                    detail=cls.restart_pending_approval_detail(),
                )
            raise PendingApprovalResolutionError(
                code="nothing_pending",
                detail="Session has no pending approval.",
            )

        normalized_token = _safe_text(token)
        if normalized_token:
            target = next((item for item in pending if _safe_text(item.get("token")) == normalized_token), None)
            if target is None:
                raise PendingApprovalResolutionError(
                    code="token_not_found",
                    detail=f"Pending approval not found: {normalized_token}",
                )
        elif len(pending) == 1:
            target = pending[0]
            normalized_token = _safe_text(target.get("token"))
        else:
            available = ", ".join(
                _safe_text(item.get("token"))
                for item in pending
                if _safe_text(item.get("token"))
            )
            raise PendingApprovalResolutionError(
                code="token_required",
                detail=f"Multiple approvals pending. Specify a token: {available}",
            )

        return PendingApprovalTarget(
            token=normalized_token,
            tool_name=_safe_text(target.get("tool_name")) or "tool",
            payload=dict(target),
        )

    @staticmethod
    def ensure_waiter(waiter: Any) -> None:
        if waiter is None or bool(getattr(waiter, "done", lambda: True)()):
            raise PendingApprovalResolutionError(
                code="not_waiting",
                detail="Pending approval is no longer waiting for input.",
            )

    @staticmethod
    def build_decision(*, approved: bool, token: str, tool_name: str) -> PendingApprovalDecision:
        command = "approve" if approved else "deny"
        decision = "approved" if approved else "denied"
        return PendingApprovalDecision(
            command=command,
            decision=decision,
            summary=f"{decision} {tool_name}",
            transcript_details="\n".join(
                [
                    f"Action: {command}",
                    f"Token: {token}",
                    f"Tool: {tool_name}",
                ]
            ),
        )


__all__ = [
    "PendingApprovalDecision",
    "PendingApprovalResolutionError",
    "PendingApprovalTarget",
    "SessionPendingApprovalService",
]
