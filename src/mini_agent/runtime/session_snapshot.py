"""Compatibility re-export for runtime session snapshot DTOs."""

from __future__ import annotations

from importlib import import_module

__all__ = [
    "RuntimeSessionImportMessage",
    "RuntimeSessionImportRequest",
    "RuntimeSessionSnapshot",
]

_COMPAT_EXPORTS: dict[str, tuple[str, str]] = {
    "RuntimeSessionImportMessage": (".support.session_snapshot", "RuntimeSessionImportMessage"),
    "RuntimeSessionImportRequest": (".support.session_snapshot", "RuntimeSessionImportRequest"),
    "RuntimeSessionSnapshot": (".support.session_snapshot", "RuntimeSessionSnapshot"),
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
