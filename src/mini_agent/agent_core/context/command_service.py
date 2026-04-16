"""Shared prepared-context policy command semantics across surfaces."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

from mini_agent.agent_core.context.turn_context import resolve_turn_context_policy


def _safe_text(value: object) -> str:
    return " ".join(str(value or "").split())


SUPPORTED_CONTEXT_ACTIONS = frozenset(
    {
        "show",
        "stats",
        "include",
        "exclude",
        "budget",
        "reset",
    }
)

MUTATING_CONTEXT_ACTIONS = frozenset(
    {
        "include",
        "exclude",
        "budget",
        "reset",
    }
)


@dataclass(frozen=True, slots=True)
class ContextCommandRequest:
    action: str
    sources: tuple[str, ...] = ()
    max_items: int | None = None
    max_total_chars: int | None = None
    max_items_per_source: int | None = None


@dataclass(frozen=True, slots=True)
class ContextCommandError(Exception):
    detail: str
    status_code: int = 400

    def __str__(self) -> str:
        return self.detail


@dataclass(frozen=True, slots=True)
class ContextCommandMutation:
    action: str
    policy: dict[str, Any]
    command_name: str
    remote_request: dict[str, Any]


@dataclass(slots=True)
class ContextCommandService:
    @staticmethod
    def normalize_action(action: str) -> str:
        return _safe_text(action).lower().replace("-", "_")

    @staticmethod
    def is_mutating_action(action: str) -> bool:
        return ContextCommandService.normalize_action(action) in MUTATING_CONTEXT_ACTIONS

    def validate_action(self, action: str) -> str:
        normalized = self.normalize_action(action)
        if normalized not in SUPPORTED_CONTEXT_ACTIONS:
            raise ContextCommandError(f"Unsupported session context action: {action}")
        return normalized

    def validate_mutating_action(self, action: str) -> str:
        normalized = self.validate_action(action)
        if normalized not in MUTATING_CONTEXT_ACTIONS:
            raise ContextCommandError(f"Unsupported session context action: {action}")
        return normalized

    def apply_mutation(
        self,
        *,
        current_policy: Any,
        command: ContextCommandRequest,
    ) -> ContextCommandMutation:
        action = self.validate_mutating_action(command.action)
        normalized_policy = resolve_turn_context_policy(current_policy or {})

        if action in {"include", "exclude"}:
            normalized_sources = self._normalize_sources(command.sources)
            if not normalized_sources:
                raise ContextCommandError(
                    detail=f"Session context action requires sources: {action}",
                )
            field_name = "include_sources" if action == "include" else "exclude_sources"
            opposite_field = "exclude_sources" if field_name == "include_sources" else "include_sources"
            normalized_policy[field_name] = normalized_sources
            normalized_policy[opposite_field] = [
                item
                for item in list(normalized_policy.get(opposite_field) or [])
                if item not in normalized_sources
            ]
            normalized_policy = resolve_turn_context_policy(normalized_policy)
            remote_request = {
                "action": action,
                "sources": list(normalized_sources),
            }
        elif action == "budget":
            if command.max_items is None:
                raise ContextCommandError(detail="Session context budget requires max_items.")
            try:
                normalized_policy["max_items"] = max(1, int(command.max_items))
                if command.max_total_chars is not None:
                    normalized_policy["max_total_chars"] = max(200, int(command.max_total_chars))
                if command.max_items_per_source is not None:
                    normalized_policy["max_items_per_source"] = max(1, int(command.max_items_per_source))
            except Exception as exc:
                raise ContextCommandError("Context budget values must be integers.") from exc
            normalized_policy = resolve_turn_context_policy(normalized_policy)
            remote_request = {
                "action": action,
                "max_items": normalized_policy["max_items"],
                "max_total_chars": normalized_policy["max_total_chars"],
                "max_items_per_source": normalized_policy["max_items_per_source"],
            }
        else:
            normalized_policy = resolve_turn_context_policy({})
            remote_request = {"action": "reset"}

        return ContextCommandMutation(
            action=action,
            policy=normalized_policy,
            command_name=f"context {action}",
            remote_request=remote_request,
        )

    @staticmethod
    def _normalize_sources(value: Sequence[str] | None) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()
        for item in list(value or ()):
            cleaned = _safe_text(item).lower()
            if not cleaned or cleaned in seen:
                continue
            seen.add(cleaned)
            normalized.append(cleaned)
        return normalized


__all__ = [
    "ContextCommandError",
    "ContextCommandMutation",
    "ContextCommandRequest",
    "ContextCommandService",
    "MUTATING_CONTEXT_ACTIONS",
    "SUPPORTED_CONTEXT_ACTIONS",
]
