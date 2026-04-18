"""Compatibility re-export for the legacy surface dependency-resolution helpers."""

from ..legacy.surface_dependency_resolution import (
    LegacySurfaceRunControlAdapter,
    resolve_surface_agent_entry_service,
    resolve_surface_model_entry_service,
    resolve_surface_run_control_service,
    resolve_surface_session_task_service,
    resolve_surface_workspace_entry_service,
)

__all__ = [
    "LegacySurfaceRunControlAdapter",
    "resolve_surface_agent_entry_service",
    "resolve_surface_model_entry_service",
    "resolve_surface_run_control_service",
    "resolve_surface_session_task_service",
    "resolve_surface_workspace_entry_service",
]
