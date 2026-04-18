"""Compatibility re-export for the legacy main-agent surface assembly helpers."""

from __future__ import annotations

from importlib import import_module

__all__ = [
    "MainAgentSurfaceAssembly",
    "assemble_main_agent_surface_service",
    "assemble_runtime_backed_main_agent_surface_service",
    "build_main_agent_surface_service",
    "build_runtime_backed_main_agent_surface_service",
]

_COMPAT_EXPORTS: dict[str, tuple[str, str]] = {
    "MainAgentSurfaceAssembly": ("..legacy.surface_service_assembly", "MainAgentSurfaceAssembly"),
    "assemble_main_agent_surface_service": (
        "..legacy.surface_service_assembly",
        "assemble_main_agent_surface_service",
    ),
    "assemble_runtime_backed_main_agent_surface_service": (
        "..legacy.surface_service_assembly",
        "assemble_runtime_backed_main_agent_surface_service",
    ),
    "build_main_agent_surface_service": ("..legacy.surface_service_assembly", "build_main_agent_surface_service"),
    "build_runtime_backed_main_agent_surface_service": (
        "..legacy.surface_service_assembly",
        "build_runtime_backed_main_agent_surface_service",
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
