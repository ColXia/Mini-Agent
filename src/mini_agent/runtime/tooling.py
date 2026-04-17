"""Compatibility re-export for runtime tooling helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from mini_agent.commands.mcp_support import resolve_runtime_mcp_config_path
from mini_agent.runtime.support import tooling as _impl

add_workspace_tools = _impl.add_workspace_tools
apply_runtime_policy_to_agent = _impl.apply_runtime_policy_to_agent
build_approval_engine = _impl.build_approval_engine
build_workspace_sandbox_manager = _impl.build_workspace_sandbox_manager
reconfigure_agent_runtime_policy = _impl.reconfigure_agent_runtime_policy
resolve_runtime_policy = _impl.resolve_runtime_policy


def _sync_runtime_tooling_globals() -> None:
    """Keep compatibility monkeypatches visible to the real owner module."""
    _impl.resolve_runtime_mcp_config_path = resolve_runtime_mcp_config_path


async def initialize_shared_tools(
    config,
    workspace_dir: Path,
    policy_engine: Any,
) -> tuple[list, Any, dict[str, Any]]:
    _sync_runtime_tooling_globals()
    return await _impl.initialize_shared_tools(
        config,
        workspace_dir=workspace_dir,
        policy_engine=policy_engine,
    )


async def initialize_agent_tools(
    config,
    workspace_dir: Path,
    approval_profile_override: str | None = None,
    access_level_override: str | None = None,
) -> tuple[list, Any, dict[str, Any]]:
    _sync_runtime_tooling_globals()
    return await _impl.initialize_agent_tools(
        config,
        workspace_dir,
        approval_profile_override=approval_profile_override,
        access_level_override=access_level_override,
    )


__all__ = [
    "add_workspace_tools",
    "apply_runtime_policy_to_agent",
    "build_approval_engine",
    "build_workspace_sandbox_manager",
    "initialize_agent_tools",
    "initialize_shared_tools",
    "reconfigure_agent_runtime_policy",
    "resolve_runtime_mcp_config_path",
    "resolve_runtime_policy",
]
