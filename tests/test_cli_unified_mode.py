"""Tests for unified terminal entry routing."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

from mini_agent import cli


def _base_args(tmp_path: Path) -> argparse.Namespace:
    return argparse.Namespace(
        command=None,
        mode="auto",
        prompt=None,
        output_format="text",
        workspace=str(tmp_path),
        approval_profile=None,
        host="127.0.0.1",
        port=8008,
        reload=False,
        task=None,
    )


def test_create_main_parser_supports_unified_mode_and_serve() -> None:
    parser = cli.create_main_parser()
    args = parser.parse_args(["--mode", "headless", "--prompt", "hello", "--output-format", "json"])
    assert args.command is None
    assert args.mode == "headless"
    assert args.prompt == "hello"
    assert args.output_format == "json"

    serve_args = parser.parse_args(["serve", "--port", "8010"])
    assert serve_args.command == "serve"
    assert serve_args.port == 8010


def test_run_unified_terminal_mode_auto_prompt_routes_to_headless(
    monkeypatch,
    tmp_path: Path,
) -> None:
    called: dict[str, object] = {}

    def _fake_headless(args: argparse.Namespace) -> None:
        called["prompt"] = args.prompt

    monkeypatch.setattr(cli, "run_headless_mode", _fake_headless)
    monkeypatch.setattr(cli, "_read_non_tty_prompt", lambda: None)

    args = _base_args(tmp_path)
    args.prompt = "hello"
    cli.run_unified_terminal_mode(args)

    assert called["prompt"] == "hello"


def test_run_unified_terminal_mode_auto_tty_routes_to_tui(
    monkeypatch,
    tmp_path: Path,
) -> None:
    called: dict[str, bool] = {"tui": False}

    def _fake_tui(args: argparse.Namespace) -> None:
        _ = args
        called["tui"] = True

    monkeypatch.setattr(cli, "run_tui_mode", _fake_tui)
    monkeypatch.setattr(cli, "_read_non_tty_prompt", lambda: None)
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(sys.stdout, "isatty", lambda: True)

    args = _base_args(tmp_path)
    cli.run_unified_terminal_mode(args)

    assert called["tui"] is True


def test_run_unified_terminal_mode_cli_mode_passes_prompt_as_task(
    monkeypatch,
    tmp_path: Path,
) -> None:
    called: dict[str, object] = {}

    def _fake_cli(args: argparse.Namespace) -> None:
        called["task"] = getattr(args, "task", None)

    monkeypatch.setattr(cli, "run_cli_mode", _fake_cli)
    args = _base_args(tmp_path)
    args.mode = "cli"
    args.prompt = "from-prompt"

    cli.run_unified_terminal_mode(args)

    assert called["task"] == "from-prompt"


def test_main_routes_default_to_unified(monkeypatch) -> None:
    called: dict[str, bool] = {"unified": False, "gateway": False}

    def _fake_unified(args: argparse.Namespace) -> None:
        _ = args
        called["unified"] = True

    def _fake_gateway(args: argparse.Namespace) -> None:
        _ = args
        called["gateway"] = True

    monkeypatch.setattr(cli, "run_unified_terminal_mode", _fake_unified)
    monkeypatch.setattr(cli, "run_gateway_mode", _fake_gateway)
    monkeypatch.setattr(sys, "argv", ["mini-agent"])

    cli.main()

    assert called["unified"] is True
    assert called["gateway"] is False


def test_main_routes_serve_intent_to_gateway(monkeypatch) -> None:
    called: dict[str, bool] = {"unified": False, "gateway": False}

    def _fake_unified(args: argparse.Namespace) -> None:
        _ = args
        called["unified"] = True

    def _fake_gateway(args: argparse.Namespace) -> None:
        _ = args
        called["gateway"] = True

    monkeypatch.setattr(cli, "run_unified_terminal_mode", _fake_unified)
    monkeypatch.setattr(cli, "run_gateway_mode", _fake_gateway)
    monkeypatch.setattr(sys, "argv", ["mini-agent", "--port", "8010"])

    cli.main()

    assert called["gateway"] is True
    assert called["unified"] is False


def test_main_routes_qq_shortcut_to_qq_command(monkeypatch) -> None:
    called: dict[str, bool] = {"qq": False}

    def _fake_run_qq(args: argparse.Namespace) -> None:
        assert args.command == "qq"
        called["qq"] = True

    monkeypatch.setattr(cli, "run_qq_command", _fake_run_qq)
    monkeypatch.setattr(sys, "argv", ["mini", "qq"])

    cli.main()

    assert called["qq"] is True
