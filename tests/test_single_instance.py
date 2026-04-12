"""Tests for single instance process detection."""

from __future__ import annotations

import subprocess
from pathlib import Path

from mini_agent.utils.single_instance import SingleInstanceManager


def test_single_instance_windows_process_check_handles_bytes_stdout(monkeypatch, tmp_path: Path) -> None:
    manager = SingleInstanceManager(name="mini-agent-test")
    manager.pid_file = tmp_path / "mini-agent-test.pid"

    class _Result:
        stdout = "python.exe,1234,Console".encode("cp936")

    monkeypatch.setattr("mini_agent.utils.single_instance.sys.platform", "win32")
    monkeypatch.setattr(
        "mini_agent.utils.single_instance.subprocess.run",
        lambda *args, **kwargs: _Result(),
    )

    assert manager._is_process_running(1234) is True


def test_single_instance_windows_process_check_handles_missing_stdout(monkeypatch, tmp_path: Path) -> None:
    manager = SingleInstanceManager(name="mini-agent-test")
    manager.pid_file = tmp_path / "mini-agent-test.pid"

    class _Result:
        stdout = None

    monkeypatch.setattr("mini_agent.utils.single_instance.sys.platform", "win32")
    monkeypatch.setattr(
        "mini_agent.utils.single_instance.subprocess.run",
        lambda *args, **kwargs: _Result(),
    )

    assert manager._is_process_running(1234) is False


def test_single_instance_windows_process_check_handles_timeout(monkeypatch, tmp_path: Path) -> None:
    manager = SingleInstanceManager(name="mini-agent-test")
    manager.pid_file = tmp_path / "mini-agent-test.pid"

    def _raise_timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd="tasklist", timeout=5)

    monkeypatch.setattr("mini_agent.utils.single_instance.sys.platform", "win32")
    monkeypatch.setattr(
        "mini_agent.utils.single_instance.subprocess.run",
        _raise_timeout,
    )

    assert manager._is_process_running(1234) is False
