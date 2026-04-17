"""Durable approval-wait contracts."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from enum import Enum
from typing import Any


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _clean_text(value: object) -> str | None:
    text = " ".join(str(value or "").split())
    return text or None


class ApprovalWaitState(str, Enum):
    """Lifecycle states for one durable approval wait."""

    PENDING = "pending"
    RESOLVED = "resolved"
    INVALIDATED = "invalidated"


class ApprovalDecision(str, Enum):
    """Stable approval outcomes."""

    APPROVED = "approved"
    DENIED = "denied"


@dataclass(frozen=True, slots=True)
class ApprovalWait:
    """Durable approval-blocking record owned by one run."""

    wait_id: str
    run_id: str
    session_id: str | None = None
    workspace_id: str | None = None
    approval_token: str | None = None
    tool_name: str = "tool"
    tool_arguments_summary: dict[str, Any] = field(default_factory=dict)
    approval_kind: str | None = None
    policy_reason: str | None = None
    cache_key: str | None = None
    can_escalate: bool = False
    wait_state: ApprovalWaitState = ApprovalWaitState.PENDING
    decision_result: ApprovalDecision | None = None
    created_at: datetime | None = None
    resolved_at: datetime | None = None
    invalidated_reason: str | None = None

    def __post_init__(self) -> None:
        normalized_wait_id = _clean_text(self.wait_id)
        normalized_run_id = _clean_text(self.run_id)
        if not normalized_wait_id:
            raise ValueError("wait_id is required")
        if not normalized_run_id:
            raise ValueError("run_id is required")
        object.__setattr__(self, "wait_id", normalized_wait_id)
        object.__setattr__(self, "run_id", normalized_run_id)
        object.__setattr__(self, "session_id", _clean_text(self.session_id))
        object.__setattr__(self, "workspace_id", _clean_text(self.workspace_id))
        object.__setattr__(self, "approval_token", _clean_text(self.approval_token))
        object.__setattr__(self, "tool_name", _clean_text(self.tool_name) or "tool")
        object.__setattr__(self, "approval_kind", _clean_text(self.approval_kind))
        object.__setattr__(self, "policy_reason", _clean_text(self.policy_reason))
        object.__setattr__(self, "cache_key", _clean_text(self.cache_key))
        object.__setattr__(self, "invalidated_reason", _clean_text(self.invalidated_reason))
        object.__setattr__(self, "tool_arguments_summary", dict(self.tool_arguments_summary or {}))
        if self.created_at is None:
            object.__setattr__(self, "created_at", _utc_now())

    @property
    def is_pending(self) -> bool:
        return self.wait_state is ApprovalWaitState.PENDING

    def resolve(self, *, approved: bool, at: datetime | None = None) -> "ApprovalWait":
        if not self.is_pending:
            raise ValueError("approval wait is no longer pending")
        timestamp = at or _utc_now()
        return replace(
            self,
            wait_state=ApprovalWaitState.RESOLVED,
            decision_result=ApprovalDecision.APPROVED if approved else ApprovalDecision.DENIED,
            resolved_at=timestamp,
            invalidated_reason=None,
        )

    def invalidate(self, reason: str | None = None, *, at: datetime | None = None) -> "ApprovalWait":
        if not self.is_pending:
            raise ValueError("approval wait is no longer pending")
        timestamp = at or _utc_now()
        return replace(
            self,
            wait_state=ApprovalWaitState.INVALIDATED,
            resolved_at=timestamp,
            invalidated_reason=_clean_text(reason),
            decision_result=None,
        )


__all__ = [
    "ApprovalDecision",
    "ApprovalWait",
    "ApprovalWaitState",
]
