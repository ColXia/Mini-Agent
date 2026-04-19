"""Terminal-facing session presentation models."""

from __future__ import annotations

from dataclasses import dataclass

from mini_agent.session.projections import SessionSummaryProjection


def _safe_text(value: object | None) -> str:
    return " ".join(str(value or "").split())


@dataclass(frozen=True)
class TerminalSessionProjection:
    source_tag: str
    scope_summary: str
    route_summary: str
    share_state: str
    share_summary: str
    peer_summary: str
    has_external_peer: bool
    show_gateway_panel: bool
    recovery_pending: bool
    last_command_preview: str | None = None

    @classmethod
    def from_summary(
        cls,
        summary: SessionSummaryProjection,
        *,
        has_local_runtime_state: bool,
        last_command_preview: str | None = None,
    ) -> TerminalSessionProjection:
        source_tag = (_safe_text(summary.channel_type) or _safe_text(summary.origin_surface) or "tui").lower()
        origin_surface = _safe_text(summary.origin_surface) or "tui"
        active_surface = _safe_text(summary.active_surface) or origin_surface
        surface_flow = origin_surface if origin_surface == active_surface else f"{origin_surface} -> {active_surface}"

        has_external_peer = any(
            (
                _safe_text(summary.channel_type),
                _safe_text(summary.conversation_id),
                _safe_text(summary.sender_id),
            )
        )
        is_local_only_surface = not has_external_peer and source_tag in {"tui", "cli", "local"}

        recovery = summary.recovery
        recovery_pending = bool(
            recovery is not None
            and _safe_text(recovery.state).lower() == "interrupted"
            and (
                (not has_local_runtime_state)
                or has_external_peer
                or bool(_safe_text(recovery.summary))
            )
        )
        show_gateway_panel = any(
            (
                has_external_peer,
                recovery_pending,
                bool(_safe_text(getattr(recovery, "last_activity", None))),
                (not has_local_runtime_state) and source_tag not in {"tui", "cli"},
            )
        )

        share_state = "shared" if bool(summary.shared) else ("local only" if is_local_only_surface else "private")
        compact_share_state = {
            "locked by origin": "locked",
            "wait until idle": "wait idle",
        }.get(share_state, share_state)
        if is_local_only_surface:
            share_summary = compact_share_state
        elif surface_flow and surface_flow != source_tag:
            share_summary = f"{compact_share_state} {surface_flow.replace(' -> ', '->')}"
        else:
            share_summary = compact_share_state

        channel = _safe_text(summary.channel_type).lower()
        conversation = _safe_text(summary.conversation_id)
        if channel and conversation:
            peer_summary = f"{channel}/{conversation}"
        else:
            peer_summary = conversation or channel or "no external peer"

        return cls(
            source_tag=source_tag,
            scope_summary=f"{'shared' if bool(summary.shared) else 'private'} [{source_tag}]",
            route_summary=(
                f"{surface_flow.replace(' -> ', '->')} / "
                f"{'reply' if bool(summary.reply_enabled) else 'own'} / "
                f"{'local' if has_local_runtime_state else 'gateway'}"
            ),
            share_state=share_state,
            share_summary=share_summary,
            peer_summary=peer_summary,
            has_external_peer=has_external_peer,
            show_gateway_panel=show_gateway_panel,
            recovery_pending=recovery_pending,
            last_command_preview=_safe_text(last_command_preview) or None,
        )


__all__ = ["TerminalSessionProjection"]

