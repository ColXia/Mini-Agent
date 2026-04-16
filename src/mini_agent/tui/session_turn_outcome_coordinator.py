"""Shared TUI turn outcome planning for local and remote turns."""

from __future__ import annotations

from dataclasses import dataclass

from mini_agent.agent_core.engine import TurnStopReason


@dataclass(frozen=True, slots=True)
class TuiTurnOutcomePlan:
    """Describe one terminal turn outcome without owning stream mechanics."""

    kind: str
    task_status: str
    task_stop_reason: str
    task_note: str
    activity_detail: str
    status_text: str
    system_message: str | None = None


@dataclass(slots=True)
class TuiSessionTurnOutcomeCoordinator:
    """Own shared local/remote turn completion and failure semantics."""

    @staticmethod
    def resolve_remote_completion(
        *,
        session_title: str,
        stop_reason: str,
        reply_text: str,
    ) -> TuiTurnOutcomePlan:
        if stop_reason in {"", TurnStopReason.END_TURN.value}:
            return TuiTurnOutcomePlan(
                kind="success",
                task_status="completed",
                task_stop_reason="end_turn",
                task_note="ok",
                activity_detail="response ready",
                status_text=f"Completed remote turn for {session_title}.",
            )
        if stop_reason == TurnStopReason.CANCELLED.value:
            return TuiTurnOutcomePlan(
                kind="cancelled",
                task_status="cancelled",
                task_stop_reason=stop_reason,
                task_note="cancelled",
                activity_detail="cancelled",
                status_text=f"Cancelled remote turn for {session_title}.",
                system_message=reply_text or "Task cancelled by user.",
            )
        if stop_reason == TurnStopReason.MAX_TURN_REQUESTS.value:
            return TuiTurnOutcomePlan(
                kind="limit",
                task_status="completed",
                task_stop_reason=stop_reason,
                task_note="max_turn_requests",
                activity_detail="turn limit reached",
                status_text=f"Remote turn reached limits for {session_title}.",
                system_message=reply_text or "Turn reached max request limit.",
            )
        return TuiTurnOutcomePlan(
            kind="failure",
            task_status="completed",
            task_stop_reason=stop_reason,
            task_note="refusal_or_failure",
            activity_detail="run failed",
            status_text=f"Remote turn failed for {session_title}.",
            system_message=reply_text or "Remote turn ended with refusal.",
        )

    @staticmethod
    def resolve_local_completion(
        *,
        session_title: str,
        state: str,
        stop_reason: str,
        message: str,
        error: str,
    ) -> TuiTurnOutcomePlan:
        if state == "completed" and stop_reason in {"", TurnStopReason.END_TURN.value}:
            return TuiTurnOutcomePlan(
                kind="success",
                task_status="completed",
                task_stop_reason=stop_reason or "end_turn",
                task_note="ok",
                activity_detail="response ready",
                status_text=f"Completed turn for {session_title}.",
            )
        if state == "interrupted" or stop_reason == TurnStopReason.CANCELLED.value:
            return TuiTurnOutcomePlan(
                kind="cancelled",
                task_status="cancelled",
                task_stop_reason=stop_reason or state,
                task_note="cancelled",
                activity_detail="cancelled",
                status_text=f"Cancelled turn for {session_title}.",
                system_message=message or "Task cancelled by user.",
            )
        if stop_reason == TurnStopReason.MAX_TURN_REQUESTS.value:
            return TuiTurnOutcomePlan(
                kind="limit",
                task_status="completed",
                task_stop_reason=stop_reason,
                task_note="max_turn_requests",
                activity_detail="turn limit reached",
                status_text=f"Turn reached limits for {session_title}.",
                system_message=message or "Turn reached max request limit.",
            )
        return TuiTurnOutcomePlan(
            kind="failure",
            task_status="completed",
            task_stop_reason=stop_reason or state,
            task_note=error or "refusal_or_failure",
            activity_detail="run failed",
            status_text=f"Turn failed for {session_title}.",
            system_message=message or error or "Turn ended with refusal.",
        )

    @staticmethod
    def resolve_remote_exception(
        *,
        session_title: str,
        detail: str,
    ) -> TuiTurnOutcomePlan:
        message = f"Remote turn failed: {detail}"
        return TuiTurnOutcomePlan(
            kind="exception",
            task_status="completed",
            task_stop_reason="exception",
            task_note=detail,
            activity_detail="exception raised",
            status_text=f"Remote turn failed for {session_title}: {detail}",
            system_message=message,
        )

    @staticmethod
    def resolve_local_exception(
        *,
        detail: str,
    ) -> TuiTurnOutcomePlan:
        message = f"Turn failed: {detail}"
        return TuiTurnOutcomePlan(
            kind="exception",
            task_status="completed",
            task_stop_reason="exception",
            task_note=detail,
            activity_detail="exception raised",
            status_text=message,
            system_message=message,
        )


__all__ = [
    "TuiSessionTurnOutcomeCoordinator",
    "TuiTurnOutcomePlan",
]
