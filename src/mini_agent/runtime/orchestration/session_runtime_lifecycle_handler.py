"""Session lifecycle bootstrap/refresh helpers extracted from the runtime manager."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from mini_agent.agent_core.session.lifecycle import (
    SessionLifecycleManager,
    SessionLifecyclePolicy,
    SessionLifecycleState,
)
from mini_agent.agent_core.session.session_key import AgentSessionKey
from mini_agent.runtime.orchestration.session_runtime_policy_coordinator import RuntimeSessionPolicyCoordinator
from mini_agent.runtime.support.workspace_path_utils import workspace_path_key


@dataclass(frozen=True)
class SessionLifecycleDecision:
    reset: bool
    reason: str | None


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
        peer_id=workspace_path_key(workspace_dir),
        thread_id=session_id,
    )


@dataclass(slots=True)
class RuntimeSessionLifecycleHandler:
    lifecycle_manager: SessionLifecycleManager
    policy_coordinator: RuntimeSessionPolicyCoordinator
    path_key: Callable[[Path], str] = workspace_path_key
    agent_id: str = "main-agent"
    channel: str = "gateway"

    def build_session_key(self, session_id: str, workspace_dir: Path) -> AgentSessionKey:
        return AgentSessionKey(
            agent_id=self.agent_id,
            channel=self.channel,
            peer_kind="workspace",
            peer_id=self.path_key(workspace_dir),
            thread_id=session_id,
        )

    def bootstrap_session(
        self,
        session_id: str,
        workspace_dir: Path,
        *,
        now_utc: datetime | None = None,
    ) -> SessionLifecycleState:
        return self.lifecycle_manager.bootstrap(
            self.build_session_key(session_id, workspace_dir),
            now_utc=now_utc,
        )

    def refresh_session(
        self,
        session: Any,
        *,
        now_utc: datetime | None = None,
        reset_runtime_state: Callable[[], None],
    ) -> bool:
        return self.policy_coordinator.refresh_session_lifecycle(
            session,
            now_utc=now_utc,
            reset_runtime_state=reset_runtime_state,
        )

    def reset_session(
        self,
        session: Any,
        *,
        now_utc: datetime | None = None,
    ) -> None:
        session.lifecycle_state = self.lifecycle_manager.reset(
            session.lifecycle_state,
            now_utc=now_utc,
        )
        session.lifecycle_state = self.lifecycle_manager.touch(
            session.lifecycle_state,
            now_utc=now_utc,
        )


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
        from mini_agent.runtime.orchestration.session_runtime_policy_coordinator import (
            resolve_session_lifecycle_policy,
        )

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


__all__ = [
    "RuntimeSessionLifecycleHandler",
    "SessionLifecycleDecision",
    "SurfaceSessionLifecycleRuntime",
    "build_surface_session_key",
]
