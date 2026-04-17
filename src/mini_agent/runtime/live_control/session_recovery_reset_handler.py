"""Recovery-context and runtime-reset mutations."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    from pathlib import Path

    from mini_agent.agent_core.engine import Agent
    from mini_agent.interfaces import MainAgentSessionRecoverySnapshot
    from mini_agent.runtime.session_state import MainAgentSessionState


def _safe_text(value: object) -> str:
    return " ".join(str(value or "").split())


@dataclass(slots=True)
class RuntimeSessionRecoveryResetHandler:
    refresh_session_diagnostics: Callable[["MainAgentSessionState"], tuple[dict[str, Any], dict[str, Any]]]
    agent_knowledge_base_enabled: Callable[[Any], bool]
    clear_runtime_task_memory_namespace: Callable[["Path", str], bool]
    stored_recovery_snapshot_from_session: Callable[
        ["MainAgentSessionState"],
        "MainAgentSessionRecoverySnapshot | None",
    ]

    def build_recovery_turn_context(
        self,
        session: "MainAgentSessionState",
    ) -> dict[str, Any] | None:
        snapshot = self.stored_recovery_snapshot_from_session(session)
        if snapshot is None:
            return None
        payload = snapshot.model_dump()
        payload["resume_strategy"] = "next_message"
        payload["continue_hint"] = "Continue from the interrupted shared-session task using restored context."
        if payload.get("pending_approvals"):
            payload["approval_hint"] = "Pending approvals from before restart were lost and must be re-evaluated."
        return payload

    def apply_stored_recovery(
        self,
        session: "MainAgentSessionState",
        stored_recovery: "MainAgentSessionRecoverySnapshot" | None,
    ) -> None:
        if stored_recovery is None:
            return
        session.projection.recovery_context_pending = True
        session.projection.recovery_state = _safe_text(stored_recovery.state)
        session.projection.recovery_summary = _safe_text(stored_recovery.summary)
        session.projection.recovery_last_activity = _safe_text(stored_recovery.last_activity) or None
        session.projection.recovery_last_user_message = _safe_text(stored_recovery.last_user_message) or None
        session.projection.recovery_last_assistant_message = (
            _safe_text(stored_recovery.last_assistant_message) or None
        )
        session.projection.recovery_pending_approvals = [
            item.model_dump() for item in list(stored_recovery.pending_approvals or [])
        ]

    def clear_recovery_context(
        self,
        session: "MainAgentSessionState",
        *,
        now_utc: datetime | None = None,
    ) -> None:
        self._clear_recovery_context(session)
        session.touch(now_utc=now_utc)

    def reset_runtime_state(
        self,
        session: "MainAgentSessionState",
        *,
        clear_runtime_task_memory: bool,
    ) -> None:
        self._reset_agent_messages(session.runtime.agent)
        if clear_runtime_task_memory:
            self.clear_runtime_task_memory_namespace(
                session.workspace_dir,
                session.session_id,
            )
        session.transcript_state.current_turn_id = None
        session.runtime.cancel_event = None
        session.runtime.pending_approvals = []
        for future in list(session.runtime.pending_approval_waiters.values()):
            if not future.done():
                future.set_result(None)
        session.runtime.pending_approval_waiters.clear()
        self._clear_recovery_context(session)
        session.projection.last_prepared_context = {}
        session.projection.prepared_context_diagnostics = {}
        session.projection.busy = False
        session.projection.running_state = ""
        session.projection.knowledge_base_enabled = self.agent_knowledge_base_enabled(session.runtime.agent)
        self.refresh_session_diagnostics(session)

    @staticmethod
    def _clear_recovery_context(session: "MainAgentSessionState") -> None:
        session.projection.recovery_context_pending = False
        session.projection.recovery_state = ""
        session.projection.recovery_summary = ""
        session.projection.recovery_last_activity = None
        session.projection.recovery_last_user_message = None
        session.projection.recovery_last_assistant_message = None
        session.projection.recovery_pending_approvals = []

    @staticmethod
    def _reset_agent_messages(agent: "Agent | None") -> None:
        if agent is None:
            return
        messages = getattr(agent, "messages", None)
        if isinstance(messages, list) and messages:
            agent.messages = [messages[0]]
        if hasattr(agent, "api_total_tokens"):
            agent.api_total_tokens = 0
        reset_runtime_state = getattr(agent, "reset_ephemeral_runtime_state", None)
        if callable(reset_runtime_state):
            reset_runtime_state()
            return
        if hasattr(agent, "last_prepared_turn_context"):
            agent.last_prepared_turn_context = None
        if hasattr(agent, "prepared_context_diagnostics"):
            agent.prepared_context_diagnostics = {}
        if hasattr(agent, "last_memory_automation"):
            agent.last_memory_automation = {}
        if hasattr(agent, "last_runtime_task_memory"):
            agent.last_runtime_task_memory = {}


__all__ = ["RuntimeSessionRecoveryResetHandler"]
