"""Durable run-owned control state contracts."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from enum import Enum


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _clean_text(value: object) -> str | None:
    text = " ".join(str(value or "").split())
    return text or None


class RunControlMode(str, Enum):
    """Stable control modes for a durable run-control record."""

    NORMAL = "normal"
    INTERRUPT_REQUESTED = "interrupt_requested"
    PAUSED = "paused"
    APPROVAL_WAIT = "approval_wait"
    RESUME_REQUESTED = "resume_requested"
    CANCEL_REQUESTED = "cancel_requested"
    TERMINAL = "terminal"


class RunWaitKind(str, Enum):
    """Durable wait kinds owned by run control."""

    NONE = "none"
    APPROVAL = "approval"
    EXTERNAL_DEPENDENCY = "external_dependency"


@dataclass(frozen=True, slots=True)
class RunControlState:
    """Durable control view for one run."""

    run_id: str
    control_mode: RunControlMode = RunControlMode.NORMAL
    active_wait_kind: RunWaitKind = RunWaitKind.NONE
    active_wait_id: str | None = None
    interrupt_requested: bool = False
    cancel_requested: bool = False
    resumable: bool = True
    last_command: str | None = None
    last_command_source: str | None = None
    last_command_at: datetime | None = None
    control_updated_at: datetime | None = None
    force_stop_requested: bool = False
    last_resume_token: str | None = None
    last_pause_reason: str | None = None
    last_cancel_reason: str | None = None
    last_approval_token: str | None = None

    def __post_init__(self) -> None:
        if not _clean_text(self.run_id):
            raise ValueError("run_id is required")
        object.__setattr__(self, "run_id", str(self.run_id).strip())
        object.__setattr__(self, "active_wait_id", _clean_text(self.active_wait_id))
        object.__setattr__(self, "last_command", _clean_text(self.last_command))
        object.__setattr__(self, "last_command_source", _clean_text(self.last_command_source))
        object.__setattr__(self, "last_resume_token", _clean_text(self.last_resume_token))
        object.__setattr__(self, "last_pause_reason", _clean_text(self.last_pause_reason))
        object.__setattr__(self, "last_cancel_reason", _clean_text(self.last_cancel_reason))
        object.__setattr__(self, "last_approval_token", _clean_text(self.last_approval_token))

    @property
    def is_terminal(self) -> bool:
        return self.control_mode is RunControlMode.TERMINAL

    @property
    def is_waiting(self) -> bool:
        return self.active_wait_kind is not RunWaitKind.NONE

    def request_interrupt(
        self,
        *,
        source: str | None = None,
        reason: str | None = None,
        at: datetime | None = None,
    ) -> "RunControlState":
        timestamp = at or _utc_now()
        return replace(
            self,
            control_mode=RunControlMode.INTERRUPT_REQUESTED,
            interrupt_requested=True,
            last_command="interrupt",
            last_command_source=_clean_text(source),
            last_command_at=timestamp,
            control_updated_at=timestamp,
            last_pause_reason=_clean_text(reason) or self.last_pause_reason,
        )

    def pause(
        self,
        *,
        reason: str | None = None,
        resumable: bool | None = None,
        at: datetime | None = None,
    ) -> "RunControlState":
        timestamp = at or _utc_now()
        return replace(
            self,
            control_mode=RunControlMode.PAUSED,
            interrupt_requested=False,
            resumable=self.resumable if resumable is None else bool(resumable),
            control_updated_at=timestamp,
            last_pause_reason=_clean_text(reason) or self.last_pause_reason,
        )

    def request_resume(
        self,
        *,
        source: str | None = None,
        resume_token: str | None = None,
        at: datetime | None = None,
    ) -> "RunControlState":
        timestamp = at or _utc_now()
        return replace(
            self,
            control_mode=RunControlMode.RESUME_REQUESTED,
            interrupt_requested=False,
            last_command="resume",
            last_command_source=_clean_text(source),
            last_command_at=timestamp,
            control_updated_at=timestamp,
            last_resume_token=_clean_text(resume_token) or self.last_resume_token,
        )

    def enter_approval_wait(
        self,
        wait_id: str,
        *,
        approval_token: str | None = None,
        at: datetime | None = None,
    ) -> "RunControlState":
        normalized_wait_id = _clean_text(wait_id)
        if not normalized_wait_id:
            raise ValueError("wait_id is required")
        timestamp = at or _utc_now()
        return replace(
            self,
            control_mode=RunControlMode.APPROVAL_WAIT,
            active_wait_kind=RunWaitKind.APPROVAL,
            active_wait_id=normalized_wait_id,
            last_approval_token=_clean_text(approval_token) or self.last_approval_token,
            control_updated_at=timestamp,
        )

    def clear_wait(self, *, at: datetime | None = None) -> "RunControlState":
        timestamp = at or _utc_now()
        next_mode = RunControlMode.NORMAL
        if self.cancel_requested:
            next_mode = RunControlMode.CANCEL_REQUESTED
        elif self.is_terminal:
            next_mode = RunControlMode.TERMINAL
        return replace(
            self,
            control_mode=next_mode,
            active_wait_kind=RunWaitKind.NONE,
            active_wait_id=None,
            control_updated_at=timestamp,
        )

    def request_cancel(
        self,
        *,
        source: str | None = None,
        reason: str | None = None,
        force_stop: bool = False,
        at: datetime | None = None,
    ) -> "RunControlState":
        timestamp = at or _utc_now()
        return replace(
            self,
            control_mode=RunControlMode.CANCEL_REQUESTED,
            cancel_requested=True,
            force_stop_requested=self.force_stop_requested or bool(force_stop),
            last_command="cancel",
            last_command_source=_clean_text(source),
            last_command_at=timestamp,
            control_updated_at=timestamp,
            last_cancel_reason=_clean_text(reason) or self.last_cancel_reason,
        )

    def mark_terminal(self, *, at: datetime | None = None) -> "RunControlState":
        timestamp = at or _utc_now()
        return replace(
            self,
            control_mode=RunControlMode.TERMINAL,
            active_wait_kind=RunWaitKind.NONE,
            active_wait_id=None,
            interrupt_requested=False,
            resumable=False,
            control_updated_at=timestamp,
        )


__all__ = [
    "RunControlMode",
    "RunControlState",
    "RunWaitKind",
]
