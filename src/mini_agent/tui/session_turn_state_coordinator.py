"""Shared TUI session/task state transitions for turn execution."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class TuiSessionTurnStateCoordinator:
    """Own small, behavior-preserving turn state transitions for TUI sessions."""

    @staticmethod
    def begin_local_turn(
        session: Any,
        *,
        task_id: str,
        resuming: bool,
    ) -> None:
        projection = session.projection
        runtime = session.runtime
        projection.busy = True
        runtime.cancel_event = None
        runtime.active_task_id = task_id
        projection.running_state = "resuming after restart" if resuming else "starting run"
        projection.pending_approvals = []

    @staticmethod
    def finish_local_turn(session: Any) -> None:
        projection = session.projection
        runtime = session.runtime
        view = session.view
        runtime.active_task_id = None
        projection.busy = False
        runtime.cancel_event = None
        projection.running_state = ""
        view.active_activity_message_index = None
        projection.pending_approvals = []

    @staticmethod
    def begin_remote_turn(
        session: Any,
        *,
        task_id: str,
    ) -> None:
        projection = session.projection
        runtime = session.runtime
        projection.busy = True
        runtime.active_task_id = task_id
        projection.reply_enabled = False
        projection.running_state = "gateway request running"
        projection.pending_approvals = []

    @staticmethod
    def finish_remote_turn(session: Any) -> None:
        projection = session.projection
        runtime = session.runtime
        runtime.active_task_id = None
        projection.busy = False
        projection.running_state = ""


__all__ = ["TuiSessionTurnStateCoordinator"]


