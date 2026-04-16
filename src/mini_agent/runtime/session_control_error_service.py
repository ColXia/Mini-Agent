"""Shared error semantics for session control surfaces."""

from __future__ import annotations


def _safe_text(value: object) -> str:
    return " ".join(str(value or "").split())


class SessionControlErrorService:
    """Own shared busy wording and remote control failure labels."""

    _BUSY_DETAIL = "Session is busy. Wait for the current turn to finish."

    @classmethod
    def busy_detail(cls) -> str:
        return cls._BUSY_DETAIL

    @classmethod
    def is_busy_detail(cls, detail: str) -> bool:
        return _safe_text(detail) == cls._BUSY_DETAIL

    @classmethod
    def remote_summary(cls, detail: str) -> str:
        if cls.is_busy_detail(detail):
            return "session busy"
        return "command failed"

    @classmethod
    def remote_status_text(cls, detail: str) -> str:
        normalized = _safe_text(detail)
        return normalized or "Remote command failed."


__all__ = ["SessionControlErrorService"]
