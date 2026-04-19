"""Tests for DesktopUI CLI command wiring."""

from __future__ import annotations

import argparse
from pathlib import Path

import pytest

import mini_agent.cli as cli


def _desktop_args(tmp_path: Path) -> argparse.Namespace:
    return argparse.Namespace(
        workspace=str(tmp_path / "workspace"),
        host="127.0.0.1",
        port=8008,
        approval_profile="build",
        access_level="default",
        startup_timeout=20.0,
        attach_only=False,
    )


def test_create_main_parser_supports_desktop_subcommand() -> None:
    parser = cli.create_main_parser()
    args = parser.parse_args(
        ["desktop", "--workspace", "workspace", "--port", "8012", "--attach-only"]
    )
    assert args.command == "desktop"
    assert args.workspace == "workspace"
    assert args.port == 8012
    assert args.attach_only is True


def test_run_desktop_command_delegates_to_desktop_app(monkeypatch, tmp_path: Path) -> None:
    captured: dict[str, object] = {}

    def _fake_run_desktop_from_cli(args: argparse.Namespace) -> int:
        captured["workspace"] = args.workspace
        captured["host"] = args.host
        captured["port"] = args.port
        captured["attach_only"] = args.attach_only
        return 0

    monkeypatch.setattr("apps.desktop_ui.main.run_desktop_from_cli", _fake_run_desktop_from_cli)
    cli.run_desktop_command(_desktop_args(tmp_path))

    assert captured["workspace"] == str(tmp_path / "workspace")
    assert captured["host"] == "127.0.0.1"
    assert captured["port"] == 8008
    assert captured["attach_only"] is False


def test_run_desktop_command_runtime_error_is_user_friendly(
    monkeypatch,
    capsys,
    tmp_path: Path,
) -> None:
    def _fake_run_desktop_from_cli(_: argparse.Namespace) -> int:
        raise RuntimeError("PySide6 is not installed.")

    monkeypatch.setattr("apps.desktop_ui.main.run_desktop_from_cli", _fake_run_desktop_from_cli)

    with pytest.raises(SystemExit) as exc_info:
        cli.run_desktop_command(_desktop_args(tmp_path))

    assert exc_info.value.code == 1
    text = capsys.readouterr().out
    assert "PySide6 is not installed." in text
