"""Helpers for transitional session-backed run identifiers."""

from __future__ import annotations


SESSION_BACKED_RUN_ID_PREFIX = "session-run:"


def build_session_backed_run_id(session_id: str) -> str:
    normalized = str(session_id or "").strip()
    if not normalized:
        raise ValueError("session_id is required")
    return f"{SESSION_BACKED_RUN_ID_PREFIX}{normalized}"


def resolve_session_backed_session_id(run_id: str) -> str | None:
    normalized = str(run_id or "").strip()
    if not normalized.startswith(SESSION_BACKED_RUN_ID_PREFIX):
        return None
    session_id = normalized[len(SESSION_BACKED_RUN_ID_PREFIX) :].strip()
    return session_id or None


__all__ = [
    "SESSION_BACKED_RUN_ID_PREFIX",
    "build_session_backed_run_id",
    "resolve_session_backed_session_id",
]
