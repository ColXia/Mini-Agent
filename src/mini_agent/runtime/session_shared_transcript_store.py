"""Runtime shared transcript store helpers."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Sequence
from uuid import uuid4

if TYPE_CHECKING:
    from mini_agent.runtime.session_state import MainAgentSessionTranscriptEntry


def _atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(content, encoding="utf-8")
    tmp_path.replace(path)


@dataclass(slots=True)
class RuntimeSessionSharedTranscriptStore:
    transcripts_dir: Path
    serialize_transcript_entry: Callable[["MainAgentSessionTranscriptEntry"], dict[str, Any]]

    def __post_init__(self) -> None:
        self.transcripts_dir.mkdir(parents=True, exist_ok=True)

    def path_for(self, session_id: str) -> Path:
        normalized = "".join(
            char if char.isalnum() or char in "._-" else "_"
            for char in str(session_id or "")
        ).strip()
        safe_session_id = normalized or uuid4().hex
        return self.transcripts_dir / f"{safe_session_id}.jsonl"

    def write(
        self,
        session_id: str,
        entries: Sequence["MainAgentSessionTranscriptEntry"],
    ) -> Path:
        transcript_path = self.path_for(session_id)
        content = "".join(
            json.dumps(self.serialize_transcript_entry(entry), ensure_ascii=False) + "\n"
            for entry in entries
        )
        _atomic_write_text(transcript_path, content)
        return transcript_path

    def read(
        self,
        session_id: str,
        record: dict[str, Any],
    ) -> list[dict[str, Any]]:
        configured_path = str(record.get("shared_transcript_path") or "").strip()
        transcript_path = Path(configured_path) if configured_path else self.path_for(session_id)
        if not transcript_path.exists():
            return []
        items: list[dict[str, Any]] = []
        for line in transcript_path.read_text(encoding="utf-8-sig").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                parsed = json.loads(line)
            except Exception:
                continue
            if isinstance(parsed, dict):
                items.append(parsed)
        return items

    def delete(self, session_id: str) -> None:
        try:
            self.path_for(session_id).unlink(missing_ok=True)
        except Exception:
            pass


__all__ = ["RuntimeSessionSharedTranscriptStore"]
