from __future__ import annotations

from mini_agent.model_manager.preset_providers import (
    PresetProvider,
    detect_preset_providers,
    get_preset_provider_config,
)


def test_detects_anthropic_provider_from_official_env_var(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")

    detected = detect_preset_providers()
    assert (PresetProvider.ANTHROPIC, "sk-ant-test") in detected


def test_get_preset_provider_config_prefers_latest_discovered_model(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai-test")

    import mini_agent.model_manager.preset_providers as preset_providers

    monkeypatch.setattr(
        preset_providers, "_discover_latest_model", lambda provider, api_key: "gpt-5.4"
    )
    preset = get_preset_provider_config(PresetProvider.OPENAI)

    assert preset is not None
    assert preset["model"] == "gpt-5.4"
    assert preset["models"][0] == "gpt-5.4"


def test_get_preset_provider_config_falls_back_to_default_when_discovery_fails(
    monkeypatch,
):
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-test-key")

    import mini_agent.model_manager.preset_providers as preset_providers

    monkeypatch.setattr(
        preset_providers, "_discover_latest_model", lambda provider, api_key: None
    )
    preset = get_preset_provider_config(PresetProvider.GEMINI)

    assert preset is not None
    assert preset["model"] == "gemini-3.1-pro"
