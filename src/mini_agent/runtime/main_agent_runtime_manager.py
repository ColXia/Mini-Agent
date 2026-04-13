"""Runtime manager for single-host main-agent session lifecycle."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
import os
from pathlib import Path
from typing import Any, Awaitable, Callable, Sequence
from uuid import uuid4

from fastapi import HTTPException

from mini_agent.agent import Agent
from mini_agent.agent_core.session import (
    AgentSessionKey,
    SessionLifecycleManager,
    SessionLifecyclePolicy,
    SessionLineageStore,
)
from mini_agent.code_agent.context_compression import estimate_tokens
from mini_agent.commands.mcp_support import (
    collect_mcp_operator_snapshot,
    format_mcp_server_list,
    format_mcp_status,
)
from mini_agent.config import Config
from mini_agent.interfaces import (
    MainAgentSessionApprovalResponse,
    MainAgentSessionContextResponse,
    MainAgentSessionControlResponse,
    MainAgentSessionDetail,
    MainAgentSessionMemoryResponse,
    MainAgentSessionMessage,
    MainAgentSessionModelSelectionResponse,
    MainAgentSessionMutationResponse,
    MainAgentSessionSkillResponse,
    MainAgentSessionSummary,
)
from mini_agent.model_manager.runtime import resolve_session_model_selection_identity
from mini_agent.runtime.session_snapshot import RuntimeSessionSnapshot
from mini_agent.runtime.interaction_surface import (
    normalize_channel_type,
    normalize_surface_label,
)
from mini_agent.runtime.session_diagnostics_service import RuntimeSessionDiagnosticsService
from mini_agent.runtime.session_context_policy_handler import RuntimeSessionContextPolicyHandler
from mini_agent.runtime.session_command_coordinator import (
    RuntimeSessionCommandCoordinator,
)
from mini_agent.runtime.session_catalog_handler import RuntimeSessionCatalogHandler
from mini_agent.runtime.session_access_handler import (
    RuntimeSessionAccessHandler,
)
from mini_agent.runtime.session_agent_runtime_handler import RuntimeSessionAgentRuntimeHandler
from mini_agent.runtime.session_creation_handler import (
    RuntimeSessionCreationHandler,
)
from mini_agent.runtime.session_hydration_builder import (
    RuntimeSessionHydrationBuilder,
    RuntimeSessionHydrationPayload,
)
from mini_agent.runtime.session_persistence_loader import RuntimeSessionPersistenceLoader
from mini_agent.runtime.session_persistence_record_builder import RuntimeSessionPersistenceRecordBuilder
from mini_agent.runtime.session_read_model_builder import RuntimeSessionReadModelBuilder
from mini_agent.runtime.session_registry_handler import RuntimeSessionRegistryHandler
from mini_agent.runtime.session_interrupt_handler import RuntimeSessionInterruptHandler
from mini_agent.runtime.session_lineage_registry import RuntimeSessionLineageRegistry
from mini_agent.runtime.session_live_state_handler import RuntimeSessionLiveStateHandler
from mini_agent.runtime.session_memory_command_handler import RuntimeSessionMemoryCommandHandler
from mini_agent.runtime.session_control_handler import RuntimeSessionControlHandler
from mini_agent.runtime.session_model_selection_handler import (
    RuntimeSessionModelSelectionHandler,
)
from mini_agent.runtime.session_operator_handler import RuntimeSessionOperatorHandler
from mini_agent.runtime.session_runtime_policy_handler import (
    RuntimeSessionRuntimePolicyHandler,
)
from mini_agent.runtime.session_skill_command_handler import RuntimeSessionSkillCommandHandler
from mini_agent.runtime.session_runtime_memory_backend_adapter import RuntimeTaskMemoryBackendAdapter
from mini_agent.runtime.session_runtime_policy_coordinator import RuntimeSessionPolicyCoordinator
from mini_agent.runtime.session_runtime_persistence import MainAgentRuntimePersistence
from mini_agent.runtime.session_state import MainAgentSessionState
from mini_agent.runtime.session_runtime_state_hydrator import RuntimeSessionStateHydrator
from mini_agent.runtime.session_restore_handler import RuntimeSessionRestoreHandler
from mini_agent.runtime.session_turn_scope_handler import RuntimeSessionTurnScopeHandler
from mini_agent.runtime.session_snapshot_handler import (
    RuntimeSessionSnapshotHandler,
    RuntimeSessionSnapshotImportCommand,
)
from mini_agent.runtime.sandbox_state import collect_sandbox_diagnostics, normalize_sandbox_diagnostics
from mini_agent.runtime.tooling import reconfigure_agent_runtime_policy
from mini_agent.memory.operator_actions import (
    save_operator_profile_fact,
    save_operator_workspace_note,
)
from mini_agent.schema import Message
from mini_agent.tools.mcp_loader import cleanup_mcp_connections
from mini_agent.turn_context import (
    context_policy_summary_line,
    format_context_policy_details,
    resolve_turn_context_policy,
)


BuildAgentFn = Callable[[Path], Awaitable[Agent]]
BuildSelectedAgentFn = Callable[[Path, str | None, str | None, str | None], Awaitable[Agent]]
_RUNTIME_SESSION_KIND = "main-agent-runtime"


def _safe_text(value: object) -> str:
    return " ".join(str(value or "").split())

class MainAgentRuntimeMode(str, Enum):
    """Runtime policy modes for main-agent orchestration."""

    SINGLE_MAIN = "single_main"
    TEAM = "team"


@dataclass(frozen=True)
class MainAgentRuntimePolicy:
    """Policy for current single-main mode and future team expansion."""

    mode: MainAgentRuntimeMode = MainAgentRuntimeMode.SINGLE_MAIN
    main_workspace_dir: Path | None = None
    max_active_sessions: int = 1
    reserved_team_slots: int = 4
    workspace_application_required: bool = True
    session_lifecycle: SessionLifecyclePolicy = field(default_factory=SessionLifecyclePolicy)


@dataclass(frozen=True)
class MainAgentRuntimeDiagnostics:
    """Runtime diagnostics snapshot for system health and ops inspection."""

    mode: str
    active_sessions: int
    max_active_sessions: int
    available_session_slots: int
    reserved_team_slots: int
    workspace_application_required: bool
    team_saturation_rejections: int
    team_workspace_conflict_rejections: int
    lifecycle_auto_resets: int
    session_reset_mode: str
    session_idle_seconds: int
    main_workspace_dir: str | None = None


class MainAgentRuntimeManager:
    """In-process manager enforcing main-agent runtime/session policies."""

    def __init__(
        self,
        *,
        ttl_seconds: int,
        build_agent: BuildAgentFn,
        build_agent_with_selection: BuildSelectedAgentFn | None = None,
        policy: MainAgentRuntimePolicy | None = None,
        storage_dir: Path | None = None,
    ):
        self._ttl_seconds = int(ttl_seconds)
        self._build_agent = build_agent
        self._build_agent_with_selection = build_agent_with_selection
        self._policy = policy or MainAgentRuntimePolicy()
        self._sessions: dict[str, MainAgentSessionState] = {}
        self._store_lock = asyncio.Lock()
        self._initialize_runtime_core(storage_dir)
        self._initialize_runtime_support_services()
        self._initialize_session_model_services()
        self._initialize_session_runtime_services()
        self._initialize_session_boundary_services()

    def _initialize_runtime_core(self, storage_dir: Path | None) -> None:
        self._lifecycle_manager = SessionLifecycleManager(self._policy.session_lifecycle)
        self._session_lineage = SessionLineageStore()
        self._session_lineage_registry = RuntimeSessionLineageRegistry(self._session_lineage)
        self._runtime_policy_coordinator = RuntimeSessionPolicyCoordinator(
            policy=self._policy,
            ttl_seconds=self._ttl_seconds,
            lifecycle_manager=self._lifecycle_manager,
        )
        self._session_persistence_records = RuntimeSessionPersistenceRecordBuilder(
            session_kind=_RUNTIME_SESSION_KIND,
            session_token_usage=self._session_token_usage,
            session_token_limit=self._session_token_limit,
        )
        self._session_persistence_loader = RuntimeSessionPersistenceLoader(
            session_kind=_RUNTIME_SESSION_KIND,
            read_shared_transcript=lambda session_id, record: self._persistence.read_shared_transcript(
                session_id,
                record,
            ),
        )
        self._persistence = MainAgentRuntimePersistence(
            storage_dir,
            record_loader=self._session_persistence_loader,
            record_builder=self._session_persistence_records,
        )

    def _initialize_runtime_support_services(self) -> None:
        self._session_diagnostics = RuntimeSessionDiagnosticsService(
            normalize_prepared_context_payload=self._normalize_prepared_context_payload,
            normalize_memory_diagnostics_payload=self._normalize_memory_diagnostics_payload,
            normalize_sandbox_diagnostics_payload=self._normalize_sandbox_diagnostics_payload,
            collect_sandbox_diagnostics=lambda agent: collect_sandbox_diagnostics(agent=agent),
        )
        self._runtime_task_memory_backend = RuntimeTaskMemoryBackendAdapter()
        self._session_runtime_state_hydrator = RuntimeSessionStateHydrator(
            agent_knowledge_base_enabled=self._agent_knowledge_base_enabled,
            normalize_prepared_context_payload=self._normalize_prepared_context_payload,
            normalize_prepared_context_diagnostics_payload=self._normalize_prepared_context_diagnostics_payload,
            restore_session_runtime_task_memory=self._runtime_task_memory_backend.restore_session_payload,
            restore_workspace_shared_runtime_task_memory=self._runtime_task_memory_backend.restore_workspace_shared_payload,
            build_memory_diagnostics_for_session=self._session_diagnostics.build_memory_diagnostics_for_session,
            build_sandbox_diagnostics_for_session=self._session_diagnostics.build_sandbox_diagnostics_for_session,
        )
        self._session_live_state = RuntimeSessionLiveStateHandler(
            build_memory_diagnostics_for_session=self._session_diagnostics.build_memory_diagnostics_for_session,
            agent_knowledge_base_enabled=self._agent_knowledge_base_enabled,
            clear_runtime_task_memory_namespace=lambda workspace_dir, session_id: (
                self._runtime_task_memory_backend.clear_session_namespace(
                    workspace_dir=workspace_dir,
                    session_id=session_id,
                )
            ),
            stored_recovery_snapshot_from_session=lambda session: self._session_read_models.stored_recovery_snapshot_from_session(
                session
            ),
        )
        self._session_memory_commands = RuntimeSessionMemoryCommandHandler(
            build_memory_diagnostics_for_session=self._session_diagnostics.build_memory_diagnostics_for_session,
            runtime_task_memory_backend=self._runtime_task_memory_backend,
            save_operator_workspace_note=save_operator_workspace_note,
            save_operator_profile_fact=save_operator_profile_fact,
        )
        self._session_access = RuntimeSessionAccessHandler(
            normalize_surface=self._normalize_surface,
            normalize_channel_type=normalize_channel_type,
            same_workspace=self._same_workspace,
        )

    def _initialize_session_model_services(self) -> None:
        self._session_hydration_builder = RuntimeSessionHydrationBuilder(
            build_model_identity=lambda source, provider_id, model_id: self._normalize_model_identity(
                source=source,
                provider_id=provider_id,
                model_id=model_id,
            ),
            runtime_policy_overrides_from_diagnostics=self._runtime_policy_overrides_from_diagnostics,
            normalize_surface=self._normalize_surface,
            normalize_context_policy_payload=self._normalize_context_policy_payload,
            normalize_prepared_context_payload=self._normalize_prepared_context_payload,
            normalize_prepared_context_diagnostics_payload=self._normalize_prepared_context_diagnostics_payload,
            normalize_memory_diagnostics_payload=self._normalize_memory_diagnostics_payload,
            normalize_sandbox_diagnostics_payload=self._normalize_sandbox_diagnostics_payload,
            build_memory_diagnostics_from_record=self._session_diagnostics.build_memory_diagnostics_from_record,
            build_sandbox_diagnostics_from_record=self._session_diagnostics.build_sandbox_diagnostics_from_record,
        )
        self._session_read_models = RuntimeSessionReadModelBuilder(
            normalize_surface=self._normalize_surface,
            normalize_model_source=self._normalize_model_source,
            normalize_context_policy_payload=self._normalize_context_policy_payload,
            normalize_prepared_context_payload=self._normalize_prepared_context_payload,
            normalize_prepared_context_diagnostics_payload=self._normalize_prepared_context_diagnostics_payload,
            build_memory_diagnostics_for_session=self._session_diagnostics.build_memory_diagnostics_for_session,
            build_memory_diagnostics_from_record=self._session_diagnostics.build_memory_diagnostics_from_record,
            build_sandbox_diagnostics_for_session=self._session_diagnostics.build_sandbox_diagnostics_for_session,
            build_sandbox_diagnostics_from_record=self._session_diagnostics.build_sandbox_diagnostics_from_record,
            snapshot_runtime_task_memory_payload=self._runtime_task_memory_backend.snapshot_session_payload,
            snapshot_workspace_shared_runtime_task_memory_payload=self._runtime_task_memory_backend.snapshot_workspace_shared_payload,
            session_token_usage=self._session_token_usage,
            session_token_limit=self._session_token_limit,
            record_token_usage=self._record_token_usage,
            record_token_limit=self._record_token_limit,
            transcript_entries_from_record=self._session_hydration_builder.transcript_entries_from_record,
            pending_approvals_from_raw=RuntimeSessionLiveStateHandler.pending_approvals_from_raw,
            serialize_agent_messages=self._serialize_agent_messages,
        )
        self._session_catalog = RuntimeSessionCatalogHandler(
            same_workspace=self._same_workspace,
            build_session_summary=self._session_read_models.build_session_summary,
            build_session_summary_from_record=self._session_read_models.build_session_summary_from_record,
            build_session_detail=lambda session, recent_limit: self._session_read_models.build_session_detail(
                session,
                recent_limit=recent_limit,
            ),
            build_session_detail_from_record=lambda record, recent_limit: self._session_read_models.build_session_detail_from_record(
                record,
                recent_limit=recent_limit,
            ),
            build_session_message=self._session_read_models.build_session_message,
            transcript_entries_from_record=self._session_hydration_builder.transcript_entries_from_record,
        )
        self._session_creation = RuntimeSessionCreationHandler(
            allocate_session_title=lambda base_title, workspace_dir: self._session_catalog.allocate_session_title(
                base_title,
                workspace_dir=workspace_dir,
                active_sessions=self._sessions.values(),
                persisted_records=self._persistence.list_session_records(),
            ),
            normalize_surface=self._normalize_surface,
            normalize_channel_type=normalize_channel_type,
            build_agent_for_identity=self._build_agent_for_identity,
            build_session_key=lambda session_id, workspace_dir: self._build_session_key(
                session_id=session_id,
                workspace_dir=workspace_dir,
            ),
            lifecycle_bootstrap=lambda session_key, now_utc: self._lifecycle_manager.bootstrap(
                session_key,
                now_utc=now_utc,
            ),
            agent_knowledge_base_enabled=self._agent_knowledge_base_enabled,
            collect_sandbox_diagnostics=lambda agent: collect_sandbox_diagnostics(agent=agent),
            route_model_identity=self._route_model_identity,
        )
        self._session_model_selection = RuntimeSessionModelSelectionHandler(
            normalize_model_identity=self._normalize_model_identity,
            resolve_selection_identity=lambda provider_source, provider_id, model_id: resolve_session_model_selection_identity(
                self._load_runtime_config(),
                provider_source=provider_source,
                provider_id=provider_id,
                model_id=model_id,
            ),
            selected_model_identity=self._selected_model_identity,
            pending_model_identity=self._pending_model_identity,
        )

    def _initialize_session_runtime_services(self) -> None:
        self._session_turn_scope = RuntimeSessionTurnScopeHandler(
            bind_surface_mutation=self._session_live_state.bind_surface,
            mark_turn_started_mutation=self._session_live_state.mark_turn_started,
            mark_turn_finished_mutation=self._session_live_state.mark_turn_finished,
            record_message_mutation=self._session_live_state.record_message,
            record_activity_mutation=self._session_live_state.record_activity,
            record_pending_approval_mutation=self._session_live_state.record_pending_approval,
            clear_pending_approval_mutation=self._session_live_state.clear_pending_approval,
            build_recovery_turn_context_fn=self._session_live_state.build_recovery_turn_context,
            clear_recovery_context_mutation=self._session_live_state.clear_recovery_context,
            capture_prepared_context_state_mutation=self._session_runtime_state_hydrator.capture_agent_prepared_context_state,
            restore_prepared_context_state_mutation=self._session_runtime_state_hydrator.restore_agent_prepared_context_state,
            apply_pending_session_model_selection=self.apply_pending_session_model_selection,
            apply_pending_session_skill_reload=self.apply_pending_session_skill_reload,
            persist_session=self._persist_session_unlocked,
        )
        self._session_agent_runtime = RuntimeSessionAgentRuntimeHandler(
            runtime_policy_overrides_from_diagnostics=self._runtime_policy_overrides_from_diagnostics,
            build_agent_for_identity=self._build_agent_for_identity,
            load_runtime_config=self._load_runtime_config,
            reconfigure_agent_runtime_policy=reconfigure_agent_runtime_policy,
            capture_agent_prepared_context_state=self._session_turn_scope.capture_prepared_context_state,
            restore_agent_prepared_context_state=self._session_turn_scope.restore_prepared_context_state,
            serialize_agent_messages=self._serialize_agent_messages,
            restore_agent_messages_payload=self._restore_agent_messages_payload,
            apply_agent_knowledge_base_enabled=self._apply_agent_knowledge_base_enabled,
            route_model_identity=self._route_model_identity,
            set_selected_model_identity=self._set_selected_model_identity,
            set_pending_model_identity=self._set_pending_model_identity,
            build_sandbox_diagnostics_for_session=self._session_diagnostics.build_sandbox_diagnostics_for_session,
            same_workspace=self._same_workspace,
            selected_model_identity=self._selected_model_identity,
            pending_model_identity=self._pending_model_identity,
        )
        self._session_runtime_policy = RuntimeSessionRuntimePolicyHandler(
            desired_runtime_policy_for_session=self._session_agent_runtime.desired_runtime_policy_for_session,
            effective_runtime_policy_for_agent=self._session_agent_runtime.effective_runtime_policy_for_agent,
        )
        self._session_control = RuntimeSessionControlHandler(
            normalize_surface=self._normalize_surface,
            apply_agent_knowledge_base_enabled=self._apply_agent_knowledge_base_enabled,
            load_runtime_config=self._load_runtime_config,
            collect_mcp_operator_snapshot=lambda config: collect_mcp_operator_snapshot(config),
            format_mcp_status=lambda snapshot: format_mcp_status(snapshot),
            format_mcp_server_list=lambda snapshot: format_mcp_server_list(snapshot),
        )
        self._session_commands = RuntimeSessionCommandCoordinator(
            append_transcript=self._session_live_state.append_transcript,
            persist_session=self._persist_session_unlocked,
        )
        self._session_interrupt = RuntimeSessionInterruptHandler(
            normalize_surface=self._normalize_surface,
            pending_approvals_from_raw=RuntimeSessionLiveStateHandler.pending_approvals_from_raw,
        )
        self._session_context_policy = RuntimeSessionContextPolicyHandler(
            normalize_context_policy_payload=self._normalize_context_policy_payload,
            format_context_policy_details=lambda value, include_header=True: format_context_policy_details(
                value,
                include_header=include_header,
            ),
            context_policy_summary_line=lambda value, include_default=True: context_policy_summary_line(
                value,
                include_default=include_default,
            ),
            normalize_surface=self._normalize_surface,
        )
        self._session_skill_commands = RuntimeSessionSkillCommandHandler()
        self._session_restore = RuntimeSessionRestoreHandler(
            transcript_entries_from_record=self._session_hydration_builder.transcript_entries_from_record,
            stored_recovery_snapshot_from_record=lambda record, transcript: self._session_read_models.stored_recovery_snapshot_from_record(
                record,
                transcript=transcript,
            ),
            build_record_hydration_payload=self._session_hydration_builder.build_record_hydration_payload,
            build_agent_for_identity=self._build_agent_for_identity,
            load_runtime_config=self._load_runtime_config,
            reconfigure_agent_runtime_policy=reconfigure_agent_runtime_policy,
            restore_agent_messages_payload=self._restore_agent_messages_payload,
            restore_agent_token_state=self._restore_agent_token_state,
            agent_knowledge_base_enabled=self._agent_knowledge_base_enabled,
            apply_agent_knowledge_base_enabled=self._apply_agent_knowledge_base_enabled,
            build_session_key=lambda session_id, workspace_dir: self._build_session_key(
                session_id=session_id,
                workspace_dir=workspace_dir,
            ),
            lifecycle_bootstrap=lambda session_key, now_utc: self._lifecycle_manager.bootstrap(
                session_key,
                now_utc=now_utc,
            ),
            build_session_state=self._session_hydration_builder.build_session_state,
            apply_stored_recovery=self._session_hydration_builder.apply_stored_recovery,
            set_selected_model_identity=self._set_selected_model_identity,
            route_model_identity=self._route_model_identity,
            hydrate_runtime_state=lambda session, payload: self._session_runtime_state_hydrator.hydrate_runtime_state(
                session,
                payload=payload,
            ),
        )
        self._session_snapshots = RuntimeSessionSnapshotHandler(
            build_snapshot_hydration_payload=self._session_hydration_builder.build_snapshot_hydration_payload,
            build_session_snapshot=self._session_read_models.build_session_snapshot,
            build_session_snapshot_from_record=self._session_read_models.build_session_snapshot_from_record,
        )

    def _initialize_session_boundary_services(self) -> None:
        self._session_registry = RuntimeSessionRegistryHandler(
            session_access=self._session_access,
            session_creation=self._session_creation,
            session_snapshots=self._session_snapshots,
            session_catalog=self._session_catalog,
            drop_expired_sessions=self._drop_expired_sessions_unlocked,
            enforce_workspace_entry=lambda active_sessions, workspace_dir: self._runtime_policy_coordinator.enforce_workspace_entry(
                active_sessions,
                workspace_dir,
                same_workspace=self._same_workspace,
            ),
            enforce_capacity=self._runtime_policy_coordinator.enforce_capacity,
            raise_workspace_mismatch=self._runtime_policy_coordinator.raise_workspace_mismatch,
            allocate_session_id=self._allocate_new_session_id_unlocked,
            load_persisted_record=self._persistence.load_session_record,
            list_persisted_records=self._persistence.list_session_records,
            restore_persisted_session=lambda record, now_utc: self._restore_persisted_session_unlocked(
                record,
                now_utc=now_utc,
            ),
            hydrate_session=lambda payload, now_utc, persist_after: self._hydrate_session_unlocked(
                payload,
                now_utc=now_utc,
                persist_after=persist_after,
            ),
            build_derived_hydration_payload=self._session_hydration_builder.build_derived_hydration_payload,
            refresh_session_lifecycle=lambda session, now_utc: self._refresh_session_lifecycle_unlocked(
                session,
                now_utc=now_utc,
            ),
            register_session=self._session_lineage_registry.register_session,
            persist_session=self._persist_session_unlocked,
        )
        self._session_operator = RuntimeSessionOperatorHandler(
            normalize_surface=self._normalize_surface,
            session_commands=self._session_commands,
            session_control=self._session_control,
            session_context_policy=self._session_context_policy,
            session_memory_commands=self._session_memory_commands,
            session_skill_commands=self._session_skill_commands,
            session_model_selection=self._session_model_selection,
            session_runtime_policy=self._session_runtime_policy,
            session_interrupt=self._session_interrupt,
            session_agent_runtime=self._session_agent_runtime,
            session_live_state=self._session_live_state,
            selected_model_identity=self._selected_model_identity,
            pending_model_identity=self._pending_model_identity,
            set_pending_model_identity=self._set_pending_model_identity,
            persist_session=self._persist_session_unlocked,
            queue_workspace_skill_reload=self.queue_workspace_skill_reload,
            cleanup_mcp_connections=lambda: cleanup_mcp_connections(),
        )

    async def clear(self) -> None:
        async with self._store_lock:
            self._sessions.clear()
            self._session_lineage = SessionLineageStore()
            self._session_lineage_registry.replace_store(self._session_lineage)
            self._runtime_policy_coordinator.clear_counters()

    async def build_ephemeral_agent(self, workspace_dir: Path) -> Agent:
        """Build an isolated agent instance without attaching a managed session."""
        self._enforce_main_workspace_policy(workspace_dir)
        return await self._build_agent(workspace_dir)

    @property
    def turn_scope_handler(self) -> RuntimeSessionTurnScopeHandler:
        return self._session_turn_scope

    def validate_workspace(self, workspace_dir: Path) -> None:
        self._enforce_main_workspace_policy(workspace_dir)

    @staticmethod
    def _normalize_model_source(value: object) -> str | None:
        normalized = _safe_text(value).lower()
        return normalized or None

    @classmethod
    def _normalize_model_identity(
        cls,
        *,
        source: object,
        provider_id: object,
        model_id: object,
    ) -> tuple[str, str, str] | None:
        normalized_source = cls._normalize_model_source(source)
        normalized_provider_id = _safe_text(provider_id)
        normalized_model_id = _safe_text(model_id)
        if normalized_source and normalized_provider_id and normalized_model_id:
            return normalized_source, normalized_provider_id, normalized_model_id
        return None

    @classmethod
    def _route_model_identity(cls, agent: Agent | None) -> tuple[str, str, str] | None:
        route = getattr(agent, "runtime_route", None)
        if route is None:
            return None
        model_id = _safe_text(getattr(route, "model", ""))
        provider_id = _safe_text(getattr(route, "provider_id", ""))
        if not model_id:
            return None
        if provider_id.startswith("preset-"):
            return ("preset", provider_id.removeprefix("preset-"), model_id)
        if provider_id:
            return ("custom", provider_id, model_id)
        return ("config", "config", model_id)

    @classmethod
    def _selected_model_identity(cls, session: "MainAgentSessionState") -> tuple[str, str, str] | None:
        explicit = cls._normalize_model_identity(
            source=session.projection.selected_model_source,
            provider_id=session.projection.selected_provider_id,
            model_id=session.projection.selected_model_id,
        )
        if explicit is not None:
            return explicit
        return cls._route_model_identity(session.runtime.agent)

    @classmethod
    def _pending_model_identity(cls, session: "MainAgentSessionState") -> tuple[str, str, str] | None:
        return cls._normalize_model_identity(
            source=session.projection.pending_model_source,
            provider_id=session.projection.pending_provider_id,
            model_id=session.projection.pending_model_id,
        )

    @staticmethod
    def _set_selected_model_identity(
        session: "MainAgentSessionState",
        identity: tuple[str, str, str] | None,
    ) -> None:
        if identity is None:
            session.projection.selected_model_source = None
            session.projection.selected_provider_id = None
            session.projection.selected_model_id = None
            return
        session.projection.selected_model_source, session.projection.selected_provider_id, session.projection.selected_model_id = identity

    @staticmethod
    def _set_pending_model_identity(
        session: "MainAgentSessionState",
        identity: tuple[str, str, str] | None,
    ) -> None:
        if identity is None:
            session.projection.pending_model_source = None
            session.projection.pending_provider_id = None
            session.projection.pending_model_id = None
            return
        session.projection.pending_model_source, session.projection.pending_provider_id, session.projection.pending_model_id = identity

    @staticmethod
    def _agent_knowledge_base_enabled(agent: Any) -> bool:
        checker = getattr(agent, "knowledge_base_enabled", None)
        if callable(checker):
            try:
                return bool(checker())
            except Exception:
                pass
        tools = getattr(agent, "tools", None)
        if isinstance(tools, dict):
            return "knowledge_base_query" in tools
        return True

    @classmethod
    def _apply_agent_knowledge_base_enabled(cls, agent: Any, enabled: bool) -> bool:
        setter = getattr(agent, "set_knowledge_base_enabled", None)
        if callable(setter):
            try:
                return bool(setter(enabled))
            except Exception:
                return cls._agent_knowledge_base_enabled(agent)
        return cls._agent_knowledge_base_enabled(agent)

    async def _build_agent_for_identity(
        self,
        workspace_dir: Path,
        identity: tuple[str, str, str] | None,
    ) -> Agent:
        if identity is None or self._build_agent_with_selection is None:
            return await self._build_agent(workspace_dir)
        source, provider_id, model_id = identity
        return await self._build_agent_with_selection(workspace_dir, source, provider_id, model_id)

    @staticmethod
    def _runtime_policy_overrides_from_diagnostics(
        value: Any,
    ) -> tuple[str | None, str | None]:
        diagnostics = normalize_sandbox_diagnostics(value)
        approval_profile = _safe_text(diagnostics.get("approval_profile")).lower() or None
        access_level = _safe_text(diagnostics.get("access_level")).lower() or None
        return approval_profile, access_level

    @staticmethod
    def _load_runtime_config() -> Config:
        return Config.load(allow_interactive_setup=False)

    async def get_or_create_session(
        self,
        session_id: str | None,
        workspace_dir: Path,
        *,
        surface: str | None = None,
        channel_type: str | None = None,
        conversation_id: str | None = None,
        sender_id: str | None = None,
        session_title_hint: str | None = None,
    ) -> MainAgentSessionState:
        async with self._store_lock:
            return await self._session_registry.get_or_create_session(
                self._sessions,
                now_utc=datetime.now(timezone.utc),
                team_mode=self._policy.mode == MainAgentRuntimeMode.TEAM,
                session_id=session_id,
                workspace_dir=workspace_dir,
                surface=surface,
                channel_type=channel_type,
                conversation_id=conversation_id,
                sender_id=sender_id,
                session_title_hint=session_title_hint,
            )

    async def create_session(
        self,
        *,
        workspace_dir: Path,
        title: str | None = None,
        surface: str | None = None,
        shared: bool = False,
    ) -> MainAgentSessionState:
        async with self._store_lock:
            return await self._session_registry.create_session(
                self._sessions,
                now_utc=datetime.now(timezone.utc),
                workspace_dir=workspace_dir,
                title=title,
                surface=surface,
                shared=shared,
            )

    async def create_derived_session(
        self,
        *,
        parent_session_id: str,
        title: str | None = None,
        surface: str | None = None,
        channel_type: str | None = None,
        conversation_id: str | None = None,
        sender_id: str | None = None,
        reason: str = "derived",
        metadata: dict[str, Any] | None = None,
    ) -> MainAgentSessionState:
        async with self._store_lock:
            parent = await self._require_managed_session_unlocked(parent_session_id)
            return await self._session_registry.create_derived_session(
                self._sessions,
                now_utc=datetime.now(timezone.utc),
                parent=parent,
                title=title,
                surface=surface,
                channel_type=channel_type,
                conversation_id=conversation_id,
                sender_id=sender_id,
                reason=reason,
                metadata=metadata,
            )

    async def import_session_snapshot(
        self,
        command: RuntimeSessionSnapshotImportCommand,
    ) -> MainAgentSessionState:
        async with self._store_lock:
            return await self._session_registry.import_session_snapshot(
                self._sessions,
                now_utc=datetime.now(timezone.utc),
                command=command,
            )

    async def export_session_snapshot(self, session_id: str) -> RuntimeSessionSnapshot:
        async with self._store_lock:
            return self._session_registry.export_session_snapshot(
                self._sessions,
                session_id=session_id,
            )

    async def get_runtime_diagnostics(self) -> MainAgentRuntimeDiagnostics:
        """Return a lock-consistent runtime diagnostics snapshot."""
        async with self._store_lock:
            active_sessions = len(self._sessions)
            payload = self._runtime_policy_coordinator.diagnostics_payload(active_sessions=active_sessions)
            return MainAgentRuntimeDiagnostics(
                **payload,
            )

    async def list_sessions(
        self,
        *,
        workspace_dir: Path | None = None,
        shared_only: bool = False,
    ) -> list[MainAgentSessionSummary]:
        async with self._store_lock:
            return self._session_registry.list_sessions(
                self._sessions,
                workspace_dir=workspace_dir,
                shared_only=shared_only,
            )

    async def rename_session(self, session_id: str, *, title: str) -> MainAgentSessionSummary:
        async with self._store_lock:
            session = await self._require_managed_session_unlocked(session_id)
        async with session.runtime.lock:
            self._session_catalog.rename_session(session, title=title)
            session.touch()
            self._persist_session_unlocked(session)
            return self._session_catalog.build_session_summary(session)

    async def set_session_shared(self, session_id: str, *, shared: bool) -> MainAgentSessionSummary:
        async with self._store_lock:
            session = await self._require_managed_session_unlocked(session_id)
        async with session.runtime.lock:
            self._session_catalog.set_session_shared(session, shared=shared)
            session.touch()
            self._persist_session_unlocked(session)
            return self._session_catalog.build_session_summary(session)

    async def get_session_detail(
        self,
        session_id: str,
        *,
        recent_limit: int = 50,
    ) -> MainAgentSessionDetail:
        async with self._store_lock:
            return self._session_registry.get_session_detail(
                self._sessions,
                session_id=session_id,
                recent_limit=recent_limit,
            )

    async def get_recent_messages(
        self,
        session_id: str,
        *,
        limit: int = 10,
    ) -> list[MainAgentSessionMessage]:
        async with self._store_lock:
            return self._session_registry.get_recent_messages(
                self._sessions,
                session_id=session_id,
                limit=limit,
            )

    async def delete_session(self, session_id: str) -> None:
        async with self._store_lock:
            found = False
            workspace_dir: Path | None = None
            if session_id in self._sessions:
                existing = self._sessions.pop(session_id, None)
                if existing is not None:
                    workspace_dir = existing.workspace_dir
                found = True
            if workspace_dir is None:
                record = self._persistence.load_session_record(session_id)
                if isinstance(record, dict):
                    workspace_dir = self._session_catalog.record_workspace_dir(record)
            if workspace_dir is not None:
                self._runtime_task_memory_backend.clear_session_namespace(
                    workspace_dir=workspace_dir,
                    session_id=session_id,
                )
            if self._persistence.delete_session(session_id):
                found = True
            self._session_lineage_registry.remove_session(session_id)
            if not found:
                raise HTTPException(status_code=404, detail="Session not found.")

    async def reset_session(self, session_id: str) -> None:
        async with self._store_lock:
            session = await self._require_managed_session_unlocked(session_id)
        async with session.runtime.lock:
            self._session_live_state.reset_runtime_state(
                session,
                clear_runtime_task_memory=True,
            )
            session.transcript_state.transcript.clear()
            session.transcript_state.next_transcript_index = 1
            session.lifecycle_state = self._lifecycle_manager.reset(session.lifecycle_state)
            session.lifecycle_state = self._lifecycle_manager.touch(session.lifecycle_state)
            session.touch()
            self._persist_session_unlocked(session)

    async def cancel_session_turn(
        self,
        session_id: str,
        *,
        reason: str | None = None,
        surface: str | None = None,
        channel_type: str | None = None,
        conversation_id: str | None = None,
        sender_id: str | None = None,
    ) -> MainAgentSessionMutationResponse:
        async with self._store_lock:
            persisted_exists = self._persistence.load_session_record(session_id) is not None
            return self._session_operator.cancel_turn(
                session_id=session_id,
                active_session=self._sessions.get(session_id),
                persisted_exists=persisted_exists,
                reason=reason,
                surface=surface,
                channel_type=channel_type,
                conversation_id=conversation_id,
                sender_id=sender_id,
            )

    async def set_active_surface(self, session_id: str, *, surface: str) -> MainAgentSessionSummary:
        async with self._store_lock:
            session = await self._require_managed_session_unlocked(session_id)
        async with session.runtime.lock:
            now = datetime.now(timezone.utc)
            self._session_live_state.bind_surface(
                session,
                surface=surface,
                reply_enabled=False,
                now_utc=now,
            )
            session.touch(now_utc=now)
            self._persist_session_unlocked(session)
            return self._session_read_models.build_session_summary(session)

    async def control_session_context(
        self,
        session_id: str,
        *,
        action: str,
        reason: str | None = None,
        surface: str | None = None,
        channel_type: str | None = None,
        conversation_id: str | None = None,
        sender_id: str | None = None,
    ) -> MainAgentSessionControlResponse:
        async with self._store_lock:
            session = await self._require_managed_session_unlocked(session_id)

        return await self._session_operator.control_session(
            session,
            action=action,
            reason=reason,
            surface=surface,
            channel_type=channel_type,
            conversation_id=conversation_id,
            sender_id=sender_id,
        )

    async def update_session_context_policy(
        self,
        session_id: str,
        *,
        action: str,
        sources: Sequence[str] | None = None,
        max_items: int | None = None,
        max_total_chars: int | None = None,
        max_items_per_source: int | None = None,
        surface: str | None = None,
        channel_type: str | None = None,
        conversation_id: str | None = None,
        sender_id: str | None = None,
    ) -> MainAgentSessionContextResponse:
        async with self._store_lock:
            session = await self._require_managed_session_unlocked(session_id)

        return await self._session_operator.update_context_policy(
            session,
            action=action,
            sources=sources,
            max_items=max_items,
            max_total_chars=max_total_chars,
            max_items_per_source=max_items_per_source,
            surface=surface,
            channel_type=channel_type,
            conversation_id=conversation_id,
            sender_id=sender_id,
        )

    async def manage_session_memory(
        self,
        session_id: str,
        *,
        action: str,
        engram_id: str | None = None,
        content: str | None = None,
        query: str | None = None,
        day: str | None = None,
        export_format: str | None = None,
        detail_mode: str | None = None,
        surface: str | None = None,
        channel_type: str | None = None,
        conversation_id: str | None = None,
        sender_id: str | None = None,
    ) -> MainAgentSessionMemoryResponse:
        async with self._store_lock:
            session = await self._require_managed_session_unlocked(session_id)

        return await self._session_operator.manage_memory(
            session,
            action=action,
            engram_id=engram_id,
            content=content,
            query=query,
            day=day,
            export_format=export_format,
            detail_mode=detail_mode,
            surface=surface,
            channel_type=channel_type,
            conversation_id=conversation_id,
            sender_id=sender_id,
        )

    async def manage_session_skills(
        self,
        session_id: str,
        *,
        action: str,
        skill_name: str | None = None,
        path: str | None = None,
        query: str | None = None,
        mode: str | None = None,
        surface: str | None = None,
        channel_type: str | None = None,
        conversation_id: str | None = None,
        sender_id: str | None = None,
    ) -> MainAgentSessionSkillResponse:
        async with self._store_lock:
            session = await self._require_managed_session_unlocked(session_id)
        return await self._session_operator.manage_skills(
            session,
            action=action,
            skill_name=skill_name,
            path=path,
            query=query,
            mode=mode,
            surface=surface,
            channel_type=channel_type,
            conversation_id=conversation_id,
            sender_id=sender_id,
        )

    async def update_session_model_selection(
        self,
        session_id: str,
        *,
        provider_source: str | None,
        provider_id: str,
        model_id: str,
        surface: str | None = None,
        channel_type: str | None = None,
        conversation_id: str | None = None,
        sender_id: str | None = None,
    ) -> MainAgentSessionModelSelectionResponse:
        async with self._store_lock:
            session = await self._require_managed_session_unlocked(session_id)
        return await self._session_operator.update_model_selection(
            session,
            provider_source=provider_source,
            provider_id=provider_id,
            model_id=model_id,
            surface=surface,
            channel_type=channel_type,
            conversation_id=conversation_id,
            sender_id=sender_id,
        )

    async def apply_pending_session_model_selection(
        self,
        session: MainAgentSessionState,
    ) -> bool:
        pending_identity = self._session_model_selection.pending_identity_to_apply(session)
        applied = await self._session_agent_runtime.apply_pending_model_selection(
            session,
            pending_identity=pending_identity,
        )
        if applied:
            session.touch()
            self._persist_session_unlocked(session)
        return applied

    async def update_session_runtime_policy(
        self,
        session_id: str,
        *,
        approval_profile: str | None = None,
        access_level: str | None = None,
        surface: str | None = None,
        channel_type: str | None = None,
        conversation_id: str | None = None,
        sender_id: str | None = None,
    ):
        async with self._store_lock:
            session = await self._require_managed_session_unlocked(session_id)
        return await self._session_operator.update_runtime_policy(
            session,
            approval_profile=approval_profile,
            access_level=access_level,
            surface=surface,
            channel_type=channel_type,
            conversation_id=conversation_id,
            sender_id=sender_id,
        )

    async def queue_workspace_skill_reload(
        self,
        workspace_dir: Path,
        *,
        current_session_id: str | None,
        reason: str,
        include_current: bool,
    ) -> tuple[str, ...]:
        async with self._store_lock:
            result = self._session_agent_runtime.queue_workspace_skill_reload(
                workspace_dir,
                sessions=self._sessions.values(),
                current_session_id=current_session_id,
                reason=reason,
                include_current=include_current,
            )
            for candidate in result.touched_sessions:
                self._persist_session_unlocked(candidate)
            return result.queued_session_ids

    async def apply_pending_session_skill_reload(
        self,
        session: MainAgentSessionState,
    ) -> bool:
        applied = await self._session_agent_runtime.apply_pending_skill_reload(session)
        if applied:
            session.touch()
            self._persist_session_unlocked(session)
        return applied

    def mark_turn_started(
        self,
        session: MainAgentSessionState,
        *,
        surface: str | None,
        detail: str | None = None,
        now_utc: datetime | None = None,
    ) -> None:
        self._session_turn_scope.mark_turn_started(
            session,
            surface=surface,
            detail=detail,
            now_utc=now_utc,
        )

    def mark_turn_finished(
        self,
        session: MainAgentSessionState,
        *,
        now_utc: datetime | None = None,
    ) -> None:
        self._session_turn_scope.mark_turn_finished(
            session,
            now_utc=now_utc,
        )

    def bind_session_surface(
        self,
        session: MainAgentSessionState,
        *,
        surface: str | None,
        channel_type: str | None = None,
        conversation_id: str | None = None,
        sender_id: str | None = None,
        now_utc: datetime | None = None,
    ) -> None:
        self._session_turn_scope.bind_surface(
            session,
            surface=surface,
            channel_type=channel_type,
            conversation_id=conversation_id,
            sender_id=sender_id,
            now_utc=now_utc,
        )

    def record_message(
        self,
        session: MainAgentSessionState,
        *,
        role: str,
        content: str,
        surface: str | None,
        metadata: dict[str, Any] | None = None,
        channel_type: str | None = None,
        conversation_id: str | None = None,
        sender_id: str | None = None,
        now_utc: datetime | None = None,
    ) -> None:
        self._session_turn_scope.record_message(
            session,
            role=role,
            content=content,
            surface=surface,
            metadata=metadata,
            channel_type=channel_type,
            conversation_id=conversation_id,
            sender_id=sender_id,
            now_utc=now_utc,
        )

    def record_turn(
        self,
        session: MainAgentSessionState,
        *,
        user_message: str,
        assistant_reply: str,
        surface: str | None,
        channel_type: str | None = None,
        conversation_id: str | None = None,
        sender_id: str | None = None,
        now_utc: datetime | None = None,
    ) -> None:
        self._session_turn_scope.record_turn(
            session,
            user_message=user_message,
            assistant_reply=assistant_reply,
            surface=surface,
            channel_type=channel_type,
            conversation_id=conversation_id,
            sender_id=sender_id,
            now_utc=now_utc,
        )

    def record_activity(
        self,
        session: MainAgentSessionState,
        *,
        label: str,
        detail: str,
        surface: str | None,
        activity_id: str | None = None,
        preview: str = "",
        output_text: str = "",
        state: str = "",
        channel_type: str | None = None,
        conversation_id: str | None = None,
        sender_id: str | None = None,
        now_utc: datetime | None = None,
    ) -> dict[str, Any]:
        return self._session_turn_scope.record_activity(
            session,
            label=label,
            detail=detail,
            surface=surface,
            activity_id=activity_id,
            preview=preview,
            output_text=output_text,
            state=state,
            channel_type=channel_type,
            conversation_id=conversation_id,
            sender_id=sender_id,
            now_utc=now_utc,
        )

    def record_pending_approval(
        self,
        session: MainAgentSessionState,
        *,
        payload: dict[str, Any],
        future: asyncio.Future[bool | None],
        now_utc: datetime | None = None,
    ) -> dict[str, Any]:
        return self._session_turn_scope.record_pending_approval(
            session,
            payload=payload,
            future=future,
            now_utc=now_utc,
        )

    def clear_pending_approval(
        self,
        session: MainAgentSessionState,
        *,
        token: str | None = None,
        now_utc: datetime | None = None,
    ) -> None:
        self._session_turn_scope.clear_pending_approval(
            session,
            token=token,
            now_utc=now_utc,
        )

    async def resolve_pending_approval(
        self,
        session_id: str,
        *,
        approved: bool,
        token: str | None = None,
        surface: str | None = None,
        channel_type: str | None = None,
        conversation_id: str | None = None,
        sender_id: str | None = None,
    ) -> MainAgentSessionApprovalResponse:
        async with self._store_lock:
            persisted_exists = self._persistence.load_session_record(session_id) is not None
            return self._session_operator.resolve_pending_approval(
                session_id=session_id,
                active_session=self._sessions.get(session_id),
                persisted_exists=persisted_exists,
                approved=approved,
                token=token,
                surface=surface,
                channel_type=channel_type,
                conversation_id=conversation_id,
                sender_id=sender_id,
            )

    def build_recovery_turn_context(
        self,
        session: MainAgentSessionState,
    ) -> dict[str, Any] | None:
        return self._session_turn_scope.build_recovery_turn_context(session)

    def clear_recovery_context(
        self,
        session: MainAgentSessionState,
        *,
        now_utc: datetime | None = None,
    ) -> None:
        self._session_turn_scope.clear_recovery_context(
            session,
            now_utc=now_utc,
        )

    def _drop_expired_sessions_unlocked(self, *, now_utc: datetime | None = None) -> None:
        expired_ids = self._runtime_policy_coordinator.expired_session_ids(
            self._sessions,
            now_utc=now_utc,
        )
        for sid in expired_ids:
            self._sessions.pop(sid, None)

    def _persist_session_unlocked(
        self,
        session: MainAgentSessionState,
        *,
        agent_messages: Sequence[Any] | None = None,
    ) -> None:
        try:
            sandbox_diagnostics = self._session_diagnostics.build_sandbox_diagnostics_for_session(session)
            self._persistence.save_session(
                session,
                agent_messages=agent_messages,
                sandbox_diagnostics=sandbox_diagnostics,
            )
        except Exception:
            return

    def _allocate_new_session_id_unlocked(self) -> str:
        while True:
            candidate = uuid4().hex
            if candidate in self._sessions:
                continue
            if self._persistence.load_session_record(candidate) is not None:
                continue
            return candidate

    async def _load_managed_session_unlocked(self, session_id: str) -> MainAgentSessionState | None:
        existing = self._sessions.get(session_id)
        if existing is not None:
            return existing
        record = self._persistence.load_session_record(session_id)
        if record is None:
            return None
        return await self._restore_persisted_session_unlocked(record)

    async def _require_managed_session_unlocked(self, session_id: str) -> MainAgentSessionState:
        session = await self._load_managed_session_unlocked(session_id)
        if session is None:
            raise HTTPException(status_code=404, detail="Session not found.")
        return session

    async def _restore_persisted_session_unlocked(
        self,
        record: dict[str, Any],
        *,
        now_utc: datetime | None = None,
    ) -> MainAgentSessionState:
        now = (now_utc or datetime.now(timezone.utc)).astimezone(timezone.utc)
        payload = self._session_restore.prepare_restore_payload(
            record,
            now_utc=now,
        )
        session_id = payload.session_id
        existing = self._sessions.get(session_id)
        if existing is not None:
            return existing
        return await self._hydrate_session_unlocked(payload, now_utc=now, persist_after=False)

    async def _hydrate_session_unlocked(
        self,
        payload: RuntimeSessionHydrationPayload,
        *,
        now_utc: datetime,
        persist_after: bool,
    ) -> MainAgentSessionState:
        session_id = payload.session_id
        execution = await self._session_restore.hydrate_payload(
            payload,
            now_utc=now_utc,
            existing_session=self._sessions.get(session_id),
        )
        if execution.created:
            self._sessions[session_id] = execution.session
            self._session_lineage_registry.register_session(execution.session)
            if persist_after:
                self._persist_session_unlocked(
                    execution.session,
                    agent_messages=execution.agent_messages_for_persist,
                )
        return execution.session

    @staticmethod
    def _restore_agent_messages_payload(
        raw_messages: Sequence[Any],
        agent: Agent,
    ) -> None:
        restored: list[Message] = []
        for raw in raw_messages or []:
            if not isinstance(raw, dict):
                continue
            try:
                restored.append(Message.model_validate(raw))
            except Exception:
                continue
        if not restored:
            return
        if restored[0].role != "system":
            base_messages = getattr(agent, "messages", None)
            if isinstance(base_messages, list) and base_messages:
                try:
                    base_system = base_messages[0]
                    if hasattr(base_system, "model_dump"):
                        restored.insert(0, Message.model_validate(base_system.model_dump()))
                    elif isinstance(base_system, dict):
                        restored.insert(0, Message.model_validate(base_system))
                    else:
                        restored.insert(
                            0,
                            Message(
                                role=str(getattr(base_system, "role", "system") or "system"),
                                content=str(getattr(base_system, "content", "")),
                            ),
                        )
                except Exception:
                    pass
        agent.messages = restored

    @staticmethod
    def _normalize_context_policy_payload(value: Any) -> dict[str, Any]:
        return resolve_turn_context_policy(value or {})

    @staticmethod
    def _normalize_prepared_context_payload(value: Any) -> dict[str, Any]:
        return dict(value) if isinstance(value, dict) else {}

    @staticmethod
    def _normalize_prepared_context_diagnostics_payload(value: Any) -> dict[str, Any]:
        return dict(value) if isinstance(value, dict) else {}

    @staticmethod
    def _normalize_memory_diagnostics_payload(value: Any) -> dict[str, Any]:
        return dict(value) if isinstance(value, dict) else {}

    @staticmethod
    def _normalize_sandbox_diagnostics_payload(value: Any) -> dict[str, Any]:
        return normalize_sandbox_diagnostics(value)

    @staticmethod
    def _serialize_agent_messages(messages: Sequence[Any]) -> list[dict[str, Any]]:
        serialized: list[dict[str, Any]] = []
        for item in messages or []:
            if hasattr(item, "model_dump"):
                payload = item.model_dump()
            elif isinstance(item, dict):
                payload = dict(item)
            elif hasattr(item, "__dict__"):
                payload = dict(vars(item))
            else:
                payload = {"role": "assistant", "content": str(item)}
            serialized.append(
                {
                    "role": payload.get("role", "assistant"),
                    "content": payload.get("content", ""),
                    "thinking": payload.get("thinking"),
                    "tool_calls": payload.get("tool_calls"),
                    "tool_call_id": payload.get("tool_call_id"),
                    "name": payload.get("name"),
                }
            )
        return serialized

    def _enforce_main_workspace_policy(self, workspace_dir: Path) -> None:
        self._runtime_policy_coordinator.enforce_main_workspace(
            workspace_dir,
            same_workspace=self._same_workspace,
        )

    @staticmethod
    def _path_key(path: Path) -> str:
        resolved = str(path.resolve())
        return resolved.lower() if os.name == "nt" else resolved

    @classmethod
    def _same_workspace(cls, left: Path, right: Path) -> bool:
        return cls._path_key(left) == cls._path_key(right)

    @staticmethod
    def _normalize_surface(surface: str | None) -> str:
        return normalize_surface_label(surface)

    @staticmethod
    def _normalize_nonnegative_int(value: Any, *, default: int = 0) -> int:
        try:
            parsed = int(value or 0)
        except Exception:
            return max(0, int(default))
        return max(0, parsed)

    @classmethod
    def _estimate_raw_message_tokens(cls, raw_messages: Sequence[Any] | None) -> int:
        restored: list[Message] = []
        for raw in raw_messages or []:
            if not isinstance(raw, dict):
                continue
            try:
                restored.append(Message.model_validate(raw))
            except Exception:
                continue
        if not restored:
            return 0
        try:
            return cls._normalize_nonnegative_int(estimate_tokens(restored))
        except Exception:
            return 0

    @classmethod
    def _session_token_usage(cls, session: MainAgentSessionState) -> int:
        live = cls._normalize_nonnegative_int(getattr(session.runtime.agent, "api_total_tokens", 0))
        if live > 0:
            return live
        messages = getattr(session.runtime.agent, "messages", None)
        if isinstance(messages, list):
            try:
                return cls._normalize_nonnegative_int(estimate_tokens(messages))
            except Exception:
                return 0
        return 0

    @classmethod
    def _session_token_limit(cls, session: MainAgentSessionState) -> int:
        return cls._normalize_nonnegative_int(getattr(session.runtime.agent, "token_limit", 0))

    @classmethod
    def _record_token_usage(cls, record: dict[str, Any]) -> int:
        explicit = cls._normalize_nonnegative_int(record.get("token_usage"))
        if explicit > 0:
            return explicit
        raw_messages = record.get("messages")
        if isinstance(raw_messages, list):
            return cls._estimate_raw_message_tokens(raw_messages)
        return 0

    @classmethod
    def _record_token_limit(cls, record: dict[str, Any]) -> int:
        return cls._normalize_nonnegative_int(record.get("token_limit"))

    @classmethod
    def _restore_agent_token_state(
        cls,
        agent: Agent,
        *,
        token_usage: Any = None,
        token_limit: Any = None,
        raw_messages: Sequence[Any] | None = None,
    ) -> None:
        usage = cls._normalize_nonnegative_int(token_usage)
        if usage <= 0:
            usage = cls._estimate_raw_message_tokens(raw_messages)
        if hasattr(agent, "api_total_tokens"):
            agent.api_total_tokens = usage

        limit = cls._normalize_nonnegative_int(token_limit)
        if limit > 0:
            setattr(agent, "token_limit", limit)

    @classmethod
    def _build_session_key(cls, *, session_id: str, workspace_dir: Path) -> AgentSessionKey:
        return AgentSessionKey(
            agent_id="main-agent",
            channel="gateway",
            peer_kind="workspace",
            peer_id=cls._path_key(workspace_dir),
            thread_id=session_id,
        )

    def _refresh_session_lifecycle_unlocked(
        self,
        session: MainAgentSessionState,
        *,
        now_utc: datetime | None = None,
    ) -> bool:
        return self._runtime_policy_coordinator.refresh_session_lifecycle(
            session,
            now_utc=now_utc,
            reset_runtime_state=lambda: self._session_live_state.reset_runtime_state(
                session,
                clear_runtime_task_memory=True,
            ),
        )
