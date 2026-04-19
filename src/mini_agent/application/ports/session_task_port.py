"""Application-facing session-to-run lookup seam."""

from __future__ import annotations

from typing import Protocol


class SessionTaskPort(Protocol):
    """Resolve run ownership from session task state."""

    async def resolve_run_id_for_session(self, session_id: str) -> str | None: ...


__all__ = ["SessionTaskPort"]
