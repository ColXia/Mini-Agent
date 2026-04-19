"""Session registry / persistence orchestration extracted from the runtime manager."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Awaitable, Callable, MutableMapping, Sequence
from uuid import uuid4

from fastapi import HTTPException

from mini_agent.runtime.handlers.session_access_handler import (
    RuntimeSessionAccessCommand,
    RuntimeSessionAccessHandler,
    RuntimeSessionAccessPlan,
)
from mini_agent.runtime.handlers.session_creation_handler import (
    RuntimeSessionCreationCommand,
    RuntimeSessionCreationHandler,
)
from mini_agent.session.bindings import DEFAULT_SESSION_TITLE

if TYPE_CHECKING:
    from mini_agent.interfaces.agent import (
        MainAgentSessionDetail,
        MainAgentSessionMessage,
        MainAgentSessionSummary,
    )
    from mini_agent.runtime.handlers.session_catalog_handler import RuntimeSessionCatalogHandler
    from mini_agent.runtime.orchestration.session_hydration_coordinator import RuntimeSessionHydrationPayload
    from mini_agent.runtime.read_models.session_snapshot_builder import RuntimeSessionSnapshot
    from mini_agent.session.store_records import MainAgentSessionState


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
class RuntimeSessionRegistryHandler:
    session_access: RuntimeSessionAccessHandler
    session_creation: RuntimeSessionCreationHandler
    session_catalog: "RuntimeSessionCatalogHandler"
    enforce_workspace_entry: Callable[[Sequence["MainAgentSessionState"], Path], None]
    enforce_capacity: Callable[..., None]
    raise_workspace_mismatch: Callable[[], None]
    load_persisted_record: Callable[[str], dict[str, Any] | None]
    list_persisted_records: Callable[[], list[dict[str, Any]]]
    restore_persisted_session: Callable[[dict[str, Any], datetime], Awaitable["MainAgentSessionState"]]
    hydrate_session: Callable[[RuntimeSessionHydrationPayload, datetime, bool], Awaitable["MainAgentSessionState"]]
    build_derived_hydration_payload: Callable[..., RuntimeSessionHydrationPayload]
    build_snapshot_hydration_payload: Callable[..., RuntimeSessionHydrationPayload]
    build_session_snapshot: Callable[["MainAgentSessionState"], "RuntimeSessionSnapshot"]
    build_session_snapshot_from_record: Callable[[dict[str, Any]], "RuntimeSessionSnapshot"]
    refresh_session_lifecycle: Callable[["MainAgentSessionState", datetime], bool]
    register_session: Callable[["MainAgentSessionState"], None]
    expired_session_ids: Callable[..., list[str]]
    build_sandbox_diagnostics_for_session: Callable[["MainAgentSessionState"], dict[str, Any]]
    save_session: Callable[["MainAgentSessionState", Sequence[Any] | None, dict[str, Any]], None]
    delete_session_record: Callable[[str], bool]
    record_workspace_dir: Callable[[dict[str, Any]], Path | None]
    clear_session_runtime_task_memory: Callable[[Path, str], None]
    remove_session_lineage: Callable[[str], None]

    async def get_or_create_session(
        self,
        sessions: MutableMapping[str, "MainAgentSessionState"],
        *,
        now_utc: datetime,
        team_mode: bool,
        session_id: str | None,
        workspace_dir: Path,
        surface: str | None = None,
        channel_type: str | None = None,
        conversation_id: str | None = None,
        sender_id: str | None = None,
        session_title_hint: str | None = None,
    ) -> "MainAgentSessionState":
        command = RuntimeSessionAccessCommand(
            session_id=session_id,
            workspace_dir=workspace_dir,
            surface=surface,
            channel_type=channel_type,
            conversation_id=conversation_id,
            sender_id=sender_id,
            session_title_hint=session_title_hint,
        )
        plan = self.session_access.build_plan(
            command,
            now_utc=now_utc,
            team_mode=team_mode,
            prepare_environment=lambda target_workspace, target_now: self._prepare_workspace_entry(
                sessions,
                workspace_dir=target_workspace,
                now_utc=target_now,
                enforce_capacity=False,
            ),
            load_active_session=lambda candidate: sessions.get(candidate),
            find_latest_active_session=lambda workspace: self.session_catalog.find_latest_active_session(
                workspace,
                sessions.values(),
            ),
            load_persisted_record=self.load_persisted_record,
            find_latest_persisted_record=lambda workspace: self.session_catalog.find_latest_persisted_record(
                workspace,
                self.list_persisted_records(),
            ),
            raise_workspace_mismatch=self.raise_workspace_mismatch,
            enforce_capacity=lambda: self._enforce_capacity(sessions),
            allocate_session_id=lambda: self.allocate_session_id(sessions),
        )
        return await self._execute_access_plan(
            sessions,
            plan=plan,
            now_utc=now_utc,
        )

    async def create_session(
        self,
        sessions: MutableMapping[str, "MainAgentSessionState"],
        *,
        now_utc: datetime,
        workspace_dir: Path,
        title: str | None = None,
        surface: str | None = None,
        shared: bool = False,
    ) -> "MainAgentSessionState":
        self._prepare_workspace_entry(
            sessions,
            workspace_dir=workspace_dir,
            now_utc=now_utc,
            enforce_capacity=True,
        )
        session_id = self.allocate_session_id(sessions)
        session = await self.session_creation.create(
            RuntimeSessionCreationCommand(
                session_id=session_id,
                workspace_dir=workspace_dir,
                title=title,
                default_title="Session",
                surface=surface,
                surface_provided=surface is not None,
                default_surface="tui",
                shared=bool(shared),
            ),
            now_utc=now_utc,
        )
        sessions[session_id] = session
        self.register_session(session)
        self.persist_session(session)
        return session

    async def create_derived_session(
        self,
        sessions: MutableMapping[str, "MainAgentSessionState"],
        *,
        now_utc: datetime,
        parent: "MainAgentSessionState",
        title: str | None = None,
        surface: str | None = None,
        channel_type: str | None = None,
        conversation_id: str | None = None,
        sender_id: str | None = None,
        reason: str = "derived",
        metadata: dict[str, Any] | None = None,
    ) -> "MainAgentSessionState":
        session_id = self.allocate_session_id(sessions)
        normalized_title = self.session_catalog.allocate_session_title(
            _safe_text(title) or "Task",
            workspace_dir=parent.workspace_dir,
            active_sessions=sessions.values(),
            persisted_records=self.list_persisted_records(),
        )
        payload = self.build_derived_hydration_payload(
            parent,
            session_id=session_id,
            now_utc=now_utc,
            title=normalized_title,
            surface=surface,
            channel_type=channel_type,
            conversation_id=conversation_id,
            sender_id=sender_id,
            reason=reason,
            metadata=metadata,
        )
        return await self.hydrate_session(payload, now_utc, True)

    async def import_session_snapshot(
        self,
        sessions: MutableMapping[str, "MainAgentSessionState"],
        *,
        now_utc: datetime,
        command: RuntimeSessionSnapshotImportCommand,
    ) -> "MainAgentSessionState":
        plan = self._prepare_snapshot_import(
            sessions,
            command=command,
            now_utc=now_utc,
        )
        return await self.hydrate_session(plan.payload, now_utc, True)

    def export_session_snapshot(
        self,
        sessions: MutableMapping[str, "MainAgentSessionState"],
        *,
        session_id: str,
    ) -> "RuntimeSessionSnapshot":
        session = sessions.get(session_id)
        record = None if session is not None else self.load_persisted_record(session_id)
        if session is not None:
            return self.build_session_snapshot(session)
        if record is not None:
            return self.build_session_snapshot_from_record(record)
        raise HTTPException(status_code=404, detail="Session not found.")

    def list_sessions(
        self,
        sessions: MutableMapping[str, "MainAgentSessionState"],
        *,
        workspace_dir: Path | None = None,
        shared_only: bool = False,
    ) -> list["MainAgentSessionSummary"]:
        return self.session_catalog.list_sessions(
            active_sessions=sessions.values(),
            persisted_records=self.list_persisted_records(),
            workspace_dir=workspace_dir,
            shared_only=shared_only,
        )

    def get_session_detail(
        self,
        sessions: MutableMapping[str, "MainAgentSessionState"],
        *,
        session_id: str,
        recent_limit: int,
    ) -> "MainAgentSessionDetail":
        return self.session_catalog.get_session_detail(
            session_id,
            active_session=sessions.get(session_id),
            persisted_record=self.load_persisted_record(session_id),
            recent_limit=recent_limit,
        )

    def get_recent_messages(
        self,
        sessions: MutableMapping[str, "MainAgentSessionState"],
        *,
        session_id: str,
        limit: int,
    ) -> list["MainAgentSessionMessage"]:
        return self.session_catalog.get_recent_messages(
            session_id,
            active_session=sessions.get(session_id),
            persisted_record=self.load_persisted_record(session_id),
            limit=limit,
        )

    def drop_expired_sessions(
        self,
        sessions: MutableMapping[str, "MainAgentSessionState"],
        *,
        now_utc: datetime | None = None,
    ) -> None:
        expired_ids = self.expired_session_ids(sessions, now_utc=now_utc)
        for session_id in expired_ids:
            sessions.pop(session_id, None)

    def persist_session(
        self,
        session: "MainAgentSessionState",
        *,
        agent_messages: Sequence[Any] | None = None,
    ) -> None:
        try:
            sandbox_diagnostics = self.build_sandbox_diagnostics_for_session(session)
            self.save_session(session, agent_messages, sandbox_diagnostics)
        except Exception:
            return

    def allocate_session_id(
        self,
        sessions: MutableMapping[str, "MainAgentSessionState"],
    ) -> str:
        while True:
            candidate = uuid4().hex
            if candidate in sessions:
                continue
            if self.load_persisted_record(candidate) is not None:
                continue
            return candidate

    async def load_managed_session(
        self,
        sessions: MutableMapping[str, "MainAgentSessionState"],
        session_id: str,
        *,
        now_utc: datetime | None = None,
    ) -> "MainAgentSessionState | None":
        existing = sessions.get(session_id)
        if existing is not None:
            return existing
        record = self.load_persisted_record(session_id)
        if record is None:
            return None
        return await self.restore_persisted_session(record, now_utc)

    async def require_managed_session(
        self,
        sessions: MutableMapping[str, "MainAgentSessionState"],
        session_id: str,
        *,
        now_utc: datetime | None = None,
    ) -> "MainAgentSessionState":
        session = await self.load_managed_session(sessions, session_id, now_utc=now_utc)
        if session is None:
            raise HTTPException(status_code=404, detail="Session not found.")
        return session

    def delete_session(
        self,
        sessions: MutableMapping[str, "MainAgentSessionState"],
        session_id: str,
    ) -> None:
        found = False
        workspace_dir: Path | None = None
        if session_id in sessions:
            existing = sessions.pop(session_id, None)
            if existing is not None:
                workspace_dir = existing.workspace_dir
            found = True
        if workspace_dir is None:
            record = self.load_persisted_record(session_id)
            if isinstance(record, dict):
                workspace_dir = self.record_workspace_dir(record)
        if workspace_dir is not None:
            self.clear_session_runtime_task_memory(workspace_dir, session_id)
        if self.delete_session_record(session_id):
            found = True
        self.remove_session_lineage(session_id)
        if not found:
            raise HTTPException(status_code=404, detail="Session not found.")

    async def _execute_access_plan(
        self,
        sessions: MutableMapping[str, "MainAgentSessionState"],
        *,
        plan: RuntimeSessionAccessPlan,
        now_utc: datetime,
    ) -> "MainAgentSessionState":
        if plan.action == "reuse_active":
            session = plan.active_session
            if session is None:
                raise HTTPException(status_code=500, detail="Session access plan missing active session.")
            self.refresh_session_lifecycle(session, now_utc)
            session.touch(now_utc=now_utc)
            self.persist_session(session)
            return session

        if plan.action == "restore_persisted":
            if plan.persisted_record is None:
                raise HTTPException(status_code=500, detail="Session access plan missing persisted record.")
            session = await self.restore_persisted_session(plan.persisted_record, now_utc)
            if plan.apply_title_hint_if_missing and plan.normalized_title_hint and not _safe_text(session.projection.title):
                session.projection.title = self.session_catalog.allocate_session_title(
                    plan.normalized_title_hint,
                    workspace_dir=plan.workspace_dir,
                    active_sessions=sessions.values(),
                    persisted_records=self.list_persisted_records(),
                )
            self.refresh_session_lifecycle(session, now_utc)
            session.touch(now_utc=now_utc)
            self.persist_session(session)
            return session

        new_session_id = plan.session_id or self.allocate_session_id(sessions)
        session = await self.session_creation.create(
            RuntimeSessionCreationCommand(
                session_id=new_session_id,
                workspace_dir=plan.workspace_dir,
                title=DEFAULT_SESSION_TITLE if plan.is_default_session else plan.normalized_title_hint,
                default_title=DEFAULT_SESSION_TITLE if plan.is_default_session else None,
                is_default=bool(plan.is_default_session),
                surface=plan.normalized_surface if plan.surface_provided else None,
                surface_provided=plan.surface_provided,
                channel_type=plan.normalized_channel_type,
                conversation_id=plan.normalized_conversation_id,
                sender_id=plan.normalized_sender_id,
                shared=False,
            ),
            now_utc=now_utc,
        )
        sessions[new_session_id] = session
        self.register_session(session)
        self.persist_session(session)
        return session

    def _prepare_snapshot_import(
        self,
        sessions: MutableMapping[str, "MainAgentSessionState"],
        *,
        command: RuntimeSessionSnapshotImportCommand,
        now_utc: datetime,
    ) -> RuntimeSessionSnapshotImportPlan:
        self._prepare_workspace_entry(
            sessions,
            workspace_dir=command.workspace_dir,
            now_utc=now_utc,
            enforce_capacity=True,
        )

        requested_session_id = _safe_text(command.session_id)
        if requested_session_id:
            if requested_session_id in sessions or self.load_persisted_record(requested_session_id) is not None:
                raise HTTPException(status_code=409, detail="Session already exists.")
            new_session_id = requested_session_id
        else:
            new_session_id = self.allocate_session_id(sessions)

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

    def _prepare_workspace_entry(
        self,
        sessions: MutableMapping[str, "MainAgentSessionState"],
        *,
        workspace_dir: Path,
        now_utc: datetime,
        enforce_capacity: bool,
    ) -> None:
        self.drop_expired_sessions(sessions, now_utc=now_utc)
        self.enforce_workspace_entry(list(sessions.values()), workspace_dir)
        if enforce_capacity:
            self._enforce_capacity(sessions)

    def _enforce_capacity(
        self,
        sessions: MutableMapping[str, "MainAgentSessionState"],
    ) -> None:
        try:
            self.enforce_capacity()
        except TypeError:
            self.enforce_capacity(len(sessions))


__all__ = [
    "RuntimeSessionRegistryHandler",
    "RuntimeSessionSnapshotImportCommand",
    "RuntimeSessionSnapshotImportPlan",
]



