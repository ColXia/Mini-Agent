from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from mini_agent.config import Config
from mini_agent.model_manager import bootstrap_llm_settings_from_config


def _write_config(
    path: Path,
    *,
    api_key: str = "${MINIMAX_API_KEY}",
    api_base: str = "https://api.minimax.io",
    model: str = "MiniMax-M2.5",
    provider: str = "anthropic",
) -> None:
    path.write_text(
        textwrap.dedent(
            f"""
            api_key: "{api_key}"
            api_base: "{api_base}"
            model: "{model}"
            provider: "{provider}"
            max_steps: 3
            workspace_dir: "./workspace"
            tools:
              enable_mcp: false
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )


def test_config_reads_api_key_from_env_local_file(tmp_path, monkeypatch):
    config_dir = tmp_path / "src" / "mini_agent" / "config"
    config_dir.mkdir(parents=True)
    config_path = config_dir / "config.yaml"
    _write_config(config_path)
    (tmp_path / ".env.local").write_text(
        "MINIMAX_API_KEY=test-local-key\n", encoding="utf-8"
    )

    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("MINIMAX_API_KEY", raising=False)

    config = Config.from_yaml(config_path)

    assert config.llm.api_key == "test-local-key"
    assert config.llm.api_base == "https://api.minimax.io"
    assert config.llm.model == "MiniMax-M2.5"
    assert config.llm.provider == "anthropic"


def test_system_env_key_has_higher_priority_than_env_local(tmp_path, monkeypatch):
    config_dir = tmp_path / "src" / "mini_agent" / "config"
    config_dir.mkdir(parents=True)
    config_path = config_dir / "config.yaml"
    _write_config(config_path)

    (tmp_path / ".env.local").write_text(
        "MINIMAX_API_KEY=from-local\n", encoding="utf-8"
    )
    monkeypatch.setenv("MINIMAX_API_KEY", "from-system-env")
    monkeypatch.chdir(tmp_path)

    config = Config.from_yaml(config_path)
    assert config.llm.api_key == "from-system-env"


def test_env_local_example_is_not_loaded_for_preset_resolution(tmp_path, monkeypatch):
    config_dir = tmp_path / "src" / "mini_agent" / "config"
    config_dir.mkdir(parents=True)
    config_path = config_dir / "config.yaml"
    _write_config(config_path, api_key="YOUR_API_KEY_HERE", model="MiniMax-M2.7")
    (tmp_path / ".env.local.example").write_text(
        "MINIMAX_API_KEY=from-example-should-not-load\n", encoding="utf-8"
    )

    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("MINIMAX_API_KEY", raising=False)

    import mini_agent.model_manager.preset_providers as preset_providers

    monkeypatch.setattr(preset_providers, "get_first_available_preset", lambda: None)

    with pytest.raises(ValueError, match="No available API keys found"):
        Config.from_yaml(config_path)


def test_preset_branch_applies_resolved_provider_model_and_api_base(tmp_path, monkeypatch):
    config_dir = tmp_path / "src" / "mini_agent" / "config"
    config_dir.mkdir(parents=True)
    config_path = config_dir / "config.yaml"
    _write_config(
        config_path,
        api_key="YOUR_API_KEY_HERE",
        api_base="https://placeholder-base",
        model="placeholder-model",
        provider="openai",
    )

    monkeypatch.chdir(tmp_path)
    import mini_agent.model_manager.preset_providers as preset_providers

    monkeypatch.setattr(
        preset_providers,
        "get_first_available_preset",
        lambda: {
            "api_key": "preset-key",
            "api_base": "https://api.openai.com/v1",
            "api_type": "openai",
            "model": "gpt-5.4",
            "models": ["gpt-5.4"],
        },
    )

    config = Config.from_yaml(config_path)
    assert config.llm.api_key == "preset-key"
    assert config.llm.api_base == "https://api.openai.com/v1"
    assert config.llm.model == "gpt-5.4"
    assert config.llm.provider == "openai"


def test_unresolved_env_reference_raises_when_no_preset_key_exists(tmp_path, monkeypatch):
    config_dir = tmp_path / "src" / "mini_agent" / "config"
    config_dir.mkdir(parents=True)
    config_path = config_dir / "config.yaml"
    _write_config(
        config_path,
        api_key="${MISSING_MINIMAX_API_KEY}",
        model="MiniMax-M2.7",
    )

    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("MISSING_MINIMAX_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("MINIMAX_API_KEY", raising=False)

    import mini_agent.model_manager.preset_providers as preset_providers

    monkeypatch.setattr(preset_providers, "get_first_available_preset", lambda: None)

    with pytest.raises(ValueError, match="No available API keys found"):
        Config.from_yaml(config_path)


def test_config_can_bootstrap_from_enabled_ollama_preset(tmp_path, monkeypatch):
    config_dir = tmp_path / "src" / "mini_agent" / "config"
    config_dir.mkdir(parents=True)
    config_path = config_dir / "config.yaml"
    _write_config(
        config_path,
        api_key="YOUR_API_KEY_HERE",
        api_base="https://placeholder-base",
        model="placeholder-model",
        provider="openai",
    )

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("MINI_AGENT_OLLAMA_ENABLED", "1")
    monkeypatch.setenv("OPENAI_API_KEY", "")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    monkeypatch.setenv("MINIMAX_API_KEY", "")

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
            "discovered_models": ["qwen3-coder"],
        },
    )

    config = Config.from_yaml(config_path)

    assert config.llm.api_key == "ollama"
    assert config.llm.api_base == "http://localhost:11434"
    assert config.llm.model == "qwen3-coder"
    assert config.llm.provider == "anthropic"


def test_config_bootstrap_honors_explicit_preset_provider_preference(tmp_path, monkeypatch):
    config_dir = tmp_path / "src" / "mini_agent" / "config"
    config_dir.mkdir(parents=True)
    config_path = config_dir / "config.yaml"
    _write_config(
        config_path,
        api_key="YOUR_API_KEY_HERE",
        api_base="https://placeholder-base",
        model="placeholder-model",
        provider="openai",
    )

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai-test")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setenv("MINI_AGENT_BOOTSTRAP_PRESET_PROVIDER", "anthropic")

    import mini_agent.model_manager.preset_providers as preset_providers

    monkeypatch.setattr(
        preset_providers,
        "_discover_preset_inventory",
        lambda provider, api_key, api_base=None: None,
    )

    config = Config.from_yaml(config_path)

    assert config.llm.api_key == "sk-ant-test"
    assert config.llm.api_base == "https://api.anthropic.com"
    assert config.llm.model == "claude-sonnet-4-6"
    assert config.llm.provider == "anthropic"


def test_bootstrap_llm_settings_preserves_bootstrap_selection_diagnostics(
    tmp_path,
    monkeypatch,
):
    config_dir = tmp_path / "src" / "mini_agent" / "config"
    config_dir.mkdir(parents=True)
    config_path = config_dir / "config.yaml"
    _write_config(
        config_path,
        api_key="YOUR_API_KEY_HERE",
        api_base="https://placeholder-base",
        model="placeholder-model",
        provider="openai",
    )

    monkeypatch.chdir(tmp_path)

    import mini_agent.model_manager.preset_providers as preset_providers

    monkeypatch.setattr(
        preset_providers,
        "get_first_available_preset",
        lambda: {
            "api_key": "sk-openai-test",
            "api_base": "https://api.openai.com/v1",
            "api_type": "openai",
            "model": "gpt-5.4",
            "models": ["gpt-5.4"],
            "bootstrap_selected_provider": "openai",
            "bootstrap_selection_reason": "bootstrap_priority",
            "bootstrap_selection_policy": "explicit_preference_then_priority",
            "bootstrap_preferred_provider": "openai",
            "bootstrap_preferred_provider_available": True,
            "bootstrap_alternatives": [{"provider": "anthropic"}],
        },
    )

    config = Config.from_yaml(config_path)
    bootstrap = bootstrap_llm_settings_from_config(config)

    assert bootstrap is not None
    assert bootstrap.bootstrap_selected_provider == "openai"
    assert bootstrap.bootstrap_selection_reason == "bootstrap_priority"
    assert bootstrap.bootstrap_selection_policy == "explicit_preference_then_priority"
    assert bootstrap.bootstrap_preferred_provider == "openai"
    assert bootstrap.bootstrap_preferred_provider_available is True
    assert bootstrap.bootstrap_alternatives == ({"provider": "anthropic"},)


def test_config_reads_runtime_retry_from_runtime_section(tmp_path, monkeypatch):
    config_dir = tmp_path / "src" / "mini_agent" / "config"
    config_dir.mkdir(parents=True)
    config_path = config_dir / "config.yaml"
    config_path.write_text(
        textwrap.dedent(
            """
            api_key: "test-key"
            api_base: "https://api.minimax.io"
            model: "MiniMax-M2.5"
            provider: "anthropic"
            runtime:
              retry:
                enabled: true
                max_retries: 7
                initial_delay: 2.5
                max_delay: 30.0
                exponential_base: 3.0
            tools:
              enable_mcp: false
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )

    monkeypatch.chdir(tmp_path)
    config = Config.from_yaml(config_path)

    assert config.runtime.retry.enabled is True
    assert config.runtime.retry.max_retries == 7
    assert config.runtime.retry.initial_delay == 2.5
    assert config.runtime.retry.max_delay == 30.0
    assert config.runtime.retry.exponential_base == 3.0


def test_config_reads_runtime_request_policy_and_rectifier_from_runtime_section(
    tmp_path,
    monkeypatch,
):
    config_dir = tmp_path / "src" / "mini_agent" / "config"
    config_dir.mkdir(parents=True)
    config_path = config_dir / "config.yaml"
    config_path.write_text(
        textwrap.dedent(
            """
            api_key: "test-key"
            api_base: "https://api.minimax.io"
            model: "MiniMax-M2.5"
            provider: "anthropic"
            runtime:
              request_policy:
                max_output_tokens: 4096
                reasoning_split_enabled: false
                thinking_budget_tokens: 1024
                temperature: 0.2
                streaming_enabled: false
                include_stream_usage: false
              rectifier:
                enabled: false
                cache_injection: false
                strip_thinking_signature: false
            tools:
              enable_mcp: false
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )

    monkeypatch.chdir(tmp_path)
    config = Config.from_yaml(config_path)

    assert config.runtime.request_policy.max_output_tokens == 4096
    assert config.runtime.request_policy.reasoning_split_enabled is False
    assert config.runtime.request_policy.thinking_budget_tokens == 1024
    assert config.runtime.request_policy.temperature == 0.2
    assert config.runtime.request_policy.streaming_enabled is False
    assert config.runtime.request_policy.include_stream_usage is False
    assert config.runtime.rectifier.enabled is False
    assert config.runtime.rectifier.cache_injection is False
    assert config.runtime.rectifier.strip_thinking_signature is False


def test_config_reads_runtime_request_policy_and_rectifier_env_defaults(
    tmp_path,
    monkeypatch,
):
    config_dir = tmp_path / "src" / "mini_agent" / "config"
    config_dir.mkdir(parents=True)
    config_path = config_dir / "config.yaml"
    _write_config(config_path, api_key="test-key")

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("MINI_AGENT_THINKING_BUDGET_TOKENS", "2048")
    monkeypatch.setenv("MINI_AGENT_LLM_TEMPERATURE", "0.4")
    monkeypatch.setenv("MINI_AGENT_STREAMING_ENABLED", "0")
    monkeypatch.setenv("MINI_AGENT_STREAM_USAGE_ENABLED", "0")
    monkeypatch.setenv("MINI_AGENT_RECTIFIER_ENABLED", "0")
    monkeypatch.setenv("MINI_AGENT_RECTIFIER_CACHE_INJECTION", "0")
    monkeypatch.setenv("MINI_AGENT_RECTIFIER_STRIP_THINKING_SIGNATURE", "0")

    config = Config.from_yaml(config_path)

    assert config.runtime.request_policy.thinking_budget_tokens == 2048
    assert config.runtime.request_policy.temperature == 0.4
    assert config.runtime.request_policy.streaming_enabled is False
    assert config.runtime.request_policy.include_stream_usage is False
    assert config.runtime.rectifier.enabled is False
    assert config.runtime.rectifier.cache_injection is False
    assert config.runtime.rectifier.strip_thinking_signature is False


def test_config_rejects_legacy_top_level_retry_section(tmp_path, monkeypatch):
    config_dir = tmp_path / "src" / "mini_agent" / "config"
    config_dir.mkdir(parents=True)
    config_path = config_dir / "config.yaml"
    config_path.write_text(
        textwrap.dedent(
            """
            api_key: "test-key"
            api_base: "https://api.minimax.io"
            model: "MiniMax-M2.5"
            provider: "anthropic"
            retry:
              enabled: true
              max_retries: 5
            tools:
              enable_mcp: false
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )

    monkeypatch.chdir(tmp_path)

    with pytest.raises(
        ValueError,
        match=r"Legacy top-level 'retry' is no longer supported.*runtime\.retry",
    ):
        Config.from_yaml(config_path)


def test_config_rejects_non_mapping_root(tmp_path, monkeypatch):
    config_dir = tmp_path / "src" / "mini_agent" / "config"
    config_dir.mkdir(parents=True)
    config_path = config_dir / "config.yaml"
    config_path.write_text("- not-a-mapping\n", encoding="utf-8")

    monkeypatch.chdir(tmp_path)

    with pytest.raises(ValueError, match="Configuration file root must be a mapping"):
        Config.from_yaml(config_path)


def test_config_skips_interactive_bootstrap_when_disabled(tmp_path, monkeypatch):
    config_dir = tmp_path / "src" / "mini_agent" / "config"
    config_dir.mkdir(parents=True)
    config_path = config_dir / "config.yaml"
    _write_config(config_path, api_key="YOUR_API_KEY_HERE", model="MiniMax-M2.7")

    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("MINIMAX_API_KEY", raising=False)

    import mini_agent.model_manager.preset_providers as preset_providers
    import mini_agent.config as config_module

    monkeypatch.setattr(preset_providers, "get_first_available_preset", lambda: None)
    monkeypatch.setattr(
        config_module,
        "run_first_launch_preset_key_setup",
        lambda: (_ for _ in ()).throw(AssertionError("should not run")),
    )

    with pytest.raises(ValueError, match="No available API keys found"):
        Config.from_yaml(config_path, allow_interactive_setup=False)
