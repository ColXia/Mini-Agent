"""Compatibility re-export for main-agent runtime policy loading helpers."""

from __future__ import annotations

from importlib import import_module

__all__ = [
    "MAIN_AGENT_MAIN_WORKSPACE_ENV",
    "MAIN_AGENT_RUNTIME_MODE_ENV",
    "MAIN_AGENT_TEAM_MAX_AGENTS_ENV",
    "load_main_agent_runtime_policy",
]

_COMPAT_EXPORTS: dict[str, tuple[str, str]] = {
    "MAIN_AGENT_MAIN_WORKSPACE_ENV": (
        ".support.main_agent_runtime_policy_loader",
        "MAIN_AGENT_MAIN_WORKSPACE_ENV",
    ),
    "MAIN_AGENT_RUNTIME_MODE_ENV": (
        ".support.main_agent_runtime_policy_loader",
        "MAIN_AGENT_RUNTIME_MODE_ENV",
    ),
    "MAIN_AGENT_TEAM_MAX_AGENTS_ENV": (
        ".support.main_agent_runtime_policy_loader",
        "MAIN_AGENT_TEAM_MAX_AGENTS_ENV",
    ),
    "load_main_agent_runtime_policy": (
        ".support.main_agent_runtime_policy_loader",
        "load_main_agent_runtime_policy",
    ),
}


def __getattr__(name: str):
    export = _COMPAT_EXPORTS.get(name)
    if export is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module_name, attr_name = export
    module = import_module(module_name, __package__)
    value = getattr(module, attr_name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(__all__))
