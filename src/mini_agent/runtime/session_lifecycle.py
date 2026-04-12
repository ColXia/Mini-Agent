"""Shared session-lifecycle runtime helpers for gateway and terminal surfaces."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import os
from pathlib import Path
from typing import Callable

from mini_agent.agent_core.session import (
    AgentSessionKey,
    SessionLifecycleManager,
    SessionLifecyclePolicy,
    SessionLifecycleState,
    SessionResetMode,
)


SESSION_RESET_MODE_ENV = "MINI_AGENT_SESSION_RESET_MODE"
SESSION_IDLE_SECONDS_ENV = "MINI_AGENT_SESSION_IDLE_SECONDS"


def _path_key(path: Path) -> str:
    resolved = str(path.resolve())
    return resolved.lower() if os.name == "nt" else resolved


def resolve_session_lifecycle_policy(
    *,
    reset_mode_raw: str | None = None,
    idle_seconds_raw: str | None = None,
) -> SessionLifecyclePolicy:
    raw_mode = (reset_mode_raw if reset_mode_raw is not None else os.getenv(SESSION_RESET_MODE_ENV, "none")).strip().lower()
    raw_idle = (idle_seconds_raw if idle_seconds_raw is not None else os.getenv(SESSION_IDLE_SECONDS_ENV, "1800")).strip()

    try:
        mode = SessionResetMode(raw_mode or SessionResetMode.NONE.value)
    except ValueError:
        mode = SessionResetMode.NONE

    try:
        idle_seconds = int(raw_idle or "1800")
    except ValueError:
        idle_seconds = 1800

    return SessionLifecyclePolicy(
        mode=mode,
        idle_seconds=max(1, idle_seconds),
    )


def build_surface_session_key(
    *,
    surface: str,
    workspace_dir: Path,
    session_id: str,
    agent_id: str = "main-agent",
) -> AgentSessionKey:
    normalized_surface = " ".join((surface or "").strip().lower().split()) or "terminal"
    return AgentSessionKey(
        agent_id=agent_id,
        channel=normalized_surface,
        peer_kind="workspace",
        peer_id=_path_key(workspace_dir),
        thread_id=session_id,
    )


@dataclass(frozen=True)
class SessionLifecycleDecision:
    reset: bool
    reason: str | None


class SurfaceSessionLifecycleRuntime:
    """Session lifecycle state machine for one runtime surface and workspace."""

    def __init__(
        self,
        *,
        surface: str,
        workspace_dir: Path,
        policy: SessionLifecyclePolicy | None = None,
        agent_id: str = "main-agent",
    ) -> None:
        self.surface = " ".join((surface or "").strip().lower().split()) or "terminal"
        self.workspace_dir = workspace_dir.resolve()
        self.agent_id = " ".join((agent_id or "").strip().split()) or "main-agent"
        self.policy = (policy or resolve_session_lifecycle_policy()).normalized()
        self._manager = SessionLifecycleManager(self.policy)
        self._states: dict[str, SessionLifecycleState] = {}
        self._auto_reset_count = 0

    @property
    def auto_reset_count(self) -> int:
        return self._auto_reset_count

    def drop_session(self, session_id: str) -> None:
        self._states.pop(str(session_id), None)

    def ensure_active(
        self,
        session_id: str,
        *,
        now_utc: datetime | None = None,
        on_reset: Callable[[], None] | None = None,
    ) -> SessionLifecycleDecision:
        normalized_session_id = str(session_id).strip()
        if not normalized_session_id:
            raise ValueError("session_id must not be empty")

        state = self._states.get(normalized_session_id)
        if state is None:
            state = self._manager.bootstrap(
                build_surface_session_key(
                    surface=self.surface,
                    workspace_dir=self.workspace_dir,
                    session_id=normalized_session_id,
                    agent_id=self.agent_id,
                ),
                now_utc=now_utc,
            )

        result = self._manager.ensure_active(state, now_utc=now_utc)
        state = result.state
        if result.reset:
            if on_reset is not None:
                on_reset()
            self._auto_reset_count += 1

        state = self._manager.touch(state, now_utc=now_utc)
        self._states[normalized_session_id] = state
        return SessionLifecycleDecision(reset=result.reset, reason=result.reason)

    def force_reset(
        self,
        session_id: str,
        *,
        now_utc: datetime | None = None,
        on_reset: Callable[[], None] | None = None,
    ) -> None:
        normalized_session_id = str(session_id).strip()
        if not normalized_session_id:
            raise ValueError("session_id must not be empty")
        state = self._states.get(normalized_session_id)
        if state is None:
            state = self._manager.bootstrap(
                build_surface_session_key(
                    surface=self.surface,
                    workspace_dir=self.workspace_dir,
                    session_id=normalized_session_id,
                    agent_id=self.agent_id,
                ),
                now_utc=now_utc,
            )
        state = self._manager.reset(state, now_utc=now_utc)
        state = self._manager.touch(state, now_utc=now_utc)
        self._states[normalized_session_id] = state
        if on_reset is not None:
            on_reset()
