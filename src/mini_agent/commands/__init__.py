"""Shared command catalog helpers for TUI/CLI/QQ surfaces.

This package exports a small public surface, but importing everything eagerly
creates avoidable cycles between runtime tooling and command helpers. Keep the
package namespace lazy so callers can continue using `from mini_agent.commands
import ...` without forcing all command submodules to initialize at once.
"""

from __future__ import annotations

from importlib import import_module
from typing import Any

_EXPORT_MAP = {
    "build_command_example_text": (".catalog", "build_command_example_text"),
    "build_command_help_text": (".catalog", "build_command_help_text"),
    "build_command_usage_text": (".catalog", "build_command_usage_text"),
    "build_unknown_action_text": (".catalog", "build_unknown_action_text"),
    "CatalogModelUseRequest": (".execution", "CatalogModelUseRequest"),
    "command_action_candidates": (".catalog", "command_action_candidates"),
    "command_completion_tokens": (".catalog", "command_completion_tokens"),
    "command_entry_for_surface": (".catalog", "command_entry_for_surface"),
    "command_entries_for_surface": (".catalog", "command_entries_for_surface"),
    "command_forms_for_surface": (".catalog", "command_forms_for_surface"),
    "load_command_catalog": (".catalog", "load_command_catalog"),
    "suggest_command_action": (".catalog", "suggest_command_action"),
    "CommandExecutionResult": (".execution", "CommandExecutionResult"),
    "LocalOperatorCommandService": (".execution", "LocalOperatorCommandService"),
    "McpReloadOutcome": (".execution", "McpReloadOutcome"),
    "parse_memory_show_target": (".execution", "parse_memory_show_target"),
    "resolve_catalog_model_use_request": (".execution", "resolve_catalog_model_use_request"),
    "CommandDispatcher": (".router", "CommandDispatcher"),
    "CommandInvocation": (".router", "CommandInvocation"),
    "CommandParseError": (".router", "CommandParseError"),
    "normalize_command_name": (".router", "normalize_command_name"),
    "parse_command_text": (".router", "parse_command_text"),
    "suggest_command_name": (".router", "suggest_command_name"),
    "mcp_support": (".mcp_support", None),
}

__all__ = list(_EXPORT_MAP)


def __getattr__(name: str) -> Any:
    try:
        module_name, attr_name = _EXPORT_MAP[name]
    except KeyError as exc:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from exc

    module = import_module(module_name, __name__)
    value = module if attr_name is None else getattr(module, attr_name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(__all__))
