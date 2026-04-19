from __future__ import annotations

import asyncio

from mini_agent.interfaces.agent import MainAgentChatRequest
from mini_agent.transport.remote_chat_client import RemoteChatClient


class _DummyGatewayClient:
    async def run_chat(
        self,
        *,
        session_id: str,
        message: str,
        workspace_dir: str,
        surface: str = "tui",
    ):
        return {
            "session_id": session_id or "sess-1",
            "reply": f"echo: {message}",
            "message_count": 2,
            "token_usage": 12,
            "workspace_dir": workspace_dir,
            "updated_at": "2026-04-18T08:00:00Z",
        }

    async def stream_chat_events(
        self,
        *,
        session_id: str,
        message: str,
        workspace_dir: str,
        surface: str = "tui",
    ):
        yield "done", {
            "session_id": session_id or "sess-1",
            "reply": f"stream:{message}",
            "message_count": 2,
            "token_usage": 13,
            "workspace_dir": workspace_dir,
            "updated_at": "2026-04-18T08:00:01Z",
        }


def test_remote_chat_client_shapes_gateway_payload_into_typed_response() -> None:
    async def _run() -> None:
        service = RemoteChatClient(chat_transport=_DummyGatewayClient())
        response = await service.run_chat(
            MainAgentChatRequest(
                session_id="sess-1",
                message="hello",
                workspace_dir="D:/file/Mini-Agent",
                surface="desktop",
            )
        )

        assert response.session_id == "sess-1"
        assert response.reply == "echo: hello"
        assert response.token_usage == 12

    asyncio.run(_run())


def test_remote_chat_client_passes_through_stream_events() -> None:
    async def _run() -> None:
        service = RemoteChatClient(chat_transport=_DummyGatewayClient())
        events: list[tuple[str, dict[str, object]]] = []

        async for event_type, payload in service.stream_chat_events(
            session_id="sess-1",
            message="hello",
            workspace_dir="D:/file/Mini-Agent",
            surface="tui",
        ):
            events.append((event_type, payload))

        assert events == [
            (
                "done",
                {
                    "session_id": "sess-1",
                    "reply": "stream:hello",
                    "message_count": 2,
                    "token_usage": 13,
                    "workspace_dir": "D:/file/Mini-Agent",
                    "updated_at": "2026-04-18T08:00:01Z",
                },
            )
        ]

    asyncio.run(_run())
