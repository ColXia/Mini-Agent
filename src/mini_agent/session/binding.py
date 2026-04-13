"""Conversation-to-session binding storage."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(content, encoding="utf-8")
    tmp_path.replace(path)


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


conversation_binding_store = ConversationBindingStore()


__all__ = ["ConversationBindingStore", "conversation_binding_store"]

