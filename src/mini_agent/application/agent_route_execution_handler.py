"""Compatibility re-export for surface route execution helpers."""

from __future__ import annotations

from importlib import import_module

__all__ = [
    "AgentRouteExecutionHandler",
    "get_model_route_diagnostics_state",
]

_COMPAT_EXPORTS: dict[str, tuple[str, str]] = {
    "AgentRouteExecutionHandler": (".facades.agent_route_execution_handler", "AgentRouteExecutionHandler"),
    "get_model_route_diagnostics_state": (
        "mini_agent.model_manager.runtime",
        "get_model_route_diagnostics_state",
    ),
}


def __getattr__(name: str):
    export = _COMPAT_EXPORTS.get(name)
    if export is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module_name, attr_name = export
    import_package = None if module_name.startswith("mini_agent.") else __package__
    module = import_module(module_name, import_package)
    value = getattr(module, attr_name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(__all__))
