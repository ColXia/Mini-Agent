"""Compatibility re-export for surface chat flow helpers."""

from __future__ import annotations

from importlib import import_module

__all__ = [
    "ExecuteSurfaceChatTurnFn",
    "SurfaceChatExecutionRequest",
    "SurfaceChatExecutionResult",
    "SurfaceChatFlowHandler",
    "SurfaceChatStreamEvent",
]

_COMPAT_EXPORTS: dict[str, tuple[str, str]] = {
    "ExecuteSurfaceChatTurnFn": (".facades.surface_chat_flow_handler", "ExecuteSurfaceChatTurnFn"),
    "SurfaceChatExecutionRequest": (
        ".facades.surface_chat_flow_handler",
        "SurfaceChatExecutionRequest",
    ),
    "SurfaceChatExecutionResult": (
        ".facades.surface_chat_flow_handler",
        "SurfaceChatExecutionResult",
    ),
    "SurfaceChatFlowHandler": (".facades.surface_chat_flow_handler", "SurfaceChatFlowHandler"),
    "SurfaceChatStreamEvent": (".facades.surface_chat_flow_handler", "SurfaceChatStreamEvent"),
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
