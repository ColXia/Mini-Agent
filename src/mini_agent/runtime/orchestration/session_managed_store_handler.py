"""Managed session store/persistence orchestration extracted from the runtime manager."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Awaitable, Callable, Mapping, MutableMapping, Sequence
from uuid import uuid4

from fastapi import HTTPException

if TYPE_CHECKING:
    from mini_agent.runtime.session_state import MainAgentSessionState


@dataclass(slots=True)
class RuntimeManagedSessionStoreHandler:
    expired_session_ids: Callable[..., list[str]]
    build_sandbox_diagnostics_for_session: Callable[["MainAgentSessionState"], dict[str, Any]]
    save_session: Callable[["MainAgentSessionState", Sequence[Any] | None, dict[str, Any]], None]
    load_session_record: Callable[[str], dict[str, Any] | None]
    delete_session_record: Callable[[str], bool]
    restore_persisted_session: Callable[[dict[str, Any], datetime | None], Awaitable["MainAgentSessionState"]]
    record_workspace_dir: Callable[[dict[str, Any]], Path | None]
    clear_session_runtime_task_memory: Callable[[Path, str], None]
    remove_session_lineage: Callable[[str], None]

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
        sessions: Mapping[str, "MainAgentSessionState"],
    ) -> str:
        while True:
            candidate = uuid4().hex
            if candidate in sessions:
                continue
            if self.load_session_record(candidate) is not None:
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
        record = self.load_session_record(session_id)
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
            record = self.load_session_record(session_id)
            if isinstance(record, dict):
                workspace_dir = self.record_workspace_dir(record)
        if workspace_dir is not None:
            self.clear_session_runtime_task_memory(workspace_dir, session_id)
        if self.delete_session_record(session_id):
            found = True
        self.remove_session_lineage(session_id)
        if not found:
            raise HTTPException(status_code=404, detail="Session not found.")


__all__ = ["RuntimeManagedSessionStoreHandler"]
