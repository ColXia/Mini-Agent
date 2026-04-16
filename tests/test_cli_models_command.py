from __future__ import annotations

import argparse

from mini_agent import cli


def _models_args(**overrides: object) -> argparse.Namespace:
    payload: dict[str, object] = {
        "list_presets": False,
        "provider": "ollama",
        "api_key": None,
        "api_base": None,
        "latest": False,
        "all": False,
    }
    payload.update(overrides)
    return argparse.Namespace(**payload)


def test_run_models_command_reports_unreachable_enabled_ollama(monkeypatch, capsys) -> None:
    monkeypatch.setenv("MINI_AGENT_OLLAMA_ENABLED", "1")
    monkeypatch.setenv("OLLAMA_HOST", "http://127.0.0.1:11434")

    import mini_agent.model_manager.preset_providers as preset_providers

    monkeypatch.setattr(
        preset_providers,
        "get_preset_provider_config",
        lambda provider, use_latest_model=False: None,
    )

    cli.run_models_command(_models_args())

    output = capsys.readouterr().out
    assert "Error: No API key provided." in output
    assert "Ollama is enabled, but the local daemon is not reachable" in output
    assert "http://127.0.0.1:11434" in output


def test_run_models_command_list_presets_loads_env_local(monkeypatch, capsys, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("MINIMAX_API_KEY", raising=False)
    (tmp_path / ".env.local").write_text("OPENAI_API_KEY=from-local-env\n", encoding="utf-8")

    cli.run_models_command(_models_args(list_presets=True, provider=None))

    output = capsys.readouterr().out
    assert "Preset Providers:" in output
    assert "OpenAI" in output
    assert "(openai)" in output
    assert "[configured]" in output
