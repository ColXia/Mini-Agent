"""Shared cancel-request semantics for session interruption flows."""

from __future__ import annotations


def _safe_text(value: object) -> str:
    return " ".join(str(value or "").split())


class SessionCancelService:
    """Own shared cancel-request wording and semantic labels."""

    REQUESTED_STATE = "cancellation requested"
    CANCEL_REQUESTED_STATUS = "cancel_requested"

    @staticmethod
    def no_running_turn_detail() -> str:
        return "Session has no running turn to cancel."

    @staticmethod
    def no_running_turn_user_text() -> str:
        return "No running turn to cancel."

    @classmethod
    def is_no_running_turn_detail(cls, detail: str) -> bool:
        return _safe_text(detail) == cls.no_running_turn_detail()

    @staticmethod
    def not_cancellable_detail() -> str:
        return "Session turn is not cancellable."

    @classmethod
    def requested_summary(cls) -> str:
        return cls.REQUESTED_STATE

    @classmethod
    def requested_status_text(cls, session_title: str) -> str:
        return f"Cancelling turn for {session_title}..."

    @classmethod
    def transcript_details(cls, *, reason: str | None) -> str:
        lines = [
            "Action: cancel",
            f"State: {cls.REQUESTED_STATE}",
        ]
        normalized_reason = _safe_text(reason)
        if normalized_reason:
            lines.append(f"Reason: {normalized_reason}")
        return "\n".join(lines)


__all__ = ["SessionCancelService"]
