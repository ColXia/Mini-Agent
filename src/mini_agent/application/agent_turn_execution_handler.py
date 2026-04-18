"""Compatibility re-export for surface agent turn execution helpers."""

from __future__ import annotations

from importlib import import_module

__all__ = [
    "AgentTurnExecutionHandler",
    "SurfaceActivityEmitter",
    "SurfaceAgentExecutionRequest",
]

_COMPAT_EXPORTS: dict[str, tuple[str, str]] = {
    "AgentTurnExecutionHandler": (".facades.agent_turn_execution_handler", "AgentTurnExecutionHandler"),
    "SurfaceActivityEmitter": (".facades.agent_turn_execution_handler", "SurfaceActivityEmitter"),
    "SurfaceAgentExecutionRequest": (
        ".facades.agent_turn_execution_handler",
        "SurfaceAgentExecutionRequest",
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
