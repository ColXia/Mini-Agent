"""Session registry / persistence orchestration extracted from the runtime manager."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Awaitable, Callable, MutableMapping, Sequence

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
from mini_agent.runtime.orchestration.session_snapshot_handler import (
    RuntimeSessionSnapshotHandler,
    RuntimeSessionSnapshotImportCommand,
)
from mini_agent.session import DEFAULT_SESSION_TITLE

if TYPE_CHECKING:
    from mini_agent.interfaces import (
        MainAgentSessionDetail,
        MainAgentSessionMessage,
        MainAgentSessionSummary,
    )
    from mini_agent.runtime.handlers.session_catalog_handler import RuntimeSessionCatalogHandler
    from mini_agent.runtime.session_hydration_builder import RuntimeSessionHydrationPayload
    from mini_agent.runtime.session_snapshot import RuntimeSessionSnapshot
    from mini_agent.runtime.session_state import MainAgentSessionState


def _safe_text(value: object) -> str:
    return " ".join(str(value or "").split())


@dataclass(slots=True)
class RuntimeSessionRegistryHandler:
    session_access: RuntimeSessionAccessHandler
    session_creation: RuntimeSessionCreationHandler
    session_snapshots: RuntimeSessionSnapshotHandler
    session_catalog: "RuntimeSessionCatalogHandler"
    drop_expired_sessions: Callable[..., None]
    enforce_workspace_entry: Callable[[Sequence["MainAgentSessionState"], Path], None]
    enforce_capacity: Callable[..., None]
    raise_workspace_mismatch: Callable[[], None]
    allocate_session_id: Callable[[], str]
    load_persisted_record: Callable[[str], dict[str, Any] | None]
    list_persisted_records: Callable[[], list[dict[str, Any]]]
    restore_persisted_session: Callable[[dict[str, Any], datetime], Awaitable["MainAgentSessionState"]]
    hydrate_session: Callable[[RuntimeSessionHydrationPayload, datetime, bool], Awaitable["MainAgentSessionState"]]
    build_derived_hydration_payload: Callable[..., RuntimeSessionHydrationPayload]
    refresh_session_lifecycle: Callable[["MainAgentSessionState", datetime], bool]
    register_session: Callable[["MainAgentSessionState"], None]
    persist_session: Callable[["MainAgentSessionState"], None]

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
            allocate_session_id=self.allocate_session_id,
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
        session_id = self.allocate_session_id()
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
        session_id = self.allocate_session_id()
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
        plan = self.session_snapshots.prepare_import(
            command,
            now_utc=now_utc,
            prepare_environment=lambda import_workspace, import_now: self._prepare_workspace_entry(
                sessions,
                workspace_dir=import_workspace,
                now_utc=import_now,
                enforce_capacity=True,
            ),
            session_exists=lambda candidate: (
                candidate in sessions or self.load_persisted_record(candidate) is not None
            ),
            allocate_session_id=self.allocate_session_id,
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
        return self.session_snapshots.export_snapshot(
            session_id,
            active_session=session,
            persisted_record=record,
        )

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

        new_session_id = plan.session_id or self.allocate_session_id()
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

    def _prepare_workspace_entry(
        self,
        sessions: MutableMapping[str, "MainAgentSessionState"],
        *,
        workspace_dir: Path,
        now_utc: datetime,
        enforce_capacity: bool,
    ) -> None:
        self.drop_expired_sessions(now_utc=now_utc)
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
]
