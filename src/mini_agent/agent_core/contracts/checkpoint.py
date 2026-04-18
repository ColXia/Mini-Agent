"""Checkpoint contracts for durable run recovery."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from ._common import clean_text, utc_now
from .run import RunPhase, RunStatus, validate_run_status_phase_pair


class CheckpointType(str, Enum):
    """Checkpoint classes recognized by v11.1."""

    BOOTSTRAP = "bootstrap"
    PRE_SIDE_EFFECT = "pre_side_effect"
    POST_SIDE_EFFECT = "post_side_effect"
    WAITING = "waiting"
    TERMINAL = "terminal"


@dataclass(frozen=True, slots=True)
class Checkpoint:
    """Recoverable kernel anchor for one run."""

    checkpoint_id: str
    run_id: str
    agent_instance_id: str
    checkpoint_seq: int
    checkpoint_type: CheckpointType
    status: RunStatus
    phase: RunPhase
    step_index: int
    workspace_attachment_id: str
    session_attachment_id: str
    capability_snapshot_hash: str
    journal_offset: int
    waiting_reason: str | None = None
    resume_token: str | None = None
    created_at: datetime | None = None
    schema_version: str = "v11.1"
    last_model_turn_ref: str | None = None
    last_tool_batch_ref: str | None = None
    last_mutation_ledger_seq: int | None = None
    recovery_context_ref: str | None = None
    error_ref: str | None = None
    recoverable: bool = True

    def __post_init__(self) -> None:
        required_fields = {
            "checkpoint_id": clean_text(self.checkpoint_id),
            "run_id": clean_text(self.run_id),
            "agent_instance_id": clean_text(self.agent_instance_id),
            "workspace_attachment_id": clean_text(self.workspace_attachment_id),
            "session_attachment_id": clean_text(self.session_attachment_id),
            "capability_snapshot_hash": clean_text(self.capability_snapshot_hash),
            "schema_version": clean_text(self.schema_version),
        }
        for field_name, value in required_fields.items():
            if not value:
                raise ValueError(f"{field_name} is required")
            object.__setattr__(self, field_name, value)
        if self.checkpoint_seq < 0:
            raise ValueError("checkpoint_seq must be >= 0")
        if self.step_index < 0:
            raise ValueError("step_index must be >= 0")
        if self.journal_offset < 0:
            raise ValueError("journal_offset must be >= 0")
        if self.last_mutation_ledger_seq is not None and self.last_mutation_ledger_seq < 0:
            raise ValueError("last_mutation_ledger_seq must be >= 0")
        validate_run_status_phase_pair(self.status, self.phase)
        object.__setattr__(self, "waiting_reason", clean_text(self.waiting_reason))
        object.__setattr__(self, "resume_token", clean_text(self.resume_token))
        object.__setattr__(self, "last_model_turn_ref", clean_text(self.last_model_turn_ref))
        object.__setattr__(self, "last_tool_batch_ref", clean_text(self.last_tool_batch_ref))
        object.__setattr__(self, "recovery_context_ref", clean_text(self.recovery_context_ref))
        object.__setattr__(self, "error_ref", clean_text(self.error_ref))
        if self.created_at is None:
            object.__setattr__(self, "created_at", utc_now())

    @property
    def is_terminal_checkpoint(self) -> bool:
        return self.checkpoint_type is CheckpointType.TERMINAL

    @property
    def is_waiting_checkpoint(self) -> bool:
        return self.checkpoint_type is CheckpointType.WAITING


__all__ = ["Checkpoint", "CheckpointType"]

