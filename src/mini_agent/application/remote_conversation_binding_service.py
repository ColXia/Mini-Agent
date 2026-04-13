"""Shared remote conversation binding service for channel adapters."""

from __future__ import annotations

from mini_agent.runtime.interaction_surface import resolve_interaction_binding
from mini_agent.session import ConversationBindingStore, conversation_binding_store


def _clean(value: str | None) -> str:
    return " ".join(str(value or "").strip().split())


class RemoteConversationBindingService:
    """Resolve and persist remote conversation-to-session bindings centrally."""

    def __init__(self, *, binding_store: ConversationBindingStore | None = None) -> None:
        self._binding_store = binding_store or conversation_binding_store

    def resolve_session_id(
        self,
        *,
        channel_type: str | None,
        conversation_id: str | None,
        explicit_session_id: str | None = None,
        dry_run: bool = False,
    ) -> str | None:
        explicit = _clean(explicit_session_id)
        if explicit:
            return explicit
        if dry_run:
            return None
        binding_key = self._binding_key(channel_type=channel_type, conversation_id=conversation_id)
        if not binding_key:
            return None
        return self._binding_store.get_session_id(binding_key)

    def persist_binding(
        self,
        *,
        channel_type: str | None,
        conversation_id: str | None,
        session_id: str | None,
        workspace_dir: str | None = None,
        dry_run: bool = False,
    ) -> None:
        if dry_run:
            return
        normalized_session_id = _clean(session_id)
        if not normalized_session_id:
            return
        binding = self._binding_context(channel_type=channel_type, conversation_id=conversation_id)
        if binding is None:
            return
        self._binding_store.set(
            binding_key=binding["binding_key"],
            session_id=normalized_session_id,
            workspace_dir=_clean(workspace_dir) or None,
            channel_type=binding["channel_type"],
            conversation_id=binding["conversation_id"],
        )

    def _binding_key(self, *, channel_type: str | None, conversation_id: str | None) -> str | None:
        binding = self._binding_context(channel_type=channel_type, conversation_id=conversation_id)
        if binding is None:
            return None
        return binding["binding_key"]

    def _binding_context(
        self,
        *,
        channel_type: str | None,
        conversation_id: str | None,
    ) -> dict[str, str] | None:
        binding = resolve_interaction_binding(
            surface=None,
            channel_type=channel_type,
            conversation_id=conversation_id,
        )
        if binding.entrance != "remote" or not binding.channel_type or not binding.conversation_id:
            return None
        return {
            "binding_key": f"{binding.channel_type}|{binding.conversation_id}",
            "channel_type": binding.channel_type,
            "conversation_id": binding.conversation_id,
        }


__all__ = ["RemoteConversationBindingService"]
