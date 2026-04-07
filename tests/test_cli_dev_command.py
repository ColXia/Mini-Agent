"""Tests for CLI dev command wiring."""

from __future__ import annotations

import argparse
from pathlib import Path

import pytest

from mini_agent import cli
from mini_agent.dev.studio_dev_manager import StudioDevStatus


def _dev_args(action: str) -> argparse.Namespace:
    return argparse.Namespace(
        action=action,
        profile="single-main",
        init_profile=False,
        show_json=False,
        host=None,
        gateway_port=None,
        frontend_port=None,
        startup_timeout=None,
        backend_reload=None,
        frontend_install=False,
        force=False,
        target="all",
        lines=50,
        follow=False,
    )


def test_create_main_parser_supports_dev_subcommand() -> None:
    parser = cli.create_main_parser()
    args = parser.parse_args(["dev", "status"])
    assert args.command == "dev"
    assert args.action == "status"

    args_profile = parser.parse_args(["dev", "profile", "--profile", "single-main", "--init-profile"])
    assert args_profile.command == "dev"
    assert args_profile.action == "profile"
    assert args_profile.profile == "single-main"
    assert args_profile.init_profile is True


def test_create_main_parser_rejects_removed_legacy_start_stop_and_flags() -> None:
    parser = cli.create_main_parser()

    with pytest.raises(SystemExit):
        parser.parse_args(["start", "gateway"])

    with pytest.raises(SystemExit):
        parser.parse_args(["stop", "gateway"])

    with pytest.raises(SystemExit):
        parser.parse_args(["--no-webui"])

    with pytest.raises(SystemExit):
        parser.parse_args(["--no-channels"])


def test_run_dev_command_status_prints(monkeypatch, capsys, tmp_path: Path) -> None:
    class _DummyManager:
        def __init__(self, repo_root: Path) -> None:
            self.repo_root = repo_root

        def status(self) -> StudioDevStatus:
            return StudioDevStatus(
                running=False,
                backend_running=False,
                frontend_running=False,
                host="127.0.0.1",
                gateway_port=8008,
                frontend_port=5174,
                backend_pid=None,
                frontend_pid=None,
                state_file=tmp_path / "state.json",
                backend_log=tmp_path / "backend.log",
                frontend_log=tmp_path / "frontend.log",
                message="state exists but unhealthy",
            )

    monkeypatch.setattr("mini_agent.dev.StudioDevManager", _DummyManager)
    cli.run_dev_command(_dev_args("status"))
    text = capsys.readouterr().out
    assert "Studio dev status" in text
    assert "state exists but unhealthy" in text


def test_run_dev_command_runtime_error_is_user_friendly(monkeypatch, capsys, tmp_path: Path) -> None:
    class _DummyManager:
        def __init__(self, repo_root: Path) -> None:
            self.repo_root = repo_root

        def up(self, **_: object) -> StudioDevStatus:  # pragma: no cover - signature bridge
            raise RuntimeError("Studio dev stack is already running.")

    monkeypatch.setattr("mini_agent.dev.StudioDevManager", _DummyManager)
    with pytest.raises(SystemExit) as exc_info:
        cli.run_dev_command(_dev_args("up"))
    assert exc_info.value.code == 1
    text = capsys.readouterr().out
    assert "Error: Studio dev stack is already running." in text
