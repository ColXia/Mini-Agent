"""Compatibility re-export for explicit user-service assembly helpers."""

from .user_services.service_assembly import (
    UserServiceAssembly,
    assemble_runtime_backed_user_services,
    assemble_typed_user_services,
)

__all__ = [
    "UserServiceAssembly",
    "assemble_runtime_backed_user_services",
    "assemble_typed_user_services",
]
