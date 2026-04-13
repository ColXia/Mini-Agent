"""Runtime session metadata registry helpers."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


def _atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(content, encoding="utf-8")
    tmp_path.replace(path)


@dataclass(slots=True)
class RuntimeSessionPersistenceMetadataRegistry:
    metadata_path: Path

    def read_payload(self) -> dict[str, Any]:
        path = self.metadata_path
        if not path.exists():
            return {"sessions": {}}
        try:
            raw = json.loads(path.read_text(encoding="utf-8-sig"))
        except Exception:
            return {"sessions": {}}
        if not isinstance(raw, dict):
            return {"sessions": {}}
        sessions = raw.get("sessions")
        if not isinstance(sessions, dict):
            raw["sessions"] = {}
        return raw

    def write_payload(self, payload: dict[str, Any]) -> None:
        _atomic_write_text(
            self.metadata_path,
            json.dumps(payload, ensure_ascii=False, indent=2),
        )

    def upsert_record(
        self,
        session_id: str,
        record: dict[str, Any],
    ) -> None:
        payload = self.read_payload()
        sessions = payload.setdefault("sessions", {})
        if not isinstance(sessions, dict):
            sessions = {}
            payload["sessions"] = sessions
        sessions[str(session_id)] = dict(record)
        self.write_payload(payload)

    def list_records(self) -> list[dict[str, Any]]:
        payload = self.read_payload()
        sessions = payload.get("sessions", {})
        if not isinstance(sessions, dict):
            return []
        records = [dict(item) for item in sessions.values() if isinstance(item, dict)]
        records.sort(key=lambda item: str(item.get("updated_at", "")), reverse=True)
        return records


__all__ = ["RuntimeSessionPersistenceMetadataRegistry"]
