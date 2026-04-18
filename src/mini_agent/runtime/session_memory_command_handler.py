"""Compatibility re-export for runtime memory command handlers."""

from __future__ import annotations

from importlib import import_module

__all__ = [
    "MUTATING_MEMORY_ACTIONS",
    "RuntimeSessionMemoryCommand",
    "RuntimeSessionMemoryCommandExecution",
    "RuntimeSessionMemoryCommandHandler",
    "SUPPORTED_MEMORY_ACTIONS",
]

_COMPAT_EXPORTS: dict[str, tuple[str, str]] = {
    "MUTATING_MEMORY_ACTIONS": (".handlers.session_memory_command_handler", "MUTATING_MEMORY_ACTIONS"),
    "SUPPORTED_MEMORY_ACTIONS": (".handlers.session_memory_command_handler", "SUPPORTED_MEMORY_ACTIONS"),
    "RuntimeSessionMemoryCommand": (
        ".handlers.session_memory_command_handler",
        "RuntimeSessionMemoryCommand",
    ),
    "RuntimeSessionMemoryCommandExecution": (
        ".handlers.session_memory_command_handler",
        "RuntimeSessionMemoryCommandExecution",
    ),
    "RuntimeSessionMemoryCommandHandler": (
        ".handlers.session_memory_command_handler",
        "RuntimeSessionMemoryCommandHandler",
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
