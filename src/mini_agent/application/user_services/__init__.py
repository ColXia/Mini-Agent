"""User-service exports for surface-facing application entrypoints."""

from __future__ import annotations

from importlib import import_module

from .agent_user_service import AgentUserService
from .command_user_service import CommandUserService
from .model_user_service import ModelUserService
from .service_assembly import (
    RuntimeBackedUserServicePorts,
    UserServiceAssembly,
    assemble_typed_user_services,
    resolve_runtime_backed_user_service_ports,
)
from .workspace_user_service import WorkspaceUserService

__all__ = [
    "AgentUserService",
    "CommandUserService",
    "ModelUserService",
    "RuntimeBackedUserServicePorts",
    "UserServiceAssembly",
    "WorkspaceUserService",
    "assemble_typed_user_services",
    "resolve_runtime_backed_user_service_ports",
]

_COMPAT_EXPORTS: dict[str, tuple[str, str]] = {
    "assemble_runtime_backed_user_services": (
        ".service_assembly",
        "assemble_runtime_backed_user_services",
    ),
}


def __getattr__(name: str):
    export = _COMPAT_EXPORTS.get(name)
    if export is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module_name, attr_name = export
    module = import_module(module_name, __name__)
    value = getattr(module, attr_name)
    globals()[name] = value
    return value
