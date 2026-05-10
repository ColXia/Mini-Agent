"""Tests for DesktopUI gateway supervision."""

from __future__ import annotations

from pathlib import Path

import pytest

from mini_agent.desktop.gateway_supervisor import DesktopGatewaySupervisor
from mini_agent.workspace_runtime.runtime_stack_manager import RuntimeStackStatus


def _status(
    *,
    tmp_path: Path,
    running: bool,
    gateway_running: bool,
    host: str = "127.0.0.1",
    port: int = 8008,
) -> RuntimeStackStatus:
    return RuntimeStackStatus(
        running=running,
        gateway_running=gateway_running,
        qqbot_running=False,
        host=host,
        gateway_port=port,
        workspace=tmp_path / "workspace",
        gateway_pid=101 if gateway_running else None,
        qqbot_pid=None,
        state_file=tmp_path / "state.json",
        gateway_log=tmp_path / "gateway.log",
        qqbot_log=tmp_path / "qqbot.log",
        qqbot_enabled=False,
        qqbot_configured=False,
        message="",
    )


def test_supervisor_attaches_to_managed_runtime(monkeypatch, tmp_path: Path) -> None:
    class _DummyManager:
        def status(self) -> RuntimeStackStatus:
            return _status(tmp_path=tmp_path, running=True, gateway_running=True, port=8011)

    monkeypatch.setattr("mini_agent.desktop.gateway_supervisor.is_port_listening", lambda host, port: True)
    supervisor = DesktopGatewaySupervisor(
        source_root=tmp_path,
        repo_root=tmp_path,
        stack_manager=_DummyManager(),  # type: ignore[arg-type]
    )

    connection = supervisor.ensure_gateway_running(
        host="127.0.0.1",
        port=8008,
        workspace=tmp_path / "requested",
        approval_profile=None,
        access_level=None,
        startup_timeout=20.0,
        attach_only=False,
    )

    assert connection.managed is True
    assert connection.started_here is False
    assert connection.port == 8011
    assert "requested 127.0.0.1:8008 was ignored" in connection.note


def test_supervisor_starts_gateway_when_missing(monkeypatch, tmp_path: Path) -> None:
    captured: dict[str, object] = {}

    class _DummyManager:
        def status(self) -> RuntimeStackStatus:
            return _status(tmp_path=tmp_path, running=False, gateway_running=False)

        def up(self, **kwargs: object) -> RuntimeStackStatus:
            captured["kwargs"] = kwargs
            return _status(tmp_path=tmp_path, running=True, gateway_running=True)

    monkeypatch.setattr("mini_agent.desktop.gateway_supervisor.is_port_listening", lambda host, port: False)
    supervisor = DesktopGatewaySupervisor(
        source_root=tmp_path,
        repo_root=tmp_path,
        stack_manager=_DummyManager(),  # type: ignore[arg-type]
    )

    connection = supervisor.ensure_gateway_running(
        host="127.0.0.1",
        port=8008,
        workspace=tmp_path / "requested",
        approval_profile="build",
        access_level="default",
        startup_timeout=33.0,
        attach_only=False,
    )

    assert connection.managed is True
    assert connection.started_here is True
    assert captured["kwargs"]["qqbot"] is False
    assert captured["kwargs"]["approval_profile"] == "build"
    assert captured["kwargs"]["access_level"] == "default"
    assert captured["kwargs"]["startup_timeout"] == 33.0


def test_supervisor_attach_only_fails_when_gateway_missing(monkeypatch, tmp_path: Path) -> None:
    class _DummyManager:
        def status(self) -> RuntimeStackStatus:
            return _status(tmp_path=tmp_path, running=False, gateway_running=False)

    monkeypatch.setattr("mini_agent.desktop.gateway_supervisor.is_port_listening", lambda host, port: False)
    supervisor = DesktopGatewaySupervisor(
        source_root=tmp_path,
        repo_root=tmp_path,
        stack_manager=_DummyManager(),  # type: ignore[arg-type]
    )

    with pytest.raises(RuntimeError, match="attach-only mode was requested"):
        supervisor.ensure_gateway_running(
            host="127.0.0.1",
            port=8008,
            workspace=tmp_path / "requested",
            approval_profile=None,
            access_level=None,
            startup_timeout=20.0,
            attach_only=True,
        )
