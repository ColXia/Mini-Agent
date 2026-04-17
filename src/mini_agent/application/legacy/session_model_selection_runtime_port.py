"""Compatibility runtime port for session-scoped model selection actions."""

from __future__ import annotations

from typing import Protocol

from mini_agent.interfaces import MainAgentSessionModelSelectionResponse


class SessionModelSelectionRuntimePort(Protocol):
    """Runtime contract for session-era model-selection compatibility actions."""

    async def update_session_model_selection(
        self,
        session_id: str,
        *,
        provider_source: str | None = None,
        provider_id: str | None = None,
        model_id: str | None = None,
        surface: str | None = None,
        channel_type: str | None = None,
        conversation_id: str | None = None,
        sender_id: str | None = None,
    ) -> MainAgentSessionModelSelectionResponse: ...


__all__ = ["SessionModelSelectionRuntimePort"]
