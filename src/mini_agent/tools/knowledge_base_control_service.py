"""Shared session knowledge-base control semantics."""

from __future__ import annotations

import inspect
from dataclasses import dataclass
from typing import Any, Awaitable, Callable


async def _maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


@dataclass(frozen=True, slots=True)
class KnowledgeBaseStatus:
    enabled: bool | None
    summary: str


@dataclass(frozen=True, slots=True)
class KnowledgeBaseToggleResult:
    action: str
    desired_enabled: bool
    effective_enabled: bool
    applied: bool


class KnowledgeBaseControlService:
    """Own the semantic state transitions for session KB toggles."""

    @staticmethod
    def status(*, current_enabled: bool | None) -> KnowledgeBaseStatus:
        if current_enabled is None:
            return KnowledgeBaseStatus(
                enabled=None,
                summary="knowledge base pending default",
            )
        enabled = bool(current_enabled)
        return KnowledgeBaseStatus(
            enabled=enabled,
            summary=f"knowledge base {'enabled' if enabled else 'disabled'}",
        )

    @staticmethod
    def toggle_summary(*, enabled: bool, applied: bool) -> str:
        if enabled:
            return "knowledge base enabled" if applied else "knowledge base already enabled"
        return "knowledge base disabled" if applied else "knowledge base already disabled"

    @staticmethod
    def control_details(
        *,
        action: str,
        enabled: bool,
        reason: str | None = None,
    ) -> str:
        lines = [
            f"Action: {action}",
            f"Knowledge Base: {'enabled' if enabled else 'disabled'}",
        ]
        if str(reason or "").strip():
            lines.append(f"Reason: {str(reason).strip()}")
        return "\n".join(lines)

    @classmethod
    async def toggle(
        cls,
        *,
        current_enabled: bool | None,
        desired_enabled: bool,
        toggle_callback: Callable[[bool], Awaitable[bool | None] | bool | None] | None,
    ) -> KnowledgeBaseToggleResult:
        if toggle_callback is None:
            raw_enabled = desired_enabled
        else:
            raw_enabled = await _maybe_await(toggle_callback(desired_enabled))
        effective_enabled = bool(raw_enabled) if raw_enabled is not None else bool(current_enabled)
        return KnowledgeBaseToggleResult(
            action="kb_on" if desired_enabled else "kb_off",
            desired_enabled=desired_enabled,
            effective_enabled=effective_enabled,
            applied=(current_enabled != effective_enabled),
        )


__all__ = [
    "KnowledgeBaseControlService",
    "KnowledgeBaseStatus",
    "KnowledgeBaseToggleResult",
]
