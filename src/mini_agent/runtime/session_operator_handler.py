"""Compatibility re-export for the runtime session operator handler."""

from __future__ import annotations

from importlib import import_module

__all__ = [
    "RuntimeSessionContextPolicyExecution",
    "RuntimeSessionModelSelectionExecution",
    "RuntimeSessionOperatorHandler",
    "RuntimeSessionSkillMutationExecution",
]

_COMPAT_EXPORTS: dict[str, tuple[str, str]] = {
    "RuntimeSessionContextPolicyExecution": (
        ".handlers.session_operator_handler",
        "RuntimeSessionContextPolicyExecution",
    ),
    "RuntimeSessionModelSelectionExecution": (
        ".handlers.session_operator_handler",
        "RuntimeSessionModelSelectionExecution",
    ),
    "RuntimeSessionOperatorHandler": (".handlers.session_operator_handler", "RuntimeSessionOperatorHandler"),
    "RuntimeSessionSkillMutationExecution": (
        ".handlers.session_operator_handler",
        "RuntimeSessionSkillMutationExecution",
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
