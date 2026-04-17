"""Runtime manager for single-host main-agent session lifecycle."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence

from mini_agent.agent_core.context.command_service import ContextCommandService
from mini_agent.agent_core.engine import Agent
from mini_agent.agent_core.skills.command_service import SkillCommandService
from mini_agent.agent_core.session import (
    SessionLifecycleManager,
    SessionLineageStore,
)
from mini_agent.commands.mcp_support import (
    collect_mcp_operator_snapshot,
    format_mcp_server_list,
    format_mcp_status,
)
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
from mini_agent.interaction import normalize_channel_type, normalize_surface_label
from mini_agent.model_manager.session_selection_service import SessionModelSelectionService
from mini_agent.model_manager.runtime import resolve_session_model_selection_identity
from mini_agent.memory.command_service import MemoryCommandService
from mini_agent.memory.runtime_backend import WorkspaceRuntimeMemoryBackend
from mini_agent.runtime.main_agent_runtime_contracts import (
    MainAgentRuntimeDiagnostics,
    MainAgentRuntimeMode,
    MainAgentRuntimePolicy,
)
from mini_agent.runtime.support.session_agent_support import (
    BuildAgentFn,
    BuildSelectedAgentFn,
    RuntimeSessionAgentSupport,
)
from mini_agent.runtime.read_models.session_model_identity_codec import RuntimeSessionModelIdentityCodec
from mini_agent.runtime.read_models.session_payload_codec import RuntimeSessionPayloadCodec
from mini_agent.runtime.read_models.session_read_model_builder import RuntimeSessionReadModelBuilder
from mini_agent.runtime.read_models.session_snapshot_builder import RuntimeSessionSnapshotBuilder
from mini_agent.runtime.session_snapshot import RuntimeSessionSnapshot
from mini_agent.runtime.handlers.session_admin_handler import RuntimeSessionAdminHandler
from mini_agent.runtime.support.session_command_coordinator import (
    RuntimeSessionCommandCoordinator,
)
from mini_agent.runtime.handlers.session_catalog_handler import RuntimeSessionCatalogHandler
from mini_agent.runtime.handlers.session_access_handler import (
    RuntimeSessionAccessHandler,
)
from mini_agent.runtime.handlers.session_agent_runtime_handler import RuntimeSessionAgentRuntimeHandler
from mini_agent.runtime.handlers.session_creation_handler import (
    RuntimeSessionCreationHandler,
)
from mini_agent.runtime.orchestration.session_hydration_coordinator import (
    RuntimeSessionHydrationCoordinator,
)
from mini_agent.runtime.orchestration.session_hydration_builder import (
    RuntimeSessionHydrationBuilder,
)
from mini_agent.runtime.orchestration.session_restore_handler import RuntimeSessionRestoreHandler
from mini_agent.runtime.orchestration.session_runtime_lifecycle_handler import RuntimeSessionLifecycleHandler
from mini_agent.runtime.orchestration.session_runtime_policy_coordinator import (
    RuntimeSessionPolicyCoordinator,
)
from mini_agent.runtime.orchestration.session_runtime_state_hydrator import (
    RuntimeSessionStateHydrator,
)
from mini_agent.runtime.support.session_diagnostics_service import RuntimeSessionDiagnosticsService
from mini_agent.runtime.support.session_persistence_loader import RuntimeSessionPersistenceLoader
from mini_agent.runtime.support.session_persistence_record_builder import RuntimeSessionPersistenceRecordBuilder
from mini_agent.runtime.handlers.session_registry_handler import RuntimeSessionRegistryHandler
from mini_agent.runtime.live_control.session_interrupt_handler import RuntimeSessionInterruptHandler
from mini_agent.runtime.live_control.session_live_state_handler import RuntimeSessionLiveStateHandler
from mini_agent.runtime.live_control.session_recovery_reset_handler import (
    RuntimeSessionRecoveryResetHandler,
)
from mini_agent.runtime.orchestration.session_managed_store_handler import (
    RuntimeManagedSessionStoreHandler,
)
from mini_agent.runtime.session_lineage_registry import RuntimeSessionLineageRegistry
from mini_agent.runtime.handlers.session_memory_command_handler import RuntimeSessionMemoryCommandHandler
from mini_agent.runtime.live_control.session_pending_approval_state_handler import (
    RuntimeSessionPendingApprovalStateHandler,
)
from mini_agent.runtime.handlers.session_agent_control_handler import RuntimeSessionAgentControlHandler
from mini_agent.runtime.handlers.session_mcp_control_handler import RuntimeSessionMcpControlHandler
from mini_agent.runtime.handlers.session_operator_handler import RuntimeSessionOperatorHandler
from mini_agent.runtime.runtime_policy_service import SessionRuntimePolicyService
from mini_agent.runtime.session_runtime_persistence import MainAgentRuntimePersistence
from mini_agent.runtime.session_state import MainAgentSessionState
from mini_agent.runtime.orchestration.session_turn_scope_handler import RuntimeSessionTurnScopeHandler
from mini_agent.runtime.orchestration.session_snapshot_handler import (
    RuntimeSessionSnapshotHandler,
    RuntimeSessionSnapshotImportCommand,
)
from mini_agent.runtime.support.sandbox_state import collect_sandbox_diagnostics
from mini_agent.runtime.support.tooling import reconfigure_agent_runtime_policy
from mini_agent.runtime.support.workspace_path_utils import same_workspace_path, workspace_path_key
from mini_agent.tools.mcp_loader import cleanup_mcp_connections
_RUNTIME_SESSION_KIND = "main-agent-runtime"


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
        load_runtime_config: Callable[[], Any],
    ):
        self._ttl_seconds = int(ttl_seconds)
        self._build_agent = build_agent
        self._build_agent_with_selection = build_agent_with_selection
        self._policy = policy or MainAgentRuntimePolicy()
        self._load_runtime_config = load_runtime_config
        self._sessions: dict[str, MainAgentSessionState] = {}
        self._store_lock = asyncio.Lock()
        self._initialize_runtime_core(storage_dir)
        self._initialize_runtime_support_services()
        self._initialize_session_model_services()
        self._initialize_session_runtime_services()
        self._initialize_session_boundary_services()

    def _initialize_runtime_core(self, storage_dir: Path | None) -> None:
        self._model_identity_codec = RuntimeSessionModelIdentityCodec()
        self._payload_codec = RuntimeSessionPayloadCodec()
        self._lifecycle_manager = SessionLifecycleManager(self._policy.session_lifecycle)
        self._session_lineage = SessionLineageStore()
        self._session_lineage_registry = RuntimeSessionLineageRegistry(self._session_lineage)
        self._runtime_policy_coordinator = RuntimeSessionPolicyCoordinator(
            policy=self._policy,
            ttl_seconds=self._ttl_seconds,
            lifecycle_manager=self._lifecycle_manager,
        )
        self._session_lifecycle = RuntimeSessionLifecycleHandler(
            lifecycle_manager=self._lifecycle_manager,
            policy_coordinator=self._runtime_policy_coordinator,
            path_key=workspace_path_key,
        )
        self._session_persistence_records = RuntimeSessionPersistenceRecordBuilder(
            session_kind=_RUNTIME_SESSION_KIND,
            session_token_usage=self._payload_codec.session_token_usage,
            session_token_limit=self._payload_codec.session_token_limit,
            agent_last_memory_automation=self._payload_codec.agent_last_memory_automation,
            agent_last_runtime_task_memory=self._payload_codec.agent_last_runtime_task_memory,
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
        self._session_agent_support = RuntimeSessionAgentSupport(
            build_agent=self._build_agent,
            build_agent_with_selection=self._build_agent_with_selection,
            load_runtime_config=self._load_runtime_config,
            payload_codec=self._payload_codec,
        )
        self._session_diagnostics = RuntimeSessionDiagnosticsService(
            normalize_prepared_context_payload=self._payload_codec.normalize_prepared_context_payload,
            normalize_memory_diagnostics_payload=self._payload_codec.normalize_memory_diagnostics_payload,
            normalize_sandbox_diagnostics_payload=self._payload_codec.normalize_sandbox_diagnostics_payload,
            collect_sandbox_diagnostics=lambda agent: collect_sandbox_diagnostics(agent=agent),
            agent_last_memory_automation=self._session_agent_support.agent_last_memory_automation,
            agent_last_runtime_task_memory=self._session_agent_support.agent_last_runtime_task_memory,
        )
        self._runtime_task_memory_backend = WorkspaceRuntimeMemoryBackend()
        self._session_runtime_state_hydrator = RuntimeSessionStateHydrator(
            agent_knowledge_base_enabled=self._session_agent_support.agent_knowledge_base_enabled,
            agent_last_prepared_context=self._session_agent_support.agent_last_prepared_context,
            agent_prepared_context_diagnostics=self._session_agent_support.agent_prepared_context_diagnostics,
            restore_session_runtime_task_memory=self._runtime_task_memory_backend.restore_session_payload,
            restore_workspace_shared_runtime_task_memory=self._runtime_task_memory_backend.restore_workspace_shared_payload,
            build_memory_diagnostics_for_session=self._session_diagnostics.build_memory_diagnostics_for_session,
            build_sandbox_diagnostics_for_session=self._session_diagnostics.build_sandbox_diagnostics_for_session,
        )
        self._session_live_state = RuntimeSessionLiveStateHandler()
        self._session_pending_approval_state = RuntimeSessionPendingApprovalStateHandler()
        self._session_recovery_reset = RuntimeSessionRecoveryResetHandler(
            refresh_session_diagnostics=self._session_runtime_state_hydrator.refresh_session_diagnostics,
            agent_knowledge_base_enabled=self._session_agent_support.agent_knowledge_base_enabled,
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
            command_service=MemoryCommandService(
                runtime_memory_backend=self._runtime_task_memory_backend,
            ),
        )
        self._session_access = RuntimeSessionAccessHandler(
            normalize_surface=normalize_surface_label,
            normalize_channel_type=normalize_channel_type,
            same_workspace=same_workspace_path,
            resolve_main_workspace=self._resolve_default_session_workspace,
        )

    def _initialize_session_model_services(self) -> None:
        self._session_hydration_builder = RuntimeSessionHydrationBuilder(
            build_model_identity=self._model_identity_codec.normalize_model_identity,
            runtime_policy_overrides_from_diagnostics=self._session_agent_support.runtime_policy_overrides_from_diagnostics,
            normalize_surface=normalize_surface_label,
            normalize_context_policy_payload=self._payload_codec.normalize_context_policy_payload,
            normalize_prepared_context_payload=self._payload_codec.normalize_prepared_context_payload,
            normalize_prepared_context_diagnostics_payload=self._payload_codec.normalize_prepared_context_diagnostics_payload,
            normalize_memory_diagnostics_payload=self._payload_codec.normalize_memory_diagnostics_payload,
            normalize_sandbox_diagnostics_payload=self._payload_codec.normalize_sandbox_diagnostics_payload,
            build_memory_diagnostics_from_record=self._session_diagnostics.build_memory_diagnostics_from_record,
            build_sandbox_diagnostics_from_record=self._session_diagnostics.build_sandbox_diagnostics_from_record,
        )
        self._session_read_models = RuntimeSessionReadModelBuilder(
            normalize_surface=normalize_surface_label,
            normalize_model_source=self._model_identity_codec.normalize_model_source,
            normalize_context_policy_payload=self._payload_codec.normalize_context_policy_payload,
            normalize_prepared_context_payload=self._payload_codec.normalize_prepared_context_payload,
            normalize_prepared_context_diagnostics_payload=self._payload_codec.normalize_prepared_context_diagnostics_payload,
            build_memory_diagnostics_for_session=self._session_diagnostics.build_memory_diagnostics_for_session,
            build_memory_diagnostics_from_record=self._session_diagnostics.build_memory_diagnostics_from_record,
            build_sandbox_diagnostics_for_session=self._session_diagnostics.build_sandbox_diagnostics_for_session,
            build_sandbox_diagnostics_from_record=self._session_diagnostics.build_sandbox_diagnostics_from_record,
            session_token_usage=self._payload_codec.session_token_usage,
            session_token_limit=self._payload_codec.session_token_limit,
            record_token_usage=self._payload_codec.record_token_usage,
            record_token_limit=self._payload_codec.record_token_limit,
            transcript_entries_from_record=self._session_hydration_builder.transcript_entries_from_record,
            pending_approvals_from_raw=RuntimeSessionPendingApprovalStateHandler.pending_approvals_from_raw,
        )
        self._session_snapshot_builder = RuntimeSessionSnapshotBuilder(
            normalize_surface=normalize_surface_label,
            normalize_model_source=self._model_identity_codec.normalize_model_source,
            normalize_context_policy_payload=self._payload_codec.normalize_context_policy_payload,
            normalize_prepared_context_payload=self._payload_codec.normalize_prepared_context_payload,
            normalize_prepared_context_diagnostics_payload=self._payload_codec.normalize_prepared_context_diagnostics_payload,
            build_memory_diagnostics_for_session=self._session_diagnostics.build_memory_diagnostics_for_session,
            build_memory_diagnostics_from_record=self._session_diagnostics.build_memory_diagnostics_from_record,
            build_sandbox_diagnostics_for_session=self._session_diagnostics.build_sandbox_diagnostics_for_session,
            build_sandbox_diagnostics_from_record=self._session_diagnostics.build_sandbox_diagnostics_from_record,
            snapshot_runtime_task_memory_payload=self._runtime_task_memory_backend.snapshot_session_payload,
            snapshot_workspace_shared_runtime_task_memory_payload=self._runtime_task_memory_backend.snapshot_workspace_shared_payload,
            session_token_usage=self._payload_codec.session_token_usage,
            session_token_limit=self._payload_codec.session_token_limit,
            record_token_usage=self._payload_codec.record_token_usage,
            record_token_limit=self._payload_codec.record_token_limit,
            transcript_entries_from_record=self._session_hydration_builder.transcript_entries_from_record,
            agent_messages=self._session_agent_support.agent_messages,
            serialize_agent_messages=self._payload_codec.serialize_agent_messages,
        )
        self._session_catalog = RuntimeSessionCatalogHandler(
            same_workspace=same_workspace_path,
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
            normalize_surface=normalize_surface_label,
            normalize_channel_type=normalize_channel_type,
            build_agent_for_identity=self._session_agent_support.build_agent_for_identity,
            bootstrap_session_lifecycle=lambda session_id, workspace_dir, now_utc: self._session_lifecycle.bootstrap_session(
                session_id,
                workspace_dir,
                now_utc=now_utc,
            ),
            agent_knowledge_base_enabled=self._session_agent_support.agent_knowledge_base_enabled,
            collect_sandbox_diagnostics=lambda agent: collect_sandbox_diagnostics(agent=agent),
            route_model_identity=self._model_identity_codec.route_model_identity,
        )
        self._session_model_selection = SessionModelSelectionService(
            normalize_model_identity=self._model_identity_codec.normalize_model_identity,
            resolve_selection_identity=lambda provider_source, provider_id, model_id: resolve_session_model_selection_identity(
                provider_source=provider_source,
                provider_id=provider_id,
                model_id=model_id,
            ),
        )

    def _initialize_session_runtime_services(self) -> None:
        self._session_hydration = RuntimeSessionHydrationCoordinator(
            prepare_restore_payload=lambda record, now_utc: self._session_restore.prepare_restore_payload(
                record,
                now_utc=now_utc,
            ),
            hydrate_payload=lambda payload, now_utc, existing_session: self._session_restore.hydrate_payload(
                payload,
                now_utc=now_utc,
                existing_session=existing_session,
            ),
            register_session=self._session_lineage_registry.register_session,
            persist_hydrated_session=lambda session, agent_messages=None: self._managed_session_store.persist_session(
                session,
                agent_messages=agent_messages,
            ),
        )
        self._managed_session_store = RuntimeManagedSessionStoreHandler(
            expired_session_ids=self._runtime_policy_coordinator.expired_session_ids,
            build_sandbox_diagnostics_for_session=self._session_diagnostics.build_sandbox_diagnostics_for_session,
            save_session=lambda session, agent_messages, sandbox_diagnostics: self._persistence.save_session(
                session,
                agent_messages=agent_messages,
                sandbox_diagnostics=sandbox_diagnostics,
            ),
            load_session_record=self._persistence.load_session_record,
            delete_session_record=self._persistence.delete_session,
            restore_persisted_session=lambda record, now_utc: self._session_hydration.restore_persisted_session(
                self._sessions,
                record,
                now_utc=now_utc,
            ),
            record_workspace_dir=self._session_catalog.record_workspace_dir,
            clear_session_runtime_task_memory=lambda workspace_dir, session_id: self._runtime_task_memory_backend.clear_session_namespace(
                workspace_dir=workspace_dir,
                session_id=session_id,
            ),
            remove_session_lineage=self._session_lineage_registry.remove_session,
        )
        self._session_turn_scope = RuntimeSessionTurnScopeHandler(
            bind_surface_mutation=self._session_live_state.bind_surface,
            mark_turn_started_mutation=self._session_live_state.mark_turn_started,
            mark_turn_finished_mutation=self._session_live_state.mark_turn_finished,
            record_message_mutation=self._session_live_state.record_message,
            record_activity_mutation=self._session_live_state.record_activity,
            record_pending_approval_mutation=self._session_pending_approval_state.record_pending_approval,
            clear_pending_approval_mutation=self._session_pending_approval_state.clear_pending_approval,
            build_recovery_turn_context_fn=self._session_recovery_reset.build_recovery_turn_context,
            clear_recovery_context_mutation=self._session_recovery_reset.clear_recovery_context,
            capture_prepared_context_state_mutation=self._session_runtime_state_hydrator.capture_agent_prepared_context_state,
            restore_prepared_context_state_mutation=self._session_runtime_state_hydrator.restore_agent_prepared_context_state,
            apply_pending_session_model_selection=self.apply_pending_session_model_selection,
            apply_pending_session_skill_reload=self.apply_pending_session_skill_reload,
            persist_session=self._managed_session_store.persist_session,
        )
        self._session_agent_runtime = RuntimeSessionAgentRuntimeHandler(
            runtime_policy_overrides_from_diagnostics=self._session_agent_support.runtime_policy_overrides_from_diagnostics,
            build_agent_for_identity=self._session_agent_support.build_agent_for_identity,
            load_runtime_config=self._session_agent_support.load_runtime_config,
            reconfigure_agent_runtime_policy=reconfigure_agent_runtime_policy,
            capture_agent_prepared_context_state=self._session_turn_scope.capture_prepared_context_state,
            restore_agent_prepared_context_state=self._session_turn_scope.restore_prepared_context_state,
            agent_messages=self._session_agent_support.agent_messages,
            serialize_agent_messages=self._payload_codec.serialize_agent_messages,
            restore_agent_messages_payload=self._payload_codec.restore_agent_messages_payload,
            apply_agent_knowledge_base_enabled=self._session_agent_support.apply_agent_knowledge_base_enabled,
            route_model_identity=self._model_identity_codec.route_model_identity,
            set_selected_model_identity=self._model_identity_codec.set_selected_model_identity,
            set_pending_model_identity=self._model_identity_codec.set_pending_model_identity,
            refresh_runtime_projection=self._session_runtime_state_hydrator.refresh_runtime_projection,
            same_workspace=same_workspace_path,
            selected_model_identity=self._model_identity_codec.selected_model_identity,
            pending_model_identity=self._model_identity_codec.pending_model_identity,
        )
        self._session_runtime_policy = SessionRuntimePolicyService()
        self._session_agent_control = RuntimeSessionAgentControlHandler(
            normalize_surface=normalize_surface_label,
            apply_agent_knowledge_base_enabled=self._session_agent_support.apply_agent_knowledge_base_enabled,
            refresh_runtime_projection=self._session_runtime_state_hydrator.refresh_runtime_projection,
        )
        self._session_mcp_control = RuntimeSessionMcpControlHandler(
            normalize_surface=normalize_surface_label,
            load_runtime_config=self._session_agent_support.load_runtime_config,
            collect_mcp_operator_snapshot=lambda config: collect_mcp_operator_snapshot(config),
            format_mcp_status=lambda snapshot: format_mcp_status(snapshot),
            format_mcp_server_list=lambda snapshot: format_mcp_server_list(snapshot),
        )
        self._session_commands = RuntimeSessionCommandCoordinator(
            append_transcript=self._session_live_state.append_transcript,
            persist_session=self._managed_session_store.persist_session,
        )
        self._session_admin = RuntimeSessionAdminHandler(
            rename_session_mutation=self._session_catalog.rename_session,
            set_session_shared_mutation=self._session_catalog.set_session_shared,
            reset_runtime_state_mutation=self._session_recovery_reset.reset_runtime_state,
            bind_surface_mutation=self._session_live_state.bind_surface,
            reset_session_lifecycle_mutation=self._session_lifecycle.reset_session,
            build_session_summary=self._session_catalog.build_session_summary,
            persist_session=self._managed_session_store.persist_session,
        )
        self._session_interrupt = RuntimeSessionInterruptHandler(
            normalize_surface=normalize_surface_label,
            pending_approvals_from_raw=RuntimeSessionPendingApprovalStateHandler.pending_approvals_from_raw,
        )
        self._session_context_commands = ContextCommandService()
        self._session_skill_commands = SkillCommandService()
        self._session_restore = RuntimeSessionRestoreHandler(
            transcript_entries_from_record=self._session_hydration_builder.transcript_entries_from_record,
            stored_recovery_snapshot_from_record=lambda record, transcript: self._session_read_models.stored_recovery_snapshot_from_record(
                record,
                transcript=transcript,
            ),
            build_record_hydration_payload=self._session_hydration_builder.build_record_hydration_payload,
            build_agent_for_identity=self._session_agent_support.build_agent_for_identity,
            load_runtime_config=self._session_agent_support.load_runtime_config,
            reconfigure_agent_runtime_policy=reconfigure_agent_runtime_policy,
            restore_agent_messages_payload=self._payload_codec.restore_agent_messages_payload,
            restore_agent_token_state=self._payload_codec.restore_agent_token_state,
            agent_knowledge_base_enabled=self._session_agent_support.agent_knowledge_base_enabled,
            apply_agent_knowledge_base_enabled=self._session_agent_support.apply_agent_knowledge_base_enabled,
            bootstrap_session_lifecycle=lambda session_id, workspace_dir, now_utc: self._session_lifecycle.bootstrap_session(
                session_id,
                workspace_dir,
                now_utc=now_utc,
            ),
            build_session_state=self._session_hydration_builder.build_session_state,
            apply_stored_recovery=self._session_recovery_reset.apply_stored_recovery,
            set_selected_model_identity=self._model_identity_codec.set_selected_model_identity,
            route_model_identity=self._model_identity_codec.route_model_identity,
            hydrate_runtime_state=lambda session, payload: self._session_runtime_state_hydrator.hydrate_runtime_state(
                session,
                payload=payload,
            ),
        )
        self._session_snapshots = RuntimeSessionSnapshotHandler(
            build_snapshot_hydration_payload=self._session_hydration_builder.build_snapshot_hydration_payload,
            build_session_snapshot=self._session_snapshot_builder.build_session_snapshot,
            build_session_snapshot_from_record=self._session_snapshot_builder.build_session_snapshot_from_record,
        )

    def _initialize_session_boundary_services(self) -> None:
        self._session_registry = RuntimeSessionRegistryHandler(
            session_access=self._session_access,
            session_creation=self._session_creation,
            session_snapshots=self._session_snapshots,
            session_catalog=self._session_catalog,
            drop_expired_sessions=lambda now_utc=None: self._managed_session_store.drop_expired_sessions(
                self._sessions,
                now_utc=now_utc,
            ),
            enforce_workspace_entry=lambda active_sessions, workspace_dir: self._runtime_policy_coordinator.enforce_workspace_entry(
                active_sessions,
                workspace_dir,
                same_workspace=same_workspace_path,
            ),
            enforce_capacity=lambda: self._runtime_policy_coordinator.enforce_capacity(
                self._billable_session_count(self._sessions.values())
            ),
            raise_workspace_mismatch=self._runtime_policy_coordinator.raise_workspace_mismatch,
            allocate_session_id=lambda: self._managed_session_store.allocate_session_id(self._sessions),
            load_persisted_record=self._persistence.load_session_record,
            list_persisted_records=self._persistence.list_session_records,
            restore_persisted_session=lambda record, now_utc: self._session_hydration.restore_persisted_session(
                self._sessions,
                record,
                now_utc=now_utc,
            ),
            hydrate_session=lambda payload, now_utc, persist_after: self._session_hydration.hydrate_session(
                self._sessions,
                payload,
                now_utc=now_utc,
                persist_after=persist_after,
            ),
            build_derived_hydration_payload=self._session_hydration_builder.build_derived_hydration_payload,
            refresh_session_lifecycle=lambda session, now_utc: self._session_lifecycle.refresh_session(
                session,
                now_utc=now_utc,
                reset_runtime_state=lambda: self._session_recovery_reset.reset_runtime_state(
                    session,
                    clear_runtime_task_memory=True,
                ),
            ),
            register_session=self._session_lineage_registry.register_session,
            persist_session=self._managed_session_store.persist_session,
        )
        self._session_operator = RuntimeSessionOperatorHandler(
            normalize_surface=normalize_surface_label,
            normalize_context_policy_payload=self._payload_codec.normalize_context_policy_payload,
            normalize_sandbox_diagnostics_payload=self._payload_codec.normalize_sandbox_diagnostics_payload,
            session_commands=self._session_commands,
            session_agent_control=self._session_agent_control,
            session_mcp_control=self._session_mcp_control,
            session_context_commands=self._session_context_commands,
            session_memory_commands=self._session_memory_commands,
            session_skill_commands=self._session_skill_commands,
            session_model_selection=self._session_model_selection,
            session_runtime_policy=self._session_runtime_policy,
            session_interrupt=self._session_interrupt,
            session_agent_runtime=self._session_agent_runtime,
            session_live_state=self._session_live_state,
            load_runtime_config=self._load_runtime_config,
            selected_model_identity=self._model_identity_codec.selected_model_identity,
            pending_model_identity=self._model_identity_codec.pending_model_identity,
            set_pending_model_identity=self._model_identity_codec.set_pending_model_identity,
            persist_session=self._managed_session_store.persist_session,
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
        self._runtime_policy_coordinator.enforce_main_workspace(
            workspace_dir,
            same_workspace=same_workspace_path,
        )
        return await self._session_agent_support.build_agent_for_identity(workspace_dir, None)

    @property
    def turn_scope_handler(self) -> RuntimeSessionTurnScopeHandler:
        return self._session_turn_scope

    def validate_workspace(self, workspace_dir: Path) -> None:
        self._runtime_policy_coordinator.enforce_main_workspace(
            workspace_dir,
            same_workspace=same_workspace_path,
        )

    def _resolve_default_session_workspace(self, workspace_dir: Path) -> Path:
        main_workspace = getattr(self._policy, "main_workspace_dir", None)
        if main_workspace is None:
            return workspace_dir
        return Path(main_workspace).resolve()

    @staticmethod
    def _billable_session_count(sessions: Iterable[MainAgentSessionState]) -> int:
        count = 0
        for session in sessions:
            if bool(getattr(getattr(session, "projection", None), "is_default", False)):
                continue
            count += 1
        return count

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

    async def ensure_session_runtime_policy_ready_for_turn(
        self,
        session: MainAgentSessionState,
        *,
        surface: str | None = None,
        channel_type: str | None = None,
        conversation_id: str | None = None,
        sender_id: str | None = None,
    ):
        return await self._session_operator.ensure_runtime_policy_ready_for_turn(
            session,
            surface=surface,
            channel_type=channel_type,
            conversation_id=conversation_id,
            sender_id=sender_id,
        )

    async def ensure_default_session(
        self,
        workspace_dir: Path,
        *,
        surface: str | None = None,
        channel_type: str | None = None,
        conversation_id: str | None = None,
        sender_id: str | None = None,
    ) -> MainAgentSessionState:
        return await self.get_or_create_session(
            None,
            workspace_dir,
            surface=surface,
            channel_type=channel_type,
            conversation_id=conversation_id,
            sender_id=sender_id,
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
            parent = await self._managed_session_store.require_managed_session(
                self._sessions,
                parent_session_id,
            )
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
            active_sessions = self._billable_session_count(self._sessions.values())
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
            session = await self._managed_session_store.require_managed_session(self._sessions, session_id)
        return await self._session_admin.rename_session(session, title=title)

    async def set_session_shared(self, session_id: str, *, shared: bool) -> MainAgentSessionSummary:
        async with self._store_lock:
            session = await self._managed_session_store.require_managed_session(self._sessions, session_id)
        return await self._session_admin.set_session_shared(session, shared=shared)

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
            self._managed_session_store.delete_session(self._sessions, session_id)

    async def reset_session(self, session_id: str) -> None:
        async with self._store_lock:
            session = await self._managed_session_store.require_managed_session(self._sessions, session_id)
        await self._session_admin.reset_session(session)

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
            session = await self._managed_session_store.require_managed_session(self._sessions, session_id)
        return await self._session_admin.set_active_surface(session, surface=surface)

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
            session = await self._managed_session_store.require_managed_session(self._sessions, session_id)

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
            session = await self._managed_session_store.require_managed_session(self._sessions, session_id)

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
            session = await self._managed_session_store.require_managed_session(self._sessions, session_id)

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
            session = await self._managed_session_store.require_managed_session(self._sessions, session_id)
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
            session = await self._managed_session_store.require_managed_session(self._sessions, session_id)
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
        pending_identity = self._session_model_selection.pending_identity_to_apply(
            pending_identity=self._model_identity_codec.pending_model_identity(session),
            busy=bool(session.projection.busy),
        )
        applied = await self._session_agent_runtime.apply_pending_model_selection(
            session,
            pending_identity=pending_identity,
        )
        if applied:
            session.touch()
            self._managed_session_store.persist_session(session)
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
            session = await self._managed_session_store.require_managed_session(self._sessions, session_id)
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
                self._managed_session_store.persist_session(candidate)
            return result.queued_session_ids

    async def apply_pending_session_skill_reload(
        self,
        session: MainAgentSessionState,
    ) -> bool:
        applied = await self._session_agent_runtime.apply_pending_skill_reload(session)
        if applied:
            session.touch()
            self._managed_session_store.persist_session(session)
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
