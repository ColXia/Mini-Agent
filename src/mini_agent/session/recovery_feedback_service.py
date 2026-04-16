"""Shared recovery/status feedback semantics for remote interaction surfaces."""

from __future__ import annotations

from typing import Sequence

from .projection import SessionPendingApprovalProjection, SessionRecoveryProjection


def _safe_text(value: object | None) -> str:
    return " ".join(str(value or "").split())


def _compact_text(value: object | None, *, max_length: int = 120) -> str | None:
    normalized = _safe_text(value)
    if not normalized:
        return None
    if len(normalized) <= max_length:
        return normalized
    return f"{normalized[: max_length - 3]}..."


class SessionRecoveryFeedbackService:
    """Own user-facing remote recovery/status text across remote adapters."""

    @staticmethod
    def route_ownership(
        *,
        origin_surface: str | None,
        active_surface: str | None,
        reply_enabled: bool,
    ) -> str:
        origin = (_safe_text(origin_surface) or "remote").lower()
        active = (_safe_text(active_surface) or origin or "unknown").lower()
        flow = origin if origin == active else f"{origin}->{active}"
        ownership = "reply" if reply_enabled else "own"
        return f"{flow} / {ownership}"

    @classmethod
    def build_remote_recovery_text(
        cls,
        *,
        session_id: str | None,
        origin_surface: str | None,
        active_surface: str | None,
        reply_enabled: bool,
        recovery: SessionRecoveryProjection | None,
        pending_approvals: Sequence[SessionPendingApprovalProjection] | None = None,
        pending_skill_reload: bool = False,
        pending_skill_reload_reason: str | None = None,
    ) -> str:
        normalized_recovery = recovery or SessionRecoveryProjection(state="idle", summary="idle")
        live_approvals = [item for item in pending_approvals or () if _safe_text(item.token)]
        lost_approvals = [
            item for item in normalized_recovery.pending_approvals if _safe_text(item.token)
        ]
        recovery_state = _safe_text(normalized_recovery.state) or "idle"
        recovery_summary = _safe_text(normalized_recovery.summary) or recovery_state or "idle"

        lines = [
            "Shared-session recovery:",
            f"sessionId: {_safe_text(session_id) or '(unknown)'}",
            (
                "route: "
                + cls.route_ownership(
                    origin_surface=origin_surface,
                    active_surface=active_surface,
                    reply_enabled=reply_enabled,
                )
            ),
            f"state: {recovery_state}",
            f"task: {recovery_summary}",
        ]

        last_activity = _safe_text(normalized_recovery.last_activity)
        if last_activity:
            lines.append(f"activity: {last_activity}")

        last_user = _compact_text(normalized_recovery.last_user_message)
        if last_user:
            lines.append(f"last user: {last_user}")

        last_assistant = _compact_text(normalized_recovery.last_assistant_message)
        if last_assistant:
            lines.append(f"last reply: {last_assistant}")

        if pending_skill_reload:
            reason = _safe_text(pending_skill_reload_reason)
            suffix = f" ({reason})" if reason else ""
            lines.append(f"skills: reload pending{suffix}")

        if live_approvals:
            tokens = ", ".join(f"{item.tool_name}[{item.token}]" for item in live_approvals)
            lines.append(f"pending approvals: {tokens}")
        elif lost_approvals:
            tokens = ", ".join(f"{item.tool_name}[{item.token}]" for item in lost_approvals)
            lines.append(f"lost approvals after restart: {tokens}")
            lines.append("resume hint: send a new message to continue with recovery context")
        elif recovery_state.lower() == "interrupted":
            lines.append("resume hint: send a new message to continue with recovery context")

        return "\n".join(lines)


__all__ = ["SessionRecoveryFeedbackService"]
