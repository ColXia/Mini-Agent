"""Compatibility re-export for legacy session application assembly helpers."""

from __future__ import annotations

from importlib import import_module

__all__ = [
    "RuntimeBackedSessionApplicationAssembly",
    "assemble_runtime_backed_session_application",
    "assemble_typed_session_application",
    "build_runtime_backed_session_service",
    "build_typed_session_service",
]

_COMPAT_EXPORTS: dict[str, tuple[str, str]] = {
    "RuntimeBackedSessionApplicationAssembly": (
        ".legacy.session_service_assembly",
        "RuntimeBackedSessionApplicationAssembly",
    ),
    "assemble_runtime_backed_session_application": (
        ".legacy.session_service_assembly",
        "assemble_runtime_backed_session_application",
    ),
    "assemble_typed_session_application": (
        ".legacy.session_service_assembly",
        "assemble_typed_session_application",
    ),
    "build_runtime_backed_session_service": (
        ".legacy.session_service_assembly",
        "build_runtime_backed_session_service",
    ),
    "build_typed_session_service": (
        ".legacy.session_service_assembly",
        "build_typed_session_service",
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
