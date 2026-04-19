"""Physical owner for the runtime manager public API surface."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Iterable, Protocol, Sequence

from mini_agent.agent_core.engine import Agent
from mini_agent.agent_core.session.lineage import SessionLineageStore
from mini_agent.interfaces.agent import (
    MainAgentSessionApprovalResponse,
    MainAgentSessionContextResponse,
    MainAgentSessionControlResponse,
    MainAgentSessionDetail,
    MainAgentSessionMemoryResponse,
    MainAgentSessionMessage,
    MainAgentSessionMutationResponse,
    MainAgentSessionSkillResponse,
    MainAgentSessionSummary,
)
from mini_agent.interfaces.system import MainAgentRuntimeDiagnostics
from mini_agent.runtime.handlers.session_admin_handler import RuntimeSessionAdminHandler
from mini_agent.runtime.handlers.session_agent_runtime_handler import (
    RuntimeSessionAgentRuntimeHandler,
    RuntimeSessionAgentSupport,
)
from mini_agent.runtime.handlers.session_context_policy_handler import RuntimeSessionContextPolicyHandler
from mini_agent.runtime.handlers.session_control_command_handler import RuntimeSessionControlCommandHandler
from mini_agent.runtime.handlers.session_memory_handler import RuntimeSessionMemoryHandler
from mini_agent.runtime.handlers.session_registry_handler import (
    RuntimeSessionRegistryHandler,
    RuntimeSessionSnapshotImportCommand,
)
from mini_agent.runtime.handlers.session_run_control_handler import RuntimeSessionRunControlHandler
from mini_agent.runtime.handlers.session_runtime_policy_handler import RuntimeSessionRuntimePolicyHandler
from mini_agent.runtime.handlers.session_skill_handler import RuntimeSessionSkillHandler
from mini_agent.runtime.live_control.run_control_store import RuntimeSessionRunControlStore
from mini_agent.runtime.live_control.session_transcript_state_handler import (
    RuntimeSessionTranscriptStateHandler,
)
from mini_agent.runtime.live_control.session_turn_scope_handler import (
    RuntimeSessionTurnScopeHandler,
)
from mini_agent.runtime.orchestration.session_runtime_policy_coordinator import (
    MainAgentRuntimeMode,
    MainAgentRuntimePolicy,
    RuntimeSessionPolicyCoordinator,
)
from mini_agent.runtime.read_models.session_model_identity_codec import RuntimeSessionModelIdentityCodec
from mini_agent.runtime.read_models.session_snapshot_builder import RuntimeSessionSnapshot
from mini_agent.runtime.support.workspace_path_utils import same_workspace_path
from mini_agent.session.lineage import RuntimeSessionLineageRegistry
from mini_agent.session.persistence import MainAgentRuntimePersistence

if TYPE_CHECKING:
    from mini_agent.session.store_records import MainAgentSessionState


class _MainAgentRuntimePublicApiSupport(Protocol):
    _store_lock: asyncio.Lock
    _sessions: dict[str, "MainAgentSessionState"]
    _policy: MainAgentRuntimePolicy
    _resolve_agent_model_identity: Callable[[], tuple[str, str, str] | None] | None
    _model_identity_codec: RuntimeSessionModelIdentityCodec
    _session_lineage: SessionLineageStore
    _session_lineage_registry: RuntimeSessionLineageRegistry
    _runtime_policy_coordinator: RuntimeSessionPolicyCoordinator
    _session_registry: RuntimeSessionRegistryHandler
    _session_admin: RuntimeSessionAdminHandler
    _session_run_control: RuntimeSessionRunControlStore
    _session_run_operator: RuntimeSessionRunControlHandler
    _session_control_handler: RuntimeSessionControlCommandHandler
    _session_context_policy_handler: RuntimeSessionContextPolicyHandler
    _session_memory_handler: RuntimeSessionMemoryHandler
    _session_skill_handler: RuntimeSessionSkillHandler
    _session_runtime_policy_handler: RuntimeSessionRuntimePolicyHandler
    _session_agent_runtime: RuntimeSessionAgentRuntimeHandler
    _session_agent_support: RuntimeSessionAgentSupport
    _session_turn_scope: RuntimeSessionTurnScopeHandler
    _session_transcript_state: RuntimeSessionTranscriptStateHandler
    _persistence: MainAgentRuntimePersistence

    @staticmethod
    def _billable_session_count(sessions: Iterable["MainAgentSessionState"]) -> int: ...


class MainAgentRuntimePublicApiMixin:
    """Extracted public API owner for runtime/session commands and read seams."""

    async def clear(self: _MainAgentRuntimePublicApiSupport) -> None:
        async with self._store_lock:
            self._sessions.clear()
            self._session_lineage = SessionLineageStore()
            self._session_lineage_registry.replace_store(self._session_lineage)
            self._runtime_policy_coordinator.clear_counters()
            self._session_run_control.clear()

    async def build_ephemeral_agent(
        self: _MainAgentRuntimePublicApiSupport,
        workspace_dir: Path,
    ) -> Agent:
        """Build an isolated agent instance without attaching a managed session."""

        self._runtime_policy_coordinator.enforce_main_workspace(
            workspace_dir,
            same_workspace=same_workspace_path,
        )
        identity = self._resolve_agent_model_identity() if callable(self._resolve_agent_model_identity) else None
        return await self._session_agent_support.build_agent_for_identity(workspace_dir, identity)

    @property
    def turn_scope_handler(self: _MainAgentRuntimePublicApiSupport) -> RuntimeSessionTurnScopeHandler:
        return self._session_turn_scope

    def validate_workspace(self: _MainAgentRuntimePublicApiSupport, workspace_dir: Path) -> None:
        self._runtime_policy_coordinator.enforce_main_workspace(
            workspace_dir,
            same_workspace=same_workspace_path,
        )

    async def get_or_create_session(
        self: _MainAgentRuntimePublicApiSupport,
        session_id: str | None,
        workspace_dir: Path,
        *,
        surface: str | None = None,
        channel_type: str | None = None,
        conversation_id: str | None = None,
        sender_id: str | None = None,
        session_title_hint: str | None = None,
    ) -> "MainAgentSessionState":
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
        self: _MainAgentRuntimePublicApiSupport,
        session: "MainAgentSessionState",
        *,
        surface: str | None = None,
        channel_type: str | None = None,
        conversation_id: str | None = None,
        sender_id: str | None = None,
    ):
        return await self._session_runtime_policy_handler.ensure_runtime_policy_ready_for_turn(
            session,
            surface=surface,
            channel_type=channel_type,
            conversation_id=conversation_id,
            sender_id=sender_id,
        )

    async def ensure_agent_model_binding_for_turn(
        self: _MainAgentRuntimePublicApiSupport,
        session: "MainAgentSessionState",
    ) -> bool:
        target_identity = self._resolve_agent_model_identity() if callable(self._resolve_agent_model_identity) else None
        current_identity = self._model_identity_codec.selected_model_identity(session)
        pending_identity = self._model_identity_codec.pending_model_identity(session)
        cleared_pending = pending_identity is not None

        if cleared_pending:
            self._model_identity_codec.set_pending_model_identity(session, None)

        if target_identity is None:
            if cleared_pending:
                session.touch()
                self._session_registry.persist_session(session)
            return cleared_pending

        if current_identity == target_identity:
            if cleared_pending:
                session.touch()
                self._session_registry.persist_session(session)
            return cleared_pending

        await self._session_agent_runtime.rebuild_agent_with_identity(session, target_identity)
        session.touch()
        self._session_registry.persist_session(session)
        return True

    async def ensure_default_session(
        self: _MainAgentRuntimePublicApiSupport,
        workspace_dir: Path,
        *,
        surface: str | None = None,
        channel_type: str | None = None,
        conversation_id: str | None = None,
        sender_id: str | None = None,
    ) -> "MainAgentSessionState":
        return await self.get_or_create_session(
            None,
            workspace_dir,
            surface=surface,
            channel_type=channel_type,
            conversation_id=conversation_id,
            sender_id=sender_id,
        )

    async def create_session(
        self: _MainAgentRuntimePublicApiSupport,
        *,
        workspace_dir: Path,
        title: str | None = None,
        surface: str | None = None,
        shared: bool = False,
    ) -> "MainAgentSessionState":
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
        self: _MainAgentRuntimePublicApiSupport,
        *,
        parent_session_id: str,
        title: str | None = None,
        surface: str | None = None,
        channel_type: str | None = None,
        conversation_id: str | None = None,
        sender_id: str | None = None,
        reason: str = "derived",
        metadata: dict[str, Any] | None = None,
    ) -> "MainAgentSessionState":
        async with self._store_lock:
            parent = await self._session_registry.require_managed_session(
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
        self: _MainAgentRuntimePublicApiSupport,
        command: RuntimeSessionSnapshotImportCommand,
    ) -> "MainAgentSessionState":
        async with self._store_lock:
            return await self._session_registry.import_session_snapshot(
                self._sessions,
                now_utc=datetime.now(timezone.utc),
                command=command,
            )

    async def export_session_snapshot(
        self: _MainAgentRuntimePublicApiSupport,
        session_id: str,
    ) -> RuntimeSessionSnapshot:
        async with self._store_lock:
            return self._session_registry.export_session_snapshot(
                self._sessions,
                session_id=session_id,
            )

    async def get_runtime_diagnostics(
        self: _MainAgentRuntimePublicApiSupport,
    ) -> MainAgentRuntimeDiagnostics:
        """Return a lock-consistent runtime diagnostics snapshot."""

        async with self._store_lock:
            active_sessions = self._billable_session_count(self._sessions.values())
            payload = self._runtime_policy_coordinator.diagnostics_payload(active_sessions=active_sessions)
            return MainAgentRuntimeDiagnostics(
                **payload,
            )

    async def list_sessions(
        self: _MainAgentRuntimePublicApiSupport,
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

    async def rename_session(
        self: _MainAgentRuntimePublicApiSupport,
        session_id: str,
        *,
        title: str,
    ) -> MainAgentSessionSummary:
        async with self._store_lock:
            session = await self._session_registry.require_managed_session(self._sessions, session_id)
        return await self._session_admin.rename_session(session, title=title)

    async def set_session_shared(
        self: _MainAgentRuntimePublicApiSupport,
        session_id: str,
        *,
        shared: bool,
    ) -> MainAgentSessionSummary:
        async with self._store_lock:
            session = await self._session_registry.require_managed_session(self._sessions, session_id)
        return await self._session_admin.set_session_shared(session, shared=shared)

    async def get_session_detail(
        self: _MainAgentRuntimePublicApiSupport,
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
        self: _MainAgentRuntimePublicApiSupport,
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

    async def resolve_run_id_for_session(
        self: _MainAgentRuntimePublicApiSupport,
        session_id: str,
    ) -> str | None:
        async with self._store_lock:
            return self._session_run_operator.resolve_run_id_for_session(
                session_id,
                active_sessions=self._sessions,
            )

    async def get_run(
        self: _MainAgentRuntimePublicApiSupport,
        run_id: str,
    ) -> dict[str, Any]:
        async with self._store_lock:
            return self._session_run_operator.get_run(
                run_id,
                active_sessions=self._sessions,
            )

    async def interrupt_run(
        self: _MainAgentRuntimePublicApiSupport,
        run_id: str,
        *,
        reason: str | None = None,
        source: str | None = None,
    ) -> dict[str, Any]:
        async with self._store_lock:
            return self._session_run_operator.interrupt_run(
                run_id,
                active_sessions=self._sessions,
                reason=reason,
                source=source,
            )

    async def resume_run(
        self: _MainAgentRuntimePublicApiSupport,
        run_id: str,
        *,
        resume_token: str | None = None,
        source: str | None = None,
    ) -> Any:
        async with self._store_lock:
            return self._session_run_operator.resume_run(
                run_id,
                active_sessions=self._sessions,
                resume_token=resume_token,
                source=source,
            )

    async def cancel_run(
        self: _MainAgentRuntimePublicApiSupport,
        run_id: str,
        *,
        reason: str | None = None,
        source: str | None = None,
    ) -> MainAgentSessionMutationResponse:
        async with self._store_lock:
            return self._session_run_operator.cancel_run(
                run_id,
                active_sessions=self._sessions,
                reason=reason,
                source=source,
            )

    async def resolve_approval_wait(
        self: _MainAgentRuntimePublicApiSupport,
        run_id: str,
        *,
        approved: bool,
        token: str | None = None,
        source: str | None = None,
        reason: str | None = None,
    ) -> MainAgentSessionApprovalResponse:
        async with self._store_lock:
            return self._session_run_operator.resolve_approval_wait(
                run_id,
                active_sessions=self._sessions,
                approved=approved,
                token=token,
                source=source,
                reason=reason,
            )

    async def delete_session(self: _MainAgentRuntimePublicApiSupport, session_id: str) -> None:
        async with self._store_lock:
            self._session_registry.delete_session(self._sessions, session_id)
            self._session_run_control.drop_session(session_id)

    async def reset_session(self: _MainAgentRuntimePublicApiSupport, session_id: str) -> None:
        async with self._store_lock:
            session = await self._session_registry.require_managed_session(self._sessions, session_id)
        await self._session_admin.reset_session(session)

    async def cancel_session_turn(
        self: _MainAgentRuntimePublicApiSupport,
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
            return self._session_run_operator.cancel_turn(
                session_id=session_id,
                active_session=self._sessions.get(session_id),
                persisted_exists=persisted_exists,
                reason=reason,
                surface=surface,
                channel_type=channel_type,
                conversation_id=conversation_id,
                sender_id=sender_id,
            )

    async def set_active_surface(
        self: _MainAgentRuntimePublicApiSupport,
        session_id: str,
        *,
        surface: str,
    ) -> MainAgentSessionSummary:
        async with self._store_lock:
            session = await self._session_registry.require_managed_session(self._sessions, session_id)
        return await self._session_admin.set_active_surface(session, surface=surface)

    async def control_session_context(
        self: _MainAgentRuntimePublicApiSupport,
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
            session = await self._session_registry.require_managed_session(self._sessions, session_id)

        return await self._session_control_handler.control_session(
            session,
            action=action,
            reason=reason,
            surface=surface,
            channel_type=channel_type,
            conversation_id=conversation_id,
            sender_id=sender_id,
        )

    async def update_session_context_policy(
        self: _MainAgentRuntimePublicApiSupport,
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
            session = await self._session_registry.require_managed_session(self._sessions, session_id)

        return await self._session_context_policy_handler.update_context_policy(
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
        self: _MainAgentRuntimePublicApiSupport,
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
            session = await self._session_registry.require_managed_session(self._sessions, session_id)

        return await self._session_memory_handler.manage_memory(
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
        self: _MainAgentRuntimePublicApiSupport,
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
            session = await self._session_registry.require_managed_session(self._sessions, session_id)
        return await self._session_skill_handler.manage_skills(
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

    async def update_session_runtime_policy(
        self: _MainAgentRuntimePublicApiSupport,
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
            session = await self._session_registry.require_managed_session(self._sessions, session_id)
        return await self._session_runtime_policy_handler.update_runtime_policy(
            session,
            approval_profile=approval_profile,
            access_level=access_level,
            surface=surface,
            channel_type=channel_type,
            conversation_id=conversation_id,
            sender_id=sender_id,
        )

    async def queue_workspace_skill_reload(
        self: _MainAgentRuntimePublicApiSupport,
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
                self._session_registry.persist_session(candidate)
            return result.queued_session_ids

    async def apply_pending_session_skill_reload(
        self: _MainAgentRuntimePublicApiSupport,
        session: "MainAgentSessionState",
    ) -> bool:
        applied = await self._session_agent_runtime.apply_pending_skill_reload(session)
        if applied:
            session.touch()
            self._session_registry.persist_session(session)
        return applied

    def mark_turn_started(
        self: _MainAgentRuntimePublicApiSupport,
        session: "MainAgentSessionState",
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
        self: _MainAgentRuntimePublicApiSupport,
        session: "MainAgentSessionState",
        *,
        now_utc: datetime | None = None,
    ) -> None:
        self._session_turn_scope.mark_turn_finished(
            session,
            now_utc=now_utc,
        )

    def bind_session_surface(
        self: _MainAgentRuntimePublicApiSupport,
        session: "MainAgentSessionState",
        *,
        surface: str | None,
        channel_type: str | None = None,
        conversation_id: str | None = None,
        sender_id: str | None = None,
        now_utc: datetime | None = None,
    ) -> None:
        self._session_transcript_state.bind_surface(
            session,
            surface=surface,
            channel_type=channel_type,
            conversation_id=conversation_id,
            sender_id=sender_id,
            now_utc=now_utc,
        )

    def record_message(
        self: _MainAgentRuntimePublicApiSupport,
        session: "MainAgentSessionState",
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
        self._session_transcript_state.record_message(
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

    def record_activity(
        self: _MainAgentRuntimePublicApiSupport,
        session: "MainAgentSessionState",
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
        return self._session_transcript_state.record_activity(
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
        self: _MainAgentRuntimePublicApiSupport,
        session: "MainAgentSessionState",
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
        self: _MainAgentRuntimePublicApiSupport,
        session: "MainAgentSessionState",
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
        self: _MainAgentRuntimePublicApiSupport,
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
            return self._session_run_operator.resolve_pending_approval(
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
        self: _MainAgentRuntimePublicApiSupport,
        session: "MainAgentSessionState",
    ) -> dict[str, Any] | None:
        return self._session_turn_scope.build_recovery_turn_context(session)

    def clear_recovery_context(
        self: _MainAgentRuntimePublicApiSupport,
        session: "MainAgentSessionState",
        *,
        now_utc: datetime | None = None,
    ) -> None:
        self._session_turn_scope.clear_recovery_context(
            session,
            now_utc=now_utc,
        )


__all__ = ["MainAgentRuntimePublicApiMixin"]
