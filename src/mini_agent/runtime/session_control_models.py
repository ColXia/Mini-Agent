"""Compatibility re-export for runtime session control models."""

from __future__ import annotations

from importlib import import_module

__all__ = [
    "RuntimeSessionControlCommand",
    "RuntimeSessionControlExecution",
    "SESSION_AGENT_CONTROL_ACTIONS",
    "SESSION_MCP_CONTROL_ACTIONS",
    "SUPPORTED_SESSION_CONTROL_ACTIONS",
    "normalize_session_control_action",
]

_COMPAT_EXPORTS: dict[str, tuple[str, str]] = {
    "RuntimeSessionControlCommand": (".support.session_control_models", "RuntimeSessionControlCommand"),
    "RuntimeSessionControlExecution": (".support.session_control_models", "RuntimeSessionControlExecution"),
    "SESSION_AGENT_CONTROL_ACTIONS": (".support.session_control_models", "SESSION_AGENT_CONTROL_ACTIONS"),
    "SESSION_MCP_CONTROL_ACTIONS": (".support.session_control_models", "SESSION_MCP_CONTROL_ACTIONS"),
    "SUPPORTED_SESSION_CONTROL_ACTIONS": (
        ".support.session_control_models",
        "SUPPORTED_SESSION_CONTROL_ACTIONS",
    ),
    "normalize_session_control_action": (
        ".support.session_control_models",
        "normalize_session_control_action",
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
