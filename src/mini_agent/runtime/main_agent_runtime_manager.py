"""Runtime manager for single-host main-agent session lifecycle."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
import os
from pathlib import Path
from typing import Awaitable, Callable
from uuid import uuid4

from fastapi import HTTPException

from mini_agent.agent import Agent
from mini_agent.interfaces import MainAgentSessionSummary


BuildAgentFn = Callable[[Path], Awaitable[Agent]]


def _to_utc_iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


@dataclass
class MainAgentSessionState:
    session_id: str
    workspace_dir: Path
    agent: Agent
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    def touch(self) -> None:
        self.updated_at = datetime.now(timezone.utc)


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
    main_workspace_dir: str | None = None


class MainAgentRuntimeManager:
    """In-process manager enforcing main-agent runtime/session policies."""

    def __init__(
        self,
        *,
        ttl_seconds: int,
        build_agent: BuildAgentFn,
        policy: MainAgentRuntimePolicy | None = None,
    ):
        self._ttl_seconds = int(ttl_seconds)
        self._build_agent = build_agent
        self._policy = policy or MainAgentRuntimePolicy()
        self._sessions: dict[str, MainAgentSessionState] = {}
        self._store_lock = asyncio.Lock()
        self._team_saturation_rejections = 0
        self._team_workspace_conflict_rejections = 0

    async def clear(self) -> None:
        async with self._store_lock:
            self._sessions.clear()
            self._team_saturation_rejections = 0
            self._team_workspace_conflict_rejections = 0

    def validate_workspace(self, workspace_dir: Path) -> None:
        self._enforce_main_workspace_policy(workspace_dir)

    async def get_or_create_session(
        self,
        session_id: str | None,
        workspace_dir: Path,
    ) -> MainAgentSessionState:
        async with self._store_lock:
            now = datetime.now(timezone.utc)
            expired_ids = [
                sid
                for sid, session in self._sessions.items()
                if (now - session.updated_at).total_seconds() > self._ttl_seconds
            ]
            for sid in expired_ids:
                self._sessions.pop(sid, None)

            self._enforce_main_workspace_policy(workspace_dir)

            if session_id and session_id in self._sessions:
                session = self._sessions[session_id]
                if not self._same_workspace(session.workspace_dir, workspace_dir):
                    if self._policy.mode == MainAgentRuntimeMode.TEAM:
                        self._team_workspace_conflict_rejections += 1
                    raise HTTPException(status_code=400, detail="Session workspace mismatch.")
                session.touch()
                return session

            # Team mode guardrail: if caller did not provide a session id and an
            # active session already exists for this workspace, reuse it to avoid
            # accidental workspace-local fan-out under retries.
            if self._policy.mode == MainAgentRuntimeMode.TEAM and not session_id:
                existing_workspace_session = self._find_latest_session_for_workspace(workspace_dir)
                if existing_workspace_session is not None:
                    existing_workspace_session.touch()
                    return existing_workspace_session

            if self._policy.mode == MainAgentRuntimeMode.SINGLE_MAIN and self._sessions:
                active = next(iter(self._sessions.values()))
                if not self._same_workspace(workspace_dir, active.workspace_dir):
                    raise HTTPException(
                        status_code=409,
                        detail=(
                            "Main-agent runtime is already active in another workspace. "
                            f"active_session_id={active.session_id}"
                        ),
                    )
                if session_id and session_id != active.session_id:
                    raise HTTPException(
                        status_code=409,
                        detail=(
                            "Main-agent runtime already has an active session. "
                            f"active_session_id={active.session_id}"
                        ),
                    )
                active.touch()
                return active

            if (
                self._policy.mode == MainAgentRuntimeMode.TEAM
                and len(self._sessions) >= max(1, int(self._policy.max_active_sessions))
            ):
                self._team_saturation_rejections += 1
                raise HTTPException(
                    status_code=409,
                    detail=(
                        "Agent-team runtime reached max_active_sessions. "
                        f"max_active_sessions={self._policy.max_active_sessions}"
                    ),
                )

            new_session_id = session_id or uuid4().hex
            agent = await self._build_agent(workspace_dir)
            session = MainAgentSessionState(
                session_id=new_session_id,
                workspace_dir=workspace_dir,
                agent=agent,
            )
            self._sessions[new_session_id] = session
            return session

    async def get_runtime_diagnostics(self) -> MainAgentRuntimeDiagnostics:
        """Return a lock-consistent runtime diagnostics snapshot."""
        async with self._store_lock:
            max_active_sessions = max(1, int(self._policy.max_active_sessions))
            active_sessions = len(self._sessions)
            available_slots = max(0, max_active_sessions - active_sessions)
            main_workspace = (
                str(self._policy.main_workspace_dir.resolve())
                if self._policy.main_workspace_dir is not None
                else None
            )
            return MainAgentRuntimeDiagnostics(
                mode=self._policy.mode.value,
                active_sessions=active_sessions,
                max_active_sessions=max_active_sessions,
                available_session_slots=available_slots,
                reserved_team_slots=max(1, int(self._policy.reserved_team_slots)),
                workspace_application_required=bool(self._policy.workspace_application_required),
                team_saturation_rejections=max(0, int(self._team_saturation_rejections)),
                team_workspace_conflict_rejections=max(0, int(self._team_workspace_conflict_rejections)),
                main_workspace_dir=main_workspace,
            )

    async def list_sessions(self) -> list[MainAgentSessionSummary]:
        async with self._store_lock:
            return [
                MainAgentSessionSummary(
                    session_id=session.session_id,
                    workspace_dir=str(session.workspace_dir),
                    created_at=_to_utc_iso(session.created_at),
                    updated_at=_to_utc_iso(session.updated_at),
                    message_count=len(session.agent.messages),
                )
                for session in self._sessions.values()
            ]

    async def delete_session(self, session_id: str) -> None:
        async with self._store_lock:
            if session_id not in self._sessions:
                raise HTTPException(status_code=404, detail="Session not found.")
            self._sessions.pop(session_id, None)

    async def reset_session(self, session_id: str) -> None:
        async with self._store_lock:
            session = self._sessions.get(session_id)
            if session is None:
                raise HTTPException(status_code=404, detail="Session not found.")
        async with session.lock:
            if session.agent.messages:
                session.agent.messages = [session.agent.messages[0]]
            session.touch()

    def _enforce_main_workspace_policy(self, workspace_dir: Path) -> None:
        if self._policy.mode != MainAgentRuntimeMode.SINGLE_MAIN:
            return
        if self._policy.main_workspace_dir is None:
            return
        main_workspace = self._policy.main_workspace_dir.resolve()
        if self._same_workspace(workspace_dir, main_workspace):
            return
        raise HTTPException(
            status_code=409,
            detail=(
                "Main-agent single-main mode requires the main workspace. "
                f"requested_workspace={workspace_dir.resolve()} "
                f"main_workspace={main_workspace} "
                "agent_team_mode=reserved"
            ),
        )

    @staticmethod
    def _path_key(path: Path) -> str:
        resolved = str(path.resolve())
        return resolved.lower() if os.name == "nt" else resolved

    @classmethod
    def _same_workspace(cls, left: Path, right: Path) -> bool:
        return cls._path_key(left) == cls._path_key(right)

    def _find_latest_session_for_workspace(self, workspace_dir: Path) -> MainAgentSessionState | None:
        candidates = [
            session
            for session in self._sessions.values()
            if self._same_workspace(session.workspace_dir, workspace_dir)
        ]
        if not candidates:
            return None
        return max(candidates, key=lambda item: item.updated_at)
