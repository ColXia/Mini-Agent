"""Unit tests for Studio dev process manager helpers."""

from __future__ import annotations

import json
from pathlib import Path

from mini_agent.dev.studio_dev_manager import StudioDevManager


def _make_repo_root(tmp_path: Path) -> Path:
    repo_root = (tmp_path / "repo").resolve()
    (repo_root / "apps" / "agent_studio").mkdir(parents=True, exist_ok=True)
    return repo_root


def test_status_not_running_without_state(tmp_path: Path) -> None:
    manager = StudioDevManager(
        repo_root=_make_repo_root(tmp_path),
        state_root=(tmp_path / ".studio-dev-state"),
    )
    status = manager.status()
    assert status.running is False
    assert status.backend_running is False
    assert status.frontend_running is False


def test_read_logs_tail(tmp_path: Path) -> None:
    manager = StudioDevManager(
        repo_root=_make_repo_root(tmp_path),
        state_root=(tmp_path / ".studio-dev-state"),
    )
    manager.backend_log_file.write_text("a\nb\nc\n", encoding="utf-8")
    manager.frontend_log_file.write_text("x\ny\n", encoding="utf-8")

    logs = manager.read_logs(target="all", lines=1)
    assert logs["backend"] == "c"
    assert logs["frontend"] == "y"


def test_status_detects_stale_state(tmp_path: Path) -> None:
    manager = StudioDevManager(
        repo_root=_make_repo_root(tmp_path),
        state_root=(tmp_path / ".studio-dev-state"),
    )
    stale_state = {
        "host": "127.0.0.1",
        "gateway_port": 8008,
        "frontend_port": 5174,
        "backend_pid": 999999,
        "frontend_pid": 999998,
    }
    manager.state_file.parent.mkdir(parents=True, exist_ok=True)
    manager.state_file.write_text(json.dumps(stale_state), encoding="utf-8")

    status = manager.status()
    assert status.running is False
    assert status.message


def test_profile_template_created_and_resolved(tmp_path: Path) -> None:
    manager = StudioDevManager(
        repo_root=_make_repo_root(tmp_path),
        state_root=(tmp_path / ".studio-dev-state"),
    )
    profile_path = manager.ensure_profile_template("single-main")
    assert profile_path.exists()

    profile = manager.resolve_profile(
        profile_name="single-main",
        host=None,
        gateway_port=None,
        frontend_port=None,
        backend_reload=None,
        startup_timeout=None,
    )
    assert profile.name == "single-main"
    assert "MINI_AGENT_RUNTIME_MODE" in profile.backend_env
    assert profile.frontend_env["VITE_API_BASE"].startswith("http://127.0.0.1:")


def test_profile_override_placeholders(tmp_path: Path) -> None:
    manager = StudioDevManager(
        repo_root=_make_repo_root(tmp_path),
        state_root=(tmp_path / ".studio-dev-state"),
    )
    profile_path = manager.ensure_profile_template("custom")
    payload = json.loads(profile_path.read_text(encoding="utf-8"))
    payload["backend_env"]["MINI_AGENT_MAIN_WORKSPACE"] = "{{repo_root}}/workspace-main"
    payload["frontend_env"]["VITE_API_BASE"] = "http://{{host}}:{{gateway_port}}"
    payload["host"] = "127.0.0.1"
    payload["gateway_port"] = 9008
    profile_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    profile = manager.resolve_profile(
        profile_name="custom",
        host="127.0.0.1",
        gateway_port=9100,
        frontend_port=5174,
        backend_reload=None,
        startup_timeout=None,
    )
    assert profile.backend_env["MINI_AGENT_MAIN_WORKSPACE"].endswith("workspace-main")
    assert profile.frontend_env["VITE_API_BASE"] == "http://127.0.0.1:9100"
