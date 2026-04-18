"""Recovery-context and runtime-reset mutations."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any, Callable

from .run_control_store import RuntimeSessionRunControlStore

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
    run_control_store: RuntimeSessionRunControlStore | None = None

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

    def apply_interrupted_recovery(
        self,
        session: "MainAgentSessionState",
        *,
        summary: str | None = None,
        last_activity: str | None = None,
        pending_approvals: list[dict[str, Any]] | None = None,
        now_utc: datetime | None = None,
    ) -> None:
        user_preview = self._last_role_preview(session, role="user") or _safe_text(
            session.projection.recovery_last_user_message
        ) or None
        assistant_preview = self._last_role_preview(session, role="assistant") or _safe_text(
            session.projection.recovery_last_assistant_message
        ) or None
        session.projection.recovery_context_pending = True
        session.projection.recovery_state = "interrupted"
        session.projection.recovery_summary = _safe_text(summary) or "interrupted after pause request"
        session.projection.recovery_last_activity = (
            _safe_text(last_activity)
            or self._last_activity_summary(session)
            or _safe_text(session.projection.recovery_last_activity)
            or None
        )
        session.projection.recovery_last_user_message = user_preview
        session.projection.recovery_last_assistant_message = assistant_preview
        session.projection.recovery_pending_approvals = [
            dict(item)
            for item in list(pending_approvals or [])
            if isinstance(item, dict)
        ]
        session.touch(now_utc=now_utc)

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
        self._run_control_store().reset_runtime_state(
            session,
            reason="runtime state reset",
        )
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

    @staticmethod
    def _last_role_preview(
        session: "MainAgentSessionState",
        *,
        role: str,
        limit: int = 160,
    ) -> str | None:
        normalized_role = _safe_text(role).lower()
        transcript = getattr(session.transcript_state, "transcript", None)
        for entry in reversed(list(transcript or [])):
            if _safe_text(getattr(entry, "role", "")).lower() != normalized_role:
                continue
            text = _safe_text(getattr(entry, "content", ""))
            if not text:
                continue
            if len(text) <= limit:
                return text
            return text[: limit - 3] + "..."
        return None

    @staticmethod
    def _last_activity_summary(session: "MainAgentSessionState") -> str | None:
        transcript = getattr(session.transcript_state, "transcript", None)
        for entry in reversed(list(transcript or [])):
            metadata = dict(entry.metadata) if isinstance(getattr(entry, "metadata", None), dict) else {}
            if getattr(entry, "role", "") == "tool" and metadata.get("kind") == "activity":
                items = metadata.get("activity_items")
                if isinstance(items, list) and items:
                    item = items[-1]
                    label = RuntimeSessionRecoveryResetHandler._activity_label(item.get("label", "activity"))
                    detail = _safe_text(item.get("detail")) or "running"
                    preview = _safe_text(item.get("preview"))
                    output_summary = _safe_text(item.get("output_summary"))
                    parts = [f"{label} {detail}"]
                    if preview:
                        parts.append(preview)
                    if output_summary and label == "shell":
                        parts.append(output_summary)
                    return " | ".join(part for part in parts if part).strip() or None
                text = _safe_text(getattr(entry, "content", ""))
                if text:
                    return text
            if metadata.get("kind") == "command":
                command = _safe_text(metadata.get("command")) or "command"
                command_summary = _safe_text(metadata.get("summary")) or _safe_text(getattr(entry, "content", "")) or "applied"
                return f"{command} | {command_summary}"
        return None

    @staticmethod
    def _activity_label(value: object) -> str:
        normalized = _safe_text(value).lower().replace("_", "-")
        if normalized in {"bash", "powershell", "shell", "shell-command"}:
            return "shell"
        if normalized.startswith("bash-"):
            return normalized.replace("bash-", "shell-", 1)
        return normalized or "activity"

    def _run_control_store(self) -> RuntimeSessionRunControlStore:
        if self.run_control_store is None:
            self.run_control_store = RuntimeSessionRunControlStore()
        return self.run_control_store


__all__ = ["RuntimeSessionRecoveryResetHandler"]
