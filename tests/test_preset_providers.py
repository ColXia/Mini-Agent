from __future__ import annotations

import pytest

from mini_agent.model_manager.preset_providers import (
    BootstrapPresetSelection,
    PresetProvider,
    _is_loopback_host,
    detect_preset_providers,
    get_preset_provider_config,
    get_first_available_preset,
    resolve_bootstrap_preset_selection,
)


@pytest.fixture(autouse=True)
def _clear_ollama_env(monkeypatch):
    monkeypatch.setenv("MINI_AGENT_OLLAMA_ENABLED", "")
    monkeypatch.setenv("MINI_AGENT_ENABLE_OLLAMA", "")
    monkeypatch.setenv("OLLAMA_HOST", "")
    monkeypatch.setenv("MINI_AGENT_OLLAMA_BASE_URL", "")
    monkeypatch.setenv("MINI_AGENT_OLLAMA_PROTOCOL", "")


def test_detects_anthropic_provider_from_official_env_var(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")

    detected = detect_preset_providers()
    assert (PresetProvider.ANTHROPIC, "sk-ant-test") in detected


def test_get_preset_provider_config_prefers_latest_discovered_model(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai-test")

    import mini_agent.model_manager.preset_providers as preset_providers

    monkeypatch.setattr(
        preset_providers,
        "_discover_preset_inventory",
        lambda provider, api_key, api_base=None: {
            "selected_model": "gpt-5.4",
            "selection_strategy": "curated_latest",
            "selection_confidence": "high",
            "discovery_source": "api_discovery",
            "discovered_models": ["gpt-5.4", "gpt-5.3"],
        },
    )
    preset = get_preset_provider_config(PresetProvider.OPENAI)

    assert preset is not None
    assert preset["model"] == "gpt-5.4"
    assert preset["models"][0] == "gpt-5.4"
    assert preset["default_model_strategy"] == "curated_latest"
    assert preset["default_model_confidence"] == "high"


def test_get_preset_provider_config_falls_back_to_default_when_discovery_fails(
    monkeypatch,
):
    monkeypatch.setenv("MINIMAX_API_KEY", "minimax-test-key")

    import mini_agent.model_manager.preset_providers as preset_providers

    monkeypatch.setattr(
        preset_providers, "_discover_preset_inventory", lambda provider, api_key, api_base=None: None
    )
    preset = get_preset_provider_config(PresetProvider.MINIMAX)

    assert preset is not None
    assert preset["model"] == "MiniMax-M2.7"
    assert preset["default_model_strategy"] == "official_default"


def test_get_preset_provider_config_returns_ollama_when_enabled_and_reachable(monkeypatch):
    monkeypatch.setenv("MINI_AGENT_OLLAMA_ENABLED", "1")

    import mini_agent.model_manager.preset_providers as preset_providers

    monkeypatch.setattr(preset_providers, "_is_ollama_reachable", lambda host: True)
    monkeypatch.setattr(
        preset_providers,
        "_discover_preset_inventory",
        lambda provider, api_key, api_base=None: {
            "selected_model": "qwen3-coder",
            "selection_strategy": "curated_latest",
            "selection_confidence": "high",
            "discovery_source": "api_discovery",
            "discovered_models": ["qwen3-coder", "gpt-oss:20b"],
        },
    )

    preset = get_preset_provider_config(PresetProvider.OLLAMA)

    assert preset is not None
    assert preset["api_key"] == "ollama"
    assert preset["api_type"] == "anthropic"
    assert preset["api_base"] == "http://localhost:11434"
    assert preset["model"] == "qwen3-coder"
    assert preset["models"][0] == "qwen3-coder"


def test_get_preset_provider_config_can_skip_ollama_probe_for_runtime_safe_resolution(monkeypatch):
    monkeypatch.setenv("MINI_AGENT_OLLAMA_ENABLED", "1")

    import mini_agent.model_manager.preset_providers as preset_providers

    def _unexpected_probe(host: str) -> bool:
        raise AssertionError(f"unexpected reachability probe for {host}")

    def _unexpected_discovery(provider, api_key, api_base=None):
        raise AssertionError(f"unexpected inventory discovery for {provider} {api_base}")

    monkeypatch.setattr(preset_providers, "_is_ollama_reachable", _unexpected_probe)
    monkeypatch.setattr(preset_providers, "_discover_preset_inventory", _unexpected_discovery)

    preset = get_preset_provider_config(
        PresetProvider.OLLAMA,
        use_latest_model=False,
        allow_unreachable_local=True,
        discover_inventory=False,
    )

    assert preset is not None
    assert preset["api_key"] == "ollama"
    assert preset["api_base"] == "http://localhost:11434"
    assert preset["model"] == "qwen3-coder"


def test_preset_providers_identify_loopback_hosts() -> None:
    assert _is_loopback_host("http://localhost:11434") is True
    assert _is_loopback_host("http://127.0.0.1:11434/v1") is True
    assert _is_loopback_host("http://[::1]:11434") is True
    assert _is_loopback_host("https://relay.example.com/v1") is False


def test_get_first_available_preset_uses_bootstrap_policy_not_provider_dict_order(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai-test")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")

    import mini_agent.model_manager.preset_providers as preset_providers

    monkeypatch.setattr(
        preset_providers,
        "_discover_preset_inventory",
        lambda provider, api_key, api_base=None: None,
    )
    monkeypatch.setattr(
        preset_providers,
        "PRESET_PROVIDERS",
        {
            PresetProvider.ANTHROPIC: preset_providers.PRESET_PROVIDERS[PresetProvider.ANTHROPIC],
            PresetProvider.OPENAI: preset_providers.PRESET_PROVIDERS[PresetProvider.OPENAI],
            PresetProvider.MINIMAX: preset_providers.PRESET_PROVIDERS[PresetProvider.MINIMAX],
            PresetProvider.OLLAMA: preset_providers.PRESET_PROVIDERS[PresetProvider.OLLAMA],
        },
    )

    preset = get_first_available_preset(use_latest_model=False)

    assert preset is not None
    assert preset["provider"] == "openai"
    assert preset["bootstrap_selected_provider"] == "openai"
    assert preset["bootstrap_selection_reason"] == "bootstrap_priority"


def test_bootstrap_preset_selection_honors_explicit_preference_and_reports_alternatives(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai-test")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setenv("MINI_AGENT_BOOTSTRAP_PRESET_PROVIDER", "anthropic")

    import mini_agent.model_manager.preset_providers as preset_providers

    monkeypatch.setattr(
        preset_providers,
        "_discover_preset_inventory",
        lambda provider, api_key, api_base=None: None,
    )

    selection = resolve_bootstrap_preset_selection(use_latest_model=False)

    assert isinstance(selection, BootstrapPresetSelection)
    assert selection.selected_provider == PresetProvider.ANTHROPIC
    assert selection.selected_reason == "explicit_preference"
    assert selection.preferred_provider == "anthropic"
    assert selection.preferred_provider_available is True
    assert any(item["provider"] == "openai" for item in selection.alternatives)
    assert selection.preset is not None
    assert selection.preset["provider"] == "anthropic"
