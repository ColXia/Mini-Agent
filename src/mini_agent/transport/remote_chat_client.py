"""Typed client-side remote chat client over the shared gateway transport."""

from __future__ import annotations

from typing import Any, AsyncIterator

from mini_agent.interfaces import MainAgentChatRequest, MainAgentChatResponse

from .chat_transport_port import RemoteChatTransportPort


class RemoteChatClient:
    """Typed client-side facade over remote chat transport."""

    def __init__(self, *, chat_transport: RemoteChatTransportPort) -> None:
        self._chat_transport = chat_transport

    async def run_chat(
        self,
        request: MainAgentChatRequest | None = None,
        **kwargs: Any,
    ) -> MainAgentChatResponse:
        if request is None:
            request = MainAgentChatRequest.model_validate(kwargs)
        elif kwargs:
            request = MainAgentChatRequest.model_validate({**request.model_dump(), **kwargs})
        payload = await self._chat_transport.run_chat(
            session_id=request.session_id or "",
            message=request.message,
            workspace_dir=request.workspace_dir or ".",
            surface=request.surface or "tui",
        )
        return MainAgentChatResponse.model_validate(payload)

    async def stream_chat_events(
        self,
        request: MainAgentChatRequest | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[tuple[str, dict[str, Any]]]:
        if request is None:
            request = MainAgentChatRequest.model_validate(kwargs)
        elif kwargs:
            request = MainAgentChatRequest.model_validate({**request.model_dump(), **kwargs})
        stream_chat = getattr(self._chat_transport, "stream_chat_events", None)
        if callable(stream_chat):
            async for event_type, payload in stream_chat(
                session_id=request.session_id or "",
                message=request.message,
                workspace_dir=request.workspace_dir or ".",
                surface=request.surface or "tui",
            ):
                yield event_type, payload
            return
        response = await self.run_chat(request)
        yield "done", response.model_dump()


__all__ = ["RemoteChatClient"]
