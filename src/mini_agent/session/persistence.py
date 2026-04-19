"""Disk persistence primitives for Mini-Agent session state."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable
import tempfile
from uuid import uuid4

from mini_agent.memory.session_search import SessionSearchIndex
from mini_agent.runtime.support.sandbox_state import normalize_sandbox_diagnostics
from mini_agent.workspace_runtime.snapshot_store import (
    capture_shared_workspace_snapshot,
    workspace_runtime_snapshot_payload,
)

if TYPE_CHECKING:
    from mini_agent.session.store_records import (
        MainAgentSessionState,
        MainAgentSessionTranscriptEntry,
    )


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


def _to_utc_iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


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


def _safe_text(value: object) -> str:
    return " ".join(str(value or "").split())


@dataclass(slots=True)
class RuntimeSessionPersistenceRecordBuilder:
    session_kind: str
    session_token_usage: Callable[["MainAgentSessionState"], int]
    session_token_limit: Callable[["MainAgentSessionState"], int]
    agent_last_memory_automation: Callable[[Any], dict[str, Any]] | None = None
    agent_last_runtime_task_memory: Callable[[Any], dict[str, Any]] | None = None
    active_pending_approvals: Callable[["MainAgentSessionState"], list[dict[str, Any]]] | None = None
    active_run_control_state: Callable[["MainAgentSessionState"], dict[str, Any] | None] | None = None
    active_approval_wait: Callable[["MainAgentSessionState"], dict[str, Any] | None] | None = None
    active_kernel_state: Callable[["MainAgentSessionState"], dict[str, Any] | None] | None = None
    selected_model_identity_for_session: (
        Callable[["MainAgentSessionState"], tuple[str, str, str] | None] | None
    ) = None
    pending_model_identity_for_session: (
        Callable[["MainAgentSessionState"], tuple[str, str, str] | None] | None
    ) = None

    @staticmethod
    def _normalize_agent_payload(value: Any) -> dict[str, Any]:
        return dict(value) if isinstance(value, dict) else {}

    def _read_agent_last_memory_automation(self, agent: Any) -> dict[str, Any]:
        if callable(self.agent_last_memory_automation):
            try:
                return self._normalize_agent_payload(self.agent_last_memory_automation(agent))
            except Exception:
                return {}
        return self._normalize_agent_payload(getattr(agent, "last_memory_automation", {}))

    def _read_agent_last_runtime_task_memory(self, agent: Any) -> dict[str, Any]:
        if callable(self.agent_last_runtime_task_memory):
            try:
                return self._normalize_agent_payload(self.agent_last_runtime_task_memory(agent))
            except Exception:
                return {}
        return self._normalize_agent_payload(getattr(agent, "last_runtime_task_memory", {}))

    def _read_active_run_control_state(self, session: "MainAgentSessionState") -> dict[str, Any] | None:
        if not callable(self.active_run_control_state):
            return None
        try:
            payload = self.active_run_control_state(session)
        except Exception:
            return None
        return dict(payload) if isinstance(payload, dict) else None

    def _read_active_approval_wait(self, session: "MainAgentSessionState") -> dict[str, Any] | None:
        if not callable(self.active_approval_wait):
            return None
        try:
            payload = self.active_approval_wait(session)
        except Exception:
            return None
        return dict(payload) if isinstance(payload, dict) else None

    def _read_active_kernel_state(self, session: "MainAgentSessionState") -> dict[str, Any] | None:
        if not callable(self.active_kernel_state):
            return None
        try:
            payload = self.active_kernel_state(session)
        except Exception:
            return None
        return dict(payload) if isinstance(payload, dict) else None

    def _read_active_pending_approvals(self, session: "MainAgentSessionState") -> list[dict[str, Any]]:
        if callable(self.active_pending_approvals):
            try:
                payload = self.active_pending_approvals(session)
            except Exception:
                payload = None
            if isinstance(payload, list):
                return [dict(item) for item in payload if isinstance(item, dict)]
        return []

    def _read_selected_model_identity(
        self,
        session: "MainAgentSessionState",
    ) -> tuple[str, str, str] | None:
        if callable(self.selected_model_identity_for_session):
            try:
                identity = self.selected_model_identity_for_session(session)
            except Exception:
                identity = None
            if isinstance(identity, tuple) and len(identity) == 3:
                return identity
        source = _safe_text(session.projection.selected_model_source) or None
        provider_id = _safe_text(session.projection.selected_provider_id) or None
        model_id = _safe_text(session.projection.selected_model_id) or None
        if source and provider_id and model_id:
            return source, provider_id, model_id
        return None

    def _read_pending_model_identity(
        self,
        session: "MainAgentSessionState",
    ) -> tuple[str, str, str] | None:
        if callable(self.pending_model_identity_for_session):
            try:
                identity = self.pending_model_identity_for_session(session)
            except Exception:
                identity = None
            if isinstance(identity, tuple) and len(identity) == 3:
                return identity
        source = _safe_text(session.projection.pending_model_source) or None
        provider_id = _safe_text(session.projection.pending_provider_id) or None
        model_id = _safe_text(session.projection.pending_model_id) or None
        if source and provider_id and model_id:
            return source, provider_id, model_id
        return None

    @staticmethod
    def serialize_transcript_entry(entry: "MainAgentSessionTranscriptEntry") -> dict[str, Any]:
        return {
            "index": int(entry.index),
            "role": _safe_text(entry.role).lower() or "assistant",
            "content": str(entry.content or ""),
            "surface": _safe_text(entry.surface).lower() or "api",
            "created_at": _to_utc_iso(entry.created_at),
            "channel_type": _safe_text(entry.channel_type) or None,
            "conversation_id": _safe_text(entry.conversation_id) or None,
            "sender_id": _safe_text(entry.sender_id) or None,
            "metadata": dict(entry.metadata) if isinstance(entry.metadata, dict) else {},
        }

    @staticmethod
    def serialize_pending_approval(item: dict[str, Any]) -> dict[str, Any]:
        return {
            "token": _safe_text(item.get("token")) or None,
            "tool_name": _safe_text(item.get("tool_name")) or None,
            "arguments": dict(item.get("arguments")) if isinstance(item.get("arguments"), dict) else {},
            "kind": _safe_text(item.get("kind")) or None,
            "reason": _safe_text(item.get("reason")) or None,
            "cache_key": _safe_text(item.get("cache_key")) or None,
            "can_escalate": bool(item.get("can_escalate", False)),
            "step": int(item.get("step") or 0),
        }

    def build_metadata_record(
        self,
        session: "MainAgentSessionState",
        *,
        transcript_path: Path,
        sandbox_diagnostics: dict[str, Any],
        workspace_runtime_snapshot: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        pending_approvals = self._read_active_pending_approvals(session)
        selected_identity = self._read_selected_model_identity(session)
        pending_identity = self._read_pending_model_identity(session)
        return {
            "session_id": session.session_id,
            "workspace_dir": str(session.workspace_dir),
            "created_at": _to_utc_iso(session.created_at),
            "updated_at": _to_utc_iso(session.updated_at),
            "message_count": len(session.transcript_state.transcript),
            "session_kind": self.session_kind,
            "title": _safe_text(session.projection.title) or None,
            "origin_surface": _safe_text(session.projection.origin_surface) or "api",
            "active_surface": _safe_text(session.projection.active_surface or session.projection.origin_surface) or "api",
            "reply_enabled": bool(session.projection.reply_enabled),
            "is_default": bool(session.projection.is_default),
            "busy": bool(session.projection.busy),
            "running_state": _safe_text(session.projection.running_state) or None,
            "channel_type": _safe_text(session.projection.channel_type) or None,
            "conversation_id": _safe_text(session.projection.conversation_id) or None,
            "sender_id": _safe_text(session.projection.sender_id) or None,
            "token_usage": self.session_token_usage(session),
            "token_limit": self.session_token_limit(session),
            "shared": bool(session.projection.shared),
            "knowledge_base_enabled": bool(session.projection.knowledge_base_enabled),
            "selected_model_source": selected_identity[0] if selected_identity is not None else None,
            "selected_provider_id": selected_identity[1] if selected_identity is not None else None,
            "selected_model_id": selected_identity[2] if selected_identity is not None else None,
            "pending_model_source": pending_identity[0] if pending_identity is not None else None,
            "pending_provider_id": pending_identity[1] if pending_identity is not None else None,
            "pending_model_id": pending_identity[2] if pending_identity is not None else None,
            "lineage_parent_session_id": _safe_text(session.lineage_state.parent_session_id) or None,
            "lineage_root_session_id": (
                _safe_text(session.lineage_state.root_session_id) or session.session_id
            ),
            "lineage_reason": _safe_text(session.lineage_state.reason) or "root",
            "lineage_created_at": _to_utc_iso(session.lineage_state.created_at),
            "lineage_metadata": (
                dict(session.lineage_state.metadata)
                if isinstance(session.lineage_state.metadata, dict)
                else {}
            ),
            "pending_skill_reload": bool(session.projection.pending_skill_reload),
            "pending_skill_reload_reason": _safe_text(session.projection.pending_skill_reload_reason) or None,
            "shared_transcript_path": str(transcript_path),
            "shared_message_count": len(session.transcript_state.transcript),
            "next_transcript_index": int(session.transcript_state.next_transcript_index),
            "pending_approvals": [self.serialize_pending_approval(item) for item in pending_approvals],
            "recovery_context_pending": bool(session.projection.recovery_context_pending),
            "recovery_state": _safe_text(session.projection.recovery_state) or None,
            "recovery_summary": _safe_text(session.projection.recovery_summary) or None,
            "recovery_last_activity": _safe_text(session.projection.recovery_last_activity) or None,
            "recovery_last_user_message": _safe_text(session.projection.recovery_last_user_message) or None,
            "recovery_last_assistant_message": _safe_text(session.projection.recovery_last_assistant_message) or None,
            "recovery_pending_approvals": [
                self.serialize_pending_approval(item)
                for item in session.projection.recovery_pending_approvals
                if isinstance(item, dict)
            ],
            "context_policy": (
                dict(session.projection.context_policy)
                if isinstance(session.projection.context_policy, dict)
                else {}
            ),
            "last_prepared_context": (
                dict(session.projection.last_prepared_context)
                if isinstance(session.projection.last_prepared_context, dict)
                else {}
            ),
            "prepared_context_diagnostics": (
                dict(session.projection.prepared_context_diagnostics)
                if isinstance(session.projection.prepared_context_diagnostics, dict)
                else {}
            ),
            "memory_diagnostics": (
                dict(session.projection.memory_diagnostics)
                if isinstance(session.projection.memory_diagnostics, dict)
                else {}
            ),
            "sandbox_diagnostics": dict(sandbox_diagnostics) if isinstance(sandbox_diagnostics, dict) else {},
            "workspace_runtime_snapshot": (
                dict(workspace_runtime_snapshot)
                if isinstance(workspace_runtime_snapshot, dict)
                else None
            ),
            "last_memory_automation": self._read_agent_last_memory_automation(session.runtime.agent),
            "last_runtime_task_memory": self._read_agent_last_runtime_task_memory(session.runtime.agent),
            "run_control": self._read_active_run_control_state(session),
            "approval_wait": self._read_active_approval_wait(session),
            "kernel_state": self._read_active_kernel_state(session),
        }


class RuntimeSessionPersistenceMetadataRegistry:
    def __init__(self, metadata_path: Path) -> None:
        self.metadata_path = metadata_path

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


class RuntimeSessionSharedTranscriptStore:
    def __init__(
        self,
        transcripts_dir: Path,
        *,
        serialize_transcript_entry,
    ) -> None:
        self.transcripts_dir = transcripts_dir
        self.serialize_transcript_entry = serialize_transcript_entry
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
        entries,
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


class RuntimeSessionPersistenceLoader:
    def __init__(
        self,
        *,
        session_kind: str,
        read_shared_transcript,
    ) -> None:
        self.session_kind = session_kind
        self.read_shared_transcript = read_shared_transcript

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


class MainAgentRuntimePersistence:
    """Persist live runtime sessions plus transcript sidecars."""

    def __init__(
        self,
        storage_dir: Path | None = None,
        *,
        record_loader: RuntimeSessionPersistenceLoader,
        record_builder,
    ) -> None:
        if storage_dir is None:
            storage_dir = Path(tempfile.gettempdir()) / f"mini-agent-main-agent-runtime-{uuid4().hex}"
        self._session_store = SessionPersistence(storage_dir)
        self._record_loader = record_loader
        self._record_builder = record_builder
        self._metadata_registry = RuntimeSessionPersistenceMetadataRegistry(
            self._session_store.metadata_path,
        )
        self._shared_transcripts = RuntimeSessionSharedTranscriptStore(
            transcripts_dir=self._session_store.base_dir / "main_agent_runtime_transcripts",
            serialize_transcript_entry=self._record_builder.serialize_transcript_entry,
        )

    def read_shared_transcript(self, session_id: str, record: dict[str, Any]) -> list[dict[str, Any]]:
        return self._shared_transcripts.read(session_id, record)

    def save_session(
        self,
        session,
        *,
        agent_messages=None,
        sandbox_diagnostics: dict[str, Any] | None = None,
    ) -> None:
        messages = list(agent_messages) if agent_messages is not None else list(getattr(session.runtime.agent, "messages", []) or [])
        self._session_store.save_session(
            session_id=session.session_id,
            workspace_dir=str(session.workspace_dir),
            created_at=_to_utc_iso(session.created_at),
            updated_at=_to_utc_iso(session.updated_at),
            messages=messages,
        )

        transcript_path = self._shared_transcripts.write(
            session.session_id,
            session.transcript_state.transcript,
        )
        normalized_sandbox = normalize_sandbox_diagnostics(
            sandbox_diagnostics or session.projection.sandbox_diagnostics,
        )
        workspace_runtime_snapshot = workspace_runtime_snapshot_payload(
            capture_shared_workspace_snapshot(
                session.workspace_dir,
                metadata={
                    "trigger": "session_persist",
                    "session_id": session.session_id,
                    "message_count": len(session.transcript_state.transcript),
                },
            )
        )
        self._metadata_registry.upsert_record(
            session.session_id,
            self._record_builder.build_metadata_record(
                session,
                transcript_path=transcript_path,
                sandbox_diagnostics=normalized_sandbox,
                workspace_runtime_snapshot=workspace_runtime_snapshot,
            ),
        )

    def list_session_records(self) -> list[dict[str, Any]]:
        records = []
        for raw_record in self._metadata_registry.list_records():
            record = self._record_loader.normalize_record(raw_record)
            if record is not None:
                records.append(record)
        records.sort(key=lambda item: str(item.get("updated_at", "")), reverse=True)
        return records

    def load_session_record(self, session_id: str) -> dict[str, Any] | None:
        return self._record_loader.load_record(
            self._session_store.load_session(session_id),
            session_id=session_id,
        )

    def delete_session(self, session_id: str) -> bool:
        existed = self._session_store.delete_session(session_id)
        self._shared_transcripts.delete(session_id)
        return existed


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
        workspace_anchor_dir: str | None = None,
        exclude_session_id: str | None = None,
    ) -> list[dict[str, Any]]:
        safe_session_id = _sanitize_session_id(session_id) if session_id else None
        safe_exclude_session_id = _sanitize_session_id(exclude_session_id) if exclude_session_id else None
        return self._session_search.search(
            query=query,
            limit=limit,
            session_id=safe_session_id,
            workspace_anchor_dir=workspace_anchor_dir,
            exclude_session_id=safe_exclude_session_id,
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
        workspace_anchor_dir: str | None = None,
        exclude_session_id: str | None = None,
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
                workspace_anchor_dir=workspace_anchor_dir,
                exclude_session_id=exclude_session_id,
            ),
        )
