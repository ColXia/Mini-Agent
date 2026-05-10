"""Tests for runtime stack manager."""

from __future__ import annotations

import json
from pathlib import Path

from mini_agent.workspace_runtime.runtime_stack_manager import RuntimeStackManager


def test_runtime_stack_status_reads_state(monkeypatch, tmp_path: Path) -> None:
    source_root = tmp_path / "src"
    qqbot_dir = source_root / "apps" / "qqbot_channel"
    qqbot_dir.mkdir(parents=True)
    (qqbot_dir / ".env").write_text("QQBOT_APPID=test\n", encoding="utf-8")

    state_root = tmp_path / "state"
    manager = RuntimeStackManager(source_root=source_root, repo_root=tmp_path, state_root=state_root)
    manager.state_file.write_text(
        json.dumps(
            {
                "host": "127.0.0.1",
                "gateway_port": 8008,
                "workspace": str(tmp_path / "workspace"),
                "gateway_pid": 11,
                "qqbot_pid": 22,
                "qqbot_enabled": True,
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        "mini_agent.workspace_runtime.runtime_stack_manager.is_process_alive",
        lambda pid: pid in {11, 22},
    )

    status = manager.status()
    assert status.running is True
    assert status.gateway_running is True
    assert status.qqbot_running is True
    assert status.qqbot_configured is True


def test_runtime_stack_read_logs_returns_tail(tmp_path: Path) -> None:
    source_root = tmp_path / "src"
    source_root.mkdir(parents=True)
    manager = RuntimeStackManager(source_root=source_root, repo_root=tmp_path, state_root=tmp_path / "state")
    manager.gateway_log_file.write_text("a\nb\nc\n", encoding="utf-8")
    manager.qqbot_log_file.write_text("1\n2\n3\n", encoding="utf-8")

    payload = manager.read_logs(target="all", lines=2)
    assert payload["gateway"] == "b\nc"
    assert payload["qqbot"] == "2\n3"


def test_runtime_stack_down_returns_log_paths(monkeypatch, tmp_path: Path) -> None:
    source_root = tmp_path / "src"
    source_root.mkdir(parents=True)
    manager = RuntimeStackManager(source_root=source_root, repo_root=tmp_path, state_root=tmp_path / "state")
    manager.state_file.write_text(
        json.dumps({"gateway_pid": 11, "qqbot_pid": 22, "host": "127.0.0.1", "gateway_port": 8008}),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        "mini_agent.workspace_runtime.runtime_stack_manager._terminate_process",
        lambda pid, force=False: True,
    )

    status = manager.down(force=True)
    assert status.gateway_log == manager.gateway_log_file
    assert status.qqbot_log == manager.qqbot_log_file
