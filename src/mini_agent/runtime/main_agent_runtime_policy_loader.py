"""Runtime-policy loading helpers for main-agent host composition roots."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Mapping

from mini_agent.runtime.main_agent_runtime_contracts import (
    MainAgentRuntimeMode,
    MainAgentRuntimePolicy,
)
from mini_agent.runtime.support.session_lifecycle import resolve_session_lifecycle_policy


MAIN_AGENT_RUNTIME_MODE_ENV = "MINI_AGENT_RUNTIME_MODE"
MAIN_AGENT_MAIN_WORKSPACE_ENV = "MINI_AGENT_MAIN_WORKSPACE"
MAIN_AGENT_TEAM_MAX_AGENTS_ENV = "MINI_AGENT_TEAM_MAX_AGENTS"


def _read_env(environ: Mapping[str, str], name: str, default: str) -> str:
    return str(environ.get(name, default)).strip()


def _resolve_runtime_mode(raw_value: str) -> MainAgentRuntimeMode:
    normalized = str(raw_value or "").strip().lower()
    if normalized == MainAgentRuntimeMode.TEAM.value:
        return MainAgentRuntimeMode.TEAM
    return MainAgentRuntimeMode.SINGLE_MAIN


def _resolve_main_workspace_dir(repo_root: Path, raw_value: str) -> Path:
    raw_workspace = str(raw_value or "").strip() or str(repo_root)
    workspace_path = Path(raw_workspace).expanduser()
    return (workspace_path if workspace_path.is_absolute() else (repo_root / workspace_path)).resolve()


def _resolve_team_max_agents(raw_value: str) -> int:
    try:
        parsed = int(str(raw_value or "").strip() or "4")
    except ValueError:
        parsed = 4
    return max(1, parsed)


def load_main_agent_runtime_policy(
    repo_root: Path,
    *,
    environ: Mapping[str, str] | None = None,
) -> MainAgentRuntimePolicy:
    env = environ or os.environ
    mode = _resolve_runtime_mode(_read_env(env, MAIN_AGENT_RUNTIME_MODE_ENV, MainAgentRuntimeMode.SINGLE_MAIN.value))
    main_workspace_dir = _resolve_main_workspace_dir(
        repo_root.resolve(),
        _read_env(env, MAIN_AGENT_MAIN_WORKSPACE_ENV, str(repo_root)),
    )
    team_max_agents = _resolve_team_max_agents(_read_env(env, MAIN_AGENT_TEAM_MAX_AGENTS_ENV, "4"))
    session_lifecycle = resolve_session_lifecycle_policy()

    if mode == MainAgentRuntimeMode.SINGLE_MAIN:
        return MainAgentRuntimePolicy(
            mode=mode,
            main_workspace_dir=main_workspace_dir,
            max_active_sessions=1,
            reserved_team_slots=team_max_agents,
            workspace_application_required=True,
            session_lifecycle=session_lifecycle,
        )

    return MainAgentRuntimePolicy(
        mode=mode,
        main_workspace_dir=main_workspace_dir,
        max_active_sessions=team_max_agents,
        reserved_team_slots=team_max_agents,
        workspace_application_required=True,
        session_lifecycle=session_lifecycle,
    )


__all__ = [
    "MAIN_AGENT_MAIN_WORKSPACE_ENV",
    "MAIN_AGENT_RUNTIME_MODE_ENV",
    "MAIN_AGENT_TEAM_MAX_AGENTS_ENV",
    "load_main_agent_runtime_policy",
]
