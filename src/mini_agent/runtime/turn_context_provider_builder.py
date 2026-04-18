"""Compatibility re-export for runtime turn-context provider assembly."""

from __future__ import annotations

from importlib import import_module

__all__ = ["build_turn_context_providers"]

_COMPAT_EXPORTS: dict[str, tuple[str, str]] = {
    "build_turn_context_providers": (
        ".support.turn_context_provider_builder",
        "build_turn_context_providers",
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
