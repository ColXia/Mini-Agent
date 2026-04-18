"""Transport-facing contract for remote chat client operations."""

from __future__ import annotations

from typing import Protocol


class RemoteChatTransportPort(Protocol):
    """Transport contract consumed by `RemoteChatClient`."""

    async def run_chat(
        self,
        *,
        session_id: str,
        message: str,
        workspace_dir: str,
        surface: str = "tui",
    ) -> dict: ...


__all__ = ["RemoteChatTransportPort"]
