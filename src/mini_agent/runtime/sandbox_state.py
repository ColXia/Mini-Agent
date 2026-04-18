"""Compatibility re-export for runtime sandbox diagnostics helpers."""

from __future__ import annotations

from importlib import import_module

__all__ = [
    "collect_sandbox_diagnostics",
    "compact_sandbox_summary",
    "format_sandbox_status",
    "normalize_sandbox_diagnostics",
    "sandbox_guardrail_summary",
    "sandbox_network_summary",
    "sandbox_policy_summary",
]

_COMPAT_EXPORTS: dict[str, tuple[str, str]] = {
    "collect_sandbox_diagnostics": (".support.sandbox_state", "collect_sandbox_diagnostics"),
    "compact_sandbox_summary": (".support.sandbox_state", "compact_sandbox_summary"),
    "format_sandbox_status": (".support.sandbox_state", "format_sandbox_status"),
    "normalize_sandbox_diagnostics": (".support.sandbox_state", "normalize_sandbox_diagnostics"),
    "sandbox_guardrail_summary": (".support.sandbox_state", "sandbox_guardrail_summary"),
    "sandbox_network_summary": (".support.sandbox_state", "sandbox_network_summary"),
    "sandbox_policy_summary": (".support.sandbox_state", "sandbox_policy_summary"),
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
