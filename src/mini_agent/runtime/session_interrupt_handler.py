"""Compatibility re-export for runtime session interrupt routing."""

from __future__ import annotations

from importlib import import_module

__all__ = [
    "RuntimeSessionApprovalExecution",
    "RuntimeSessionCancelExecution",
    "RuntimeSessionInterruptHandler",
]

_COMPAT_EXPORTS: dict[str, tuple[str, str]] = {
    "RuntimeSessionApprovalExecution": (
        ".live_control.session_interrupt_handler",
        "RuntimeSessionApprovalExecution",
    ),
    "RuntimeSessionCancelExecution": (
        ".live_control.session_interrupt_handler",
        "RuntimeSessionCancelExecution",
    ),
    "RuntimeSessionInterruptHandler": (
        ".live_control.session_interrupt_handler",
        "RuntimeSessionInterruptHandler",
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
