from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import HTTPException

from mini_agent.config import AgentConfig, Config, LLMConfig, SecurityConfig, ToolsConfig
from mini_agent.runtime.main_agent_runtime_contracts import MainAgentRuntimeDiagnostics
from mini_agent.runtime.workspace_runtime_adapter import MainAgentWorkspaceRuntimeAdapter
from mini_agent.runtime.support.workspace_path_utils import same_workspace_path


def _make_config() -> Config:
    return Config(
        llm=LLMConfig(api_key="test-key"),
        agent=AgentConfig(),
        tools=ToolsConfig(enable_mcp=False, enable_skills=False),
        security=SecurityConfig(approval_profile="build", sandbox_mode="workspace"),
    )


class _RuntimeManagerStub:
    def __init__(self, *, main_workspace: Path, project_workspace: Path) -> None:
        self.main_workspace = main_workspace.resolve()
        self.project_workspace = project_workspace.resolve()

    async def list_sessions(self, *, workspace_dir=None, shared_only=False):  # noqa: ANN001, ANN003
        _ = workspace_dir
        sessions = [
            {
                "session_id": "sess-main",
                "workspace_dir": str(self.main_workspace),
                "updated_at": "2026-04-18T10:00:00+00:00",
                "busy": True,
                "shared": False,
                "is_default": False,
            },
            {
                "session_id": "sess-project",
                "workspace_dir": str(self.project_workspace),
                "updated_at": "2026-04-17T10:00:00+00:00",
                "busy": False,
                "shared": True,
                "is_default": False,
            },
        ]
        if shared_only:
            return [item for item in sessions if item["shared"]]
        return sessions

    async def get_runtime_diagnostics(self):
        return MainAgentRuntimeDiagnostics(
            mode="single_main",
            active_sessions=1,
            max_active_sessions=1,
            available_session_slots=0,
            reserved_team_slots=4,
            workspace_application_required=True,
            team_saturation_rejections=0,
            team_workspace_conflict_rejections=0,
            lifecycle_auto_resets=0,
            session_reset_mode="idle",
            session_idle_seconds=3600,
            main_workspace_dir=str(self.main_workspace),
        )

    def validate_workspace(self, workspace_dir: Path) -> None:
        if same_workspace_path(workspace_dir, self.main_workspace):
            return
        raise HTTPException(status_code=409, detail="single-main workspace only")


@pytest.mark.asyncio
async def test_workspace_runtime_adapter_lists_workspaces_and_resolves_active_workspace(tmp_path: Path) -> None:
    main_workspace = tmp_path / "default"
    project_workspace = tmp_path / "project-a"
    main_workspace.mkdir()
    project_workspace.mkdir()
    adapter = MainAgentWorkspaceRuntimeAdapter(
        runtime_manager=_RuntimeManagerStub(
            main_workspace=main_workspace,
            project_workspace=project_workspace,
        ),
        config_loader=_make_config,
        repo_root=main_workspace,
    )

    workspaces = await adapter.list_workspaces()
    active = await adapter.get_active_workspace()

    assert len(workspaces) == 2
    assert workspaces[0]["workspace_dir"] == str(main_workspace.resolve())
    assert workspaces[0]["active"] is True
    assert workspaces[0]["default"] is True
    assert workspaces[0]["session_count"] == 1
    assert workspaces[1]["workspace_dir"] == str(project_workspace.resolve())
    assert workspaces[1]["shared_session_count"] == 1
    assert active["workspace_dir"] == str(main_workspace.resolve())
    assert active["active"] is True


@pytest.mark.asyncio
async def test_workspace_runtime_adapter_builds_runtime_summary(tmp_path: Path) -> None:
    main_workspace = tmp_path / "default"
    project_workspace = tmp_path / "project-a"
    main_workspace.mkdir()
    project_workspace.mkdir()
    adapter = MainAgentWorkspaceRuntimeAdapter(
        runtime_manager=_RuntimeManagerStub(
            main_workspace=main_workspace,
            project_workspace=project_workspace,
        ),
        config_loader=_make_config,
        repo_root=main_workspace,
    )

    summary = await adapter.get_workspace_runtime_summary()

    assert summary["workspace_dir"] == str(main_workspace.resolve())
    assert summary["runtime_policy"]["mode"] == "single_main"
    assert summary["runtime"]["workspace_root"] == str(main_workspace.resolve())
    assert summary["runtime"]["mode"] == "direct"
    assert summary["runtime"]["scope"] == "workspace_only"


@pytest.mark.asyncio
async def test_workspace_runtime_adapter_rejects_switch_outside_main_workspace_in_single_main_mode(tmp_path: Path) -> None:
    main_workspace = tmp_path / "default"
    project_workspace = tmp_path / "project-a"
    main_workspace.mkdir()
    project_workspace.mkdir()
    adapter = MainAgentWorkspaceRuntimeAdapter(
        runtime_manager=_RuntimeManagerStub(
            main_workspace=main_workspace,
            project_workspace=project_workspace,
        ),
        config_loader=_make_config,
        repo_root=main_workspace,
    )

    with pytest.raises(HTTPException, match="single-main workspace only"):
        await adapter.switch_workspace(str(project_workspace))
