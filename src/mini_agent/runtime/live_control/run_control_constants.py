"""Shared live-control constants for run-backed session execution."""

from __future__ import annotations


INTERRUPT_REQUESTED_RUNNING_STATE = "interrupt requested"
INTERRUPT_REQUESTED_STATUS = "interrupt_requested"
INTERRUPTING_PHASE = "interrupting"
RESUME_REQUESTED_STATUS = "resume_requested"
RESUMING_PHASE = "resuming"
PAUSED_STATUS = "paused"
PAUSED_PHASE = "paused"
CANCEL_REQUESTED_RUNNING_STATE = "cancellation requested"
CANCEL_REQUESTED_STATUS = "cancel_requested"
CANCELLING_PHASE = "cancelling"
SESSION_BACKED_RUN_ID_PREFIX = "session-run:"


__all__ = [
    "CANCEL_REQUESTED_RUNNING_STATE",
    "CANCEL_REQUESTED_STATUS",
    "CANCELLING_PHASE",
    "INTERRUPT_REQUESTED_RUNNING_STATE",
    "INTERRUPT_REQUESTED_STATUS",
    "INTERRUPTING_PHASE",
    "PAUSED_PHASE",
    "PAUSED_STATUS",
    "RESUME_REQUESTED_STATUS",
    "RESUMING_PHASE",
    "SESSION_BACKED_RUN_ID_PREFIX",
]
