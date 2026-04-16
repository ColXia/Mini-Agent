"""Session-owned port for remote conversation binding lookup and persistence."""

from __future__ import annotations

from typing import Protocol


class ConversationBindingPort(Protocol):
    """Minimal binding contract consumed by shared channel ingress flows."""

    def resolve_session_id(
        self,
        *,
        surface: str | None = None,
        channel_type: str | None = None,
        conversation_id: str | None = None,
        explicit_session_id: str | None = None,
        dry_run: bool = False,
    ) -> str | None: ...

    def persist_binding(
        self,
        *,
        surface: str | None = None,
        channel_type: str | None = None,
        conversation_id: str | None = None,
        session_id: str | None,
        workspace_dir: str | None = None,
        dry_run: bool = False,
    ) -> None: ...


__all__ = ["ConversationBindingPort"]
