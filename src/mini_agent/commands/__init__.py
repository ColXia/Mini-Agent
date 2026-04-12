"""Shared command catalog helpers for TUI/CLI/QQ surfaces."""

from .catalog import (
    build_command_example_text,
    build_command_help_text,
    build_command_usage_text,
    build_unknown_action_text,
    command_action_candidates,
    command_completion_tokens,
    command_entry_for_surface,
    command_entries_for_surface,
    command_forms_for_surface,
    load_command_catalog,
    suggest_command_action,
)
from .execution import (
    CommandExecutionResult,
    LocalOperatorCommandService,
    McpReloadOutcome,
    parse_memory_show_target,
)
from .router import (
    CommandDispatcher,
    CommandInvocation,
    CommandParseError,
    normalize_command_name,
    parse_command_text,
    suggest_command_name,
)

__all__ = [
    "build_command_example_text",
    "build_command_help_text",
    "build_command_usage_text",
    "build_unknown_action_text",
    "command_action_candidates",
    "command_completion_tokens",
    "command_entry_for_surface",
    "command_entries_for_surface",
    "command_forms_for_surface",
    "load_command_catalog",
    "suggest_command_action",
    "CommandExecutionResult",
    "LocalOperatorCommandService",
    "McpReloadOutcome",
    "parse_memory_show_target",
    "CommandDispatcher",
    "CommandInvocation",
    "CommandParseError",
    "normalize_command_name",
    "parse_command_text",
    "suggest_command_name",
]
