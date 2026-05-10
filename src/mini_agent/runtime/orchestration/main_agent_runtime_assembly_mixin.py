"""Physical owner for runtime manager initialization and assembly seams."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Iterable, Protocol

from mini_agent.agent_core.context.command_service import ContextCommandService
from mini_agent.agent_core.session.lifecycle import SessionLifecycleManager
from mini_agent.agent_core.session.lineage import SessionLineageStore
from mini_agent.agent_core.skills.command_service import SkillCommandService
from mini_agent.commands.mcp_support import (
    collect_mcp_operator_snapshot,
    format_mcp_server_list,
    format_mcp_status,
)
from mini_agent.memory.command_service import MemoryCommandService
from mini_agent.memory.runtime_backend import WorkspaceRuntimeMemoryBackend
from mini_agent.runtime.handlers.session_access_handler import RuntimeSessionAccessHandler
from mini_agent.runtime.handlers.session_admin_handler import RuntimeSessionAdminHandler
from mini_agent.runtime.handlers.session_agent_control_handler import RuntimeSessionAgentControlHandler
from mini_agent.runtime.handlers.session_agent_runtime_handler import (
    BuildAgentFn,
    BuildSelectedAgentFn,
    RuntimeSessionAgentRuntimeHandler,
    RuntimeSessionAgentSupport,
)
from mini_agent.runtime.handlers.session_catalog_handler import RuntimeSessionCatalogHandler
from mini_agent.runtime.handlers.session_command_coordinator import RuntimeSessionCommandCoordinator
from mini_agent.runtime.handlers.session_context_policy_handler import RuntimeSessionContextPolicyHandler
from mini_agent.runtime.handlers.session_control_command_handler import RuntimeSessionControlCommandHandler
from mini_agent.runtime.handlers.session_creation_handler import RuntimeSessionCreationHandler
from mini_agent.runtime.handlers.session_mcp_control_handler import RuntimeSessionMcpControlHandler
from mini_agent.runtime.handlers.session_memory_command_handler import RuntimeSessionMemoryCommandHandler
from mini_agent.runtime.handlers.session_memory_handler import RuntimeSessionMemoryHandler
from mini_agent.runtime.handlers.session_registry_handler import RuntimeSessionRegistryHandler
from mini_agent.runtime.handlers.session_run_control_handler import RuntimeSessionRunControlHandler
from mini_agent.runtime.handlers.session_runtime_policy_handler import RuntimeSessionRuntimePolicyHandler
from mini_agent.runtime.handlers.session_skill_handler import RuntimeSessionSkillHandler
from mini_agent.runtime.live_control.run_control_store import RuntimeSessionRunControlStore
from mini_agent.runtime.live_control.session_interrupt_handler import RuntimeSessionInterruptHandler
from mini_agent.runtime.live_control.session_pending_approval_state_handler import (
    RuntimeSessionPendingApprovalStateHandler,
)
from mini_agent.runtime.live_control.session_recovery_reset_handler import (
    RuntimeSessionRecoveryResetHandler,
)
from mini_agent.runtime.live_control.session_transcript_state_handler import (
    RuntimeSessionTranscriptStateHandler,
)
from mini_agent.runtime.live_control.session_turn_scope_handler import (
    RuntimeSessionTurnScopeHandler,
)
from mini_agent.runtime.orchestration.session_hydration_coordinator import (
    RuntimeSessionHydrationBuilder,
    RuntimeSessionHydrationCoordinator,
)
from mini_agent.runtime.orchestration.session_restore_handler import (
    RuntimeSessionRestoreHandler,
    RuntimeSessionStateHydrator,
)
from mini_agent.runtime.orchestration.session_runtime_lifecycle_handler import (
    RuntimeSessionLifecycleHandler,
)
from mini_agent.runtime.orchestration.session_runtime_policy_coordinator import (
    MainAgentRuntimePolicy,
    RuntimeSessionPolicyCoordinator,
    SessionRuntimePolicyService,
)
from mini_agent.runtime.read_models.run_projection_builder import RuntimeSessionRunProjectionBuilder
from mini_agent.runtime.read_models.session_diagnostics import RuntimeSessionDiagnosticsService
from mini_agent.runtime.read_models.session_model_identity_codec import RuntimeSessionModelIdentityCodec
from mini_agent.runtime.read_models.session_payload_codec import RuntimeSessionPayloadCodec
from mini_agent.runtime.read_models.session_read_model_builder import RuntimeSessionReadModelBuilder
from mini_agent.runtime.read_models.session_snapshot_builder import RuntimeSessionSnapshotBuilder
from mini_agent.runtime.support.interaction_surface import normalize_channel_type, normalize_surface_label
from mini_agent.runtime.support.sandbox_state import collect_sandbox_diagnostics
from mini_agent.runtime.support.tooling import reconfigure_agent_runtime_policy
from mini_agent.runtime.support.workspace_path_utils import (
    same_workspace_path,
    workspace_path_key,
)
from mini_agent.session.lineage import RuntimeSessionLineageRegistry
from mini_agent.session.persistence import (
    MainAgentRuntimePersistence,
    RuntimeSessionPersistenceLoader,
    RuntimeSessionPersistenceRecordBuilder,
)
from mini_agent.tools.mcp_loader import cleanup_mcp_connections

if TYPE_CHECKING:
    from mini_agent.session.store_records import MainAgentSessionState


_RUNTIME_SESSION_KIND = "main-agent-runtime"


class _MainAgentRuntimeAssemblySupport(Protocol):
    _ttl_seconds: int
    _build_agent: BuildAgentFn
    _build_agent_with_selection: BuildSelectedAgentFn | None
    _policy: MainAgentRuntimePolicy
    _load_runtime_config: Callable[[], Any]
    _resolve_agent_model_identity: Callable[[], tuple[str, str, str] | None] | None
    _sessions: dict[str, "MainAgentSessionState"]

    _model_identity_codec: Any
    _payload_codec: Any
    _lifecycle_manager: Any
    _session_lineage: Any
    _session_lineage_registry: Any
    _runtime_policy_coordinator: Any
    _session_lifecycle: Any
    _session_persistence_records: Any
    _session_persistence_loader: Any
    _persistence: Any
    _session_agent_support: Any
    _session_diagnostics: Any
    _session_run_control: Any
    _run_projection_builder: Any
    _runtime_task_memory_backend: Any
    _session_runtime_state_hydrator: Any
    _session_transcript_state: Any
    _session_turn_scope: Any
    _session_pending_approval_state: Any
    _session_recovery_reset: Any
    _session_memory_commands: Any
    _session_access: Any
    _session_hydration_builder: Any
    _session_read_models: Any
    _session_snapshot_builder: Any
    _session_catalog: Any
    _session_creation: Any
    _session_hydration: Any
    _session_agent_runtime: Any
    _session_runtime_policy: Any
    _session_agent_control: Any
    _session_mcp_control: Any
    _session_commands: Any
    _session_admin: Any
    _session_interrupt: Any
    _session_context_commands: Any
    _session_skill_commands: Any
    _session_restore: Any
    _session_registry: Any
    _session_control_handler: Any
    _session_context_policy_handler: Any
    _session_memory_handler: Any
    _session_run_operator: Any
    _session_runtime_policy_handler: Any
    _session_skill_handler: Any

    def _resolve_default_session_workspace(self, workspace_dir: Path) -> Path: ...

    @staticmethod
    def _billable_session_count(sessions: Iterable["MainAgentSessionState"]) -> int: ...

    async def ensure_agent_model_binding_for_turn(
        self,
        session: "MainAgentSessionState",
    ) -> bool: ...

    async def queue_workspace_skill_reload(
        self,
        session: "MainAgentSessionState",
        workspace_dir: Path | None = None,
    ) -> None: ...

    async def apply_pending_session_skill_reload(
        self,
        session: "MainAgentSessionState",
    ) -> bool: ...


class MainAgentRuntimeAssemblyMixin:
    """Extracted owner for runtime initialization and service assembly."""

    def _initialize_runtime_core(
        self: _MainAgentRuntimeAssemblySupport,
        storage_dir: Path | None,
    ) -> None:
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
            active_pending_approvals=lambda session: self._session_run_control.pending_approval_payloads(session),
            active_run_control_state=lambda session: self._session_run_control.serialize_run_control_state(
                self._session_run_control.current_control_state(session)
            ),
            active_approval_wait=lambda session: self._session_run_control.serialize_approval_wait(
                self._session_run_control.current_approval_wait(session)
            ),
            active_kernel_state=lambda session: self._session_run_control.build_kernel_state_payload(session),
            selected_model_identity_for_session=self._model_identity_codec.selected_model_identity,
            pending_model_identity_for_session=self._model_identity_codec.pending_model_identity,
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

    def _initialize_runtime_support_services(self: _MainAgentRuntimeAssemblySupport) -> None:
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
        self._session_run_control = RuntimeSessionRunControlStore(
            selected_model_identity_for_session=self._model_identity_codec.selected_model_identity,
        )
        self._run_projection_builder = RuntimeSessionRunProjectionBuilder(
            run_control_store=self._session_run_control,
        )
        self._runtime_task_memory_backend = WorkspaceRuntimeMemoryBackend()
        self._session_runtime_state_hydrator = RuntimeSessionStateHydrator(
            agent_knowledge_base_enabled=self._session_agent_support.agent_knowledge_base_enabled,
            agent_last_prepared_context=self._session_agent_support.agent_last_prepared_context,
            agent_prepared_context_diagnostics=self._session_agent_support.agent_prepared_context_diagnostics,
            restore_session_runtime_task_memory=self._runtime_task_memory_backend.restore_session_payload,
            restore_workspace_shared_runtime_task_memory=self._runtime_task_memory_backend.restore_workspace_shared_payload,
            restore_workspace_runtime_snapshot=self._session_diagnostics.restore_workspace_runtime_snapshot_payload,
            build_memory_diagnostics_for_session=self._session_diagnostics.build_memory_diagnostics_for_session,
            build_sandbox_diagnostics_for_session=self._session_diagnostics.build_sandbox_diagnostics_for_session,
        )
        self._session_transcript_state = RuntimeSessionTranscriptStateHandler()
        self._session_turn_scope = RuntimeSessionTurnScopeHandler(
            run_control_store=self._session_run_control,
        )
        self._session_pending_approval_state = RuntimeSessionPendingApprovalStateHandler(
            run_control_store=self._session_run_control,
        )
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
            run_control_store=self._session_run_control,
        )
        self._session_turn_scope.transcript_state = self._session_transcript_state
        self._session_turn_scope.pending_approval_state = self._session_pending_approval_state
        self._session_turn_scope.recovery_reset = self._session_recovery_reset
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

    def _initialize_session_model_services(self: _MainAgentRuntimeAssemblySupport) -> None:
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
            build_workspace_runtime_snapshot_for_session=(
                self._session_diagnostics.build_workspace_runtime_snapshot_for_session
            ),
            build_workspace_runtime_snapshot_from_record=(
                self._session_diagnostics.build_workspace_runtime_snapshot_from_record
            ),
            session_token_usage=self._payload_codec.session_token_usage,
            session_token_limit=self._payload_codec.session_token_limit,
            record_token_usage=self._payload_codec.record_token_usage,
            record_token_limit=self._payload_codec.record_token_limit,
            transcript_entries_from_record=self._session_hydration_builder.transcript_entries_from_record,
            pending_approvals_from_raw=RuntimeSessionPendingApprovalStateHandler.pending_approvals_from_raw,
            active_pending_approvals_for_session=lambda session: self._session_run_control.pending_approval_payloads(
                session
            ),
            selected_model_identity_for_session=self._model_identity_codec.selected_model_identity,
            pending_model_identity_for_session=self._model_identity_codec.pending_model_identity,
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
            selected_model_identity_for_session=self._model_identity_codec.selected_model_identity,
            pending_model_identity_for_session=self._model_identity_codec.pending_model_identity,
            build_workspace_runtime_snapshot_for_session=(
                self._session_diagnostics.build_workspace_runtime_snapshot_for_session
            ),
            build_workspace_runtime_snapshot_from_record=(
                self._session_diagnostics.build_workspace_runtime_snapshot_from_record
            ),
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
            default_model_identity=self._resolve_agent_model_identity,
            bootstrap_session_lifecycle=lambda session_id, workspace_dir, now_utc: self._session_lifecycle.bootstrap_session(
                session_id,
                workspace_dir,
                now_utc=now_utc,
            ),
            agent_knowledge_base_enabled=self._session_agent_support.agent_knowledge_base_enabled,
            collect_sandbox_diagnostics=lambda agent: collect_sandbox_diagnostics(agent=agent),
            route_model_identity=self._model_identity_codec.route_model_identity,
        )

    def _initialize_session_runtime_services(self: _MainAgentRuntimeAssemblySupport) -> None:
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
            persist_hydrated_session=lambda session, agent_messages=None: self._session_registry.persist_session(
                session,
                agent_messages=agent_messages,
            ),
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
            append_transcript=self._session_transcript_state.append_transcript,
            persist_session=lambda session: self._session_registry.persist_session(session),
        )
        self._session_admin = RuntimeSessionAdminHandler(
            rename_session_mutation=self._session_catalog.rename_session,
            set_session_shared_mutation=self._session_catalog.set_session_shared,
            reset_runtime_state_mutation=self._session_recovery_reset.reset_runtime_state,
            bind_surface_mutation=self._session_transcript_state.bind_surface,
            reset_session_lifecycle_mutation=self._session_lifecycle.reset_session,
            build_session_summary=self._session_catalog.build_session_summary,
            persist_session=lambda session: self._session_registry.persist_session(session),
        )
        self._session_interrupt = RuntimeSessionInterruptHandler(
            normalize_surface=normalize_surface_label,
            run_control_store=self._session_run_control,
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

    def _initialize_session_boundary_services(self: _MainAgentRuntimeAssemblySupport) -> None:
        self._session_registry = RuntimeSessionRegistryHandler(
            session_access=self._session_access,
            session_creation=self._session_creation,
            session_catalog=self._session_catalog,
            enforce_workspace_entry=lambda active_sessions, workspace_dir: self._runtime_policy_coordinator.enforce_workspace_entry(
                active_sessions,
                workspace_dir,
                same_workspace=same_workspace_path,
            ),
            enforce_capacity=lambda: self._runtime_policy_coordinator.enforce_capacity(
                self._billable_session_count(self._sessions.values())
            ),
            raise_workspace_mismatch=self._runtime_policy_coordinator.raise_workspace_mismatch,
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
            build_snapshot_hydration_payload=self._session_hydration_builder.build_snapshot_hydration_payload,
            build_session_snapshot=self._session_snapshot_builder.build_session_snapshot,
            build_session_snapshot_from_record=self._session_snapshot_builder.build_session_snapshot_from_record,
            refresh_session_lifecycle=lambda session, now_utc: self._session_lifecycle.refresh_session(
                session,
                now_utc=now_utc,
                reset_runtime_state=lambda: self._session_recovery_reset.reset_runtime_state(
                    session,
                    clear_runtime_task_memory=True,
                ),
            ),
            register_session=self._session_lineage_registry.register_session,
            expired_session_ids=self._runtime_policy_coordinator.expired_session_ids,
            build_sandbox_diagnostics_for_session=self._session_diagnostics.build_sandbox_diagnostics_for_session,
            save_session=lambda session, agent_messages, sandbox_diagnostics: self._persistence.save_session(
                session,
                agent_messages=agent_messages,
                sandbox_diagnostics=sandbox_diagnostics,
            ),
            delete_session_record=self._persistence.delete_session,
            record_workspace_dir=self._session_catalog.record_workspace_dir,
            clear_session_runtime_task_memory=lambda workspace_dir, session_id: self._runtime_task_memory_backend.clear_session_namespace(
                workspace_dir=workspace_dir,
                session_id=session_id,
            ),
            remove_session_lineage=self._session_lineage_registry.remove_session,
        )
        self._session_control_handler = RuntimeSessionControlCommandHandler(
            session_commands=self._session_commands,
            session_agent_control=self._session_agent_control,
            session_mcp_control=self._session_mcp_control,
            session_agent_runtime=self._session_agent_runtime,
            selected_model_identity=self._model_identity_codec.selected_model_identity,
            cleanup_mcp_connections=lambda: cleanup_mcp_connections(),
        )
        self._session_context_policy_handler = RuntimeSessionContextPolicyHandler(
            normalize_surface=normalize_surface_label,
            normalize_context_policy_payload=self._payload_codec.normalize_context_policy_payload,
            session_commands=self._session_commands,
            session_context_commands=self._session_context_commands,
        )
        self._session_memory_handler = RuntimeSessionMemoryHandler(
            normalize_surface=normalize_surface_label,
            session_commands=self._session_commands,
            session_memory_commands=self._session_memory_commands,
            persist_session=lambda session: self._session_registry.persist_session(session),
        )
        self._session_run_operator = RuntimeSessionRunControlHandler(
            run_control_store=self._session_run_control,
            run_projection_builder=self._run_projection_builder,
            session_commands=self._session_commands,
            session_interrupt=self._session_interrupt,
            load_persisted_record=self._persistence.load_session_record,
            persist_session=lambda session: self._session_registry.persist_session(session),
        )
        self._session_runtime_policy_handler = RuntimeSessionRuntimePolicyHandler(
            normalize_surface=normalize_surface_label,
            normalize_sandbox_diagnostics_payload=self._payload_codec.normalize_sandbox_diagnostics_payload,
            session_commands=self._session_commands,
            session_runtime_policy=self._session_runtime_policy,
            session_agent_runtime=self._session_agent_runtime,
            session_transcript_state=self._session_transcript_state,
            active_pending_approvals=lambda session: self._session_run_control.pending_approval_payloads(session),
        )
        self._session_skill_handler = RuntimeSessionSkillHandler(
            normalize_surface=normalize_surface_label,
            session_commands=self._session_commands,
            session_skill_commands=self._session_skill_commands,
            session_agent_runtime=self._session_agent_runtime,
            load_runtime_config=self._load_runtime_config,
            selected_model_identity=self._model_identity_codec.selected_model_identity,
            queue_workspace_skill_reload=self.queue_workspace_skill_reload,
        )
        self._session_transcript_state.persist_session_fn = lambda session: self._session_registry.persist_session(session)
        self._session_turn_scope.restore_prepared_context_state_mutation = (
            self._session_runtime_state_hydrator.restore_agent_prepared_context_state
        )
        self._session_turn_scope.capture_prepared_context_state_mutation = (
            self._session_runtime_state_hydrator.capture_agent_prepared_context_state
        )
        self._session_turn_scope.ensure_agent_model_binding_for_turn_fn = self.ensure_agent_model_binding_for_turn
        self._session_turn_scope.apply_pending_session_skill_reload_fn = self.apply_pending_session_skill_reload
        self._session_turn_scope.persist_session_fn = lambda session: self._session_registry.persist_session(session)

    def _resolve_default_session_workspace(
        self: _MainAgentRuntimeAssemblySupport,
        workspace_dir: Path,
    ) -> Path:
        main_workspace = getattr(self._policy, "main_workspace_dir", None)
        if main_workspace is None:
            return workspace_dir
        return Path(main_workspace).resolve()

    @staticmethod
    def _billable_session_count(sessions: Iterable["MainAgentSessionState"]) -> int:
        count = 0
        for session in sessions:
            if bool(getattr(getattr(session, "projection", None), "is_default", False)):
                continue
            count += 1
        return count
