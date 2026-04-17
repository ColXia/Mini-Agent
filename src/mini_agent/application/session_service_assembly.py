"""Compatibility re-export for legacy session application assembly helpers."""

from .legacy.session_service_assembly import (
    RuntimeBackedSessionApplicationAssembly,
    assemble_runtime_backed_session_application,
    assemble_typed_session_application,
    build_runtime_backed_session_service,
    build_typed_session_service,
)

__all__ = [
    "RuntimeBackedSessionApplicationAssembly",
    "assemble_runtime_backed_session_application",
    "assemble_typed_session_application",
    "build_runtime_backed_session_service",
    "build_typed_session_service",
]
