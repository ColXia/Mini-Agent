"""Compatibility re-export for runtime tooling helpers."""

from __future__ import annotations

from importlib import import_module
from pathlib import Path
from typing import Any

from mini_agent.commands.mcp_support import resolve_runtime_mcp_config_path


_COMPAT_EXPORTS: dict[str, tuple[str, str]] = {
    "add_workspace_tools": (".support.tooling", "add_workspace_tools"),
    "apply_runtime_policy_to_agent": (".support.tooling", "apply_runtime_policy_to_agent"),
    "build_approval_engine": (".support.tooling", "build_approval_engine"),
    "build_workspace_sandbox_manager": (".support.tooling", "build_workspace_sandbox_manager"),
    "reconfigure_agent_runtime_policy": (".support.tooling", "reconfigure_agent_runtime_policy"),
    "resolve_runtime_policy": (".support.tooling", "resolve_runtime_policy"),
}


def _runtime_tooling_impl():
    return import_module(".support.tooling", __package__)


def __getattr__(name: str):
    export = _COMPAT_EXPORTS.get(name)
    if export is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module_name, attr_name = export
    module = import_module(module_name, __package__)
    value = getattr(module, attr_name)
    globals()[name] = value
    return value


def _sync_runtime_tooling_globals() -> None:
    """Keep compatibility monkeypatches visible to the real owner module."""
    _runtime_tooling_impl().resolve_runtime_mcp_config_path = resolve_runtime_mcp_config_path


async def initialize_shared_tools(
    config,
    workspace_dir: Path,
    policy_engine: Any,
) -> tuple[list, Any, dict[str, Any]]:
    _sync_runtime_tooling_globals()
    return await _runtime_tooling_impl().initialize_shared_tools(
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
    return await _runtime_tooling_impl().initialize_agent_tools(
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


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(__all__))
