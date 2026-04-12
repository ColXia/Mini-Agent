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
        "auto_discover_models": False,
        "selected_model_id": None,
        "priority": 0,
        "catalog": str(tmp_path / "providers.json"),
        "source": None,
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
