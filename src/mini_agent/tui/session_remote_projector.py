"""TUI-facing remote session projection helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Sequence

from mini_agent.interfaces import surface_payload_from_dto
from mini_agent.session import SessionDetailProjection, SessionSummaryProjection


def _safe_text(value: object) -> str:
    return " ".join(str(value or "").split())


@dataclass(slots=True)
class TuiRemoteSessionProjector:
    """Apply remote session transport payloads onto TUI-local session state."""

    resolve_session_title: Callable[[SessionSummaryProjection, str], str]
    normalize_model_identity: Callable[..., tuple[str, str, str] | None]
    set_selected_model_identity: Callable[[Any, tuple[str, str, str] | None], None]
    set_pending_model_identity: Callable[[Any, tuple[str, str, str] | None], None]
    normalize_pending_approvals_payload: Callable[[Any], list[dict[str, Any]]]
    normalize_memory_diagnostics_payload: Callable[[Any], dict[str, Any]]
    normalize_sandbox_diagnostics_payload: Callable[[Any], dict[str, Any]]
    normalize_context_policy_payload: Callable[[Any], dict[str, Any]]
    normalize_prepared_context_payload: Callable[[Any], dict[str, Any]]
    normalize_prepared_context_diagnostics_payload: Callable[[Any], dict[str, Any]]
    build_chat_entries: Callable[[Sequence[dict[str, Any]]], list[Any]]
    replace_messages: Callable[[Any, Sequence[Any], bool], None]
    last_command_summary: Callable[[Any], str]

    @staticmethod
    def _approval_payloads(items: Sequence[Any]) -> list[dict[str, Any]]:
        payloads: list[dict[str, Any]] = []
        for item in items:
            try:
                payload = surface_payload_from_dto(item.to_transport())
            except Exception:
                continue
            if payload:
                payloads.append(payload)
        return payloads

    def apply_summary(self, session: Any, payload: dict[str, Any]) -> bool:
        projection = SessionSummaryProjection.from_transport_payload(payload)
        if projection is None:
            return False

        state = session.projection
        operator = session.operator
        supplemental = state.supplemental
        session.title = self.resolve_session_title(
            projection,
            session.title or session.session_id,
        )
        state.origin_surface = projection.origin_surface or state.origin_surface or "qq"
        state.active_surface = projection.active_surface or state.active_surface or state.origin_surface
        state.reply_enabled = bool(projection.reply_enabled)
        state.busy = bool(projection.busy)
        state.running_state = projection.running_state or (state.running_state if state.busy else "")
        state.is_default = bool(projection.is_default)
        state.channel_type = projection.channel_type or state.channel_type
        state.conversation_id = projection.conversation_id or state.conversation_id
        state.sender_id = projection.sender_id or state.sender_id
        state.shared = bool(projection.shared)
        state.token_usage = max(0, int(projection.token_usage))
        state.token_limit = max(0, int(projection.token_limit))
        if payload.get("knowledge_base_enabled") is not None:
            state.knowledge_base_enabled = bool(projection.knowledge_base_enabled)

        self.set_selected_model_identity(
            session,
            self.normalize_model_identity(
                source=projection.selected_model_source,
                provider_id=projection.selected_provider_id,
                model_id=projection.selected_model_id,
            ),
        )
        self.set_pending_model_identity(
            session,
            self.normalize_model_identity(
                source=projection.pending_model_source,
                provider_id=projection.pending_provider_id,
                model_id=projection.pending_model_id,
            ),
        )

        operator.pending_skill_reload = bool(projection.pending_skill_reload)
        operator.pending_skill_reload_reason = _safe_text(projection.pending_skill_reload_reason)
        supplemental.remote_message_count = max(0, int(projection.message_count))
        supplemental.remote_updated_at = projection.updated_at or supplemental.remote_updated_at
        state.memory_diagnostics = self.normalize_memory_diagnostics_payload(projection.memory_diagnostics)
        state.sandbox_diagnostics = self.normalize_sandbox_diagnostics_payload(projection.sandbox_diagnostics)

        if projection.recovery is not None:
            supplemental.remote_recovery_state = projection.recovery.state
            supplemental.remote_recovery_summary = projection.recovery.summary
            supplemental.remote_last_activity_summary = _safe_text(projection.recovery.last_activity)
            supplemental.recovery_pending_approvals = self.normalize_pending_approvals_payload(
                self._approval_payloads(projection.recovery.pending_approvals)
            )
        else:
            supplemental.remote_recovery_state = ""
            supplemental.remote_recovery_summary = ""
            supplemental.remote_last_activity_summary = ""
            supplemental.recovery_pending_approvals = []

        state.pending_approvals = self.normalize_pending_approvals_payload(
            self._approval_payloads(projection.pending_approvals)
        )
        return True

    def apply_detail(
        self,
        session: Any,
        payload: dict[str, Any],
        *,
        preserve_follow_output: bool,
    ) -> bool:
        detail = SessionDetailProjection.from_transport_payload(payload)
        if detail is None:
            return False

        self.apply_summary(session, payload)
        state = session.projection
        state.context_policy = self.normalize_context_policy_payload(detail.context_policy)
        state.last_prepared_context = self.normalize_prepared_context_payload(detail.last_prepared_context)
        state.prepared_context_diagnostics = self.normalize_prepared_context_diagnostics_payload(
            detail.prepared_context_diagnostics
        )
        if isinstance(payload.get("recent_messages"), list):
            recent_message_payloads = [
                message_payload
                for message_payload in (
                    surface_payload_from_dto(item.to_transport()) for item in detail.recent_messages
                )
                if message_payload
            ]
            self.replace_messages(
                session,
                self.build_chat_entries(recent_message_payloads),
                preserve_follow_output,
            )
        state.supplemental.remote_last_command_summary = self.last_command_summary(session)
        return True

    def apply_run(self, session: Any, payload: dict[str, Any]) -> bool:
        if not isinstance(payload, dict):
            return False
        run_id = _safe_text(payload.get("run_id"))
        if not run_id:
            self.clear_run(session)
            return False

        supplemental = session.projection.supplemental
        approval_wait_payload = payload.get("approval_wait") if isinstance(payload.get("approval_wait"), dict) else {}
        approval_token = _safe_text(approval_wait_payload.get("approval_token"))
        tool_name = _safe_text(approval_wait_payload.get("tool_name"))
        tool_arguments = (
            dict(approval_wait_payload.get("tool_arguments_summary") or {})
            if isinstance(approval_wait_payload.get("tool_arguments_summary"), dict)
            else {}
        )
        wait_payload: dict[str, Any] = {}
        if _safe_text(approval_wait_payload.get("wait_id")) and (approval_token or tool_name):
            wait_payload = {
                "wait_id": _safe_text(approval_wait_payload.get("wait_id")),
                "run_id": run_id,
                "session_id": _safe_text(payload.get("session_id")) or session.session_id,
                "token": approval_token or None,
                "tool_name": tool_name or "tool",
                "arguments": tool_arguments,
                "kind": _safe_text(approval_wait_payload.get("approval_kind")) or None,
                "reason": _safe_text(approval_wait_payload.get("policy_reason")) or None,
                "cache_key": _safe_text(approval_wait_payload.get("cache_key")) or None,
                "can_escalate": bool(approval_wait_payload.get("can_escalate")),
                "wait_state": _safe_text(approval_wait_payload.get("wait_state")) or None,
            }

        supplemental.remote_run_id = run_id
        supplemental.remote_run_status = _safe_text(payload.get("status"))
        supplemental.remote_run_phase = _safe_text(payload.get("phase"))
        supplemental.remote_run_busy = bool(payload.get("busy"))
        supplemental.remote_run_running_state = _safe_text(payload.get("running_state"))
        supplemental.remote_run_control_mode = _safe_text(payload.get("control_mode"))
        supplemental.remote_run_interrupt_requested = bool(payload.get("interrupt_requested"))
        supplemental.remote_run_cancel_requested = bool(payload.get("cancel_requested"))
        supplemental.remote_run_resumable = bool(payload.get("resumable"))
        supplemental.remote_run_waiting_on_approval = bool(payload.get("waiting_on_approval"))
        supplemental.remote_run_active_wait_id = _safe_text(payload.get("active_wait_id")) or None
        supplemental.remote_run_approval_wait = wait_payload
        return True

    @staticmethod
    def clear_run(session: Any) -> None:
        supplemental = session.projection.supplemental
        supplemental.remote_run_id = ""
        supplemental.remote_run_status = ""
        supplemental.remote_run_phase = ""
        supplemental.remote_run_busy = False
        supplemental.remote_run_running_state = ""
        supplemental.remote_run_control_mode = ""
        supplemental.remote_run_interrupt_requested = False
        supplemental.remote_run_cancel_requested = False
        supplemental.remote_run_resumable = False
        supplemental.remote_run_waiting_on_approval = False
        supplemental.remote_run_active_wait_id = None
        supplemental.remote_run_approval_wait = {}

    def apply_messages(self, session: Any, items: Sequence[dict[str, Any]]) -> None:
        self.replace_messages(
            session,
            self.build_chat_entries([item for item in items if isinstance(item, dict)]),
            True,
        )


__all__ = ["TuiRemoteSessionProjector"]
