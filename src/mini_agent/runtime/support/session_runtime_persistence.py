"""Persistence wrapper for gateway-managed runtime sessions."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import tempfile
from typing import TYPE_CHECKING, Any, Sequence
from uuid import uuid4

from mini_agent.runtime.support.session_persistence_loader import RuntimeSessionPersistenceLoader
from mini_agent.runtime.support.session_persistence_metadata_registry import RuntimeSessionPersistenceMetadataRegistry
from mini_agent.runtime.support.session_persistence_record_builder import RuntimeSessionPersistenceRecordBuilder
from mini_agent.runtime.support.session_shared_transcript_store import RuntimeSessionSharedTranscriptStore
from mini_agent.runtime.support.sandbox_state import normalize_sandbox_diagnostics
from mini_agent.session.persistence import SessionPersistence

if TYPE_CHECKING:
    from mini_agent.runtime.session_state import MainAgentSessionState


def _to_utc_iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


class MainAgentRuntimePersistence:
    """Persist live runtime sessions plus transcript sidecars."""

    def __init__(
        self,
        storage_dir: Path | None = None,
        *,
        record_loader: RuntimeSessionPersistenceLoader,
        record_builder: RuntimeSessionPersistenceRecordBuilder,
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
        session: MainAgentSessionState,
        *,
        agent_messages: Sequence[Any] | None = None,
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
        self._metadata_registry.upsert_record(
            session.session_id,
            self._record_builder.build_metadata_record(
                session,
                transcript_path=transcript_path,
                sandbox_diagnostics=normalized_sandbox,
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


__all__ = ["MainAgentRuntimePersistence"]
