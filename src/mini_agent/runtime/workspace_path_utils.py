"""Compatibility re-export for runtime workspace path helpers."""

from __future__ import annotations

from importlib import import_module

__all__ = ["same_workspace_path", "workspace_path_key"]

_COMPAT_EXPORTS: dict[str, tuple[str, str]] = {
    "same_workspace_path": (".support.workspace_path_utils", "same_workspace_path"),
    "workspace_path_key": (".support.workspace_path_utils", "workspace_path_key"),
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
