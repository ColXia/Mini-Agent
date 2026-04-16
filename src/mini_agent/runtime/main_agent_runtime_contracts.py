"""Shared runtime contracts for main-agent session orchestration."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from mini_agent.agent_core.session import SessionLifecyclePolicy


class MainAgentRuntimeMode(str, Enum):
    """Runtime policy modes for main-agent orchestration."""

    SINGLE_MAIN = "single_main"
    TEAM = "team"


@dataclass(frozen=True)
class MainAgentRuntimePolicy:
    """Policy for current single-main mode and future team expansion."""

    mode: MainAgentRuntimeMode = MainAgentRuntimeMode.SINGLE_MAIN
    main_workspace_dir: Path | None = None
    max_active_sessions: int = 1
    reserved_team_slots: int = 4
    workspace_application_required: bool = True
    session_lifecycle: SessionLifecyclePolicy = field(default_factory=SessionLifecyclePolicy)


@dataclass(frozen=True)
class MainAgentRuntimeDiagnostics:
    """Runtime diagnostics snapshot for system health and ops inspection."""

    mode: str
    active_sessions: int
    max_active_sessions: int
    available_session_slots: int
    reserved_team_slots: int
    workspace_application_required: bool
    team_saturation_rejections: int
    team_workspace_conflict_rejections: int
    lifecycle_auto_resets: int
    session_reset_mode: str
    session_idle_seconds: int
    main_workspace_dir: str | None = None


__all__ = [
    "MainAgentRuntimeDiagnostics",
    "MainAgentRuntimeMode",
    "MainAgentRuntimePolicy",
]
