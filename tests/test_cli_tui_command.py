"""Tests for CLI TUI command wiring."""

from __future__ import annotations

import argparse
from pathlib import Path
from types import SimpleNamespace

import mini_agent.cli as cli
import mini_agent.utils.terminal_utils as terminal_utils


def test_create_main_parser_supports_tui_subcommand() -> None:
    parser = cli.create_main_parser()
    args = parser.parse_args(["tui", "--workspace", "workspace", "--prompt", "hello"])
    assert args.command == "tui"
    assert args.workspace == "workspace"
    assert args.prompt == "hello"


def test_run_tui_mode_invokes_tui_runner(monkeypatch, tmp_path: Path) -> None:
    called: dict[str, object] = {}

    async def _fake_run_tui(
        *,
        workspace: Path,
        approval_profile: str | None,
        access_level: str | None,
        initial_prompt: str | None,
        config_loader,
    ) -> None:
        called["workspace"] = workspace
        called["approval_profile"] = approval_profile
        called["access_level"] = access_level
        called["initial_prompt"] = initial_prompt
        called["config_loader"] = config_loader

    monkeypatch.setattr("mini_agent.tui.app.run_tui", _fake_run_tui)

    args = argparse.Namespace(
        workspace=str(tmp_path / "demo"),
        approval_profile="plan",
        prompt="seed prompt",
        access_level="default",
    )
    cli.run_tui_mode(args)

    assert called["workspace"] == Path(args.workspace)
    assert called["approval_profile"] == "plan"
    assert called["access_level"] == "default"
    assert called["initial_prompt"] == "seed prompt"
    assert called["config_loader"] is cli.load_noninteractive_config


def test_supports_unicode_box_art_requires_utf8_on_windows(monkeypatch) -> None:
    monkeypatch.setattr(terminal_utils.os, "name", "nt", raising=False)

    assert terminal_utils.supports_unicode_box_art(SimpleNamespace(encoding="utf-8")) is True
    assert terminal_utils.supports_unicode_box_art(SimpleNamespace(encoding="cp65001")) is True
    assert terminal_utils.supports_unicode_box_art(SimpleNamespace(encoding="gbk")) is False


def test_print_banner_falls_back_to_ascii_when_unicode_box_art_is_unsafe(monkeypatch, capsys) -> None:
    monkeypatch.setattr(cli, "supports_unicode_box_art", lambda: False)

    cli.print_banner()

    captured = capsys.readouterr().out
    assert "Mini-Agent - Intelligent Agent Platform" in captured
    assert "Powered by MiniMax M2.5" in captured
    assert "╔" not in captured
