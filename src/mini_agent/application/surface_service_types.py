"""Compatibility re-export for the support surface service types module."""

from __future__ import annotations

from importlib import import_module

__all__ = [
    "FormatBootstrapErrorFn",
    "ResolveWorkspaceDirFn",
    "SseEventFn",
    "ToUtcIsoFn",
]

_COMPAT_EXPORTS: dict[str, tuple[str, str]] = {
    "FormatBootstrapErrorFn": (".support.surface_service_types", "FormatBootstrapErrorFn"),
    "ResolveWorkspaceDirFn": (".support.surface_service_types", "ResolveWorkspaceDirFn"),
    "SseEventFn": (".support.surface_service_types", "SseEventFn"),
    "ToUtcIsoFn": (".support.surface_service_types", "ToUtcIsoFn"),
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
