from __future__ import annotations

import asyncio

from mini_agent.tui.gateway_client import TuiGatewayClient


def test_tui_gateway_client_create_session_sync_normalizes_payload() -> None:
    client = TuiGatewayClient(base_url="http://127.0.0.1:8008")
    captured: dict[str, object] = {}

    def _fake_request_json(method: str, path: str, *, query=None, payload=None):  # noqa: ANN001
        captured["method"] = method
        captured["path"] = path
        captured["query"] = query
        captured["payload"] = payload
        return {"session_id": "sess-1"}

    client._request_json = _fake_request_json  # type: ignore[method-assign]
    _ = client.create_session_sync(
        workspace_dir="D:/file/Mini-Agent",
        title="  Demo Session  ",
        surface=" ",
        shared=True,
    )

    assert captured["method"] == "POST"
    assert captured["path"] == "/api/v1/agent/sessions"
    assert captured["payload"] == {
        "workspace_dir": "D:/file/Mini-Agent",
        "title": "Demo Session",
        "surface": "tui",
        "shared": True,
    }


def test_tui_gateway_client_control_session_normalizes_binding_payload() -> None:
    async def _run() -> None:
        client = TuiGatewayClient(base_url="http://127.0.0.1:8008")
        captured: dict[str, object] = {}

        def _fake_request_json(method: str, path: str, *, query=None, payload=None):  # noqa: ANN001
            captured["method"] = method
            captured["path"] = path
            captured["query"] = query
            captured["payload"] = payload
            return {"status": "controlled"}

        client._request_json = _fake_request_json  # type: ignore[method-assign]
        await client.control_session(
            " sess-1 ",
            action=" compact ",
            reason="trim",
            surface=" qq ",
            channel_type=" qqbot ",
            conversation_id=" group:demo ",
            sender_id=" user-1 ",
        )

        assert captured["method"] == "POST"
        assert captured["path"] == "/api/v1/agent/sessions/sess-1/control"
        assert captured["payload"] == {
            "action": "compact",
            "reason": "trim",
            "surface": "qq",
            "channel_type": "qq",
            "conversation_id": "group:demo",
            "sender_id": "user-1",
        }

    asyncio.run(_run())


def test_tui_gateway_client_chat_payload_uses_default_surface() -> None:
    payload = TuiGatewayClient._chat_payload(
        session_id=" sess-2 ",
        message="hello",
        workspace_dir="D:/file/Mini-Agent",
        surface=" ",
    )

    assert payload == {
        "message": "hello",
        "session_id": "sess-2",
        "workspace_dir": "D:/file/Mini-Agent",
        "surface": "tui",
        "dry_run": False,
    }
