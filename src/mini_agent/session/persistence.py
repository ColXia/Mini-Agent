"""Disk persistence primitives for Mini-Agent session state."""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mini_agent.memory.session_search import SessionSearchIndex


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(content, encoding="utf-8")
    tmp_path.replace(path)


def _parse_utc_iso(value: Any) -> datetime:
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value)
            if parsed.tzinfo is None:
                return parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc)
        except Exception:
            pass
    return datetime.fromtimestamp(0, tz=timezone.utc)


def _message_to_dict(msg: Any) -> dict[str, Any]:
    if hasattr(msg, "model_dump"):
        payload = msg.model_dump()  # pydantic model
    elif isinstance(msg, dict):
        payload = dict(msg)
    elif hasattr(msg, "__dict__"):
        payload = dict(vars(msg))
    else:
        payload = {"role": "assistant", "content": str(msg)}

    return {
        "role": payload.get("role", "assistant"),
        "content": payload.get("content", ""),
        "thinking": payload.get("thinking"),
        "tool_calls": payload.get("tool_calls"),
        "tool_call_id": payload.get("tool_call_id"),
        "name": payload.get("name"),
    }


def _serialize_messages(messages: list[Any]) -> list[dict[str, Any]]:
    return [_message_to_dict(msg) for msg in messages]


