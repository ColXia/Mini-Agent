"""Service-facing contract for remote chat client operations."""

from __future__ import annotations

from typing import Any, AsyncIterator, Protocol

from mini_agent.interfaces.agent import MainAgentChatRequest, MainAgentChatResponse


class RemoteChatServicePort(Protocol):
    """Chat service contract consumed by TUI/Desktop remote chat surfaces."""

    async def run_chat(
        self,
        request: MainAgentChatRequest | None = None,
        **kwargs: Any,
    ) -> MainAgentChatResponse | dict[str, Any]: ...

    async def stream_chat_events(
        self,
        request: MainAgentChatRequest | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[tuple[str, dict[str, Any]]]: ...


__all__ = ["RemoteChatServicePort"]
