"""Runtime session persistence record builders."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    from mini_agent.runtime.session_state import (
        MainAgentSessionState,
        MainAgentSessionTranscriptEntry,
    )


def _safe_text(value: object) -> str:
    return " ".join(str(value or "").split())


def _to_utc_iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


@dataclass(slots=True)
class RuntimeSessionPersistenceRecordBuilder:
    session_kind: str
    session_token_usage: Callable[["MainAgentSessionState"], int]
    session_token_limit: Callable[["MainAgentSessionState"], int]
    agent_last_memory_automation: Callable[[Any], dict[str, Any]] | None = None
    agent_last_runtime_task_memory: Callable[[Any], dict[str, Any]] | None = None
    active_pending_approvals: Callable[["MainAgentSessionState"], list[dict[str, Any]]] | None = None
    active_run_control_state: Callable[["MainAgentSessionState"], dict[str, Any] | None] | None = None
    active_approval_wait: Callable[["MainAgentSessionState"], dict[str, Any] | None] | None = None
    selected_model_identity_for_session: (
        Callable[["MainAgentSessionState"], tuple[str, str, str] | None] | None
    ) = None
    pending_model_identity_for_session: (
        Callable[["MainAgentSessionState"], tuple[str, str, str] | None] | None
    ) = None

    @staticmethod
    def _normalize_agent_payload(value: Any) -> dict[str, Any]:
        return dict(value) if isinstance(value, dict) else {}

    def _read_agent_last_memory_automation(self, agent: Any) -> dict[str, Any]:
        if callable(self.agent_last_memory_automation):
            try:
                return self._normalize_agent_payload(self.agent_last_memory_automation(agent))
            except Exception:
                return {}
        return self._normalize_agent_payload(getattr(agent, "last_memory_automation", {}))

    def _read_agent_last_runtime_task_memory(self, agent: Any) -> dict[str, Any]:
        if callable(self.agent_last_runtime_task_memory):
            try:
                return self._normalize_agent_payload(self.agent_last_runtime_task_memory(agent))
            except Exception:
                return {}
        return self._normalize_agent_payload(getattr(agent, "last_runtime_task_memory", {}))

    def _read_active_run_control_state(self, session: "MainAgentSessionState") -> dict[str, Any] | None:
        if not callable(self.active_run_control_state):
            return None
        try:
            payload = self.active_run_control_state(session)
        except Exception:
            return None
        return dict(payload) if isinstance(payload, dict) else None

    def _read_active_approval_wait(self, session: "MainAgentSessionState") -> dict[str, Any] | None:
        if not callable(self.active_approval_wait):
            return None
        try:
            payload = self.active_approval_wait(session)
        except Exception:
            return None
        return dict(payload) if isinstance(payload, dict) else None

    def _read_active_pending_approvals(self, session: "MainAgentSessionState") -> list[dict[str, Any]]:
        if callable(self.active_pending_approvals):
            try:
                payload = self.active_pending_approvals(session)
            except Exception:
                payload = None
            if isinstance(payload, list):
                return [dict(item) for item in payload if isinstance(item, dict)]
        legacy = getattr(session.runtime, "pending_approvals", None)
        if not isinstance(legacy, list):
            return []
        return [dict(item) for item in legacy if isinstance(item, dict)]

    def _read_selected_model_identity(
        self,
        session: "MainAgentSessionState",
    ) -> tuple[str, str, str] | None:
        if callable(self.selected_model_identity_for_session):
            try:
                identity = self.selected_model_identity_for_session(session)
            except Exception:
                identity = None
            if isinstance(identity, tuple) and len(identity) == 3:
                return identity
        source = _safe_text(session.projection.selected_model_source) or None
        provider_id = _safe_text(session.projection.selected_provider_id) or None
        model_id = _safe_text(session.projection.selected_model_id) or None
        if source and provider_id and model_id:
            return source, provider_id, model_id
        return None

    def _read_pending_model_identity(
        self,
        session: "MainAgentSessionState",
    ) -> tuple[str, str, str] | None:
        if callable(self.pending_model_identity_for_session):
            try:
                identity = self.pending_model_identity_for_session(session)
            except Exception:
                identity = None
            if isinstance(identity, tuple) and len(identity) == 3:
                return identity
        source = _safe_text(session.projection.pending_model_source) or None
        provider_id = _safe_text(session.projection.pending_provider_id) or None
        model_id = _safe_text(session.projection.pending_model_id) or None
        if source and provider_id and model_id:
            return source, provider_id, model_id
        return None

    @staticmethod
    def serialize_transcript_entry(entry: "MainAgentSessionTranscriptEntry") -> dict[str, Any]:
        return {
            "index": int(entry.index),
            "role": _safe_text(entry.role).lower() or "assistant",
            "content": str(entry.content or ""),
            "surface": _safe_text(entry.surface).lower() or "api",
            "created_at": _to_utc_iso(entry.created_at),
            "channel_type": _safe_text(entry.channel_type) or None,
            "conversation_id": _safe_text(entry.conversation_id) or None,
            "sender_id": _safe_text(entry.sender_id) or None,
            "metadata": dict(entry.metadata) if isinstance(entry.metadata, dict) else {},
        }

    @staticmethod
    def serialize_pending_approval(item: dict[str, Any]) -> dict[str, Any]:
        return {
            "token": _safe_text(item.get("token")) or None,
            "tool_name": _safe_text(item.get("tool_name")) or None,
            "arguments": dict(item.get("arguments")) if isinstance(item.get("arguments"), dict) else {},
            "kind": _safe_text(item.get("kind")) or None,
            "reason": _safe_text(item.get("reason")) or None,
            "cache_key": _safe_text(item.get("cache_key")) or None,
            "can_escalate": bool(item.get("can_escalate", False)),
            "step": int(item.get("step") or 0),
        }

    def build_metadata_record(
        self,
        session: "MainAgentSessionState",
        *,
        transcript_path: Path,
        sandbox_diagnostics: dict[str, Any],
        workspace_runtime_snapshot: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        pending_approvals = self._read_active_pending_approvals(session)
        selected_identity = self._read_selected_model_identity(session)
        pending_identity = self._read_pending_model_identity(session)
        return {
            "session_id": session.session_id,
            "workspace_dir": str(session.workspace_dir),
            "created_at": _to_utc_iso(session.created_at),
            "updated_at": _to_utc_iso(session.updated_at),
            "message_count": len(session.transcript_state.transcript),
            "session_kind": self.session_kind,
            "title": _safe_text(session.projection.title) or None,
            "origin_surface": _safe_text(session.projection.origin_surface) or "api",
            "active_surface": _safe_text(session.projection.active_surface or session.projection.origin_surface) or "api",
            "reply_enabled": bool(session.projection.reply_enabled),
            "is_default": bool(session.projection.is_default),
            "busy": bool(session.projection.busy),
            "running_state": _safe_text(session.projection.running_state) or None,
            "channel_type": _safe_text(session.projection.channel_type) or None,
            "conversation_id": _safe_text(session.projection.conversation_id) or None,
            "sender_id": _safe_text(session.projection.sender_id) or None,
            "token_usage": self.session_token_usage(session),
            "token_limit": self.session_token_limit(session),
            "shared": bool(session.projection.shared),
            "knowledge_base_enabled": bool(session.projection.knowledge_base_enabled),
            "selected_model_source": selected_identity[0] if selected_identity is not None else None,
            "selected_provider_id": selected_identity[1] if selected_identity is not None else None,
            "selected_model_id": selected_identity[2] if selected_identity is not None else None,
            "pending_model_source": pending_identity[0] if pending_identity is not None else None,
            "pending_provider_id": pending_identity[1] if pending_identity is not None else None,
            "pending_model_id": pending_identity[2] if pending_identity is not None else None,
            "lineage_parent_session_id": _safe_text(session.lineage_state.parent_session_id) or None,
            "lineage_root_session_id": (
                _safe_text(session.lineage_state.root_session_id) or session.session_id
            ),
            "lineage_reason": _safe_text(session.lineage_state.reason) or "root",
            "lineage_created_at": _to_utc_iso(session.lineage_state.created_at),
            "lineage_metadata": (
                dict(session.lineage_state.metadata)
                if isinstance(session.lineage_state.metadata, dict)
                else {}
            ),
            "pending_skill_reload": bool(session.projection.pending_skill_reload),
            "pending_skill_reload_reason": _safe_text(session.projection.pending_skill_reload_reason) or None,
            "shared_transcript_path": str(transcript_path),
            "shared_message_count": len(session.transcript_state.transcript),
            "next_transcript_index": int(session.transcript_state.next_transcript_index),
            "pending_approvals": [self.serialize_pending_approval(item) for item in pending_approvals],
            "recovery_context_pending": bool(session.projection.recovery_context_pending),
            "recovery_state": _safe_text(session.projection.recovery_state) or None,
            "recovery_summary": _safe_text(session.projection.recovery_summary) or None,
            "recovery_last_activity": _safe_text(session.projection.recovery_last_activity) or None,
            "recovery_last_user_message": _safe_text(session.projection.recovery_last_user_message) or None,
            "recovery_last_assistant_message": _safe_text(session.projection.recovery_last_assistant_message) or None,
            "recovery_pending_approvals": [
                self.serialize_pending_approval(item)
                for item in session.projection.recovery_pending_approvals
                if isinstance(item, dict)
            ],
            "context_policy": (
                dict(session.projection.context_policy)
                if isinstance(session.projection.context_policy, dict)
                else {}
            ),
            "last_prepared_context": (
                dict(session.projection.last_prepared_context)
                if isinstance(session.projection.last_prepared_context, dict)
                else {}
            ),
            "prepared_context_diagnostics": (
                dict(session.projection.prepared_context_diagnostics)
                if isinstance(session.projection.prepared_context_diagnostics, dict)
                else {}
            ),
            "memory_diagnostics": (
                dict(session.projection.memory_diagnostics)
                if isinstance(session.projection.memory_diagnostics, dict)
                else {}
            ),
            "sandbox_diagnostics": dict(sandbox_diagnostics) if isinstance(sandbox_diagnostics, dict) else {},
            "workspace_runtime_snapshot": (
                dict(workspace_runtime_snapshot)
                if isinstance(workspace_runtime_snapshot, dict)
                else None
            ),
            "last_memory_automation": self._read_agent_last_memory_automation(session.runtime.agent),
            "last_runtime_task_memory": self._read_agent_last_runtime_task_memory(session.runtime.agent),
            "run_control": self._read_active_run_control_state(session),
            "approval_wait": self._read_active_approval_wait(session),
        }


__all__ = ["RuntimeSessionPersistenceRecordBuilder"]
