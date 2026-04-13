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


def test_tui_gateway_client_get_system_health_sync_uses_health_endpoint() -> None:
    client = TuiGatewayClient(base_url="http://127.0.0.1:8008")
    captured: dict[str, object] = {}

    def _fake_request_json(method: str, path: str, *, query=None, payload=None):  # noqa: ANN001
        captured["method"] = method
        captured["path"] = path
        captured["query"] = query
        captured["payload"] = payload
        return {"status": "ok"}

    client._request_json = _fake_request_json  # type: ignore[method-assign]
    payload = client.get_system_health_sync()

    assert payload == {"status": "ok"}
    assert captured["method"] == "GET"
    assert captured["path"] == "/api/v1/system/health"
    assert captured["query"] is None
    assert captured["payload"] is None


def test_tui_gateway_client_list_agent_models_sync_uses_models_endpoint() -> None:
    client = TuiGatewayClient(base_url="http://127.0.0.1:8008")
    captured: dict[str, object] = {}

    def _fake_request_json(method: str, path: str, *, query=None, payload=None):  # noqa: ANN001
        captured["method"] = method
        captured["path"] = path
        captured["query"] = query
        captured["payload"] = payload
        return {"items": []}

    client._request_json = _fake_request_json  # type: ignore[method-assign]
    payload = client.list_agent_models_sync()

    assert payload == {"items": []}
    assert captured["method"] == "GET"
    assert captured["path"] == "/api/v1/agent/models"
    assert captured["query"] is None
    assert captured["payload"] is None


def test_tui_gateway_client_update_session_model_sync_uses_model_endpoint() -> None:
    client = TuiGatewayClient(base_url="http://127.0.0.1:8008")
    captured: dict[str, object] = {}

    def _fake_request_json(method: str, path: str, *, query=None, payload=None):  # noqa: ANN001
        captured["method"] = method
        captured["path"] = path
        captured["query"] = query
        captured["payload"] = payload
        return {"status": "selected"}

    client._request_json = _fake_request_json  # type: ignore[method-assign]
    payload = client.update_session_model_sync(
        " sess-1 ",
        provider_source="preset",
        provider_id="openai",
        model_id="gpt-5.4",
        surface=" desktop ",
    )

    assert payload == {"status": "selected"}
    assert captured["method"] == "POST"
    assert captured["path"] == "/api/v1/agent/sessions/sess-1/model"
    assert captured["payload"] == {
        "provider_source": "preset",
        "provider_id": "openai",
        "model_id": "gpt-5.4",
        "surface": "desktop",
        "channel_type": None,
        "conversation_id": None,
        "sender_id": None,
    }


def test_tui_gateway_client_create_derived_session_sync_uses_fork_endpoint() -> None:
    client = TuiGatewayClient(base_url="http://127.0.0.1:8008")
    captured: dict[str, object] = {}

    def _fake_request_json(method: str, path: str, *, query=None, payload=None):  # noqa: ANN001
        captured["method"] = method
        captured["path"] = path
        captured["query"] = query
        captured["payload"] = payload
        return {"session_id": "sess-2"}

    client._request_json = _fake_request_json  # type: ignore[method-assign]
    payload = client.create_derived_session_sync(
        " parent-1 ",
        title=" Child Session ",
        surface=" desktop ",
    )

    assert payload == {"session_id": "sess-2"}
    assert captured["method"] == "POST"
    assert captured["path"] == "/api/v1/agent/sessions/parent-1/fork"
    assert captured["payload"] == {
        "title": "Child Session",
        "surface": "desktop",
        "channel_type": None,
        "conversation_id": None,
        "sender_id": None,
    }


def test_tui_gateway_client_rename_session_sync_uses_patch_endpoint() -> None:
    client = TuiGatewayClient(base_url="http://127.0.0.1:8008")
    captured: dict[str, object] = {}

    def _fake_request_json(method: str, path: str, *, query=None, payload=None):  # noqa: ANN001
        captured["method"] = method
        captured["path"] = path
        captured["query"] = query
        captured["payload"] = payload
        return {"status": "renamed"}

    client._request_json = _fake_request_json  # type: ignore[method-assign]
    payload = client.rename_session_sync(" sess-1 ", title="  Demo Session  ")

    assert payload == {"status": "renamed"}
    assert captured["method"] == "PATCH"
    assert captured["path"] == "/api/v1/agent/sessions/sess-1"
    assert captured["payload"] == {"title": "Demo Session"}


def test_tui_gateway_client_set_session_shared_sync_uses_share_endpoint() -> None:
    client = TuiGatewayClient(base_url="http://127.0.0.1:8008")
    captured: dict[str, object] = {}

    def _fake_request_json(method: str, path: str, *, query=None, payload=None):  # noqa: ANN001
        captured["method"] = method
        captured["path"] = path
        captured["query"] = query
        captured["payload"] = payload
        return {"status": "shared"}

    client._request_json = _fake_request_json  # type: ignore[method-assign]
    payload = client.set_session_shared_sync(" sess-1 ", shared=True)

    assert payload == {"status": "shared"}
    assert captured["method"] == "POST"
    assert captured["path"] == "/api/v1/agent/sessions/sess-1/share"
    assert captured["payload"] == {"shared": True}


def test_tui_gateway_client_control_session_sync_normalizes_binding_payload() -> None:
    client = TuiGatewayClient(base_url="http://127.0.0.1:8008")
    captured: dict[str, object] = {}

    def _fake_request_json(method: str, path: str, *, query=None, payload=None):  # noqa: ANN001
        captured["method"] = method
        captured["path"] = path
        captured["query"] = query
        captured["payload"] = payload
        return {"status": "controlled"}

    client._request_json = _fake_request_json  # type: ignore[method-assign]
    payload = client.control_session_sync(
        " sess-1 ",
        action=" compact ",
        reason="trim",
        surface=" desktop ",
    )

    assert payload == {"status": "controlled"}
    assert captured["method"] == "POST"
    assert captured["path"] == "/api/v1/agent/sessions/sess-1/control"
    assert captured["payload"] == {
        "action": "compact",
        "reason": "trim",
        "surface": "desktop",
        "channel_type": None,
        "conversation_id": None,
        "sender_id": None,
    }


def test_tui_gateway_client_respond_to_approval_sync_uses_approval_endpoint() -> None:
    client = TuiGatewayClient(base_url="http://127.0.0.1:8008")
    captured: dict[str, object] = {}

    def _fake_request_json(method: str, path: str, *, query=None, payload=None):  # noqa: ANN001
        captured["method"] = method
        captured["path"] = path
        captured["query"] = query
        captured["payload"] = payload
        return {"decision": "approved"}

    client._request_json = _fake_request_json  # type: ignore[method-assign]
    payload = client.respond_to_approval_sync(
        " sess-1 ",
        approved=True,
        token=" tok-1 ",
        surface="desktop",
    )

    assert payload == {"decision": "approved"}
    assert captured["method"] == "POST"
    assert captured["path"] == "/api/v1/agent/sessions/sess-1/approval"
    assert captured["payload"] == {
        "approved": True,
        "token": "tok-1",
        "surface": "desktop",
        "channel_type": None,
        "conversation_id": None,
        "sender_id": None,
    }
