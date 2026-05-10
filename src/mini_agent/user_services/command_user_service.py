"""Command user service for v11.3.

This module provides the CommandUserService that sits between
User Surfaces and the Business Logic Layer for command-related operations.

Key responsibilities:
- Command parsing
- Command execution
- Command feedback
- Command help
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable

from mini_agent.utils.text import safe_text


def _safe_text(value: Any) -> str:
    return safe_text(value)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class CommandParseResultKind(str, Enum):
    """Result kinds for command parsing."""

    VALID = "valid"
    UNKNOWN_COMMAND = "unknown_command"
    INVALID_SYNTAX = "invalid_syntax"
    EMPTY_INPUT = "empty_input"


class CommandExecuteResultKind(str, Enum):
    """Result kinds for command execution."""

    SUCCESS = "success"
    FAILED = "failed"
    REJECTED = "rejected"
    PENDING = "pending"


@dataclass(frozen=True, slots=True)
class CommandInfo:
    """Information about a command."""

    name: str
    description: str
    usage: str
    aliases: tuple[str, ...] = ()
    requires_confirmation: bool = False
    category: str = "general"

    @property
    def full_usage(self) -> str:
        if self.aliases:
            return f"/{self.name} {self.usage} (aliases: {', '.join(self.aliases)})"
        return f"/{self.name} {self.usage}"


@dataclass(frozen=True, slots=True)
class CommandParseResult:
    """Result of command parsing."""

    result_kind: CommandParseResultKind
    command_name: str | None = None
    arguments: dict[str, Any] = field(default_factory=dict)
    raw_input: str = ""
    error_message: str | None = None


@dataclass(frozen=True, slots=True)
class CommandExecuteResult:
    """Result of command execution."""

    result_kind: CommandExecuteResultKind
    command_name: str | None = None
    output: str | None = None
    error_message: str | None = None
    requires_followup: bool = False
    followup_prompt: str | None = None


@dataclass(slots=True)
class CommandUserService:
    """User service for command-related operations.

    This service provides a stable interface for TUI / Desktop / Remote
    to interact with the command subsystem.

    The service aggregates:
    - Command registry
    - Command parsing
    - Command execution
    - Command help
    """

    _commands: dict[str, CommandInfo] = field(default_factory=dict)
    _aliases: dict[str, str] = field(default_factory=dict)
    _parser: Callable[[str], CommandParseResult] | None = None
    _executor: Callable[[str, dict[str, Any]], CommandExecuteResult] | None = None

    def parse_command(self, raw_input: str) -> CommandParseResult:
        """Parse a raw input string as a command.

        Args:
            raw_input: The raw input string

        Returns:
            A CommandParseResult
        """
        normalized = _safe_text(raw_input).strip()
        if not normalized:
            return CommandParseResult(
                result_kind=CommandParseResultKind.EMPTY_INPUT,
                raw_input=raw_input,
            )

        if not normalized.startswith("/"):
            return CommandParseResult(
                result_kind=CommandParseResultKind.INVALID_SYNTAX,
                raw_input=raw_input,
                error_message="Commands must start with /",
            )

        if self._parser:
            return self._parser(normalized)

        # Default parsing
        parts = normalized[1:].split(maxsplit=1)
        command_name = parts[0].lower() if parts else ""
        arguments: dict[str, Any] = {}

        if len(parts) > 1:
            arguments["raw_args"] = parts[1]

        if command_name not in self._commands and command_name not in self._aliases:
            return CommandParseResult(
                result_kind=CommandParseResultKind.UNKNOWN_COMMAND,
                command_name=command_name,
                raw_input=raw_input,
                error_message=f"Unknown command: {command_name}",
            )

        # Resolve alias
        resolved_name = self._aliases.get(command_name, command_name)

        return CommandParseResult(
            result_kind=CommandParseResultKind.VALID,
            command_name=resolved_name,
            arguments=arguments,
            raw_input=raw_input,
        )

    def execute_command(self, command_name: str, arguments: dict[str, Any]) -> CommandExecuteResult:
        """Execute a parsed command.

        Args:
            command_name: The command name
            arguments: The command arguments

        Returns:
            A CommandExecuteResult
        """
        normalized_name = _safe_text(command_name).lower()
        if not normalized_name:
            return CommandExecuteResult(
                result_kind=CommandExecuteResultKind.REJECTED,
                error_message="Command name is required",
            )

        if normalized_name not in self._commands:
            return CommandExecuteResult(
                result_kind=CommandExecuteResultKind.REJECTED,
                command_name=normalized_name,
                error_message=f"Unknown command: {normalized_name}",
            )

        if self._executor:
            return self._executor(normalized_name, arguments)

        # Default execution
        return CommandExecuteResult(
            result_kind=CommandExecuteResultKind.SUCCESS,
            command_name=normalized_name,
            output=f"Command {normalized_name} executed",
        )

    def get_command_help(self, command_name: str) -> CommandInfo | None:
        """Get help for a specific command.

        Args:
            command_name: The command name

        Returns:
            The CommandInfo, or None if not found
        """
        normalized = _safe_text(command_name).lower()
        resolved = self._aliases.get(normalized, normalized)
        return self._commands.get(resolved)

    def list_commands(self, category: str | None = None) -> list[CommandInfo]:
        """List all available commands.

        Args:
            category: Optional category filter

        Returns:
            A list of CommandInfo objects
        """
        commands = list(self._commands.values())
        if category:
            commands = [c for c in commands if c.category == category]
        return sorted(commands, key=lambda c: c.name)

    def register_command(self, info: CommandInfo) -> None:
        """Register a command.

        Args:
            info: The CommandInfo to register
        """
        normalized_name = _safe_text(info.name).lower()
        self._commands[normalized_name] = info
        for alias in info.aliases:
            normalized_alias = _safe_text(alias).lower()
            self._aliases[normalized_alias] = normalized_name

    def unregister_command(self, command_name: str) -> CommandInfo | None:
        """Unregister a command.

        Args:
            command_name: The command name

        Returns:
            The removed CommandInfo, or None if not found
        """
        normalized = _safe_text(command_name).lower()
        info = self._commands.pop(normalized, None)
        if info:
            # Remove aliases
            for alias in info.aliases:
                self._aliases.pop(_safe_text(alias).lower(), None)
        return info

    def set_parser(self, parser: Callable[[str], CommandParseResult]) -> None:
        """Set the custom command parser.

        Args:
            parser: A function that parses raw input
        """
        self._parser = parser

    def set_executor(self, executor: Callable[[str, dict[str, Any]], CommandExecuteResult]) -> None:
        """Set the custom command executor.

        Args:
            executor: A function that executes commands
        """
        self._executor = executor

    def clear(self) -> None:
        """Clear all registered commands."""
        self._commands.clear()
        self._aliases.clear()


__all__ = [
    "CommandExecuteResult",
    "CommandExecuteResultKind",
    "CommandInfo",
    "CommandParseResult",
    "CommandParseResultKind",
    "CommandUserService",
]
