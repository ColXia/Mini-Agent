"""Tests for P13 T1.1 provider config normalization and validation."""

from __future__ import annotations

import pytest

from mini_agent.model_manager import (
    ProviderCatalog,
    ProviderConfig,
    normalize_provider_catalog,
    normalize_provider_config,
)


def test_provider_config_normalization_and_redaction():
    provider = normalize_provider_config(
        {
            "name": " OpenAI Primary ",
            "api_type": "openai",
            "api_base": "https://api.example.com/v1/",
            "api_key": " sk-1234567890abcdef ",
            "models": [" gpt-4o-mini ", "gpt-4o-mini", "gpt-4o"],
            "priority": "9",
            "timeout": 120,
            "model_context_windows": {
                " gpt-4o-mini ": "128000",
                "missing-model": 4096,
                "gpt-4o": -1,
            },
            "model_learned_token_limits": {
                " gpt-4o-mini ": "64000",
                "missing-model": 32000,
                "gpt-4o": 0,
            },
            "headers": {
                " X-Trace ": " trace-1 ",
                "Authorization": "should_be_filtered",
                "Host": "should_be_filtered",
            },
        }
    )

    assert provider.id == "openai-primary"
    assert provider.name == "OpenAI Primary"
    assert provider.api_base == "https://api.example.com/v1"
    assert provider.api_key == "sk-1234567890abcdef"
    assert provider.models == ["gpt-4o-mini", "gpt-4o"]
    assert provider.default_model == "gpt-4o-mini"
    assert provider.supports_model("GPT-4O") is True
    assert provider.priority == 9
    assert provider.headers == {"X-Trace": "trace-1"}
    assert provider.model_context_windows == {"gpt-4o-mini": 128000}
    assert provider.model_learned_token_limits == {"gpt-4o-mini": 64000}

    redacted = provider.redacted()
    assert redacted["api_key"] == "sk-1***cdef"


def test_provider_catalog_normalized_order_and_find():
    catalog = normalize_provider_catalog(
        {
            "providers": [
                {
                    "id": "b",
                    "name": "B Provider",
                    "api_type": "openai",
                    "api_base": "https://b.example.com/v1",
                    "api_key": "sk-b",
                    "models": ["b-1"],
                    "enabled": False,
                    "priority": 100,
                },
                {
                    "id": "a",
                    "name": "A Provider",
                    "api_type": "openai",
                    "api_base": "https://a.example.com/v1",
                    "api_key": "sk-a",
                    "models": ["a-1"],
                    "enabled": True,
                    "priority": 2,
                },
                {
                    "id": "c",
                    "name": "C Provider",
                    "api_type": "openai",
                    "api_base": "https://c.example.com/v1",
                    "api_key": "sk-c",
                    "models": ["c-1"],
                    "enabled": True,
                    "priority": 8,
                },
            ]
        }
    )

    assert [provider.id for provider in catalog.providers] == ["c", "a", "b"]
    assert [provider.id for provider in catalog.enabled()] == ["c", "a"]
    assert catalog.find("a") is not None
    assert catalog.find("missing") is None

    redacted = catalog.redacted()
    assert len(redacted["providers"]) == 3
    assert redacted["providers"][0]["api_key"] == "****"


def test_provider_config_legacy_custom_api_type_normalizes_to_openai():
    provider = normalize_provider_config(
        {
            "name": "Legacy Custom",
            "api_type": "custom",
            "api_base": "https://legacy.example.com/v1",
            "api_key": "sk-legacy-valid",
            "models": ["legacy-model"],
        }
    )

    assert provider.api_type.value == "openai"


@pytest.mark.parametrize(
    "payload",
    [
        {
            "name": "Bad URL",
            "api_type": "openai",
            "api_base": "ftp://bad.example.com",
            "api_key": "sk-valid",
            "models": ["x"],
        },
        {
            "name": "Missing model",
            "api_type": "openai",
            "api_base": "https://ok.example.com/v1",
            "api_key": "sk-valid",
            "models": [],
        },
        {
            "name": "Placeholder key",
            "api_type": "openai",
            "api_base": "https://ok.example.com/v1",
            "api_key": "YOUR_API_KEY_HERE",
            "models": ["x"],
        },
        {
            "id": "bad id!",
            "name": "Bad ID",
            "api_type": "openai",
            "api_base": "https://ok.example.com/v1",
            "api_key": "sk-valid",
            "models": ["x"],
        },
        {
            "name": "Bad timeout",
            "api_type": "openai",
            "api_base": "https://ok.example.com/v1",
            "api_key": "sk-valid",
            "models": ["x"],
            "timeout": 1,
        },
        {
            "name": "Gemini Removed",
            "api_type": "gemini",
            "api_base": "https://gemini.example.com",
            "api_key": "sk-valid",
            "models": ["gemini-2.5-pro"],
        },
    ],
)
def test_provider_config_validation_rejects_invalid_payloads(payload):
    with pytest.raises(Exception):
        normalize_provider_config(payload)


def test_provider_catalog_rejects_duplicate_ids():
    first = ProviderConfig(
        id="same",
        name="A",
        api_type="openai",
        api_base="https://a.example.com/v1",
        api_key="sk-a",
        models=["a"],
    )
    second = ProviderConfig(
        id="same",
        name="B",
        api_type="openai",
        api_base="https://b.example.com/v1",
        api_key="sk-b",
        models=["b"],
    )
    with pytest.raises(Exception):
        ProviderCatalog(providers=[first, second])
