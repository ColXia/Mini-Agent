"""Runtime snapshot import/export routing extracted from the runtime manager."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Sequence

from fastapi import HTTPException

from mini_agent.runtime.orchestration.session_hydration_builder import RuntimeSessionHydrationPayload
from mini_agent.runtime.support.session_snapshot import RuntimeSessionSnapshot

if TYPE_CHECKING:
    from mini_agent.runtime.session_state import MainAgentSessionState


def _safe_text(value: object) -> str:
    return " ".join(str(value or "").split())


@dataclass(frozen=True, slots=True)
class RuntimeSessionSnapshotImportCommand:
    session_id: str | None
    workspace_dir: Path
    title: str | None = None
    origin_surface: str | None = None
    active_surface: str | None = None
    reply_enabled: bool = False
    channel_type: str | None = None
    conversation_id: str | None = None
    sender_id: str | None = None
    token_usage: int = 0
    token_limit: int = 0
    shared: bool = False
    knowledge_base_enabled: bool | None = None
    selected_model_source: str | None = None
    selected_provider_id: str | None = None
    selected_model_id: str | None = None
    pending_model_source: str | None = None
    pending_provider_id: str | None = None
    pending_model_id: str | None = None
    lineage_parent_session_id: str | None = None
    lineage_root_session_id: str | None = None
    lineage_reason: str | None = None
    lineage_created_at: str | None = None
    lineage_metadata: dict[str, Any] | None = None
    pending_skill_reload: bool = False
    pending_skill_reload_reason: str | None = None
    context_policy: dict[str, Any] | None = None
    last_prepared_context: dict[str, Any] | None = None
    prepared_context_diagnostics: dict[str, Any] | None = None
    memory_diagnostics: dict[str, Any] | None = None
    sandbox_diagnostics: dict[str, Any] | None = None
    workspace_runtime_snapshot: dict[str, Any] | None = None
    runtime_task_memory_payload: dict[str, Any] | None = None
    workspace_shared_runtime_memory_payload: dict[str, Any] | None = None
    agent_messages: Sequence[dict[str, Any]] | None = None
    transcript: Sequence[dict[str, Any]] | None = None


@dataclass(frozen=True, slots=True)
class RuntimeSessionSnapshotImportPlan:
    session_id: str
    payload: RuntimeSessionHydrationPayload


@dataclass(slots=True)
class RuntimeSessionSnapshotHandler:
    build_snapshot_hydration_payload: Callable[..., RuntimeSessionHydrationPayload]
    build_session_snapshot: Callable[["MainAgentSessionState"], RuntimeSessionSnapshot]
    build_session_snapshot_from_record: Callable[[dict[str, Any]], RuntimeSessionSnapshot]

    def prepare_import(
        self,
        command: RuntimeSessionSnapshotImportCommand,
        *,
        now_utc: datetime,
        prepare_environment: Callable[[Path, datetime], None],
        session_exists: Callable[[str], bool],
        allocate_session_id: Callable[[], str],
    ) -> RuntimeSessionSnapshotImportPlan:
        prepare_environment(command.workspace_dir, now_utc)

        requested_session_id = _safe_text(command.session_id)
        if requested_session_id:
            if session_exists(requested_session_id):
                raise HTTPException(status_code=409, detail="Session already exists.")
            new_session_id = requested_session_id
        else:
            new_session_id = allocate_session_id()

        payload = self.build_snapshot_hydration_payload(
            session_id=new_session_id,
            workspace_dir=command.workspace_dir,
            created_at=now_utc,
            updated_at=now_utc,
            title=command.title,
            origin_surface=command.origin_surface,
            active_surface=command.active_surface,
            reply_enabled=command.reply_enabled,
            channel_type=command.channel_type,
            conversation_id=command.conversation_id,
            sender_id=command.sender_id,
            token_usage=command.token_usage,
            token_limit=command.token_limit,
            shared=command.shared,
            knowledge_base_enabled=command.knowledge_base_enabled,
            selected_model_source=command.selected_model_source,
            selected_provider_id=command.selected_provider_id,
            selected_model_id=command.selected_model_id,
            pending_model_source=command.pending_model_source,
            pending_provider_id=command.pending_provider_id,
            pending_model_id=command.pending_model_id,
            lineage_parent_session_id=command.lineage_parent_session_id,
            lineage_root_session_id=command.lineage_root_session_id,
            lineage_reason=command.lineage_reason,
            lineage_created_at=command.lineage_created_at,
            lineage_metadata=command.lineage_metadata,
            pending_skill_reload=command.pending_skill_reload,
            pending_skill_reload_reason=command.pending_skill_reload_reason,
            context_policy=command.context_policy,
            last_prepared_context=command.last_prepared_context,
            prepared_context_diagnostics=command.prepared_context_diagnostics,
            memory_diagnostics=command.memory_diagnostics,
            sandbox_diagnostics=command.sandbox_diagnostics,
            workspace_runtime_snapshot=command.workspace_runtime_snapshot,
            runtime_task_memory_payload=command.runtime_task_memory_payload,
            workspace_shared_runtime_memory_payload=command.workspace_shared_runtime_memory_payload,
            agent_messages=command.agent_messages,
            transcript=command.transcript,
        )
        return RuntimeSessionSnapshotImportPlan(
            session_id=new_session_id,
            payload=payload,
        )

    def export_snapshot(
        self,
        session_id: str,
        *,
        active_session: "MainAgentSessionState" | None,
        persisted_record: dict[str, Any] | None,
    ) -> RuntimeSessionSnapshot:
        if active_session is not None:
            return self.build_session_snapshot(active_session)
        if persisted_record is not None:
            return self.build_session_snapshot_from_record(persisted_record)
        raise HTTPException(status_code=404, detail="Session not found.")


__all__ = [
    "RuntimeSessionSnapshotHandler",
    "RuntimeSessionSnapshotImportCommand",
    "RuntimeSessionSnapshotImportPlan",
]