def _sanitize_checkpoint_name(name: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", name or ""):
        raise ValueError("checkpoint_name must match [A-Za-z0-9_-]{1,64}")
    return name


def _sanitize_session_id(session_id: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", session_id or ""):
        raise ValueError("session_id must match [A-Za-z0-9][A-Za-z0-9._-]{0,127}")
    return session_id


class SessionPersistence:
    """Filesystem-backed session persistence (metadata + transcript + checkpoints)."""

    def __init__(self, base_dir: Path | None = None):
        if base_dir is None:
            env_dir = os.getenv("MINI_AGENT_SESSION_STORE_DIR")
            if env_dir:
                base_dir = Path(env_dir)
            else:
                base_dir = Path.home() / ".mini-agent" / "sessions"

        self.base_dir = base_dir.expanduser().resolve()
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.metadata_path = self.base_dir / "sessions.json"
        self.transcripts_dir = self.base_dir / "transcripts"
        self.checkpoints_dir = self.base_dir / "checkpoints"
        self.transcripts_dir.mkdir(parents=True, exist_ok=True)
        self.checkpoints_dir.mkdir(parents=True, exist_ok=True)
        self._session_search = SessionSearchIndex(self.base_dir)

    def _read_metadata(self) -> dict[str, Any]:
        if not self.metadata_path.exists():
            return {"sessions": {}}
        with open(self.metadata_path, encoding="utf-8-sig") as f:
            raw = json.load(f)
        if not isinstance(raw, dict):
            return {"sessions": {}}
        sessions = raw.get("sessions")
        if not isinstance(sessions, dict):
            raw["sessions"] = {}
        return raw

    def _write_metadata(self, payload: dict[str, Any]) -> None:
        _atomic_write_text(self.metadata_path, json.dumps(payload, ensure_ascii=False, indent=2))

    def _transcript_path(self, session_id: str) -> Path:
        safe_session_id = _sanitize_session_id(session_id)
        return self.transcripts_dir / f"{safe_session_id}.jsonl"

    def _checkpoint_path(self, session_id: str, checkpoint_name: str) -> Path:
        safe_session_id = _sanitize_session_id(session_id)
        safe_name = _sanitize_checkpoint_name(checkpoint_name)
        return self.checkpoints_dir / safe_session_id / f"{safe_name}.jsonl"

    def _delete_session_files(self, session_id: str) -> bool:
        transcript_path = self._transcript_path(session_id)
        existed = False
        if transcript_path.exists():
            transcript_path.unlink()
            existed = True

        session_checkpoint_dir = self.checkpoints_dir / _sanitize_session_id(session_id)
        if session_checkpoint_dir.exists():
            for file in session_checkpoint_dir.glob("*.jsonl"):
                file.unlink(missing_ok=True)
            try:
                session_checkpoint_dir.rmdir()
            except OSError:
                pass
            existed = True

        return existed

    def save_session(
        self,
        *,
        session_id: str,
        workspace_dir: str,
        created_at: str,
        updated_at: str,
        messages: list[Any],
        execution_policy: dict[str, Any] | None = None,
        configured_execution_policy: dict[str, Any] | None = None,
    ) -> None:
        safe_session_id = _sanitize_session_id(session_id)
        serialized = _serialize_messages(messages)
        transcript_path = self._transcript_path(safe_session_id)
        transcript_content = "".join(json.dumps(msg, ensure_ascii=False) + "\n" for msg in serialized)
        _atomic_write_text(transcript_path, transcript_content)

        metadata = self._read_metadata()
        metadata["sessions"][safe_session_id] = {
            "session_id": safe_session_id,
            "workspace_dir": workspace_dir,
            "created_at": created_at,
            "updated_at": updated_at,
            "message_count": len(serialized),
            "transcript_path": str(transcript_path),
            "execution_policy": execution_policy or {},
            "configured_execution_policy": configured_execution_policy or {},
        }
        self._write_metadata(metadata)
        try:
            self._session_search.upsert_session(
                session_id=safe_session_id,
                workspace_dir=workspace_dir,
                updated_at=updated_at,
                messages=serialized,
            )
        except Exception:
            pass

    def load_session(self, session_id: str) -> dict[str, Any] | None:
        safe_session_id = _sanitize_session_id(session_id)
        metadata = self._read_metadata()
        record = metadata.get("sessions", {}).get(safe_session_id)
        if not isinstance(record, dict):
            return None

        transcript_path = self._transcript_path(safe_session_id)
        if not transcript_path.exists():
            return None

        messages: list[dict[str, Any]] = []
        for line in transcript_path.read_text(encoding="utf-8-sig").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                parsed = json.loads(line)
                if isinstance(parsed, dict):
                    messages.append(parsed)
            except Exception:
                continue

        record = dict(record)
        record["messages"] = messages
        record["message_count"] = len(messages)
        return record

    def list_sessions(self) -> list[dict[str, Any]]:
        metadata = self._read_metadata()
        sessions = metadata.get("sessions", {})
        if not isinstance(sessions, dict):
            return []
        records = [dict(v) for v in sessions.values() if isinstance(v, dict)]
        records.sort(key=lambda r: r.get("updated_at", ""), reverse=True)
        return records

    def delete_session(self, session_id: str) -> bool:
        safe_session_id = _sanitize_session_id(session_id)
        metadata = self._read_metadata()
        sessions = metadata.get("sessions", {})
        existed = safe_session_id in sessions if isinstance(sessions, dict) else False

        if isinstance(sessions, dict) and safe_session_id in sessions:
            del sessions[safe_session_id]
            self._write_metadata(metadata)

        if self._delete_session_files(safe_session_id):
            existed = True
        try:
            self._session_search.delete_session(safe_session_id)
        except Exception:
            pass

        return existed

    def save_checkpoint(self, session_id: str, checkpoint_name: str, messages: list[Any]) -> dict[str, Any]:
        checkpoint_path = self._checkpoint_path(session_id, checkpoint_name)
        checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
        serialized = _serialize_messages(messages)
        content = "".join(json.dumps(msg, ensure_ascii=False) + "\n" for msg in serialized)
        _atomic_write_text(checkpoint_path, content)
        return {
            "checkpoint_name": _sanitize_checkpoint_name(checkpoint_name),
            "session_id": session_id,
            "created_at": _utc_now_iso(),
            "message_count": len(serialized),
        }

    def list_checkpoints(self, session_id: str) -> list[dict[str, Any]]:
        safe_session_id = _sanitize_session_id(session_id)
        session_checkpoint_dir = self.checkpoints_dir / safe_session_id
        if not session_checkpoint_dir.exists():
            return []

        records = []
        for file in session_checkpoint_dir.glob("*.jsonl"):
            stat = file.stat()
            created = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat()
            message_count = len(file.read_text(encoding="utf-8-sig").splitlines())
            records.append(
                {
                    "checkpoint_name": file.stem,
                    "session_id": safe_session_id,
                    "created_at": created,
                    "message_count": message_count,
                }
            )
        records.sort(key=lambda item: item["created_at"], reverse=True)
        return records

    def load_checkpoint(self, session_id: str, checkpoint_name: str) -> list[dict[str, Any]] | None:
        checkpoint_path = self._checkpoint_path(session_id, checkpoint_name)
        if not checkpoint_path.exists():
            return None

        messages: list[dict[str, Any]] = []
        for line in checkpoint_path.read_text(encoding="utf-8-sig").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                parsed = json.loads(line)
                if isinstance(parsed, dict):
                    messages.append(parsed)
            except Exception:
                continue
        return messages

    def cleanup(
        self,
        *,
        max_age_seconds: int | None = None,
        max_count: int | None = None,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        if max_age_seconds is not None and max_age_seconds <= 0:
            raise ValueError("max_age_seconds must be > 0.")
        if max_count is not None and max_count <= 0:
            raise ValueError("max_count must be > 0.")

        metadata = self._read_metadata()
        sessions = metadata.get("sessions", {})
        if not isinstance(sessions, dict):
            sessions = {}
            metadata["sessions"] = sessions

        records: list[dict[str, Any]] = []
        for session_id, record in sessions.items():
            if not isinstance(record, dict):
                continue
            records.append(
                {
                    "session_id": str(session_id),
                    "updated_at": _parse_utc_iso(record.get("updated_at")),
                }
            )

        if max_age_seconds is None and max_count is None:
            return {
                "deleted": 0,
                "remaining": len(records),
                "deleted_session_ids": [],
            }

        now = now or datetime.now(timezone.utc)
        to_delete: set[str] = set()

        if max_age_seconds is not None:
            for record in records:
                age = (now - record["updated_at"]).total_seconds()
                if age > max_age_seconds:
                    to_delete.add(record["session_id"])

        if max_count is not None:
            remaining = [r for r in records if r["session_id"] not in to_delete]
            remaining.sort(key=lambda item: item["updated_at"], reverse=True)
            if len(remaining) > max_count:
                for extra in remaining[max_count:]:
                    to_delete.add(extra["session_id"])

        if not to_delete:
            return {
                "deleted": 0,
                "remaining": len(records),
                "deleted_session_ids": [],
            }

        for session_id in to_delete:
            sessions.pop(session_id, None)
        self._write_metadata(metadata)

        for session_id in to_delete:
            try:
                self._delete_session_files(session_id)
            except ValueError:
                # Legacy invalid IDs are removed from metadata even if files are not addressable.
                continue
            try:
                self._session_search.delete_session(session_id)
            except Exception:
                pass

        remaining = len(records) - len(to_delete)
        return {
            "deleted": len(to_delete),
            "remaining": max(remaining, 0),
            "deleted_session_ids": sorted(to_delete),
        }

    def search_sessions(
        self,
        *,
        query: str,
        limit: int = 20,
        session_id: str | None = None,
    ) -> list[dict[str, Any]]:
        safe_session_id = _sanitize_session_id(session_id) if session_id else None
        return self._session_search.search(
            query=query,
            limit=limit,
            session_id=safe_session_id,
        )

    def session_search_stats(self) -> dict[str, Any]:
        return self._session_search.stats()

    def search_relevant_memory(
        self,
        *,
        query: str,
        memory_file: Path | str,
        top_k: int = 5,
        stale_after_days: int = 30,
    ) -> dict[str, Any]:
        from mini_agent.memory.relevance import ConsolidatedMemoryRelevanceRetriever

        retriever = ConsolidatedMemoryRelevanceRetriever(memory_file)
        return retriever.search(
            query=query,
            top_k=top_k,
            stale_after_days=stale_after_days,
            support_lookup=lambda side_query, side_limit: self.search_sessions(
                query=side_query,
                limit=side_limit,
            ),
        )
