"""TUI-facing remote session projection helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Sequence

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
                payloads.append(item.to_transport().model_dump())
            except Exception:
                continue
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
            self.replace_messages(
                session,
                self.build_chat_entries([item.to_transport().model_dump() for item in detail.recent_messages]),
                preserve_follow_output,
            )
        state.supplemental.remote_last_command_summary = self.last_command_summary(session)
        return True

    def apply_messages(self, session: Any, items: Sequence[dict[str, Any]]) -> None:
        self.replace_messages(
            session,
            self.build_chat_entries([item for item in items if isinstance(item, dict)]),
            True,
        )


__all__ = ["TuiRemoteSessionProjector"]
