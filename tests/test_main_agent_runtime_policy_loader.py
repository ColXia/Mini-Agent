from __future__ import annotations

from pathlib import Path

import pytest

from mini_agent.agent_core.session import SessionResetMode
from mini_agent.runtime.main_agent_runtime_contracts import MainAgentRuntimeMode
from mini_agent.runtime.support.main_agent_runtime_policy_loader import (
    MAIN_AGENT_MAIN_WORKSPACE_ENV,
    MAIN_AGENT_RUNTIME_MODE_ENV,
    MAIN_AGENT_TEAM_MAX_AGENTS_ENV,
    load_main_agent_runtime_policy,
)
from mini_agent.runtime.support.session_lifecycle import (
    SESSION_IDLE_SECONDS_ENV,
    SESSION_RESET_MODE_ENV,
)


def test_loader_builds_single_main_policy_from_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    monkeypatch.setenv(MAIN_AGENT_RUNTIME_MODE_ENV, "single_main")
    monkeypatch.setenv(MAIN_AGENT_MAIN_WORKSPACE_ENV, str(repo_root))
    monkeypatch.setenv(MAIN_AGENT_TEAM_MAX_AGENTS_ENV, "6")
    monkeypatch.setenv(SESSION_RESET_MODE_ENV, "idle")
    monkeypatch.setenv(SESSION_IDLE_SECONDS_ENV, "90")

    policy = load_main_agent_runtime_policy(repo_root)

    assert policy.mode == MainAgentRuntimeMode.SINGLE_MAIN
    assert policy.main_workspace_dir == repo_root.resolve()
    assert policy.max_active_sessions == 1
    assert policy.reserved_team_slots == 6
    assert policy.session_lifecycle.mode == SessionResetMode.IDLE
    assert policy.session_lifecycle.idle_seconds == 90


def test_loader_builds_team_policy_and_falls_back_for_invalid_values(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    monkeypatch.setenv(MAIN_AGENT_RUNTIME_MODE_ENV, "team")
    monkeypatch.setenv(MAIN_AGENT_MAIN_WORKSPACE_ENV, ".")
    monkeypatch.setenv(MAIN_AGENT_TEAM_MAX_AGENTS_ENV, "not-a-number")
    monkeypatch.setenv(SESSION_RESET_MODE_ENV, "invalid-mode")
    monkeypatch.setenv(SESSION_IDLE_SECONDS_ENV, "bad-seconds")

    policy = load_main_agent_runtime_policy(repo_root)

    assert policy.mode == MainAgentRuntimeMode.TEAM
    assert policy.main_workspace_dir == repo_root.resolve()
    assert policy.max_active_sessions == 4
    assert policy.reserved_team_slots == 4
    assert policy.session_lifecycle.mode == SessionResetMode.NONE
    assert policy.session_lifecycle.idle_seconds == 1800
