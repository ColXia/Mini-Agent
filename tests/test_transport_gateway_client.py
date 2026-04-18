from __future__ import annotations

import asyncio

from mini_agent.transport.gateway_client import GatewayClient


def test_gateway_client_create_session_sync_normalizes_payload() -> None:
    client = GatewayClient(base_url="http://127.0.0.1:8008")
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


def test_gateway_client_control_session_normalizes_binding_payload() -> None:
    async def _run() -> None:
        client = GatewayClient(base_url="http://127.0.0.1:8008")
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


def test_gateway_client_chat_payload_uses_default_surface() -> None:
    payload = GatewayClient._chat_payload(
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


def test_gateway_client_get_system_health_sync_uses_health_endpoint() -> None:
    client = GatewayClient(base_url="http://127.0.0.1:8008")
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


def test_gateway_client_update_session_runtime_policy_sync_normalizes_binding_payload() -> None:
    client = GatewayClient(base_url="http://127.0.0.1:8008")
    captured: dict[str, object] = {}

    def _fake_request_json(method: str, path: str, *, query=None, payload=None):  # noqa: ANN001
        captured["method"] = method
        captured["path"] = path
        captured["query"] = query
        captured["payload"] = payload
        return {"approval_profile": "build", "access_level": "default"}

    client._request_json = _fake_request_json  # type: ignore[method-assign]
    payload = client.update_session_runtime_policy_sync(
        " sess-1 ",
        approval_profile=" build ",
        access_level=" default ",
        surface=" desktop ",
    )

    assert payload == {"approval_profile": "build", "access_level": "default"}
    assert captured["method"] == "POST"
    assert captured["path"] == "/api/v1/agent/sessions/sess-1/policy"
    assert captured["payload"] == {
        "approval_profile": "build",
        "access_level": "default",
        "surface": "desktop",
        "channel_type": None,
        "conversation_id": None,
        "sender_id": None,
    }


def test_gateway_client_list_agent_models_sync_uses_models_endpoint() -> None:
    client = GatewayClient(base_url="http://127.0.0.1:8008")
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


def test_gateway_client_agent_model_binding_endpoints_use_typed_model_routes() -> None:
    client = GatewayClient(base_url="http://127.0.0.1:8008")
    captured: list[tuple[str, str, object, object]] = []

    def _fake_request_json(method: str, path: str, *, query=None, payload=None):  # noqa: ANN001
        captured.append((method, path, query, payload))
        return {"ok": True}

    client._request_json = _fake_request_json  # type: ignore[method-assign]

    assert client.list_agent_model_candidates_sync(agent_id=" main-agent ") == {"ok": True}
    assert client.get_current_agent_model_binding_sync(agent_id=" main-agent ") == {"ok": True}
    assert client.set_agent_model_binding_sync(
        agent_id=" main-agent ",
        provider_source=" custom ",
        provider_id=" maas ",
        model_id=" astron-code-latest ",
    ) == {"ok": True}
    assert client.get_current_agent_model_capabilities_sync(agent_id=" main-agent ") == {"ok": True}
    assert client.get_agent_model_binding_diagnostics_sync(agent_id=" main-agent ") == {"ok": True}

    assert captured == [
        ("GET", "/api/v1/agent/model/candidates", {"agent_id": "main-agent"}, None),
        ("GET", "/api/v1/agent/model/binding", {"agent_id": "main-agent"}, None),
        (
            "PUT",
            "/api/v1/agent/model/binding",
            None,
            {
                "agent_id": "main-agent",
                "provider_source": "custom",
                "provider_id": "maas",
                "model_id": "astron-code-latest",
            },
        ),
        ("GET", "/api/v1/agent/model/capabilities", {"agent_id": "main-agent"}, None),
        ("GET", "/api/v1/agent/model/diagnostics", {"agent_id": "main-agent"}, None),
    ]


def test_gateway_client_list_ops_models_sync_uses_ops_models_endpoint() -> None:
    client = GatewayClient(base_url="http://127.0.0.1:8008")
    captured: dict[str, object] = {}

    def _fake_request_json(method: str, path: str, *, query=None, payload=None):  # noqa: ANN001
        captured["method"] = method
        captured["path"] = path
        captured["query"] = query
        captured["payload"] = payload
        return {"items": []}

    client._request_json = _fake_request_json  # type: ignore[method-assign]
    payload = client.list_ops_models_sync(catalog_path=" D:/file/Mini-Agent/providers.json ")

    assert payload == {"items": []}
    assert captured["method"] == "GET"
    assert captured["path"] == "/api/v1/ops/models"
    assert captured["query"] == {"catalog_path": "D:/file/Mini-Agent/providers.json"}
    assert captured["payload"] is None


def test_gateway_client_list_ops_providers_sync_uses_ops_providers_endpoint() -> None:
    client = GatewayClient(base_url="http://127.0.0.1:8008")
    captured: dict[str, object] = {}

    def _fake_request_json(method: str, path: str, *, query=None, payload=None):  # noqa: ANN001
        captured["method"] = method
        captured["path"] = path
        captured["query"] = query
        captured["payload"] = payload
        return {"items": []}

    client._request_json = _fake_request_json  # type: ignore[method-assign]
    payload = client.list_ops_providers_sync()

    assert payload == {"items": []}
    assert captured["method"] == "GET"
    assert captured["path"] == "/api/v1/ops/providers"
    assert captured["query"] == {"catalog_path": None}
    assert captured["payload"] is None


def test_gateway_client_set_model_role_sync_uses_ops_role_endpoint() -> None:
    client = GatewayClient(base_url="http://127.0.0.1:8008")
    captured: dict[str, object] = {}

    def _fake_request_json(method: str, path: str, *, query=None, payload=None):  # noqa: ANN001
        captured["method"] = method
        captured["path"] = path
        captured["query"] = query
        captured["payload"] = payload
        return {"provider_id": "maas"}

    client._request_json = _fake_request_json  # type: ignore[method-assign]
    payload = client.set_model_role_sync(
        source=" custom ",
        provider_id=" maas ",
        model_id=" astron-code-latest ",
        model_role=" chat ",
    )

    assert payload == {"provider_id": "maas"}
    assert captured["method"] == "PATCH"
    assert captured["path"] == "/api/v1/ops/models/role"
    assert captured["payload"] == {
        "source": "custom",
        "provider_id": "maas",
        "model_id": "astron-code-latest",
        "model_role": "chat",
    }


def test_gateway_client_probe_model_capabilities_sync_uses_ops_probe_endpoint() -> None:
    client = GatewayClient(base_url="http://127.0.0.1:8008")
    captured: dict[str, object] = {}

    def _fake_request_json(method: str, path: str, *, query=None, payload=None):  # noqa: ANN001
        captured["method"] = method
        captured["path"] = path
        captured["query"] = query
        captured["payload"] = payload
        return {"model_id": "astron-code-latest"}

    client._request_json = _fake_request_json  # type: ignore[method-assign]
    payload = client.probe_model_capabilities_sync(
        source="preset",
        provider_id="minimax",
        model_id="MiniMax-M2.7",
    )

    assert payload == {"model_id": "astron-code-latest"}
    assert captured["method"] == "POST"
    assert captured["path"] == "/api/v1/ops/models/probe"
    assert captured["payload"] == {
        "source": "preset",
        "provider_id": "minimax",
        "model_id": "MiniMax-M2.7",
    }


def test_gateway_client_bind_feature_model_sync_uses_ops_bindings_endpoint() -> None:
    client = GatewayClient(base_url="http://127.0.0.1:8008")
    captured: dict[str, object] = {}

    def _fake_request_json(method: str, path: str, *, query=None, payload=None):  # noqa: ANN001
        captured["method"] = method
        captured["path"] = path
        captured["query"] = query
        captured["payload"] = payload
        return {"feature_role": "embedding"}

    client._request_json = _fake_request_json  # type: ignore[method-assign]
    payload = client.bind_feature_model_sync(
        feature_role=" embedding ",
        source=" custom ",
        provider_id=" ollama ",
        model_id=" qwen3-embedding:0.6b ",
    )

    assert payload == {"feature_role": "embedding"}
    assert captured["method"] == "PUT"
    assert captured["path"] == "/api/v1/ops/models/bindings"
    assert captured["payload"] == {
        "feature_role": "embedding",
        "source": "custom",
        "provider_id": "ollama",
        "model_id": "qwen3-embedding:0.6b",
    }


def test_gateway_client_discover_provider_models_sync_uses_discovery_endpoint() -> None:
    client = GatewayClient(base_url="http://127.0.0.1:8008")
    captured: dict[str, object] = {}

    def _fake_request_json(method: str, path: str, *, query=None, payload=None):  # noqa: ANN001
        captured["method"] = method
        captured["path"] = path
        captured["query"] = query
        captured["payload"] = payload
        return {"latest_model_id": "astron-code-latest", "models": []}

    client._request_json = _fake_request_json  # type: ignore[method-assign]
    payload = client.discover_provider_models_sync(
        api_type=" openai ",
        api_base=" https://example.com/v2 ",
        api_key=" test-key ",
    )

    assert payload == {"latest_model_id": "astron-code-latest", "models": []}
    assert captured["method"] == "POST"
    assert captured["path"] == "/api/v1/ops/providers/model-discovery"
    assert captured["query"] is None
    assert captured["payload"] == {
        "api_type": "openai",
        "api_base": "https://example.com/v2",
        "api_key": "test-key",
    }


def test_gateway_client_validate_provider_connection_sync_uses_validation_endpoint() -> None:
    client = GatewayClient(base_url="http://127.0.0.1:8008")
    captured: dict[str, object] = {}

    def _fake_request_json(method: str, path: str, *, query=None, payload=None):  # noqa: ANN001
        captured["method"] = method
        captured["path"] = path
        captured["query"] = query
        captured["payload"] = payload
        return {"status": "reachable_no_models", "message": "Connection ok."}

    client._request_json = _fake_request_json  # type: ignore[method-assign]
    payload = client.validate_provider_connection_sync(
        api_type=" ollama ",
        api_base=" http://127.0.0.1:11434/v1 ",
        api_key=" ",
    )

    assert payload == {"status": "reachable_no_models", "message": "Connection ok."}
    assert captured["method"] == "POST"
    assert captured["path"] == "/api/v1/ops/providers/validate"
    assert captured["query"] is None
    assert captured["payload"] == {
        "api_type": "ollama",
        "api_base": "http://127.0.0.1:11434/v1",
        "api_key": None,
    }


def test_gateway_client_create_provider_sync_uses_ops_provider_create_endpoint() -> None:
    client = GatewayClient(base_url="http://127.0.0.1:8008")
    captured: dict[str, object] = {}

    def _fake_request_json(method: str, path: str, *, query=None, payload=None):  # noqa: ANN001
        captured["method"] = method
        captured["path"] = path
        captured["query"] = query
        captured["payload"] = payload
        return {"id": "maas-smoke"}

    client._request_json = _fake_request_json  # type: ignore[method-assign]
    payload = client.create_provider_sync(
        payload={
            "id": "maas-smoke",
            "name": "MaaS Smoke",
            "api_type": "openai",
            "api_base": "https://example.com/v2",
            "api_key": "secret",
            "models": ["astron-code-latest"],
        }
    )

    assert payload == {"id": "maas-smoke"}
    assert captured["method"] == "POST"
    assert captured["path"] == "/api/v1/ops/providers"
    assert captured["payload"] == {
        "id": "maas-smoke",
        "name": "MaaS Smoke",
        "api_type": "openai",
        "api_base": "https://example.com/v2",
        "api_key": "secret",
        "models": ["astron-code-latest"],
    }


def test_gateway_client_update_provider_sync_uses_ops_provider_update_endpoint() -> None:
    client = GatewayClient(base_url="http://127.0.0.1:8008")
    captured: dict[str, object] = {}

    def _fake_request_json(method: str, path: str, *, query=None, payload=None):  # noqa: ANN001
        captured["method"] = method
        captured["path"] = path
        captured["query"] = query
        captured["payload"] = payload
        return {"id": "ollama-local"}

    client._request_json = _fake_request_json  # type: ignore[method-assign]
    payload = client.update_provider_sync(
        provider_id=" ollama-local ",
        payload={
            "name": "Ollama Local",
            "api_type": "ollama",
            "api_base": "http://127.0.0.1:11434",
            "api_key": "unused",
            "models": ["qwen3.5:9b"],
        },
        catalog_path=" D:/file/Mini-Agent/providers.json ",
    )

    assert payload == {"id": "ollama-local"}
    assert captured["method"] == "PUT"
    assert captured["path"] == "/api/v1/ops/providers/ollama-local"
    assert captured["query"] == {"catalog_path": "D:/file/Mini-Agent/providers.json"}
    assert captured["payload"] == {
        "name": "Ollama Local",
        "api_type": "ollama",
        "api_base": "http://127.0.0.1:11434",
        "api_key": "unused",
        "models": ["qwen3.5:9b"],
    }


def test_gateway_client_get_ops_memory_summary_sync_uses_memory_summary_endpoint() -> None:
    client = GatewayClient(base_url="http://127.0.0.1:8008")
    captured: dict[str, object] = {}

    def _fake_request_json(method: str, path: str, *, query=None, payload=None):  # noqa: ANN001
        captured["method"] = method
        captured["path"] = path
        captured["query"] = query
        captured["payload"] = payload
        return {"workspace_dir": "D:/file/Mini-Agent"}

    client._request_json = _fake_request_json  # type: ignore[method-assign]
    payload = client.get_ops_memory_summary_sync(workspace_dir=" D:/file/Mini-Agent ")

    assert payload == {"workspace_dir": "D:/file/Mini-Agent"}
    assert captured["method"] == "GET"
    assert captured["path"] == "/api/v1/ops/memory/summary"
    assert captured["query"] == {"workspace_dir": "D:/file/Mini-Agent"}
    assert captured["payload"] is None


def test_gateway_client_search_ops_memory_sync_uses_memory_search_endpoint() -> None:
    client = GatewayClient(base_url="http://127.0.0.1:8008")
    captured: dict[str, object] = {}

    def _fake_request_json(method: str, path: str, *, query=None, payload=None):  # noqa: ANN001
        captured["method"] = method
        captured["path"] = path
        captured["query"] = query
        captured["payload"] = payload
        return {"items": [], "total": 0}

    client._request_json = _fake_request_json  # type: ignore[method-assign]
    payload = client.search_ops_memory_sync(
        query=" routing facts ",
        limit=12,
        workspace_dir=" D:/file/Mini-Agent ",
    )

    assert payload == {"items": [], "total": 0}
    assert captured["method"] == "GET"
    assert captured["path"] == "/api/v1/ops/memory/search"
    assert captured["query"] == {
        "query": "routing facts",
        "limit": 12,
        "workspace_dir": "D:/file/Mini-Agent",
    }
    assert captured["payload"] is None


def test_gateway_client_get_ops_memory_daily_sync_uses_memory_daily_endpoint() -> None:
    client = GatewayClient(base_url="http://127.0.0.1:8008")
    captured: dict[str, object] = {}

    def _fake_request_json(method: str, path: str, *, query=None, payload=None):  # noqa: ANN001
        captured["method"] = method
        captured["path"] = path
        captured["query"] = query
        captured["payload"] = payload
        return {"day": "2026-04-17"}

    client._request_json = _fake_request_json  # type: ignore[method-assign]
    payload = client.get_ops_memory_daily_sync(
        day=" 2026-04-17 ",
        workspace_dir=" D:/file/Mini-Agent ",
    )

    assert payload == {"day": "2026-04-17"}
    assert captured["method"] == "GET"
    assert captured["path"] == "/api/v1/ops/memory/daily/2026-04-17"
    assert captured["query"] == {"workspace_dir": "D:/file/Mini-Agent"}
    assert captured["payload"] is None


def test_gateway_client_ensure_default_session_sync_uses_default_endpoint() -> None:
    client = GatewayClient(base_url="http://127.0.0.1:8008")
    captured: dict[str, object] = {}

    def _fake_request_json(method: str, path: str, *, query=None, payload=None):  # noqa: ANN001
        captured["method"] = method
        captured["path"] = path
        captured["query"] = query
        captured["payload"] = payload
        return {"session_id": "default"}

    client._request_json = _fake_request_json  # type: ignore[method-assign]
    payload = client.ensure_default_session_sync(
        workspace_dir="D:/file/Mini-Agent/sub",
        surface=" desktop ",
        channel_type=" qqbot ",
        conversation_id=" group:demo ",
        sender_id=" user-1 ",
    )

    assert payload == {"session_id": "default"}
    assert captured["method"] == "POST"
    assert captured["path"] == "/api/v1/agent/sessions/default"
    assert captured["payload"] == {
        "workspace_dir": "D:/file/Mini-Agent/sub",
        "surface": "desktop",
        "channel_type": "qq",
        "conversation_id": "group:demo",
        "sender_id": "user-1",
    }


def test_gateway_client_list_workspaces_sync_uses_workspace_endpoint() -> None:
    client = GatewayClient(base_url="http://127.0.0.1:8008")
    captured: dict[str, object] = {}

    def _fake_request_json(method: str, path: str, *, query=None, payload=None):  # noqa: ANN001
        captured["method"] = method
        captured["path"] = path
        captured["query"] = query
        captured["payload"] = payload
        return [{"workspace_id": "ws-1"}]

    client._request_json = _fake_request_json  # type: ignore[method-assign]
    payload = client.list_workspaces_sync()

    assert payload == [{"workspace_id": "ws-1"}]
    assert captured["method"] == "GET"
    assert captured["path"] == "/api/v1/agent/workspaces"
    assert captured["query"] is None
    assert captured["payload"] is None


def test_gateway_client_get_workspace_sync_uses_workspace_resolve_endpoint() -> None:
    client = GatewayClient(base_url="http://127.0.0.1:8008")
    captured: dict[str, object] = {}

    def _fake_request_json(method: str, path: str, *, query=None, payload=None):  # noqa: ANN001
        captured["method"] = method
        captured["path"] = path
        captured["query"] = query
        captured["payload"] = payload
        return {"workspace_id": "ws-1"}

    client._request_json = _fake_request_json  # type: ignore[method-assign]
    payload = client.get_workspace_sync(" D:/file/Mini-Agent ")

    assert payload == {"workspace_id": "ws-1"}
    assert captured["method"] == "GET"
    assert captured["path"] == "/api/v1/agent/workspaces/resolve"
    assert captured["query"] == {"workspace_id": "D:/file/Mini-Agent"}
    assert captured["payload"] is None


def test_gateway_client_switch_workspace_sync_uses_workspace_switch_endpoint() -> None:
    client = GatewayClient(base_url="http://127.0.0.1:8008")
    captured: dict[str, object] = {}

    def _fake_request_json(method: str, path: str, *, query=None, payload=None):  # noqa: ANN001
        captured["method"] = method
        captured["path"] = path
        captured["query"] = query
        captured["payload"] = payload
        return {"workspace_id": "ws-1", "switched": True}

    client._request_json = _fake_request_json  # type: ignore[method-assign]
    payload = client.switch_workspace_sync(" D:/file/Mini-Agent ")

    assert payload == {"workspace_id": "ws-1", "switched": True}
    assert captured["method"] == "POST"
    assert captured["path"] == "/api/v1/agent/workspaces/switch"
    assert captured["query"] is None
    assert captured["payload"] == {"workspace_id": "D:/file/Mini-Agent"}


def test_gateway_client_get_workspace_runtime_summary_sync_uses_workspace_runtime_endpoint() -> None:
    client = GatewayClient(base_url="http://127.0.0.1:8008")
    captured: dict[str, object] = {}

    def _fake_request_json(method: str, path: str, *, query=None, payload=None):  # noqa: ANN001
        captured["method"] = method
        captured["path"] = path
        captured["query"] = query
        captured["payload"] = payload
        return {"workspace_id": "ws-1", "runtime": {"mode": "direct"}}

    client._request_json = _fake_request_json  # type: ignore[method-assign]
    payload = client.get_workspace_runtime_summary_sync(workspace_id=" D:/file/Mini-Agent ")

    assert payload == {"workspace_id": "ws-1", "runtime": {"mode": "direct"}}
    assert captured["method"] == "GET"
    assert captured["path"] == "/api/v1/agent/workspaces/runtime"
    assert captured["query"] == {"workspace_id": "D:/file/Mini-Agent"}
    assert captured["payload"] is None


def test_gateway_client_update_session_model_sync_uses_model_endpoint() -> None:
    client = GatewayClient(base_url="http://127.0.0.1:8008")
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


def test_gateway_client_create_derived_session_sync_uses_fork_endpoint() -> None:
    client = GatewayClient(base_url="http://127.0.0.1:8008")
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


def test_gateway_client_rename_session_sync_uses_patch_endpoint() -> None:
    client = GatewayClient(base_url="http://127.0.0.1:8008")
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


def test_gateway_client_set_session_shared_sync_uses_share_endpoint() -> None:
    client = GatewayClient(base_url="http://127.0.0.1:8008")
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


def test_gateway_client_control_session_sync_normalizes_binding_payload() -> None:
    client = GatewayClient(base_url="http://127.0.0.1:8008")
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


def test_gateway_client_cancel_session_normalizes_binding_payload() -> None:
    async def _run() -> None:
        client = GatewayClient(base_url="http://127.0.0.1:8008")
        captured: dict[str, object] = {}

        def _fake_request_json(method: str, path: str, *, query=None, payload=None):  # noqa: ANN001
            captured["method"] = method
            captured["path"] = path
            captured["query"] = query
            captured["payload"] = payload
            return {"status": "cancel_requested"}

        client._request_json = _fake_request_json  # type: ignore[method-assign]
        await client.cancel_session(
            " sess-1 ",
            reason=" user_cancel ",
            surface=" qqbot ",
            channel_type=" qqbot ",
            conversation_id=" group:demo ",
            sender_id=" user-1 ",
        )

        assert captured["method"] == "POST"
        assert captured["path"] == "/api/v1/agent/sessions/sess-1/cancel"
        assert captured["payload"] == {
            "reason": " user_cancel ",
            "surface": "qq",
            "channel_type": "qq",
            "conversation_id": "group:demo",
            "sender_id": "user-1",
        }

    asyncio.run(_run())


def test_gateway_client_respond_to_approval_sync_uses_approval_endpoint() -> None:
    client = GatewayClient(base_url="http://127.0.0.1:8008")
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
