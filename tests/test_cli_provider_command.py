"""Tests for CLI provider learned-limit actions."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from mini_agent import cli


def _provider_args(action: str, tmp_path: Path, **overrides: object) -> argparse.Namespace:
    payload: dict[str, object] = {
        "action": action,
        "id": None,
        "name": None,
        "url": None,
        "key": None,
        "type": "openai",
        "models": None,
        "model_id": None,
        "model_name": None,
        "model_role": None,
        "context_window": None,
        "learned_token_limit": None,
        "supports_tools": None,
        "supports_thinking": None,
        "auto_discover_models": False,
        "selected_model_id": None,
        "priority": 0,
        "timeout": 60,
        "header": None,
        "catalog": str(tmp_path / "providers.json"),
        "source": None,
        "feature_role": None,
    }
    payload.update(overrides)
    return argparse.Namespace(**payload)


def test_create_main_parser_supports_provider_limit_actions() -> None:
    parser = cli.create_main_parser()
    args = parser.parse_args(
        ["provider", "clear-limit", "--source", "custom", "--id", "maas", "--model-id", "astron-code-latest"]
    )
    assert args.command == "provider"
    assert args.action == "clear-limit"
    assert args.source == "custom"
    assert args.id == "maas"
    assert args.model_id == "astron-code-latest"


def test_create_main_parser_supports_provider_probe_action() -> None:
    parser = cli.create_main_parser()
    args = parser.parse_args(
        ["provider", "probe", "--source", "custom", "--id", "maas", "--model-id", "astron-code-latest"]
    )
    assert args.command == "provider"
    assert args.action == "probe"
    assert args.source == "custom"
    assert args.id == "maas"
    assert args.model_id == "astron-code-latest"


def test_run_provider_command_lists_learned_token_limits(capsys, tmp_path: Path) -> None:
    catalog_path = tmp_path / "providers.json"
    catalog_path.write_text(
        json.dumps(
            {
                "providers": [
                    {
                        "id": "maas",
                        "name": "MaaS",
                        "api_type": "openai",
                        "api_base": "https://maas.example.com/anthropic",
                        "api_key": "sk-maas",
                        "models": ["astron-code-latest"],
                        "model_display_names": {"astron-code-latest": "GLM-5/K2.5"},
                        "model_context_windows": {"astron-code-latest": 128000},
                        "model_learned_token_limits": {"astron-code-latest": 96000},
                    }
                ]
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    cli.run_provider_command(_provider_args("limits", tmp_path))

    text = capsys.readouterr().out
    assert "Learned Token Limits" in text
    assert "[custom] maas/astron-code-latest" in text
    assert "96,000" in text


def test_run_provider_command_clears_learned_token_limit(capsys, tmp_path: Path) -> None:
    catalog_path = tmp_path / "providers.json"
    catalog_path.write_text(
        json.dumps(
            {
                "providers": [
                    {
                        "id": "maas",
                        "name": "MaaS",
                        "api_type": "openai",
                        "api_base": "https://maas.example.com/anthropic",
                        "api_key": "sk-maas",
                        "models": ["astron-code-latest"],
                        "model_learned_token_limits": {"astron-code-latest": 96000},
                    }
                ]
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    cli.run_provider_command(
        _provider_args(
            "clear-limit",
            tmp_path,
            id="maas",
            source="custom",
            model_id="astron-code-latest",
        )
    )

    text = capsys.readouterr().out
    assert "Cleared learned token limit for maas/astron-code-latest" in text

    payload = json.loads(catalog_path.read_text(encoding="utf-8"))
    provider = payload["providers"][0]
    assert provider.get("model_learned_token_limits") == {}


def test_run_provider_command_add_persists_advanced_model_metadata(
    capsys,
    tmp_path: Path,
) -> None:
    catalog_path = tmp_path / "providers.json"

    cli.run_provider_command(
        _provider_args(
            "add",
            tmp_path,
            name="MaaS",
            url="https://maas.example.com/v2",
            key="sk-maas",
            type="openai",
            model_id="astron-code-latest",
            model_name="Astron Latest",
            model_role="chat",
            context_window=256000,
            learned_token_limit=128000,
            supports_tools=True,
            supports_thinking=True,
            timeout=45,
            header=["X-Tenant=tenant-a"],
        )
    )

    text = capsys.readouterr().out
    assert "Provider added successfully" in text

    payload = json.loads(catalog_path.read_text(encoding="utf-8"))
    provider = payload["providers"][0]
    assert provider["timeout"] == 45
    assert provider["headers"] == {"X-Tenant": "tenant-a"}
    assert provider["model_context_windows"]["astron-code-latest"] == 256000
    assert provider["model_learned_token_limits"]["astron-code-latest"] == 128000
    assert provider["model_metadata"]["astron-code-latest"]["model_role"] == "chat"
    assert provider["model_metadata"]["astron-code-latest"]["supports_tools"] is True
    assert provider["model_metadata"]["astron-code-latest"]["supports_thinking"] is True


def test_run_provider_command_set_role_and_bind_feature(capsys, tmp_path: Path) -> None:
    catalog_path = tmp_path / "providers.json"
    catalog_path.write_text(
        json.dumps(
            {
                "providers": [
                    {
                        "id": "ollama-local",
                        "name": "Ollama Local",
                        "api_type": "openai",
                        "api_base": "http://localhost:11434/v1",
                        "api_key": "ollama",
                        "models": ["qwen3.5:9b", "qwen3-embedding:0.6b"],
                    }
                ]
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    cli.run_provider_command(
        _provider_args(
            "set-role",
            tmp_path,
            id="ollama-local",
            source="custom",
            model_id="qwen3-embedding:0.6b",
            model_role="embedding",
        )
    )
    role_text = capsys.readouterr().out
    assert "Updated model role" in role_text

    cli.run_provider_command(
        _provider_args(
            "bind-feature",
            tmp_path,
            id="ollama-local",
            source="custom",
            model_id="qwen3-embedding:0.6b",
            feature_role="embedding",
        )
    )
    bind_text = capsys.readouterr().out
    assert "Feature model bound" in bind_text

    cli.run_provider_command(_provider_args("bindings", tmp_path))
    list_text = capsys.readouterr().out
    assert "Feature Model Bindings" in list_text
    assert "embedding" in list_text


def test_run_provider_command_probe(capsys, tmp_path: Path, monkeypatch) -> None:
    catalog_path = tmp_path / "providers.json"
    catalog_path.write_text(
        json.dumps(
            {
                "providers": [
                    {
                        "id": "maas",
                        "name": "MaaS",
                        "api_type": "openai",
                        "api_base": "https://maas.example.com/v2",
                        "api_key": "sk-maas",
                        "models": ["astron-code-latest"],
                    }
                ]
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        "mini_agent.application.use_cases.operations_provider_use_cases.ProviderOperationsUseCases.probe_model_capabilities",
        lambda self, **kwargs: type(
            "_ProbeResult",
            (),
            {
                "source": "custom",
                "provider_id": "maas",
                "model": type(
                    "_ProbeModel",
                    (),
                    {
                        "model_id": "astron-code-latest",
                        "context_window": 256000,
                        "supports_tools_truth": "supported",
                        "supports_tools_confidence": "high",
                        "supports_tools_source": "active_probe_tool_call",
                        "supports_thinking_truth": "unsupported",
                        "supports_thinking_confidence": "medium",
                        "supports_thinking_source": "active_probe_no_thinking",
                    },
                )(),
                "updated_fields": ["supports_tools", "supports_thinking"],
                "notes": ["tool probe completed"],
            },
        )(),
    )

    cli.run_provider_command(
        _provider_args(
            "probe",
            tmp_path,
            id="maas",
            source="custom",
            model_id="astron-code-latest",
        )
    )

    text = capsys.readouterr().out
    assert "Model Capability Probe" in text
    assert "supports_tools: supported" in text
    assert "supports_thinking: unsupported" in text
    assert "updated_fields: supports_tools, supports_thinking" in text
