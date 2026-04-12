from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from mini_agent.config import Config


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
