"""Transitional session-task seams for application compatibility."""

from __future__ import annotations

from typing import Any, Protocol


class SessionTaskPort(Protocol):
    """Compatibility contract for session-owned task routing during migration."""

    async def get_session_task(self, session_id: str) -> Any: ...

    async def resolve_run_id_for_session(self, session_id: str) -> str | None: ...

    async def cancel_session_turn(
        self,
        session_id: str,
        *,
        reason: str | None = None,
        surface: str | None = None,
        channel_type: str | None = None,
        conversation_id: str | None = None,
        sender_id: str | None = None,
    ) -> Any: ...

    async def resolve_pending_approval(
        self,
        session_id: str,
        *,
        approved: bool,
        token: str | None = None,
        surface: str | None = None,
        channel_type: str | None = None,
        conversation_id: str | None = None,
        sender_id: str | None = None,
    ) -> Any: ...


__all__ = ["SessionTaskPort"]
