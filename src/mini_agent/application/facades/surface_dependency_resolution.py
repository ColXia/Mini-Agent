"""Compatibility re-export for the legacy surface dependency-resolution helpers."""

from __future__ import annotations

from importlib import import_module

__all__ = [
    "LegacySurfaceRunControlAdapter",
    "resolve_surface_agent_entry_service",
    "resolve_surface_model_entry_service",
    "resolve_surface_run_control_service",
    "resolve_surface_session_task_service",
    "resolve_surface_workspace_entry_service",
]

_COMPAT_EXPORTS: dict[str, tuple[str, str]] = {
    "LegacySurfaceRunControlAdapter": ("..legacy.surface_dependency_resolution", "LegacySurfaceRunControlAdapter"),
    "resolve_surface_agent_entry_service": (
        "..legacy.surface_dependency_resolution",
        "resolve_surface_agent_entry_service",
    ),
    "resolve_surface_model_entry_service": (
        "..legacy.surface_dependency_resolution",
        "resolve_surface_model_entry_service",
    ),
    "resolve_surface_run_control_service": (
        "..legacy.surface_dependency_resolution",
        "resolve_surface_run_control_service",
    ),
    "resolve_surface_session_task_service": (
        "..legacy.surface_dependency_resolution",
        "resolve_surface_session_task_service",
    ),
    "resolve_surface_workspace_entry_service": (
        "..legacy.surface_dependency_resolution",
        "resolve_surface_workspace_entry_service",
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
