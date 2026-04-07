"""Tests for Open WebUI adapter core behavior."""

from __future__ import annotations

from typing import Any

import pytest

from apps.open_webui.adapter import (
    GatewayRequestError,
    OpenWebUIAdapter,
    OpenWebUIAdapterConfig,
    OpenWebUIAdapterError,
)


def test_open_webui_adapter_config_from_env_parses_and_normalizes() -> None:
    config = OpenWebUIAdapterConfig.from_env(
        {
            "MINI_AGENT_GATEWAY_BASE_URL": "http://127.0.0.1:8008/",
            "MINI_AGENT_OPENWEBUI_GATEWAY_TOKEN": " gateway-token ",
            "MINI_AGENT_OPENWEBUI_API_KEYS": " key-a, key-b ,,",
            "MINI_AGENT_OPENWEBUI_DEFAULT_MODEL": "mini-agent-strong",
            "MINI_AGENT_OPENWEBUI_MODELS": "mini-agent-strong,mini-agent-lite",
            "MINI_AGENT_OPENWEBUI_TIMEOUT_SECONDS": "0.2",
            "MINI_AGENT_OPENWEBUI_CHANNEL_TYPE": "open_webui_custom",
        }
    )

    assert config.gateway_base_url == "http://127.0.0.1:8008"
    assert config.gateway_auth_token == "gateway-token"
    assert config.adapter_api_keys == ("key-a", "key-b")
    assert config.default_model == "mini-agent-strong"
    assert config.available_models == ("mini-agent-strong", "mini-agent-lite")
    assert config.timeout_seconds == 1.0
    assert config.channel_type == "open_webui_custom"


def test_open_webui_adapter_chat_reuses_session_for_same_conversation() -> None:
    captured_payloads: list[dict[str, Any]] = []

    def _transport(payload: dict[str, Any]) -> dict[str, Any]:
        captured_payloads.append(dict(payload))
        return {
            "session_id": payload.get("session_id") or "sess-openwebui-001",
            "reply": "ok",
            "token_usage": "7",
            "workspace_dir": payload.get("workspace_dir"),
        }

    adapter = OpenWebUIAdapter(transport=_transport)

    first = adapter.chat(
        messages=[{"role": "user", "content": "hello"}],
        user="alice",
        metadata={"conversation_id": "conv-1", "workspace_dir": "C:/tmp/project"},
    )
    second = adapter.chat(
        messages=[{"role": "user", "content": "hello again"}],
        user="alice",
        metadata={"conversation_id": "conv-1"},
    )

    assert first.session_id == "sess-openwebui-001"
    assert second.session_id == "sess-openwebui-001"
    assert first.token_usage == 7
    assert first.workspace_dir == "C:/tmp/project"

    assert captured_payloads[0]["session_id"] is None
    assert captured_payloads[1]["session_id"] == "sess-openwebui-001"
    assert captured_payloads[0]["conversation_id"] == "conv-1"
    assert captured_payloads[0]["sender_id"] == "alice"


def test_open_webui_adapter_chat_extracts_text_from_content_chunks() -> None:
    captured_payloads: list[dict[str, Any]] = []

    def _transport(payload: dict[str, Any]) -> dict[str, Any]:
        captured_payloads.append(dict(payload))
        return {"session_id": "sess-1", "reply": "ok", "token_usage": 1}

    adapter = OpenWebUIAdapter(transport=_transport)
    adapter.chat(
        messages=[
            {"role": "assistant", "content": "old"},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "line-1"},
                    {"type": "image_url", "image_url": "ignored"},
                    "line-2",
                ],
            },
        ]
    )

    assert captured_payloads[0]["message"] == "line-1\nline-2"


def test_open_webui_adapter_chat_rejects_empty_prompt() -> None:
    adapter = OpenWebUIAdapter(transport=lambda _payload: {"session_id": "x", "reply": "ok", "token_usage": 1})
    with pytest.raises(OpenWebUIAdapterError, match="no usable prompt"):
        adapter.chat(messages=[{"role": "user", "content": []}])


def test_open_webui_adapter_chat_requires_gateway_session_id() -> None:
    adapter = OpenWebUIAdapter(transport=lambda _payload: {"reply": "ok", "token_usage": 1})
    with pytest.raises(GatewayRequestError, match="missing session_id"):
        adapter.chat(messages=[{"role": "user", "content": "hello"}])


def test_open_webui_default_transport_uses_v1_envelope(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    class _Resp:
        status_code = 200
        text = '{"ok": true}'

        @staticmethod
        def json() -> dict[str, Any]:
            return {
                "ok": True,
                "data": {
                    "session_id": "sess-v1-001",
                    "reply": "hello-from-v1",
                    "token_usage": 3,
                    "workspace_dir": "C:/tmp/work",
                },
                "error": None,
            }

    def _post(url: str, **kwargs: Any) -> _Resp:
        captured["url"] = url
        captured["kwargs"] = kwargs
        return _Resp()

    monkeypatch.setattr("apps.open_webui.adapter.requests.post", _post)
    adapter = OpenWebUIAdapter(config=OpenWebUIAdapterConfig(gateway_base_url="http://127.0.0.1:8008"))

    result = adapter.chat(messages=[{"role": "user", "content": "hello"}])

    assert captured["url"].endswith("/api/v1/agent/chat")
    assert result.session_id == "sess-v1-001"
    assert result.reply == "hello-from-v1"
    assert result.token_usage == 3


def test_open_webui_default_transport_rejects_contract_error(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Resp:
        status_code = 200
        text = '{"ok": false}'

        @staticmethod
        def json() -> dict[str, Any]:
            return {
                "ok": False,
                "data": None,
                "error": {"code": "bad_request", "message": "blocked"},
            }

    def _post(_url: str, **_kwargs: Any) -> _Resp:
        return _Resp()

    monkeypatch.setattr("apps.open_webui.adapter.requests.post", _post)
    adapter = OpenWebUIAdapter(config=OpenWebUIAdapterConfig(gateway_base_url="http://127.0.0.1:8008"))

    with pytest.raises(GatewayRequestError, match="contract error"):
        adapter.chat(messages=[{"role": "user", "content": "hello"}])
