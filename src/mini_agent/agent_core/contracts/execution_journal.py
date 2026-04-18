"""Execution journal contracts."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime
from typing import Any

from ._common import clean_text, normalize_mapping, utc_now
from .run import RunPhase, RunStatus, validate_run_status_phase_pair


@dataclass(frozen=True, slots=True)
class ExecutionJournalEvent:
    """One append-only execution fact."""

    event_seq: int
    event_type: str
    run_id: str
    agent_instance_id: str
    workspace_id: str
    session_id: str
    status: RunStatus
    phase: RunPhase
    step_index: int
    event_ts: datetime | None = None
    correlation_id: str | None = None
    causation_id: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.event_seq < 1:
            raise ValueError("event_seq must be >= 1")
        if self.step_index < 0:
            raise ValueError("step_index must be >= 0")
        validate_run_status_phase_pair(self.status, self.phase)
        required_fields = {
            "event_type": clean_text(self.event_type),
            "run_id": clean_text(self.run_id),
            "agent_instance_id": clean_text(self.agent_instance_id),
            "workspace_id": clean_text(self.workspace_id),
            "session_id": clean_text(self.session_id),
        }
        for field_name, value in required_fields.items():
            if not value:
                raise ValueError(f"{field_name} is required")
            object.__setattr__(self, field_name, value)
        object.__setattr__(self, "correlation_id", clean_text(self.correlation_id))
        object.__setattr__(self, "causation_id", clean_text(self.causation_id))
        object.__setattr__(self, "payload", normalize_mapping(self.payload))
        if self.event_ts is None:
            object.__setattr__(self, "event_ts", utc_now())


@dataclass(frozen=True, slots=True)
class ExecutionJournal:
    """Append-only execution fact stream for one run."""

    journal_stream_id: str
    run_id: str
    agent_instance_id: str
    workspace_id: str
    session_id: str
    events: tuple[ExecutionJournalEvent, ...] = ()
    created_at: datetime | None = None
    closed_at: datetime | None = None

    def __post_init__(self) -> None:
        required_fields = {
            "journal_stream_id": clean_text(self.journal_stream_id),
            "run_id": clean_text(self.run_id),
            "agent_instance_id": clean_text(self.agent_instance_id),
            "workspace_id": clean_text(self.workspace_id),
            "session_id": clean_text(self.session_id),
        }
        for field_name, value in required_fields.items():
            if not value:
                raise ValueError(f"{field_name} is required")
            object.__setattr__(self, field_name, value)
        normalized_events: list[ExecutionJournalEvent] = []
        for index, event in enumerate(self.events, start=1):
            if not isinstance(event, ExecutionJournalEvent):
                raise ValueError("events must contain ExecutionJournalEvent items")
            if event.event_seq != index:
                raise ValueError("events must use contiguous event_seq values starting at 1")
            normalized_events.append(event)
        object.__setattr__(self, "events", tuple(normalized_events))
        if self.created_at is None:
            object.__setattr__(self, "created_at", utc_now())

    @property
    def last_event_seq(self) -> int:
        return 0 if not self.events else self.events[-1].event_seq

    @property
    def latest_event(self) -> ExecutionJournalEvent | None:
        return None if not self.events else self.events[-1]

    def append(
        self,
        *,
        event_type: str,
        status: RunStatus,
        phase: RunPhase,
        step_index: int,
        correlation_id: str | None = None,
        causation_id: str | None = None,
        payload: dict[str, Any] | None = None,
        event_ts: datetime | None = None,
    ) -> "ExecutionJournal":
        event = ExecutionJournalEvent(
            event_seq=self.last_event_seq + 1,
            event_type=event_type,
            run_id=self.run_id,
            agent_instance_id=self.agent_instance_id,
            workspace_id=self.workspace_id,
            session_id=self.session_id,
            status=status,
            phase=phase,
            step_index=step_index,
            event_ts=event_ts,
            correlation_id=correlation_id,
            causation_id=causation_id,
            payload=payload or {},
        )
        return replace(self, events=self.events + (event,))

    def close(self, *, at: datetime | None = None) -> "ExecutionJournal":
        return replace(self, closed_at=at or utc_now())


__all__ = ["ExecutionJournal", "ExecutionJournalEvent"]

