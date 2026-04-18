"""Runtime contract for session-scoped agent actions."""

from __future__ import annotations

from typing import Any, Protocol

from mini_agent.interfaces import (
    MainAgentSessionContextResponse,
    MainAgentSessionControlResponse,
    MainAgentSessionMemoryResponse,
    MainAgentSessionSkillResponse,
)


class SessionAgentRuntimePort(Protocol):
    """Typed runtime contract for session-scoped agent compatibility actions."""

    async def update_session_runtime_policy(
        self,
        session_id: str,
        *,
        approval_profile: str | None = None,
        access_level: str | None = None,
        surface: str | None = None,
        channel_type: str | None = None,
        conversation_id: str | None = None,
        sender_id: str | None = None,
    ) -> Any: ...

    async def control_session_context(
        self,
        session_id: str,
        *,
        action: str,
        reason: str | None = None,
        surface: str | None = None,
        channel_type: str | None = None,
        conversation_id: str | None = None,
        sender_id: str | None = None,
    ) -> MainAgentSessionControlResponse: ...

    async def update_session_context_policy(
        self,
        session_id: str,
        *,
        action: str,
        sources: list[str] | None = None,
        max_items: int | None = None,
        max_total_chars: int | None = None,
        max_items_per_source: int | None = None,
        surface: str | None = None,
        channel_type: str | None = None,
        conversation_id: str | None = None,
        sender_id: str | None = None,
    ) -> MainAgentSessionContextResponse: ...

    async def manage_session_memory(
        self,
        session_id: str,
        *,
        action: str,
        engram_id: str | None = None,
        content: str | None = None,
        query: str | None = None,
        day: str | None = None,
        export_format: str | None = None,
        detail_mode: str | None = None,
        surface: str | None = None,
        channel_type: str | None = None,
        conversation_id: str | None = None,
        sender_id: str | None = None,
    ) -> MainAgentSessionMemoryResponse: ...

    async def manage_session_skills(
        self,
        session_id: str,
        *,
        action: str,
        skill_name: str | None = None,
        path: str | None = None,
        query: str | None = None,
        mode: str | None = None,
        surface: str | None = None,
        channel_type: str | None = None,
        conversation_id: str | None = None,
        sender_id: str | None = None,
    ) -> MainAgentSessionSkillResponse: ...


__all__ = ["SessionAgentRuntimePort"]
