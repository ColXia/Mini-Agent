"""Tests for Open WebUI OpenAI-compatible adapter API."""

from __future__ import annotations

import json
from typing import Any

from fastapi.testclient import TestClient

from apps.open_webui.adapter import (
    AdapterChatResult,
    GatewayRequestError,
    OpenWebUIAdapter,
    OpenWebUIAdapterConfig,
)
from apps.open_webui.main import _build_guardrail_warnings, create_open_webui_adapter_app


class _AdapterStub:
    def __init__(
        self,
        *,
        models: tuple[str, ...] = ("mini-agent",),
        result: AdapterChatResult | None = None,
        error: Exception | None = None,
    ) -> None:
        self._models = models
        self._result = result or AdapterChatResult(session_id="sess-1", reply="hello", token_usage=5)
        self._error = error
        self.calls: list[dict[str, Any]] = []

    def list_models(self) -> tuple[str, ...]:
        return self._models

    def chat(
        self,
        *,
        messages: list[dict[str, Any]],
        user: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> AdapterChatResult:
        self.calls.append({"messages": messages, "user": user, "metadata": metadata})
        if self._error is not None:
            raise self._error
        return self._result


def test_open_webui_models_requires_adapter_token_when_configured() -> None:
    config = OpenWebUIAdapterConfig(adapter_api_keys=("key-1",))
    adapter = _AdapterStub(models=("mini-agent", "mini-agent-lite"))
    app = create_open_webui_adapter_app(config=config, adapter=adapter)

    with TestClient(app) as client:
        assert client.get("/v1/models").status_code == 401
        assert client.get("/v1/models", headers={"Authorization": "Bearer wrong"}).status_code == 401

        by_bearer = client.get("/v1/models", headers={"Authorization": "Bearer key-1"})
        assert by_bearer.status_code == 200
        assert [item["id"] for item in by_bearer.json()["data"]] == ["mini-agent", "mini-agent-lite"]

        by_api_key = client.get("/v1/models", headers={"x-api-key": "key-1"})
        assert by_api_key.status_code == 200


def test_open_webui_chat_completions_non_stream_shape() -> None:
    config = OpenWebUIAdapterConfig(default_model="mini-agent-default")
    adapter = _AdapterStub(result=AdapterChatResult(session_id="sess-xyz", reply="done", token_usage=9))
    app = create_open_webui_adapter_app(config=config, adapter=adapter)

    with TestClient(app) as client:
        response = client.post(
            "/v1/chat/completions",
            json={
                "messages": [{"role": "user", "content": "hello"}],
                "user": "alice",
                "metadata": {"conversation_id": "conv-1"},
            },
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["object"] == "chat.completion"
        assert payload["model"] == "mini-agent-default"
        assert payload["choices"][0]["message"]["role"] == "assistant"
        assert payload["choices"][0]["message"]["content"] == "done"
        assert payload["usage"]["total_tokens"] == 9
        assert payload["session_id"] == "sess-xyz"
        assert adapter.calls[0]["user"] == "alice"
        assert adapter.calls[0]["metadata"] == {"conversation_id": "conv-1"}


def test_open_webui_chat_completions_stream_emits_done_event() -> None:
    config = OpenWebUIAdapterConfig()
    adapter = _AdapterStub(result=AdapterChatResult(session_id="sess-stream", reply="stream body", token_usage=4))
    app = create_open_webui_adapter_app(config=config, adapter=adapter)

    with TestClient(app) as client:
        response = client.post(
            "/v1/chat/completions",
            json={
                "messages": [{"role": "user", "content": "hello stream"}],
                "model": "mini-agent-stream",
                "stream": True,
            },
        )
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")

        data_lines = [line[len("data: ") :] for line in response.text.splitlines() if line.startswith("data: ")]
        assert data_lines[-1] == "[DONE]"

        chunks = [json.loads(item) for item in data_lines if item != "[DONE]"]
        assert chunks[0]["choices"][0]["delta"]["role"] == "assistant"
        assert chunks[-1]["choices"][0]["finish_reason"] == "stop"
        content_chunks = [
            item["choices"][0]["delta"].get("content", "")
            for item in chunks
            if item["choices"][0]["delta"].get("content")
        ]
        assert "".join(content_chunks) == "stream body"


def test_open_webui_chat_completions_reuses_gateway_session_by_conversation() -> None:
    captured_payloads: list[dict[str, Any]] = []

    def _transport(payload: dict[str, Any]) -> dict[str, Any]:
        captured_payloads.append(dict(payload))
        return {
            "session_id": payload.get("session_id") or "sess-conv-001",
            "reply": "ok",
            "token_usage": 1,
        }

    config = OpenWebUIAdapterConfig(adapter_api_keys=("key-1",))
    adapter = OpenWebUIAdapter(config=config, transport=_transport)
    app = create_open_webui_adapter_app(config=config, adapter=adapter)

    request_payload = {
        "messages": [{"role": "user", "content": "hello"}],
        "user": "alice",
        "metadata": {"conversation_id": "conv-42"},
    }
    headers = {"Authorization": "Bearer key-1"}

    with TestClient(app) as client:
        first = client.post("/v1/chat/completions", json=request_payload, headers=headers)
        assert first.status_code == 200
        second = client.post(
            "/v1/chat/completions",
            json={
                "messages": [{"role": "user", "content": "next"}],
                "user": "alice",
                "metadata": {"conversation_id": "conv-42"},
            },
            headers=headers,
        )
        assert second.status_code == 200
        assert second.json()["session_id"] == "sess-conv-001"

    assert captured_payloads[0]["session_id"] is None
    assert captured_payloads[1]["session_id"] == "sess-conv-001"


def test_open_webui_chat_completions_maps_adapter_failure_to_502() -> None:
    config = OpenWebUIAdapterConfig()
    adapter = _AdapterStub(error=GatewayRequestError("gateway offline"))
    app = create_open_webui_adapter_app(config=config, adapter=adapter)

    with TestClient(app) as client:
        response = client.post(
            "/v1/chat/completions",
            json={"messages": [{"role": "user", "content": "hello"}]},
        )
        assert response.status_code == 502
        assert "gateway offline" in response.json()["detail"]


def test_open_webui_health_contains_guardrail_warnings() -> None:
    config = OpenWebUIAdapterConfig(
        gateway_base_url="https://gateway.example.com",
        gateway_auth_token=None,
        adapter_api_keys=(),
        default_model="mini-agent",
        available_models=("mini-agent",),
        timeout_seconds=301,
    )
    app = create_open_webui_adapter_app(config=config, adapter=_AdapterStub())

    with TestClient(app) as client:
        response = client.get("/health")
        assert response.status_code == 200
        payload = response.json()
        assert payload["guardrail_warning_count"] >= 3
        warnings = "\n".join(payload["guardrail_warnings"])
        assert "adapter_auth_disabled" in warnings
        assert "gateway_auth_missing" in warnings
        assert "timeout_too_high" in warnings


def test_guardrail_primary_key_mismatch_warning() -> None:
    config = OpenWebUIAdapterConfig(
        adapter_api_keys=("k1", "k2"),
        default_model="mini-agent",
        available_models=("mini-agent",),
    )
    warnings = _build_guardrail_warnings(
        config=config,
        env={"MINI_AGENT_OPENWEBUI_PRIMARY_API_KEY": "k3"},
    )
    assert any("primary_key_not_allowed" in item for item in warnings)
