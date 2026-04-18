"""Runtime session snapshot export builders."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

try:
    from mini_agent.interaction import normalize_channel_type
except Exception:  # pragma: no cover - compatibility path for staged interaction extraction
    from mini_agent.runtime.support.interaction_surface import normalize_channel_type
from mini_agent.runtime.support.session_snapshot import (
    RuntimeSessionImportMessage,
    RuntimeSessionSnapshot,
)

if TYPE_CHECKING:
    from mini_agent.runtime.session_state import (
        MainAgentSessionState,
        MainAgentSessionTranscriptEntry,
    )


def _safe_text(value: object) -> str:
    return " ".join(str(value or "").split())


def _to_utc_iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


@dataclass(slots=True)
class RuntimeSessionSnapshotBuilder:
    normalize_surface: Callable[[object | None], str]
    normalize_model_source: Callable[[object], str | None]
    normalize_context_policy_payload: Callable[[Any], dict[str, Any]]
    normalize_prepared_context_payload: Callable[[Any], dict[str, Any]]
    normalize_prepared_context_diagnostics_payload: Callable[[Any], dict[str, Any]]
    build_memory_diagnostics_for_session: Callable[["MainAgentSessionState"], dict[str, Any]]
    build_memory_diagnostics_from_record: Callable[[dict[str, Any]], dict[str, Any]]
    build_sandbox_diagnostics_for_session: Callable[["MainAgentSessionState"], dict[str, Any]]
    build_sandbox_diagnostics_from_record: Callable[[dict[str, Any]], dict[str, Any]]
    build_workspace_runtime_snapshot_for_session: Callable[["MainAgentSessionState"], dict[str, Any] | None]
    build_workspace_runtime_snapshot_from_record: Callable[[dict[str, Any]], dict[str, Any] | None]
    snapshot_runtime_task_memory_payload: Callable[..., dict[str, Any]]
    snapshot_workspace_shared_runtime_task_memory_payload: Callable[..., dict[str, Any]]
    session_token_usage: Callable[["MainAgentSessionState"], int]
    session_token_limit: Callable[["MainAgentSessionState"], int]
    record_token_usage: Callable[[dict[str, Any]], int]
    record_token_limit: Callable[[dict[str, Any]], int]
    transcript_entries_from_record: Callable[[dict[str, Any]], list["MainAgentSessionTranscriptEntry"]]
    agent_messages: Callable[[Any], list[Any]]
    serialize_agent_messages: Callable[[Any], list[dict[str, Any]]]

    def build_session_snapshot(self, session: "MainAgentSessionState") -> RuntimeSessionSnapshot:
        memory_diagnostics = self.build_memory_diagnostics_for_session(session)
        sandbox_diagnostics = self.build_sandbox_diagnostics_for_session(session)
        workspace_runtime_snapshot = self.build_workspace_runtime_snapshot_for_session(session)
        return RuntimeSessionSnapshot(
            session_id=session.session_id,
            workspace_dir=str(session.workspace_dir),
            title=_safe_text(session.projection.title) or None,
            origin_surface=self.normalize_surface(session.projection.origin_surface),
            active_surface=self.normalize_surface(
                session.projection.active_surface or session.projection.origin_surface
            ),
            reply_enabled=bool(session.projection.reply_enabled),
            is_default=bool(session.projection.is_default),
            channel_type=session.projection.channel_type,
            conversation_id=session.projection.conversation_id,
            sender_id=session.projection.sender_id,
            token_usage=self.session_token_usage(session),
            token_limit=self.session_token_limit(session),
            shared=bool(session.projection.shared),
            knowledge_base_enabled=bool(session.projection.knowledge_base_enabled),
            selected_model_source=session.projection.selected_model_source,
            selected_provider_id=session.projection.selected_provider_id,
            selected_model_id=session.projection.selected_model_id,
            pending_model_source=session.projection.pending_model_source,
            pending_provider_id=session.projection.pending_provider_id,
            pending_model_id=session.projection.pending_model_id,
            lineage_parent_session_id=session.lineage_state.parent_session_id,
            lineage_root_session_id=_safe_text(session.lineage_state.root_session_id) or session.session_id,
            lineage_reason=_safe_text(session.lineage_state.reason) or "root",
            lineage_created_at=_to_utc_iso(session.lineage_state.created_at),
            lineage_metadata=(
                dict(session.lineage_state.metadata)
                if isinstance(session.lineage_state.metadata, dict)
                else {}
            ),
            pending_skill_reload=bool(session.projection.pending_skill_reload),
            pending_skill_reload_reason=_safe_text(session.projection.pending_skill_reload_reason) or None,
            context_policy=self.normalize_context_policy_payload(session.projection.context_policy),
            last_prepared_context=self.normalize_prepared_context_payload(session.projection.last_prepared_context),
            prepared_context_diagnostics=self.normalize_prepared_context_diagnostics_payload(
                session.projection.prepared_context_diagnostics
            ),
            memory_diagnostics=dict(memory_diagnostics),
            sandbox_diagnostics=dict(sandbox_diagnostics),
            workspace_runtime_snapshot=(
                dict(workspace_runtime_snapshot) if isinstance(workspace_runtime_snapshot, dict) else {}
            ),
            runtime_task_memory_payload=self.snapshot_runtime_task_memory_payload(
                workspace_dir=session.workspace_dir,
                session_id=session.session_id,
            ),
            workspace_shared_runtime_memory_payload=self.snapshot_workspace_shared_runtime_task_memory_payload(
                workspace_dir=session.workspace_dir,
            ),
            agent_messages=self.serialize_agent_messages(self.agent_messages(session.runtime.agent)),
            transcript=[self._build_import_message(entry) for entry in session.transcript_state.transcript],
        )

    def build_session_snapshot_from_record(self, record: dict[str, Any]) -> RuntimeSessionSnapshot:
        transcript = self.transcript_entries_from_record(record)
        raw_messages = record.get("messages")
        agent_messages = raw_messages if isinstance(raw_messages, list) else []
        workspace_dir = Path(str(record.get("workspace_dir", "."))).expanduser().resolve()
        session_id = _safe_text(record.get("session_id")) or None
        return RuntimeSessionSnapshot(
            session_id=session_id,
            workspace_dir=str(record.get("workspace_dir", "")),
            title=_safe_text(record.get("title")) or None,
            origin_surface=self.normalize_surface(record.get("origin_surface")),
            active_surface=self.normalize_surface(record.get("active_surface") or record.get("origin_surface")),
            reply_enabled=bool(record.get("reply_enabled", False)),
            is_default=bool(record.get("is_default", False)),
            channel_type=normalize_channel_type(record.get("channel_type")),
            conversation_id=_safe_text(record.get("conversation_id")) or None,
            sender_id=_safe_text(record.get("sender_id")) or None,
            token_usage=self.record_token_usage(record),
            token_limit=self.record_token_limit(record),
            shared=bool(record.get("shared", False)),
            knowledge_base_enabled=bool(record.get("knowledge_base_enabled", True)),
            selected_model_source=self.normalize_model_source(record.get("selected_model_source")),
            selected_provider_id=_safe_text(record.get("selected_provider_id")) or None,
            selected_model_id=_safe_text(record.get("selected_model_id")) or None,
            pending_model_source=self.normalize_model_source(record.get("pending_model_source")),
            pending_provider_id=_safe_text(record.get("pending_provider_id")) or None,
            pending_model_id=_safe_text(record.get("pending_model_id")) or None,
            lineage_parent_session_id=_safe_text(record.get("lineage_parent_session_id")) or None,
            lineage_root_session_id=_safe_text(record.get("lineage_root_session_id")) or session_id,
            lineage_reason=_safe_text(record.get("lineage_reason")) or "root",
            lineage_created_at=_safe_text(record.get("lineage_created_at")) or None,
            lineage_metadata=(
                dict(record.get("lineage_metadata"))
                if isinstance(record.get("lineage_metadata"), dict)
                else {}
            ),
            pending_skill_reload=bool(record.get("pending_skill_reload", False)),
            pending_skill_reload_reason=_safe_text(record.get("pending_skill_reload_reason")) or None,
            context_policy=self.normalize_context_policy_payload(record.get("context_policy")),
            last_prepared_context=self.normalize_prepared_context_payload(record.get("last_prepared_context")),
            prepared_context_diagnostics=self.normalize_prepared_context_diagnostics_payload(
                record.get("prepared_context_diagnostics")
            ),
            memory_diagnostics=self.build_memory_diagnostics_from_record(record),
            sandbox_diagnostics=self.build_sandbox_diagnostics_from_record(record),
            workspace_runtime_snapshot=(
                dict(self.build_workspace_runtime_snapshot_from_record(record) or {})
            ),
            runtime_task_memory_payload=(
                self.snapshot_runtime_task_memory_payload(
                    workspace_dir=workspace_dir,
                    session_id=session_id,
                )
                if session_id
                else {}
            ),
            workspace_shared_runtime_memory_payload=self.snapshot_workspace_shared_runtime_task_memory_payload(
                workspace_dir=workspace_dir,
            ),
            agent_messages=self.serialize_agent_messages(agent_messages),
            transcript=[self._build_import_message(entry) for entry in transcript],
        )

    @staticmethod
    def _build_import_message(entry: "MainAgentSessionTranscriptEntry") -> RuntimeSessionImportMessage:
        return RuntimeSessionImportMessage(
            role=entry.role,
            content=entry.content,
            surface=entry.surface,
            created_at=_to_utc_iso(entry.created_at),
            channel_type=entry.channel_type,
            conversation_id=entry.conversation_id,
            sender_id=entry.sender_id,
            metadata=dict(entry.metadata) if entry.metadata else None,
        )


__all__ = ["RuntimeSessionSnapshotBuilder"]
