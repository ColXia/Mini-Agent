"""Shared formatting and normalization for context-control actions."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


def _safe_text(value: object) -> str:
    return " ".join(str(value or "").split())


def _safe_nonnegative_int(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


@dataclass(frozen=True, slots=True)
class SessionContextControlResult:
    action: str
    applied: bool
    message_count_before: int
    message_count_after: int
    token_count_before: int
    token_count_after: int
    stats: dict[str, int] = field(default_factory=dict)
    summary: str = ""
    details: str = ""


class SessionContextControlResultService:
    """Normalize session context-control results across runtime and surfaces."""

    @staticmethod
    def validate_action(action: str) -> str:
        normalized = _safe_text(action).lower().replace("-", "_")
        if normalized in {"compact", "drop_memories"}:
            return normalized
        raise ValueError(f"Unsupported context control action: {action}")

    @classmethod
    def normalize_result(
        cls,
        *,
        action: str,
        payload: Any,
        reason: str | None = None,
    ) -> SessionContextControlResult:
        normalized_action = cls.validate_action(action)
        result = payload if isinstance(payload, dict) else {"applied": bool(payload)}
        applied = bool(result.get("applied", False))
        stats = result.get("stats") if isinstance(result.get("stats"), dict) else {}
        normalized_stats = {
            "masked_messages": _safe_nonnegative_int(stats.get("masked_messages")),
            "snipped_messages": _safe_nonnegative_int(stats.get("snipped_messages")),
            "merged_messages": _safe_nonnegative_int(stats.get("merged_messages")),
        }
        before_messages = _safe_nonnegative_int(result.get("message_count_before"))
        after_messages = _safe_nonnegative_int(result.get("message_count_after"))
        before_tokens = _safe_nonnegative_int(result.get("token_count_before"))
        after_tokens = _safe_nonnegative_int(result.get("token_count_after"))
        return SessionContextControlResult(
            action=normalized_action,
            applied=applied,
            message_count_before=before_messages,
            message_count_after=after_messages,
            token_count_before=before_tokens,
            token_count_after=after_tokens,
            stats=normalized_stats,
            summary=cls.summary(action=normalized_action, applied=applied),
            details=cls.details(
                action=normalized_action,
                message_count_before=before_messages,
                message_count_after=after_messages,
                token_count_before=before_tokens,
                token_count_after=after_tokens,
                stats=normalized_stats,
                reason=reason,
            ),
        )

    @classmethod
    def summary(cls, *, action: str, applied: bool) -> str:
        normalized_action = cls.validate_action(action)
        if normalized_action == "compact":
            return "context compacted" if applied else "context already compact"
        return "older memories dropped" if applied else "no older memories to drop"

    @classmethod
    def details(
        cls,
        *,
        action: str,
        message_count_before: int,
        message_count_after: int,
        token_count_before: int,
        token_count_after: int,
        stats: dict[str, int] | None = None,
        reason: str | None = None,
    ) -> str:
        normalized_action = cls.validate_action(action)
        detail_lines = [
            f"Action: {normalized_action}",
            f"Messages: {_safe_nonnegative_int(message_count_before)} -> {_safe_nonnegative_int(message_count_after)}",
            f"Tokens: {_safe_nonnegative_int(token_count_before)} -> {_safe_nonnegative_int(token_count_after)}",
        ]
        normalized_reason = _safe_text(reason)
        if normalized_reason:
            detail_lines.append(f"Reason: {normalized_reason}")
        normalized_stats = stats if isinstance(stats, dict) else {}
        if normalized_stats:
            detail_lines.append(
                "Stats: "
                f"masked={_safe_nonnegative_int(normalized_stats.get('masked_messages'))}, "
                f"snipped={_safe_nonnegative_int(normalized_stats.get('snipped_messages'))}, "
                f"merged={_safe_nonnegative_int(normalized_stats.get('merged_messages'))}"
            )
        return "\n".join(detail_lines)

    @classmethod
    def tui_status_text(
        cls,
        *,
        result: SessionContextControlResult,
        session_title: str,
    ) -> str:
        if result.action == "compact":
            return (
                f"Compacted {session_title}: {result.token_count_before} -> {result.token_count_after} tokens."
                if result.applied
                else f"{session_title} context was already compact."
            )
        return (
            f"Dropped older memories for {session_title}: {result.token_count_before} -> {result.token_count_after} tokens."
            if result.applied
            else f"No older memories needed dropping for {session_title}."
        )

    @classmethod
    def cli_label(cls, *, result: SessionContextControlResult) -> str:
        if result.action == "compact":
            return "Context compacted" if result.applied else "Context already compact"
        return "Older memories dropped" if result.applied else "No older memories needed dropping"


__all__ = [
    "SessionContextControlResult",
    "SessionContextControlResultService",
]
