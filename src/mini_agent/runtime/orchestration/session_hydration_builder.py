"""Runtime session hydration builders extracted from the runtime manager."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Sequence
from uuid import uuid4

try:
    from mini_agent.interaction import normalize_channel_type
except Exception:  # pragma: no cover - compatibility path for staged interaction extraction
    from mini_agent.runtime.support.interaction_surface import normalize_channel_type

if TYPE_CHECKING:
    from mini_agent.agent_core.engine import Agent
    from mini_agent.agent_core.session import SessionLifecycleState
    from mini_agent.interfaces import MainAgentSessionRecoverySnapshot
    from mini_agent.runtime.session_state import (
        MainAgentSessionState,
        MainAgentSessionTranscriptEntry,
    )


def _safe_text(value: object) -> str:
    return " ".join(str(value or "").split())


def _from_utc_iso(value: object, fallback: datetime) -> datetime:
    raw = str(value or "").strip()
    if not raw:
        return fallback
    try:
        parsed = datetime.fromisoformat(raw)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except Exception:
        return fallback


@dataclass(slots=True)
class RuntimeSessionHydrationPayload:
    session_id: str
    workspace_dir: Path
    created_at: datetime
    updated_at: datetime
    selected_identity: tuple[str, str, str] | None
    pending_identity: tuple[str, str, str] | None
    desired_approval_profile: str | None
    desired_access_level: str | None
    agent_messages: Sequence[Any] | None
    token_usage: Any
    token_limit: Any
    requested_knowledge_base_enabled: bool | None
    title: str
    origin_surface: str
    active_surface: str
    reply_enabled: bool
    is_default: bool
    channel_type: str | None
    conversation_id: str | None
    sender_id: str | None
    shared: bool
    lineage_parent_session_id: str | None
    lineage_root_session_id: str
    lineage_reason: str
    lineage_created_at: datetime
    lineage_metadata: dict[str, Any]
    pending_skill_reload: bool
    pending_skill_reload_reason: str
    context_policy: dict[str, Any]
    last_prepared_context: dict[str, Any]
    prepared_context_diagnostics: dict[str, Any]
    memory_diagnostics: dict[str, Any]
    sandbox_diagnostics: dict[str, Any]
    transcript: list["MainAgentSessionTranscriptEntry"]
    kernel_state_payload: dict[str, Any] | None = None
    workspace_runtime_snapshot: dict[str, Any] | None = None
    runtime_task_memory_payload: dict[str, Any] | None = None
    workspace_shared_runtime_memory_payload: dict[str, Any] | None = None
    stored_recovery: "MainAgentSessionRecoverySnapshot" | None = None


@dataclass(slots=True)
class RuntimeSessionHydrationBuilder:
    build_model_identity: Callable[[object, object, object], tuple[str, str, str] | None]
    runtime_policy_overrides_from_diagnostics: Callable[[Any], tuple[str | None, str | None]]
    normalize_surface: Callable[[object | None], str]
    normalize_context_policy_payload: Callable[[Any], dict[str, Any]]
    normalize_prepared_context_payload: Callable[[Any], dict[str, Any]]
    normalize_prepared_context_diagnostics_payload: Callable[[Any], dict[str, Any]]
    normalize_memory_diagnostics_payload: Callable[[Any], dict[str, Any]]
    normalize_sandbox_diagnostics_payload: Callable[[Any], dict[str, Any]]
    build_memory_diagnostics_from_record: Callable[[dict[str, Any]], dict[str, Any]]
    build_sandbox_diagnostics_from_record: Callable[[dict[str, Any]], dict[str, Any]]

    @staticmethod
    def _normalize_lineage_payload(
        *,
        session_id: str,
        created_at: datetime,
        lineage_parent_session_id: object = None,
        lineage_root_session_id: object = None,
        lineage_reason: object = None,
        lineage_created_at: object = None,
        lineage_metadata: Any = None,
    ) -> tuple[str | None, str, str, datetime, dict[str, Any]]:
        parent_session_id = _safe_text(lineage_parent_session_id) or None
        root_session_id = _safe_text(lineage_root_session_id)
        normalized_reason = _safe_text(lineage_reason) or ("child" if parent_session_id else "root")
        normalized_created_at = _from_utc_iso(lineage_created_at, created_at)
        metadata = dict(lineage_metadata) if isinstance(lineage_metadata, dict) else {}

        if parent_session_id is None:
            return None, root_session_id or session_id, normalized_reason or "root", normalized_created_at, metadata
        return (
            parent_session_id,
            root_session_id or parent_session_id,
            normalized_reason or "child",
            normalized_created_at,
            metadata,
        )

    def import_transcript_entries(
        self,
        items: Sequence[dict[str, Any]] | None,
        *,
        default_surface: str,
        now_utc: datetime,
    ) -> list["MainAgentSessionTranscriptEntry"]:
        from mini_agent.runtime.session_state import MainAgentSessionTranscriptEntry

        entries: list[MainAgentSessionTranscriptEntry] = []
        for fallback_index, item in enumerate(items or [], start=1):
            if not isinstance(item, dict):
                continue
            try:
                index = int(item.get("index", fallback_index) or fallback_index)
            except Exception:
                index = fallback_index
            entries.append(
                MainAgentSessionTranscriptEntry(
                    index=max(1, index),
                    role=_safe_text(item.get("role")).lower() or "assistant",
                    content=str(item.get("content", "")),
                    surface=self.normalize_surface(item.get("surface") or default_surface),
                    created_at=_from_utc_iso(item.get("created_at"), now_utc),
                    channel_type=_safe_text(item.get("channel_type")) or None,
                    conversation_id=_safe_text(item.get("conversation_id")) or None,
                    sender_id=_safe_text(item.get("sender_id")) or None,
                    metadata=dict(item.get("metadata")) if isinstance(item.get("metadata"), dict) else {},
                )
            )
        entries.sort(key=lambda item: (item.index, item.created_at))
        for normalized_index, entry in enumerate(entries, start=1):
            entry.index = normalized_index
        return entries

    def transcript_entries_from_record(
        self,
        record: dict[str, Any],
    ) -> list["MainAgentSessionTranscriptEntry"]:
        updated_at = _from_utc_iso(record.get("updated_at"), datetime.now(timezone.utc))
        default_surface = _safe_text(record.get("active_surface") or record.get("origin_surface")) or "api"
        raw_transcript = record.get("shared_transcript")
        items = raw_transcript if isinstance(raw_transcript, list) else []
        return self.import_transcript_entries(items, default_surface=default_surface, now_utc=updated_at)

    def build_record_hydration_payload(
        self,
        record: dict[str, Any],
        *,
        now_utc: datetime,
        transcript: list["MainAgentSessionTranscriptEntry"] | None = None,
        stored_recovery: "MainAgentSessionRecoverySnapshot" | None = None,
    ) -> RuntimeSessionHydrationPayload:
        selected_identity = self.build_model_identity(
            record.get("selected_model_source"),
            record.get("selected_provider_id"),
            record.get("selected_model_id"),
        )
        pending_identity = self.build_model_identity(
            record.get("pending_model_source"),
            record.get("pending_provider_id"),
            record.get("pending_model_id"),
        )
        desired_approval_profile, desired_access_level = self.runtime_policy_overrides_from_diagnostics(
            record.get("sandbox_diagnostics")
        )
        restored_knowledge_base_enabled = record.get("knowledge_base_enabled")
        normalized_transcript = transcript if transcript is not None else self.transcript_entries_from_record(record)
        session_id = _safe_text(record.get("session_id")) or uuid4().hex
        created_at = _from_utc_iso(record.get("created_at"), now_utc)
        (
            lineage_parent_session_id,
            lineage_root_session_id,
            lineage_reason,
            lineage_created_at,
            lineage_metadata,
        ) = self._normalize_lineage_payload(
            session_id=session_id,
            created_at=created_at,
            lineage_parent_session_id=record.get("lineage_parent_session_id"),
            lineage_root_session_id=record.get("lineage_root_session_id"),
            lineage_reason=record.get("lineage_reason"),
            lineage_created_at=record.get("lineage_created_at"),
            lineage_metadata=record.get("lineage_metadata"),
        )
        return RuntimeSessionHydrationPayload(
            session_id=session_id,
            workspace_dir=Path(str(record.get("workspace_dir", "."))).expanduser().resolve(),
            created_at=created_at,
            updated_at=_from_utc_iso(record.get("updated_at"), now_utc),
            selected_identity=selected_identity,
            pending_identity=pending_identity,
            desired_approval_profile=desired_approval_profile,
            desired_access_level=desired_access_level,
            agent_messages=record.get("messages") if isinstance(record.get("messages"), list) else None,
            token_usage=record.get("token_usage"),
            token_limit=record.get("token_limit"),
            requested_knowledge_base_enabled=(
                bool(restored_knowledge_base_enabled)
                if restored_knowledge_base_enabled is not None
                else None
            ),
            title=_safe_text(record.get("title")),
            origin_surface=self.normalize_surface(record.get("origin_surface")),
            active_surface=self.normalize_surface(record.get("active_surface") or record.get("origin_surface")),
            reply_enabled=bool(record.get("reply_enabled", False)),
            is_default=bool(record.get("is_default", False)),
            channel_type=normalize_channel_type(record.get("channel_type")),
            conversation_id=_safe_text(record.get("conversation_id")) or None,
            sender_id=_safe_text(record.get("sender_id")) or None,
            shared=bool(record.get("shared", False)),
            lineage_parent_session_id=lineage_parent_session_id,
            lineage_root_session_id=lineage_root_session_id,
            lineage_reason=lineage_reason,
            lineage_created_at=lineage_created_at,
            lineage_metadata=lineage_metadata,
            pending_skill_reload=bool(record.get("pending_skill_reload", False)),
            pending_skill_reload_reason=_safe_text(record.get("pending_skill_reload_reason")),
            context_policy=self.normalize_context_policy_payload(record.get("context_policy")),
            last_prepared_context=self.normalize_prepared_context_payload(record.get("last_prepared_context")),
            prepared_context_diagnostics=self.normalize_prepared_context_diagnostics_payload(
                record.get("prepared_context_diagnostics")
            ),
            memory_diagnostics=self.build_memory_diagnostics_from_record(record),
            sandbox_diagnostics=self.build_sandbox_diagnostics_from_record(record),
            kernel_state_payload=(
                dict(record.get("kernel_state")) if isinstance(record.get("kernel_state"), dict) else None
            ),
            workspace_runtime_snapshot=(
                dict(record.get("workspace_runtime_snapshot"))
                if isinstance(record.get("workspace_runtime_snapshot"), dict)
                else None
            ),
            transcript=normalized_transcript,
            stored_recovery=stored_recovery,
        )

    def build_snapshot_hydration_payload(
        self,
        *,
        session_id: str,
        workspace_dir: Path,
        created_at: datetime,
        updated_at: datetime,
        title: str | None = None,
        origin_surface: str | None = None,
        active_surface: str | None = None,
        reply_enabled: bool = False,
        is_default: bool = False,
        channel_type: str | None = None,
        conversation_id: str | None = None,
        sender_id: str | None = None,
        token_usage: int = 0,
        token_limit: int = 0,
        shared: bool = False,
        knowledge_base_enabled: bool | None = None,
        selected_model_source: str | None = None,
        selected_provider_id: str | None = None,
        selected_model_id: str | None = None,
        pending_model_source: str | None = None,
        pending_provider_id: str | None = None,
        pending_model_id: str | None = None,
        lineage_parent_session_id: str | None = None,
        lineage_root_session_id: str | None = None,
        lineage_reason: str | None = None,
        lineage_created_at: str | None = None,
        lineage_metadata: dict[str, Any] | None = None,
        pending_skill_reload: bool = False,
        pending_skill_reload_reason: str | None = None,
        context_policy: dict[str, Any] | None = None,
        last_prepared_context: dict[str, Any] | None = None,
        prepared_context_diagnostics: dict[str, Any] | None = None,
        memory_diagnostics: dict[str, Any] | None = None,
        sandbox_diagnostics: dict[str, Any] | None = None,
        workspace_runtime_snapshot: dict[str, Any] | None = None,
        runtime_task_memory_payload: dict[str, Any] | None = None,
        workspace_shared_runtime_memory_payload: dict[str, Any] | None = None,
        agent_messages: Sequence[dict[str, Any]] | None = None,
        transcript: Sequence[dict[str, Any]] | None = None,
    ) -> RuntimeSessionHydrationPayload:
        selected_identity = self.build_model_identity(
            selected_model_source,
            selected_provider_id,
            selected_model_id,
        )
        pending_identity = self.build_model_identity(
            pending_model_source,
            pending_provider_id,
            pending_model_id,
        )
        desired_approval_profile, desired_access_level = self.runtime_policy_overrides_from_diagnostics(
            sandbox_diagnostics
        )
        normalized_origin = self.normalize_surface(origin_surface or active_surface or "tui")
        normalized_active = self.normalize_surface(active_surface or origin_surface or normalized_origin)
        (
            normalized_lineage_parent_session_id,
            normalized_lineage_root_session_id,
            normalized_lineage_reason,
            normalized_lineage_created_at,
            normalized_lineage_metadata,
        ) = self._normalize_lineage_payload(
            session_id=session_id,
            created_at=created_at,
            lineage_parent_session_id=lineage_parent_session_id,
            lineage_root_session_id=lineage_root_session_id,
            lineage_reason=lineage_reason,
            lineage_created_at=lineage_created_at,
            lineage_metadata=lineage_metadata,
        )
        return RuntimeSessionHydrationPayload(
            session_id=session_id,
            workspace_dir=workspace_dir,
            created_at=created_at,
            updated_at=updated_at,
            selected_identity=selected_identity,
            pending_identity=pending_identity,
            desired_approval_profile=desired_approval_profile,
            desired_access_level=desired_access_level,
            agent_messages=agent_messages,
            token_usage=token_usage,
            token_limit=token_limit,
            requested_knowledge_base_enabled=knowledge_base_enabled,
            title=_safe_text(title),
            origin_surface=normalized_origin,
            active_surface=normalized_active,
            reply_enabled=bool(reply_enabled),
            is_default=bool(is_default),
            channel_type=normalize_channel_type(channel_type),
            conversation_id=_safe_text(conversation_id) or None,
            sender_id=_safe_text(sender_id) or None,
            shared=bool(shared),
            lineage_parent_session_id=normalized_lineage_parent_session_id,
            lineage_root_session_id=normalized_lineage_root_session_id,
            lineage_reason=normalized_lineage_reason,
            lineage_created_at=normalized_lineage_created_at,
            lineage_metadata=normalized_lineage_metadata,
            pending_skill_reload=bool(pending_skill_reload),
            pending_skill_reload_reason=_safe_text(pending_skill_reload_reason),
            context_policy=self.normalize_context_policy_payload(context_policy),
            last_prepared_context=self.normalize_prepared_context_payload(last_prepared_context),
            prepared_context_diagnostics=self.normalize_prepared_context_diagnostics_payload(
                prepared_context_diagnostics
            ),
            memory_diagnostics=self.normalize_memory_diagnostics_payload(memory_diagnostics),
            sandbox_diagnostics=self.normalize_sandbox_diagnostics_payload(sandbox_diagnostics),
            kernel_state_payload=None,
            workspace_runtime_snapshot=(
                dict(workspace_runtime_snapshot) if isinstance(workspace_runtime_snapshot, dict) else None
            ),
            transcript=self.import_transcript_entries(
                transcript,
                default_surface=normalized_active,
                now_utc=updated_at,
            ),
            runtime_task_memory_payload=(
                dict(runtime_task_memory_payload) if isinstance(runtime_task_memory_payload, dict) else None
            ),
            workspace_shared_runtime_memory_payload=(
                dict(workspace_shared_runtime_memory_payload)
                if isinstance(workspace_shared_runtime_memory_payload, dict)
                else None
            ),
        )

    def build_derived_hydration_payload(
        self,
        parent: "MainAgentSessionState",
        *,
        session_id: str,
        now_utc: datetime,
        title: str,
        surface: str | None = None,
        channel_type: str | None = None,
        conversation_id: str | None = None,
        sender_id: str | None = None,
        reason: str = "derived",
        metadata: dict[str, Any] | None = None,
    ) -> RuntimeSessionHydrationPayload:
        selected_identity = self.build_model_identity(
            parent.projection.selected_model_source,
            parent.projection.selected_provider_id,
            parent.projection.selected_model_id,
        )
        parent_root_session_id = _safe_text(parent.lineage_state.root_session_id) or parent.session_id
        inherited_surface = surface or parent.projection.active_surface or parent.projection.origin_surface
        return self.build_snapshot_hydration_payload(
            session_id=session_id,
            workspace_dir=parent.workspace_dir,
            created_at=now_utc,
            updated_at=now_utc,
            title=title,
            origin_surface=inherited_surface,
            active_surface=inherited_surface,
            reply_enabled=False,
            is_default=False,
            channel_type=channel_type,
            conversation_id=conversation_id,
            sender_id=sender_id,
            shared=False,
            knowledge_base_enabled=bool(parent.projection.knowledge_base_enabled),
            selected_model_source=selected_identity[0] if selected_identity is not None else None,
            selected_provider_id=selected_identity[1] if selected_identity is not None else None,
            selected_model_id=selected_identity[2] if selected_identity is not None else None,
            context_policy=dict(parent.projection.context_policy),
            sandbox_diagnostics=dict(parent.projection.sandbox_diagnostics),
            lineage_parent_session_id=parent.session_id,
            lineage_root_session_id=parent_root_session_id,
            lineage_reason=reason,
            lineage_metadata=dict(metadata or {}),
            transcript=[],
        )

    def build_session_state(
        self,
        payload: RuntimeSessionHydrationPayload,
        *,
        lifecycle_state: "SessionLifecycleState",
        agent: "Agent",
        effective_knowledge_base_enabled: bool,
    ) -> "MainAgentSessionState":
        from mini_agent.runtime.session_state import (
            MainAgentSessionLineageState,
            MainAgentSessionProjectionState,
            MainAgentSessionRuntimeHostState,
            MainAgentSessionState,
            MainAgentSessionTranscriptState,
        )

        session = MainAgentSessionState(
            session_id=payload.session_id,
            workspace_dir=payload.workspace_dir,
            lifecycle_state=lifecycle_state,
            runtime=MainAgentSessionRuntimeHostState(agent=agent),
            created_at=payload.created_at,
            updated_at=payload.updated_at,
            lineage_state=MainAgentSessionLineageState(
                parent_session_id=payload.lineage_parent_session_id,
                root_session_id=payload.lineage_root_session_id,
                reason=payload.lineage_reason,
                created_at=payload.lineage_created_at,
                metadata=dict(payload.lineage_metadata),
            ),
            projection=MainAgentSessionProjectionState(
                title=payload.title,
                origin_surface=payload.origin_surface,
                active_surface=payload.active_surface,
                reply_enabled=payload.reply_enabled,
                is_default=bool(payload.is_default),
                busy=False,
                running_state="",
                channel_type=payload.channel_type,
                conversation_id=payload.conversation_id,
                sender_id=payload.sender_id,
                shared=payload.shared,
                knowledge_base_enabled=effective_knowledge_base_enabled,
                selected_model_source=payload.selected_identity[0] if payload.selected_identity is not None else None,
                selected_provider_id=payload.selected_identity[1] if payload.selected_identity is not None else None,
                selected_model_id=payload.selected_identity[2] if payload.selected_identity is not None else None,
                pending_model_source=payload.pending_identity[0] if payload.pending_identity is not None else None,
                pending_provider_id=payload.pending_identity[1] if payload.pending_identity is not None else None,
                pending_model_id=payload.pending_identity[2] if payload.pending_identity is not None else None,
                pending_skill_reload=payload.pending_skill_reload,
                pending_skill_reload_reason=payload.pending_skill_reload_reason,
                context_policy=payload.context_policy,
                last_prepared_context=payload.last_prepared_context,
                prepared_context_diagnostics=payload.prepared_context_diagnostics,
                memory_diagnostics=payload.memory_diagnostics,
                sandbox_diagnostics=payload.sandbox_diagnostics,
            ),
            transcript_state=MainAgentSessionTranscriptState(
                transcript=payload.transcript,
                next_transcript_index=max([entry.index for entry in payload.transcript] or [0]) + 1,
            ),
        )
        session.runtime.kernel_state_payload = (
            dict(payload.kernel_state_payload)
            if isinstance(payload.kernel_state_payload, dict)
            else None
        )
        return session

    @staticmethod
    def apply_stored_recovery(
        session: "MainAgentSessionState",
        stored_recovery: "MainAgentSessionRecoverySnapshot" | None,
    ) -> None:
        if stored_recovery is None:
            return
        session.projection.recovery_context_pending = True
        session.projection.recovery_state = _safe_text(stored_recovery.state)
        session.projection.recovery_summary = _safe_text(stored_recovery.summary)
        session.projection.recovery_last_activity = _safe_text(stored_recovery.last_activity) or None
        session.projection.recovery_last_user_message = _safe_text(stored_recovery.last_user_message) or None
        session.projection.recovery_last_assistant_message = (
            _safe_text(stored_recovery.last_assistant_message) or None
        )
        session.projection.recovery_pending_approvals = [
            item.model_dump() for item in list(stored_recovery.pending_approvals or [])
        ]

__all__ = ["RuntimeSessionHydrationBuilder", "RuntimeSessionHydrationPayload"]
