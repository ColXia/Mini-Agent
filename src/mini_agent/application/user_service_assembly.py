"""Compatibility re-export for explicit user-service assembly helpers."""

from .user_services.service_assembly import (
    RuntimeBackedUserServicePorts,
    UserServiceAssembly,
    assemble_runtime_backed_user_services,
    assemble_typed_user_services,
    resolve_runtime_backed_user_service_ports,
)

__all__ = [
    "RuntimeBackedUserServicePorts",
    "UserServiceAssembly",
    "assemble_runtime_backed_user_services",
    "assemble_typed_user_services",
    "resolve_runtime_backed_user_service_ports",
]
