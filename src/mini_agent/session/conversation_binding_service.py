"""Shared remote conversation-to-session binding service."""

from __future__ import annotations

from mini_agent.runtime.support.interaction_surface import resolve_interaction_binding

from .binding import ConversationBindingStore, conversation_binding_store


def _clean(value: str | None) -> str:
    return " ".join(str(value or "").strip().split())


class ConversationBindingService:
    """Resolve and persist remote conversation-to-session bindings centrally."""

    def __init__(self, *, binding_store: ConversationBindingStore | None = None) -> None:
        self._binding_store = binding_store or conversation_binding_store

    def resolve_session_id(
        self,
        *,
        surface: str | None = None,
        channel_type: str | None = None,
        conversation_id: str | None = None,
        explicit_session_id: str | None = None,
        dry_run: bool = False,
    ) -> str | None:
        explicit = _clean(explicit_session_id)
        if explicit:
            return explicit
        if dry_run:
            return None
        binding = resolve_interaction_binding(
            surface=surface or channel_type,
            channel_type=channel_type,
            conversation_id=conversation_id,
            default_surface=None,
        )
        if binding.entrance != "remote" or not binding.channel_type or not binding.conversation_id:
            return None
        binding_key = f"{binding.channel_type}|{binding.conversation_id}"
        return self._binding_store.get_session_id(binding_key)

    def persist_binding(
        self,
        *,
        surface: str | None = None,
        channel_type: str | None = None,
        conversation_id: str | None = None,
        session_id: str | None,
        workspace_dir: str | None = None,
        dry_run: bool = False,
    ) -> None:
        if dry_run:
            return
        normalized_session_id = _clean(session_id)
        if not normalized_session_id:
            return
        binding = resolve_interaction_binding(
            surface=surface or channel_type,
            channel_type=channel_type,
            conversation_id=conversation_id,
            default_surface=None,
        )
        if binding.entrance != "remote" or not binding.channel_type or not binding.conversation_id:
            return
        binding_key = f"{binding.channel_type}|{binding.conversation_id}"
        self._binding_store.set(
            binding_key=binding_key,
            session_id=normalized_session_id,
            workspace_dir=_clean(workspace_dir) or None,
            channel_type=binding.channel_type,
            conversation_id=binding.conversation_id,
        )


__all__ = ["ConversationBindingService"]
