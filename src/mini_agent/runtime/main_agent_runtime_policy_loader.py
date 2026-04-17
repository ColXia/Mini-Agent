"""Compatibility re-export for main-agent runtime policy loading helpers."""

from .support.main_agent_runtime_policy_loader import (
    MAIN_AGENT_MAIN_WORKSPACE_ENV,
    MAIN_AGENT_RUNTIME_MODE_ENV,
    MAIN_AGENT_TEAM_MAX_AGENTS_ENV,
    load_main_agent_runtime_policy,
)

__all__ = [
    "MAIN_AGENT_MAIN_WORKSPACE_ENV",
    "MAIN_AGENT_RUNTIME_MODE_ENV",
    "MAIN_AGENT_TEAM_MAX_AGENTS_ENV",
    "load_main_agent_runtime_policy",
]
