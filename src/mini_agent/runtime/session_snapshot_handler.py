"""Compatibility re-export for runtime snapshot routing helpers."""

from __future__ import annotations

from importlib import import_module

__all__ = [
    "RuntimeSessionSnapshotHandler",
    "RuntimeSessionSnapshotImportCommand",
    "RuntimeSessionSnapshotImportPlan",
]

_COMPAT_EXPORTS: dict[str, tuple[str, str]] = {
    "RuntimeSessionSnapshotHandler": (
        ".orchestration.session_snapshot_handler",
        "RuntimeSessionSnapshotHandler",
    ),
    "RuntimeSessionSnapshotImportCommand": (
        ".orchestration.session_snapshot_handler",
        "RuntimeSessionSnapshotImportCommand",
    ),
    "RuntimeSessionSnapshotImportPlan": (
        ".orchestration.session_snapshot_handler",
        "RuntimeSessionSnapshotImportPlan",
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
