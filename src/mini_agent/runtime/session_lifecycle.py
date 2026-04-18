"""Compatibility re-export for runtime session lifecycle helpers."""

from __future__ import annotations

from importlib import import_module

__all__ = [
    "SESSION_IDLE_SECONDS_ENV",
    "SESSION_RESET_MODE_ENV",
    "SessionLifecycleDecision",
    "SurfaceSessionLifecycleRuntime",
    "build_surface_session_key",
    "resolve_session_lifecycle_policy",
]

_COMPAT_EXPORTS: dict[str, tuple[str, str]] = {
    "SESSION_IDLE_SECONDS_ENV": (".support.session_lifecycle", "SESSION_IDLE_SECONDS_ENV"),
    "SESSION_RESET_MODE_ENV": (".support.session_lifecycle", "SESSION_RESET_MODE_ENV"),
    "SessionLifecycleDecision": (".support.session_lifecycle", "SessionLifecycleDecision"),
    "SurfaceSessionLifecycleRuntime": (".support.session_lifecycle", "SurfaceSessionLifecycleRuntime"),
    "build_surface_session_key": (".support.session_lifecycle", "build_surface_session_key"),
    "resolve_session_lifecycle_policy": (
        ".support.session_lifecycle",
        "resolve_session_lifecycle_policy",
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
