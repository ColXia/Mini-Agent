"""Deterministic runtime-mode matrix tests for P19 rollout."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from apps.agent_studio_gateway import main as gateway_main
from mini_agent.runtime.main_agent_runtime_manager import (
    MainAgentRuntimeManager,
    MainAgentRuntimeMode,
    MainAgentRuntimePolicy,
)


class _DummyAgent:
    def __init__(self) -> None:
        self.messages = [SimpleNamespace(role="system", content="system")]
        self.api_total_tokens = 0

    def add_user_message(self, content: str) -> None:
        self.messages.append(SimpleNamespace(role="user", content=content))

    async def run(self) -> str:
        text = f"mock:{self.messages[-1].content}"
        self.messages.append(SimpleNamespace(role="assistant", content=text))
        self.api_total_tokens += 7
        return text


@pytest.mark.asyncio
async def test_single_main_profile_contract(monkeypatch: pytest.MonkeyPatch) -> None:
    repo_root = gateway_main.REPO_ROOT.resolve()

    monkeypatch.setattr(gateway_main, "MAIN_AGENT_RUNTIME_MODE_RAW", "single_main")
    monkeypatch.setattr(gateway_main, "MAIN_AGENT_MAIN_WORKSPACE_RAW", str(repo_root))
    monkeypatch.setattr(gateway_main, "MAIN_AGENT_TEAM_MAX_AGENTS_RAW", "4")
    monkeypatch.setattr(gateway_main, "_MAIN_AGENT_RUNTIME_MANAGER", None)

    policy = gateway_main._parse_main_agent_runtime_policy()
    assert policy.mode == MainAgentRuntimeMode.SINGLE_MAIN
    assert policy.max_active_sessions == 1
    assert policy.reserved_team_slots == 4
    assert policy.workspace_application_required is True
    assert policy.main_workspace_dir == repo_root

    health = await gateway_main._build_health_response()
    assert health.runtime.mode == "single_main"
    assert health.runtime.max_active_sessions == 1
    assert health.runtime.active_sessions == 0
    assert health.runtime.available_session_slots == 1
    assert health.runtime.team_saturation_rejections == 0
    assert health.runtime.team_workspace_conflict_rejections == 0
    assert health.runtime.lifecycle_auto_resets == 0
    assert health.runtime.session_reset_mode == "none"
    assert health.runtime.session_idle_seconds >= 1
    assert health.runtime.main_workspace_dir
    assert health.runtime.workspace_application_required is True


@pytest.mark.asyncio
async def test_team_profile_contract(monkeypatch: pytest.MonkeyPatch) -> None:
    repo_root = gateway_main.REPO_ROOT.resolve()

    monkeypatch.setattr(gateway_main, "MAIN_AGENT_RUNTIME_MODE_RAW", "team")
    monkeypatch.setattr(gateway_main, "MAIN_AGENT_MAIN_WORKSPACE_RAW", str(repo_root))
    monkeypatch.setattr(gateway_main, "MAIN_AGENT_TEAM_MAX_AGENTS_RAW", "2")
    monkeypatch.setattr(gateway_main, "_MAIN_AGENT_RUNTIME_MANAGER", None)

    policy = gateway_main._parse_main_agent_runtime_policy()
    assert policy.mode == MainAgentRuntimeMode.TEAM
    assert policy.max_active_sessions == 2
    assert policy.reserved_team_slots == 2
    assert policy.workspace_application_required is True
    assert policy.main_workspace_dir == repo_root

    health = await gateway_main._build_health_response()
    assert health.runtime.mode == "team"
    assert health.runtime.max_active_sessions == 2
    assert health.runtime.active_sessions == 0
    assert health.runtime.available_session_slots == 2
    assert health.runtime.team_saturation_rejections == 0
    assert health.runtime.team_workspace_conflict_rejections == 0
    assert health.runtime.lifecycle_auto_resets == 0
    assert health.runtime.session_reset_mode == "none"
    assert health.runtime.session_idle_seconds >= 1
    assert health.runtime.main_workspace_dir
    assert health.runtime.workspace_application_required is True

    async def _build_agent(_workspace: Path):
        return _DummyAgent()

    runtime = MainAgentRuntimeManager(
        ttl_seconds=3600,
        build_agent=_build_agent,
        policy=MainAgentRuntimePolicy(
            mode=MainAgentRuntimeMode.TEAM,
            main_workspace_dir=repo_root,
            max_active_sessions=2,
            reserved_team_slots=2,
        ),
    )

    workspace_a = repo_root
    workspace_b = (repo_root / "workspace-b").resolve()
    workspace_c = (repo_root / "workspace-c").resolve()

    first = await runtime.get_or_create_session("sess-a", workspace_a)
    second = await runtime.get_or_create_session("sess-b", workspace_b)
    assert first.session_id == "sess-a"
    assert second.session_id == "sess-b"

    # Guardrail: no session_id on same workspace should reuse existing session.
    reused = await runtime.get_or_create_session(None, workspace_a)
    assert reused.session_id == "sess-a"

    # Guardrail: capacity remains bounded at max_active_sessions.
    with pytest.raises(Exception) as exc_info:
        await runtime.get_or_create_session("sess-c", workspace_c)
    exc = exc_info.value
    assert getattr(exc, "status_code", None) == 409
    assert "max_active_sessions" in str(getattr(exc, "detail", ""))

    diagnostics = await runtime.get_runtime_diagnostics()
    assert diagnostics.mode == "team"
    assert diagnostics.active_sessions == 2
    assert diagnostics.max_active_sessions == 2
    assert diagnostics.available_session_slots == 0
    assert diagnostics.reserved_team_slots == 2
    assert diagnostics.team_saturation_rejections == 1
    assert diagnostics.team_workspace_conflict_rejections == 0
