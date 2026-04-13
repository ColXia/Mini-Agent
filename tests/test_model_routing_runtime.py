"""Tests for runtime routed LLM settings resolution."""

from __future__ import annotations

import json

import pytest

from mini_agent.config import (
    OFFICIAL_PRESET_ENV_KEYS,
    AgentConfig,
    Config,
    LLMConfig,
    SecurityConfig,
    ToolsConfig,
)
from mini_agent.model_manager.preset_providers import PresetProvider, get_preset_provider_config
from mini_agent.model_manager.runtime import (
    get_circuit_breaker_registry,
    reset_model_manager_runtime_state,
    resolve_session_model_selection_identity,
    resolve_routed_llm_candidates,
    resolve_routed_llm_settings,
)


def _make_config(*, provider: str = "anthropic", model: str = "MiniMax-M2.5") -> Config:
    return Config(
        llm=LLMConfig(
            api_key="cfg-key",
            api_base="https://api.minimaxi.com",
            provider=provider,
            model=model,
        ),
        agent=AgentConfig(),
        tools=ToolsConfig(enable_mcp=False, enable_skills=False),
        security=SecurityConfig(),
    )


@pytest.fixture(autouse=True)
def _reset_runtime_state():
    reset_model_manager_runtime_state()
    yield
    reset_model_manager_runtime_state()


@pytest.fixture(autouse=True)
def _clear_preset_provider_keys(monkeypatch):
    for env_key in OFFICIAL_PRESET_ENV_KEYS:
        # Keep keys present-but-empty so load_dotenv(override=False) cannot
        # repopulate real local keys from .env.local during this test module.
        monkeypatch.setenv(env_key, "")


def test_resolve_routed_llm_settings_falls_back_to_config_without_catalog(monkeypatch, tmp_path):
    # Isolate from machine-level ~/.mini-agent/providers.json.
    monkeypatch.setenv("MINI_AGENT_PROVIDER_CATALOG_PATH", str(tmp_path / "missing.json"))
    config = _make_config(provider="anthropic", model="MiniMax-M2.5")

    resolved = resolve_routed_llm_settings(config, requested_model="MiniMax-M2.5")
    assert resolved.source == "config"
    assert resolved.model == "MiniMax-M2.5"
    assert resolved.api_key == "cfg-key"
    assert resolved.api_base == "https://api.minimaxi.com"
    assert resolved.provider.value == "anthropic"


def test_resolve_routed_llm_settings_uses_provider_catalog(monkeypatch, tmp_path):
    catalog_path = tmp_path / "providers.json"
    catalog_path.write_text(
        json.dumps(
            {
                "providers": [
                    {
                        "id": "openai-secondary",
                        "name": "OpenAI Secondary",
                        "api_type": "openai",
                        "api_base": "https://openai.secondary.example.com/v1",
                        "api_key": "sk-openai-secondary",
                        "models": ["gpt-4o-mini"],
                        "enabled": True,
                        "priority": 4,
                    },
                    {
                        "id": "anth-primary",
                        "name": "Anthropic Primary",
                        "api_type": "anthropic",
                        "api_base": "https://anth.primary.example.com",
                        "api_key": "sk-anth-primary",
                        "models": ["claude-3-5-sonnet", "claude-3-7-sonnet"],
                        "enabled": True,
                        "priority": 7,
                    },
                ]
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("MINI_AGENT_PROVIDER_CATALOG_PATH", str(catalog_path))
    config = _make_config(provider="anthropic", model="claude")

    resolved = resolve_routed_llm_settings(config, requested_model="claude")
    assert resolved.source == "provider_catalog"
    assert resolved.provider_id == "anth-primary"
    assert resolved.provider.value == "anthropic"
    assert resolved.api_base == "https://anth.primary.example.com"
    assert resolved.api_key == "sk-anth-primary"
    assert resolved.model in {"claude-3-5-sonnet", "claude-3-7-sonnet"}
    assert resolved.mapping_mode in {"exact", "partial", "fallback_default"}


def test_resolve_routed_llm_candidates_skip_open_breaker_provider(monkeypatch, tmp_path):
    catalog_path = tmp_path / "providers.json"
    catalog_path.write_text(
        json.dumps(
            {
                "providers": [
                    {
                        "id": "anth-primary",
                        "name": "Anthropic Primary",
                        "api_type": "anthropic",
                        "api_base": "https://anth.primary.example.com",
                        "api_key": "sk-anth-primary",
                        "models": ["claude-3-7-sonnet"],
                        "enabled": True,
                        "priority": 9,
                    },
                    {
                        "id": "openai-secondary",
                        "name": "OpenAI Secondary",
                        "api_type": "openai",
                        "api_base": "https://openai.secondary.example.com/v1",
                        "api_key": "sk-openai-secondary",
                        "models": ["gpt-4o-mini"],
                        "enabled": True,
                        "priority": 6,
                    },
                ]
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("MINI_AGENT_PROVIDER_CATALOG_PATH", str(catalog_path))
    config = _make_config(provider="anthropic", model="claude")

    breakers = get_circuit_breaker_registry()
    for _ in range(4):
        breakers.record_failure("anth-primary", reason="open-threshold")

    candidates = resolve_routed_llm_candidates(config, requested_model="claude")
    assert candidates[0].provider_id == "openai-secondary"
    assert candidates[0].breaker_allowed is True
    assert all(item.provider_id != "anth-primary" for item in candidates)

    selected = resolve_routed_llm_settings(config, requested_model="claude")
    assert selected.provider_id == "openai-secondary"


def test_resolve_session_model_selection_identity_infers_unique_custom_source(monkeypatch, tmp_path):
    catalog_path = tmp_path / "providers.json"
    catalog_path.write_text(
        json.dumps(
            {
                "providers": [
                    {
                        "id": "maas",
                        "name": "MaaS",
                        "api_type": "openai",
                        "api_base": "https://maas.example.com/v1",
                        "api_key": "sk-maas",
                        "models": ["astron-code-latest"],
                        "enabled": True,
                        "priority": 10,
                    }
                ]
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("MINI_AGENT_PROVIDER_CATALOG_PATH", str(catalog_path))
    config = _make_config(provider="openai", model="astron-code-latest")

    identity = resolve_session_model_selection_identity(
        config,
        provider_id="maas",
        model_id="astron-code-latest",
    )

    assert identity == ("custom", "maas", "astron-code-latest")


def test_resolve_session_model_selection_identity_rejects_ambiguous_source(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai-preset")
    preset = get_preset_provider_config(PresetProvider.OPENAI, use_latest_model=False)
    assert preset is not None
    shared_model = str(preset["model"])

    catalog_path = tmp_path / "providers.json"
    catalog_path.write_text(
        json.dumps(
            {
                "providers": [
                    {
                        "id": "openai",
                        "name": "OpenAI Mirror",
                        "api_type": "openai",
                        "api_base": "https://openai-mirror.example.com/v1",
                        "api_key": "sk-openai-mirror",
                        "models": [shared_model],
                        "enabled": True,
                        "priority": 10,
                    }
                ]
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("MINI_AGENT_PROVIDER_CATALOG_PATH", str(catalog_path))
    config = _make_config(provider="openai", model=shared_model)

    with pytest.raises(ValueError, match="ambiguous across sources"):
        resolve_session_model_selection_identity(
            config,
            provider_id="openai",
            model_id=shared_model,
        )
