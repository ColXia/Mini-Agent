"""Durable run contract."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from enum import Enum

from ._common import clean_text, utc_now


class RunStatus(str, Enum):
    """Status values for one formal execution unit."""

    QUEUED = "queued"
    RUNNING = "running"
    WAITING = "waiting"
    PAUSED = "paused"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"


class RunPhase(str, Enum):
    """Pipeline phases for one formal execution unit."""

    CREATED = "created"
    BINDING = "binding"
    RESOLVING_CAPABILITIES = "resolving_capabilities"
    PREPARING_CONTEXT = "preparing_context"
    PLANNING = "planning"
    AWAITING_APPROVAL = "awaiting_approval"
    EXECUTING_TOOLS = "executing_tools"
    COMMITTING_EFFECTS = "committing_effects"
    WRITING_REPLY = "writing_reply"
    POST_TURN = "post_turn"
    TERMINAL = "terminal"


class RunInterruptState(str, Enum):
    """Interrupt lifecycle markers for one run."""

    NONE = "none"
    REQUESTED = "requested"
    ACKNOWLEDGED = "acknowledged"
    RESUMING = "resuming"


_VALID_STATUS_PHASE_PAIRS: set[tuple[RunStatus, RunPhase]] = {
    (RunStatus.QUEUED, RunPhase.CREATED),
    (RunStatus.RUNNING, RunPhase.BINDING),
    (RunStatus.RUNNING, RunPhase.RESOLVING_CAPABILITIES),
    (RunStatus.RUNNING, RunPhase.PREPARING_CONTEXT),
    (RunStatus.RUNNING, RunPhase.PLANNING),
    (RunStatus.WAITING, RunPhase.AWAITING_APPROVAL),
    (RunStatus.RUNNING, RunPhase.EXECUTING_TOOLS),
    (RunStatus.RUNNING, RunPhase.COMMITTING_EFFECTS),
    (RunStatus.RUNNING, RunPhase.WRITING_REPLY),
    (RunStatus.RUNNING, RunPhase.POST_TURN),
    (RunStatus.PAUSED, RunPhase.PLANNING),
    (RunStatus.PAUSED, RunPhase.EXECUTING_TOOLS),
    (RunStatus.COMPLETED, RunPhase.TERMINAL),
    (RunStatus.CANCELLED, RunPhase.TERMINAL),
    (RunStatus.FAILED, RunPhase.TERMINAL),
}


def validate_run_status_phase_pair(status: RunStatus, phase: RunPhase) -> None:
    if (status, phase) not in _VALID_STATUS_PHASE_PAIRS:
        raise ValueError(f"invalid run status/phase pairing: {status.value} + {phase.value}")


@dataclass(frozen=True, slots=True)
class Run:
    """One formal execution unit."""

    run_id: str
    agent_instance_id: str
    agent_profile_id: str
    workspace_id: str
    session_id: str
    trigger_source: str
    status: RunStatus = RunStatus.QUEUED
    phase: RunPhase = RunPhase.CREATED
    step_index: int = 0
    waiting_reason: str | None = None
    interrupt_state: RunInterruptState = RunInterruptState.NONE
    terminal_reason: str | None = None
    workspace_attachment_id: str | None = None
    session_attachment_id: str | None = None
    capability_snapshot_id: str | None = None
    active_checkpoint_id: str | None = None
    last_checkpoint_seq: int = 0
    journal_stream_id: str | None = None
    restorable: bool = True
    created_at: datetime | None = None
    started_at: datetime | None = None
    updated_at: datetime | None = None
    ended_at: datetime | None = None
    last_error_code: str | None = None
    last_error_summary: str | None = None
    last_model_request_id: str | None = None
    last_tool_batch_id: str | None = None
    last_mutation_ledger_seq: int | None = None

    def __post_init__(self) -> None:
        required_fields = {
            "run_id": clean_text(self.run_id),
            "agent_instance_id": clean_text(self.agent_instance_id),
            "agent_profile_id": clean_text(self.agent_profile_id),
            "workspace_id": clean_text(self.workspace_id),
            "session_id": clean_text(self.session_id),
            "trigger_source": clean_text(self.trigger_source),
        }
        for field_name, value in required_fields.items():
            if not value:
                raise ValueError(f"{field_name} is required")
            object.__setattr__(self, field_name, value)
        if self.step_index < 0:
            raise ValueError("step_index must be >= 0")
        if self.last_checkpoint_seq < 0:
            raise ValueError("last_checkpoint_seq must be >= 0")
        if self.last_mutation_ledger_seq is not None and self.last_mutation_ledger_seq < 0:
            raise ValueError("last_mutation_ledger_seq must be >= 0")
        validate_run_status_phase_pair(self.status, self.phase)
        object.__setattr__(self, "waiting_reason", clean_text(self.waiting_reason))
        object.__setattr__(self, "terminal_reason", clean_text(self.terminal_reason))
        object.__setattr__(
            self,
            "workspace_attachment_id",
            clean_text(self.workspace_attachment_id),
        )
        object.__setattr__(self, "session_attachment_id", clean_text(self.session_attachment_id))
        object.__setattr__(self, "capability_snapshot_id", clean_text(self.capability_snapshot_id))
        object.__setattr__(self, "active_checkpoint_id", clean_text(self.active_checkpoint_id))
        object.__setattr__(self, "journal_stream_id", clean_text(self.journal_stream_id))
        object.__setattr__(self, "last_error_code", clean_text(self.last_error_code))
        object.__setattr__(self, "last_error_summary", clean_text(self.last_error_summary))
        object.__setattr__(
            self,
            "last_model_request_id",
            clean_text(self.last_model_request_id),
        )
        object.__setattr__(self, "last_tool_batch_id", clean_text(self.last_tool_batch_id))
        if self.created_at is None:
            object.__setattr__(self, "created_at", utc_now())

    @property
    def is_terminal(self) -> bool:
        return self.status in {
            RunStatus.COMPLETED,
            RunStatus.CANCELLED,
            RunStatus.FAILED,
        }

    def transition(
        self,
        *,
        status: RunStatus,
        phase: RunPhase,
        waiting_reason: str | None = None,
        interrupt_state: RunInterruptState | None = None,
        terminal_reason: str | None = None,
        at: datetime | None = None,
    ) -> "Run":
        validate_run_status_phase_pair(status, phase)
        timestamp = at or utc_now()
        ended_at = self.ended_at
        if status in {RunStatus.COMPLETED, RunStatus.CANCELLED, RunStatus.FAILED}:
            ended_at = timestamp
        return replace(
            self,
            status=status,
            phase=phase,
            waiting_reason=clean_text(waiting_reason),
            interrupt_state=self.interrupt_state if interrupt_state is None else interrupt_state,
            terminal_reason=clean_text(terminal_reason) or self.terminal_reason,
            updated_at=timestamp,
            ended_at=ended_at,
            started_at=self.started_at or (timestamp if status is RunStatus.RUNNING else self.started_at),
        )

    def bind_attachments(
        self,
        *,
        workspace_attachment_id: str,
        session_attachment_id: str,
        at: datetime | None = None,
    ) -> "Run":
        timestamp = at or utc_now()
        normalized_workspace_attachment_id = clean_text(workspace_attachment_id)
        normalized_session_attachment_id = clean_text(session_attachment_id)
        if not normalized_workspace_attachment_id:
            raise ValueError("workspace_attachment_id is required")
        if not normalized_session_attachment_id:
            raise ValueError("session_attachment_id is required")
        return replace(
            self,
            workspace_attachment_id=normalized_workspace_attachment_id,
            session_attachment_id=normalized_session_attachment_id,
            updated_at=timestamp,
        )

    def attach_capability_snapshot(self, capability_snapshot_id: str, *, at: datetime | None = None) -> "Run":
        timestamp = at or utc_now()
        normalized_snapshot_id = clean_text(capability_snapshot_id)
        if not normalized_snapshot_id:
            raise ValueError("capability_snapshot_id is required")
        return replace(self, capability_snapshot_id=normalized_snapshot_id, updated_at=timestamp)

    def activate_checkpoint(
        self,
        checkpoint_id: str,
        *,
        checkpoint_seq: int,
        restorable: bool | None = None,
        at: datetime | None = None,
    ) -> "Run":
        if checkpoint_seq < 0:
            raise ValueError("checkpoint_seq must be >= 0")
        timestamp = at or utc_now()
        normalized_checkpoint_id = clean_text(checkpoint_id)
        if not normalized_checkpoint_id:
            raise ValueError("checkpoint_id is required")
        return replace(
            self,
            active_checkpoint_id=normalized_checkpoint_id,
            last_checkpoint_seq=checkpoint_seq,
            restorable=self.restorable if restorable is None else bool(restorable),
            updated_at=timestamp,
        )

    def advance_step(self, *, step_index: int | None = None, at: datetime | None = None) -> "Run":
        next_step_index = self.step_index + 1 if step_index is None else step_index
        if next_step_index < 0:
            raise ValueError("step_index must be >= 0")
        timestamp = at or utc_now()
        return replace(self, step_index=next_step_index, updated_at=timestamp)


__all__ = [
    "Run",
    "RunInterruptState",
    "RunPhase",
    "RunStatus",
    "validate_run_status_phase_pair",
]

