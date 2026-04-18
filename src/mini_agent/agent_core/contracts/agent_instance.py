"""Durable agent-instance contract."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from enum import Enum

from ._common import clean_text, utc_now
from .run_control_state import RunWaitKind


class AgentInstanceLifecycleState(str, Enum):
    """Lifecycle states for one durable agent instance."""

    COLD = "cold"
    READY = "ready"
    ATTACHED = "attached"
    RUNNING = "running"
    WAITING = "waiting"
    PAUSED = "paused"
    MIGRATING = "migrating"
    ERRORED = "errored"
    RETIRED = "retired"


@dataclass(frozen=True, slots=True)
class AgentInstance:
    """Persistent execution subject for the kernel."""

    agent_instance_id: str
    agent_profile_id: str
    lifecycle_state: AgentInstanceLifecycleState = AgentInstanceLifecycleState.COLD
    active_run_id: str | None = None
    current_workspace_id: str | None = None
    current_session_id: str | None = None
    current_workspace_attachment_id: str | None = None
    current_session_attachment_id: str | None = None
    checkpoint_head_id: str | None = None
    journal_head_seq: int = 0
    interrupt_requested: bool = False
    cancel_requested: bool = False
    pending_wait_kind: RunWaitKind = RunWaitKind.NONE
    pending_wait_id: str | None = None
    restored_from_checkpoint_id: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    retired_at: datetime | None = None

    def __post_init__(self) -> None:
        normalized_instance_id = clean_text(self.agent_instance_id)
        normalized_profile_id = clean_text(self.agent_profile_id)
        if not normalized_instance_id:
            raise ValueError("agent_instance_id is required")
        if not normalized_profile_id:
            raise ValueError("agent_profile_id is required")
        if self.journal_head_seq < 0:
            raise ValueError("journal_head_seq must be >= 0")
        object.__setattr__(self, "agent_instance_id", normalized_instance_id)
        object.__setattr__(self, "agent_profile_id", normalized_profile_id)
        object.__setattr__(self, "active_run_id", clean_text(self.active_run_id))
        object.__setattr__(self, "current_workspace_id", clean_text(self.current_workspace_id))
        object.__setattr__(self, "current_session_id", clean_text(self.current_session_id))
        object.__setattr__(
            self,
            "current_workspace_attachment_id",
            clean_text(self.current_workspace_attachment_id),
        )
        object.__setattr__(
            self,
            "current_session_attachment_id",
            clean_text(self.current_session_attachment_id),
        )
        object.__setattr__(self, "checkpoint_head_id", clean_text(self.checkpoint_head_id))
        object.__setattr__(self, "pending_wait_id", clean_text(self.pending_wait_id))
        object.__setattr__(
            self,
            "restored_from_checkpoint_id",
            clean_text(self.restored_from_checkpoint_id),
        )
        if self.created_at is None:
            object.__setattr__(self, "created_at", utc_now())

    def transition_lifecycle(
        self,
        lifecycle_state: AgentInstanceLifecycleState,
        *,
        at: datetime | None = None,
    ) -> "AgentInstance":
        timestamp = at or utc_now()
        retired_at = self.retired_at
        if lifecycle_state is AgentInstanceLifecycleState.RETIRED and retired_at is None:
            retired_at = timestamp
        return replace(
            self,
            lifecycle_state=lifecycle_state,
            updated_at=timestamp,
            retired_at=retired_at,
        )

    def attach(
        self,
        *,
        workspace_id: str,
        session_id: str,
        workspace_attachment_id: str,
        session_attachment_id: str,
        at: datetime | None = None,
    ) -> "AgentInstance":
        timestamp = at or utc_now()
        return replace(
            self,
            lifecycle_state=AgentInstanceLifecycleState.ATTACHED,
            current_workspace_id=clean_text(workspace_id),
            current_session_id=clean_text(session_id),
            current_workspace_attachment_id=clean_text(workspace_attachment_id),
            current_session_attachment_id=clean_text(session_attachment_id),
            updated_at=timestamp,
        )

    def activate_run(self, run_id: str, *, at: datetime | None = None) -> "AgentInstance":
        normalized_run_id = clean_text(run_id)
        if not normalized_run_id:
            raise ValueError("run_id is required")
        timestamp = at or utc_now()
        return replace(
            self,
            lifecycle_state=AgentInstanceLifecycleState.RUNNING,
            active_run_id=normalized_run_id,
            pending_wait_kind=RunWaitKind.NONE,
            pending_wait_id=None,
            interrupt_requested=False,
            cancel_requested=False,
            updated_at=timestamp,
        )

    def mark_waiting(
        self,
        *,
        wait_kind: RunWaitKind,
        wait_id: str | None = None,
        at: datetime | None = None,
    ) -> "AgentInstance":
        timestamp = at or utc_now()
        return replace(
            self,
            lifecycle_state=AgentInstanceLifecycleState.WAITING,
            pending_wait_kind=wait_kind,
            pending_wait_id=clean_text(wait_id),
            updated_at=timestamp,
        )

    def mark_paused(self, *, wait_id: str | None = None, at: datetime | None = None) -> "AgentInstance":
        timestamp = at or utc_now()
        return replace(
            self,
            lifecycle_state=AgentInstanceLifecycleState.PAUSED,
            interrupt_requested=False,
            pending_wait_id=clean_text(wait_id),
            updated_at=timestamp,
        )

    def request_interrupt(self, *, at: datetime | None = None) -> "AgentInstance":
        timestamp = at or utc_now()
        return replace(self, interrupt_requested=True, updated_at=timestamp)

    def request_cancel(self, *, at: datetime | None = None) -> "AgentInstance":
        timestamp = at or utc_now()
        return replace(self, cancel_requested=True, updated_at=timestamp)

    def record_checkpoint(
        self,
        checkpoint_id: str,
        *,
        journal_head_seq: int | None = None,
        at: datetime | None = None,
    ) -> "AgentInstance":
        normalized_checkpoint_id = clean_text(checkpoint_id)
        if not normalized_checkpoint_id:
            raise ValueError("checkpoint_id is required")
        next_journal_head_seq = self.journal_head_seq if journal_head_seq is None else journal_head_seq
        if next_journal_head_seq < 0:
            raise ValueError("journal_head_seq must be >= 0")
        timestamp = at or utc_now()
        return replace(
            self,
            checkpoint_head_id=normalized_checkpoint_id,
            journal_head_seq=next_journal_head_seq,
            updated_at=timestamp,
        )

    def clear_active_run(self, *, at: datetime | None = None) -> "AgentInstance":
        timestamp = at or utc_now()
        next_state = (
            AgentInstanceLifecycleState.ATTACHED
            if self.current_workspace_attachment_id and self.current_session_attachment_id
            else AgentInstanceLifecycleState.READY
        )
        return replace(
            self,
            lifecycle_state=next_state,
            active_run_id=None,
            interrupt_requested=False,
            cancel_requested=False,
            pending_wait_kind=RunWaitKind.NONE,
            pending_wait_id=None,
            updated_at=timestamp,
        )


__all__ = ["AgentInstance", "AgentInstanceLifecycleState"]

