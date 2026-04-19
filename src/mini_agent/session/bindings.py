"""Conversation-to-session binding storage."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

from mini_agent.runtime.support.interaction_surface import resolve_interaction_binding


DEFAULT_SESSION_ID = "default"
DEFAULT_SESSION_TITLE = "Session 1"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(content, encoding="utf-8")
    tmp_path.replace(path)


def is_default_session_id(session_id: object) -> bool:
    return " ".join(str(session_id or "").split()) == DEFAULT_SESSION_ID


def _clean(value: str | None) -> str:
    return " ".join(str(value or "").strip().split())


class ConversationBindingStore:
    """Persistent binding map from channel conversation key to session_id."""

    def __init__(self, path: Path | None = None):
        if path is None:
            env_path = os.getenv("MINI_AGENT_BINDING_STORE_PATH")
            if env_path:
                path = Path(env_path)
            else:
                path = Path.home() / ".mini-agent" / "sessions" / "conversation_bindings.json"
        self.path = path.expanduser().resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"bindings": {}}
        try:
            with open(self.path, encoding="utf-8-sig") as f:
                payload = json.load(f)
        except Exception:
            return {"bindings": {}}
        if not isinstance(payload, dict):
            return {"bindings": {}}
        bindings = payload.get("bindings")
        if not isinstance(bindings, dict):
            payload["bindings"] = {}
        return payload

    def _save(self, payload: dict[str, Any]) -> None:
        _atomic_write_text(
            self.path,
            json.dumps(payload, ensure_ascii=False, indent=2),
        )

    def get(self, binding_key: str) -> dict[str, Any] | None:
        payload = self._load()
        record = payload.get("bindings", {}).get(binding_key)
        if isinstance(record, dict):
            return record
        return None

    def get_session_id(self, binding_key: str) -> str | None:
        record = self.get(binding_key)
        if not record:
            return None
        session_id = record.get("session_id")
        if isinstance(session_id, str) and session_id:
            return session_id
        return None

    def set(
        self,
        *,
        binding_key: str,
        session_id: str,
        workspace_dir: str | None = None,
        channel_type: str | None = None,
        conversation_id: str | None = None,
    ) -> None:
        payload = self._load()
        bindings = payload.setdefault("bindings", {})
        bindings[binding_key] = {
            "binding_key": binding_key,
            "session_id": session_id,
            "channel_type": channel_type or "",
            "conversation_id": conversation_id or "",
            "workspace_dir": workspace_dir or "",
            "updated_at": _utc_now_iso(),
        }
        self._save(payload)

    def delete(self, binding_key: str) -> bool:
        payload = self._load()
        bindings = payload.get("bindings", {})
        if not isinstance(bindings, dict) or binding_key not in bindings:
            return False
        del bindings[binding_key]
        self._save(payload)
        return True


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


conversation_binding_store = ConversationBindingStore()


__all__ = [
    "ConversationBindingPort",
    "ConversationBindingService",
    "ConversationBindingStore",
    "DEFAULT_SESSION_ID",
    "DEFAULT_SESSION_TITLE",
    "conversation_binding_store",
    "is_default_session_id",
]

