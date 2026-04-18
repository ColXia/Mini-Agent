"""Compatibility re-export for explicit user-service assembly helpers."""

from __future__ import annotations

from importlib import import_module

__all__ = [
    "RuntimeBackedUserServicePorts",
    "UserServiceAssembly",
    "assemble_runtime_backed_user_services",
    "assemble_typed_user_services",
    "resolve_runtime_backed_user_service_ports",
]

_COMPAT_EXPORTS: dict[str, tuple[str, str]] = {
    "RuntimeBackedUserServicePorts": (".user_services.service_assembly", "RuntimeBackedUserServicePorts"),
    "UserServiceAssembly": (".user_services.service_assembly", "UserServiceAssembly"),
    "assemble_runtime_backed_user_services": (
        ".user_services.service_assembly",
        "assemble_runtime_backed_user_services",
    ),
    "assemble_typed_user_services": (".user_services.service_assembly", "assemble_typed_user_services"),
    "resolve_runtime_backed_user_service_ports": (
        ".user_services.service_assembly",
        "resolve_runtime_backed_user_service_ports",
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
