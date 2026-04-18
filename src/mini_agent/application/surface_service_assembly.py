"""Compatibility re-export for explicit main-agent surface assembly helpers."""

from .facades.surface_service_assembly import (
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
