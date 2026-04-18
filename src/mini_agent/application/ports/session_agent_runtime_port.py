"""Compatibility re-export for session-scoped agent compatibility runtime ports."""

from __future__ import annotations

from importlib import import_module

__all__ = ["SessionAgentRuntimePort"]

_COMPAT_EXPORTS: dict[str, tuple[str, str]] = {
    "SessionAgentRuntimePort": ("mini_agent.application.legacy.session_agent_runtime_port", "SessionAgentRuntimePort"),
}


def __getattr__(name: str):
    export = _COMPAT_EXPORTS.get(name)
    if export is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module_name, attr_name = export
    module = import_module(module_name)
    value = getattr(module, attr_name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(__all__))
