"""Compatibility re-export for the legacy main-agent surface assembly helpers."""

from ..legacy.surface_service_assembly import (
    MainAgentSurfaceAssembly,
    assemble_main_agent_surface_service,
    assemble_runtime_backed_main_agent_surface_service,
    build_main_agent_surface_service,
    build_runtime_backed_main_agent_surface_service,
)

__all__ = [
    "MainAgentSurfaceAssembly",
    "assemble_main_agent_surface_service",
    "assemble_runtime_backed_main_agent_surface_service",
    "build_main_agent_surface_service",
    "build_runtime_backed_main_agent_surface_service",
]
