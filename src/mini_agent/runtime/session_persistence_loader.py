"""Runtime session persistence record loaders."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


def _safe_text(value: object) -> str:
    return " ".join(str(value or "").split())


@dataclass(slots=True)
class RuntimeSessionPersistenceLoader:
    session_kind: str
    read_shared_transcript: Callable[[str, dict[str, Any]], list[dict[str, Any]]]

    def normalize_record(self, raw_record: Any) -> dict[str, Any] | None:
        if not isinstance(raw_record, dict):
            return None
        if _safe_text(raw_record.get("session_kind")) != self.session_kind:
            return None
        return dict(raw_record)

    def load_record(
        self,
        raw_record: Any,
        *,
        session_id: str,
    ) -> dict[str, Any] | None:
        loaded = self.normalize_record(raw_record)
        if loaded is None:
            return None
        loaded["shared_transcript"] = self.read_shared_transcript(session_id, loaded)
        return loaded


__all__ = ["RuntimeSessionPersistenceLoader"]
