from __future__ import annotations

import asyncio
from datetime import datetime

import pytest

from mini_agent.model_manager.model_discovery import (
    DiscoveryResult,
    ModelDiscoveryCache,
    ModelDiscoveryService,
    ModelInfo,
    ProviderType,
    _normalize_provider_type,
    _should_bypass_proxy_env,
    infer_model_capabilities,
)


def test_model_discovery_bypasses_proxy_env_for_loopback_hosts() -> None:
    assert _should_bypass_proxy_env("http://localhost:11434") is True
    assert _should_bypass_proxy_env("http://127.0.0.1:11434/v1/models") is True
    assert _should_bypass_proxy_env("http://[::1]:11434/api/tags") is True
    assert _should_bypass_proxy_env("https://api.openai.com/v1") is False


def test_model_discovery_disables_trust_env_for_loopback(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class _FakeAsyncClient:
        def __init__(self, *, timeout, trust_env):  # noqa: ANN001
            captured["timeout"] = timeout
            captured["trust_env"] = trust_env

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):  # noqa: ANN001
            return None

    async def _fake_fetch_ollama_models(self, client, url, api_key):  # noqa: ANN001
        _ = (self, client, url, api_key)
        return []

    monkeypatch.setattr("mini_agent.model_manager.model_discovery.httpx.AsyncClient", _FakeAsyncClient)
    monkeypatch.setattr(ModelDiscoveryService, "_fetch_ollama_models", _fake_fetch_ollama_models)

    asyncio.run(
        ModelDiscoveryService()._fetch_models(  # noqa: SLF001
            ProviderType.OLLAMA,
            "ollama",
            "http://localhost:11434",
        )
    )

    assert captured["trust_env"] is False


def test_model_discovery_keeps_trust_env_for_remote_hosts(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class _FakeAsyncClient:
        def __init__(self, *, timeout, trust_env):  # noqa: ANN001
            captured["timeout"] = timeout
            captured["trust_env"] = trust_env

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):  # noqa: ANN001
            return None

    async def _fake_fetch_openai_models(self, client, url, api_key):  # noqa: ANN001
        _ = (self, client, url, api_key)
        return []

    monkeypatch.setattr("mini_agent.model_manager.model_discovery.httpx.AsyncClient", _FakeAsyncClient)
    monkeypatch.setattr(ModelDiscoveryService, "_fetch_openai_models", _fake_fetch_openai_models)

    asyncio.run(
        ModelDiscoveryService()._fetch_models(  # noqa: SLF001
            ProviderType.OPENAI,
            "sk-test",
            "https://relay.example.com/v1/models",
        )
    )

    assert captured["trust_env"] is True


def test_model_discovery_rejects_removed_gemini_provider_type() -> None:
    with pytest.raises(ValueError):
        ProviderType("gemini")

    assert _normalize_provider_type("gemini") == ProviderType.CUSTOM


def test_model_discovery_uses_curated_manifest_for_minimax(monkeypatch) -> None:
    class _UnexpectedAsyncClient:
        def __init__(self, *args, **kwargs):  # noqa: ANN002, ANN003
            raise AssertionError("minimax discovery should not instantiate an HTTP client")

    monkeypatch.setattr("mini_agent.model_manager.model_discovery.httpx.AsyncClient", _UnexpectedAsyncClient)

    result = asyncio.run(
        ModelDiscoveryService().discover_models(
            ProviderType.MINIMAX,
            "sk-minimax",
            "https://api.minimaxi.com",
            use_cache=False,
        )
    )

    assert result.discovery_source == "curated_manifest"
    assert result.models[0].id == "MiniMax-M2.7"


def test_model_discovery_fetch_models_uses_curated_manifest_for_minimax() -> None:
    models = asyncio.run(
        ModelDiscoveryService()._fetch_models(  # noqa: SLF001
            ProviderType.MINIMAX,
            "sk-minimax",
            "https://api.minimaxi.com",
        )
    )

    assert [item.id for item in models[:3]] == [
        "MiniMax-M2.7",
        "MiniMax-M2.5",
        "MiniMax-M1",
    ]


def test_model_discovery_cache_scopes_entries_by_normalized_base_url(tmp_path) -> None:
    cache = ModelDiscoveryCache(cache_dir=tmp_path)
    result = DiscoveryResult(
        provider=ProviderType.OPENAI,
        models=[
            ModelInfo(
                id="gpt-5.4",
                name="gpt-5.4",
                provider=ProviderType.OPENAI,
            )
        ],
        fetched_at=datetime.now(),
        discovery_source="api_discovery",
    )

    cache.set(
        result,
        api_base="https://relay-a.example.com/v1/models",
        protocol_flavor="openai-models",
    )

    same_scope = cache.get(
        ProviderType.OPENAI,
        api_base="https://relay-a.example.com/v1/",
        protocol_flavor="openai-models",
    )
    different_scope = cache.get(
        ProviderType.OPENAI,
        api_base="https://relay-b.example.com/v1/models",
        protocol_flavor="openai-models",
    )

    assert same_scope is not None
    assert same_scope.models[0].id == "gpt-5.4"
    assert different_scope is None


def test_infer_model_capabilities_keeps_unknown_without_evidence() -> None:
    capabilities = infer_model_capabilities(
        ProviderType.OPENAI,
        "gpt-5.4",
        raw_capabilities=[],
    )

    assert capabilities["supports_tools"] is None
    assert capabilities["supports_tools_truth"] == "unknown"
    assert capabilities["supports_tools_confidence"] == "low"
    assert capabilities["supports_tools_source"] == "no_capability_evidence"
    assert capabilities["supports_thinking"] is None
    assert capabilities["supports_thinking_truth"] == "unknown"
    assert capabilities["supports_thinking_confidence"] == "low"
    assert capabilities["supports_thinking_source"] == "no_capability_evidence"


def test_infer_model_capabilities_marks_supported_when_api_capabilities_are_present() -> None:
    capabilities = infer_model_capabilities(
        ProviderType.OPENAI,
        "gpt-5.4",
        raw_capabilities=["tool_use", "reasoning"],
    )

    assert capabilities["supports_tools"] is True
    assert capabilities["supports_tools_truth"] == "supported"
    assert capabilities["supports_tools_confidence"] == "high"
    assert capabilities["supports_tools_source"] == "api_capabilities"
    assert capabilities["supports_thinking"] is True
    assert capabilities["supports_thinking_truth"] == "supported"
    assert capabilities["supports_thinking_confidence"] == "high"
    assert capabilities["supports_thinking_source"] == "api_capabilities"
