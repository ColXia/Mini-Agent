"""Shared user-facing feedback semantics for session operations."""

from __future__ import annotations

from dataclasses import dataclass


def _safe_text(value: object) -> str:
    return " ".join(str(value or "").split())


@dataclass(frozen=True, slots=True)
class SessionFeedback:
    summary: str
    status_text: str


class SessionFeedbackService:
    """Own shared session feedback semantics across interactive surfaces."""

    @staticmethod
    def _resolved_title(title: str | None, *, fallback: str = "session") -> str:
        return _safe_text(title) or fallback

    @staticmethod
    def _resolved_status(status: str, *, shared: bool | None = None) -> str:
        normalized = _safe_text(status).lower()
        if normalized in {"shared", "unshared", "renamed", "deleted", "reset"}:
            return normalized
        if shared is True:
            return "shared"
        if shared is False:
            return "unshared"
        return normalized or "updated"

    @classmethod
    def mutation_feedback(
        cls,
        *,
        status: str,
        title: str | None = None,
        shared: bool | None = None,
    ) -> SessionFeedback:
        resolved_status = cls._resolved_status(status, shared=shared)
        resolved_title = cls._resolved_title(title)
        if resolved_status == "shared":
            return SessionFeedback(
                summary="shared",
                status_text=f"Shared {resolved_title} to remote surfaces.",
            )
        if resolved_status == "unshared":
            return SessionFeedback(
                summary="unshared",
                status_text=f"Unshared {resolved_title}.",
            )
        if resolved_status == "renamed":
            return SessionFeedback(
                summary="renamed",
                status_text=f"Renamed session to {resolved_title}.",
            )
        if resolved_status == "deleted":
            return SessionFeedback(
                summary="deleted",
                status_text=f"Deleted session {resolved_title}.",
            )
        if resolved_status == "reset":
            return SessionFeedback(
                summary="reset",
                status_text=f"Reset remote session {resolved_title}.",
            )
        return SessionFeedback(
            summary=resolved_status or "updated",
            status_text=f"Updated {resolved_title}.",
        )

    @classmethod
    def creation_feedback(cls, *, title: str | None = None, derived: bool = False) -> SessionFeedback:
        resolved_title = cls._resolved_title(
            title,
            fallback="derived session" if derived else "session",
        )
        if derived:
            return SessionFeedback(
                summary="created",
                status_text=f"Created derived session {resolved_title}.",
            )
        return SessionFeedback(
            summary="created",
            status_text=f"Created {resolved_title}.",
        )

    @classmethod
    def fork_feedback(
        cls,
        *,
        title: str | None = None,
        parent_title: str | None = None,
    ) -> SessionFeedback:
        resolved_title = cls._resolved_title(title, fallback="derived session")
        resolved_parent_title = cls._resolved_title(parent_title)
        return SessionFeedback(
            summary="forked",
            status_text=f"Forked {resolved_title} from {resolved_parent_title}.",
        )


__all__ = [
    "SessionFeedback",
    "SessionFeedbackService",
]
