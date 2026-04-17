"""Session lifecycle bootstrap/refresh helpers extracted from the runtime manager."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from mini_agent.agent_core.session import AgentSessionKey, SessionLifecycleManager, SessionLifecycleState
from mini_agent.runtime.orchestration.session_runtime_policy_coordinator import RuntimeSessionPolicyCoordinator
from mini_agent.runtime.support.workspace_path_utils import workspace_path_key


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


__all__ = ["RuntimeSessionLifecycleHandler"]
