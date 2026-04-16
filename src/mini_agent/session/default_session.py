"""Shared default-session semantics for all entry surfaces."""

from __future__ import annotations

DEFAULT_SESSION_ID = "default"
DEFAULT_SESSION_TITLE = "Session 1"


def is_default_session_id(session_id: object) -> bool:
    return " ".join(str(session_id or "").split()) == DEFAULT_SESSION_ID


__all__ = [
    "DEFAULT_SESSION_ID",
    "DEFAULT_SESSION_TITLE",
    "is_default_session_id",
]
