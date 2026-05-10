"""Tests for runtime stack CLI command wiring."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

import mini_agent.cli as cli
from mini_agent.workspace_runtime.runtime_stack_manager import RuntimeStackStatus


def _stack_args(action: str, tmp_path: Path) -> argparse.Namespace:
    return argparse.Namespace(
        action=action,
        workspace=str(tmp_path / "workspace"),
        host="127.0.0.1",
        port=8008,
        qqbot=None,
        tui=False,
        tui_prompt=None,
        startup_timeout=20.0,
        force=False,
        target="all",
        lines=50,
        approval_profile=None,
        access_level=None,
    )


def test_create_main_parser_supports_stack_subcommand() -> None:
    parser = cli.create_main_parser()
    args = parser.parse_args(
        ["stack", "up", "--workspace", "workspace", "--qqbot", "--no-tui", "--tui-prompt", "hello"]
    )
    assert args.command == "stack"
    assert args.action == "up"
    assert args.workspace == "workspace"
    assert args.qqbot is True
    assert args.tui is False
    assert args.tui_prompt == "hello"


def test_create_main_parser_supports_qq_shortcut_subcommand() -> None:
    parser = cli.create_main_parser()
    args = parser.parse_args(["qq", "--workspace", "workspace", "--prompt", "hello"])
    assert args.command == "qq"
    assert args.action == "up"
    assert args.workspace == "workspace"
    assert args.prompt == "hello"
    assert args.host == "127.0.0.1"
    assert args.port == 8008
    assert args.tui is True


def test_create_main_parser_supports_qq_shortcut_actions() -> None:
    parser = cli.create_main_parser()
    args = parser.parse_args(["qq", "status"])
    assert args.command == "qq"
    assert args.action == "status"


def test_run_stack_command_status_prints(monkeypatch, capsys, tmp_path: Path) -> None:
    class _DummyManager:
        def __init__(self, *, source_root: Path, repo_root: Path | None = None) -> None:
            self.source_root = source_root
            self.repo_root = repo_root

        def status(self) -> RuntimeStackStatus:
            return RuntimeStackStatus(
                running=False,
                gateway_running=False,
                qqbot_running=False,
                host="127.0.0.1",
                gateway_port=8008,
                workspace=tmp_path,
                gateway_pid=None,
                qqbot_pid=None,
                state_file=tmp_path / "state.json",
                gateway_log=tmp_path / "gateway.log",
                qqbot_log=tmp_path / "qqbot.log",
                qqbot_enabled=False,
                qqbot_configured=False,
                message="qqbot .env not found",
            )

    monkeypatch.setattr("mini_agent.workspace_runtime.runtime_stack_manager.RuntimeStackManager", _DummyManager)
    cli.run_stack_command(_stack_args("status", tmp_path))
    text = capsys.readouterr().out
    assert "Runtime stack status" in text
    assert "qqbot .env not found" in text


def test_run_stack_command_up_attaches_tui(monkeypatch, tmp_path: Path) -> None:
    captured: dict[str, object] = {}

    class _DummyManager:
        def __init__(self, *, source_root: Path, repo_root: Path | None = None) -> None:
            self.source_root = source_root
            self.repo_root = repo_root

        def up(self, **kwargs: object) -> RuntimeStackStatus:
            captured["up_kwargs"] = kwargs
            return RuntimeStackStatus(
                running=True,
                gateway_running=True,
                qqbot_running=True,
                host="127.0.0.1",
                gateway_port=8008,
                workspace=Path(kwargs["workspace"]),
                gateway_pid=101,
                qqbot_pid=202,
                state_file=tmp_path / "state.json",
                gateway_log=tmp_path / "gateway.log",
                qqbot_log=tmp_path / "qqbot.log",
                qqbot_enabled=True,
                qqbot_configured=True,
                message="",
            )

    def _fake_run_tui_mode(args: argparse.Namespace) -> None:
        captured["tui_workspace"] = args.workspace
        captured["tui_prompt"] = args.prompt

    monkeypatch.setattr("mini_agent.workspace_runtime.runtime_stack_manager.RuntimeStackManager", _DummyManager)
    monkeypatch.setattr(cli, "run_tui_mode", _fake_run_tui_mode)

    args = _stack_args("up", tmp_path)
    args.tui = True
    args.qqbot = True
    args.tui_prompt = "seed"
    cli.run_stack_command(args)

    assert captured["tui_workspace"] == str(Path(args.workspace).resolve())
    assert captured["tui_prompt"] == "seed"
    assert os.environ["MINI_AGENT_GATEWAY_BASE"] == "http://127.0.0.1:8008"


def test_run_qq_command_delegates_to_stack_up_with_qqbot_and_tui(tmp_path: Path, monkeypatch) -> None:
    captured: dict[str, object] = {}

    def _fake_run_stack_command(args: argparse.Namespace) -> None:
        captured["action"] = args.action
        captured["workspace"] = args.workspace
        captured["host"] = args.host
        captured["port"] = args.port
        captured["qqbot"] = args.qqbot
        captured["tui"] = args.tui
        captured["tui_prompt"] = args.tui_prompt
        captured["startup_timeout"] = args.startup_timeout
        captured["approval_profile"] = args.approval_profile

    monkeypatch.setattr(cli, "run_stack_command", _fake_run_stack_command)

    cli.run_qq_command(
        argparse.Namespace(
            action="up",
            workspace=str(tmp_path / "workspace"),
            host="127.0.0.1",
            port=8011,
            prompt="boot",
            tui=True,
            startup_timeout=33.0,
            force=False,
            target="all",
            lines=120,
            approval_profile="build",
            access_level="default",
        )
    )

    assert captured["action"] == "up"
    assert captured["workspace"] == str(tmp_path / "workspace")
    assert captured["host"] == "127.0.0.1"
    assert captured["port"] == 8011
    assert captured["qqbot"] is True
    assert captured["tui"] is True
    assert captured["tui_prompt"] == "boot"
    assert captured["startup_timeout"] == 33.0
    assert captured["approval_profile"] == "build"


def test_run_qq_command_status_delegates_to_stack_status(tmp_path: Path, monkeypatch) -> None:
    captured: dict[str, object] = {}

    def _fake_run_stack_command(args: argparse.Namespace) -> None:
        captured["action"] = args.action
        captured["qqbot"] = args.qqbot
        captured["tui"] = args.tui
        captured["tui_prompt"] = args.tui_prompt
        captured["force"] = args.force
        captured["target"] = args.target
        captured["lines"] = args.lines

    monkeypatch.setattr(cli, "run_stack_command", _fake_run_stack_command)

    cli.run_qq_command(
        argparse.Namespace(
            action="status",
            workspace=str(tmp_path / "workspace"),
            host="127.0.0.1",
            port=8008,
            prompt="ignored",
            tui=True,
            startup_timeout=20.0,
            force=True,
            target="qqbot",
            lines=25,
            approval_profile=None,
            access_level=None,
        )
    )

    assert captured["action"] == "status"
    assert captured["qqbot"] is None
    assert captured["tui"] is False
    assert captured["tui_prompt"] is None
    assert captured["force"] is True
    assert captured["target"] == "qqbot"
    assert captured["lines"] == 25
