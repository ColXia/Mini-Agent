"""Shared command parsing and lightweight dispatch helpers."""

from __future__ import annotations

import difflib
import inspect
import shlex
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from .catalog import command_entries_for_surface


def normalize_command_name(value: Any) -> str:
    return " ".join(str(value or "").split()).strip().lower().replace("-", "_")


class CommandParseError(ValueError):
    """Raised when a slash-command cannot be parsed."""


@dataclass(slots=True)
class CommandInvocation:
    """Normalized command invocation payload."""

    surface: str
    raw_text: str
    raw_name: str
    name: str
    args: list[str]
    tokens: list[str]
    alias_name: str | None = None

    @property
    def action(self) -> str:
        return normalize_command_name(self.args[0]) if self.args else ""

    def arg(self, index: int, default: str = "") -> str:
        try:
            return str(self.args[index])
        except Exception:
            return default

    def joined_args(self, start: int = 0) -> str:
        return " ".join(self.args[start:]).strip()


def parse_command_text(
    command_text: str,
    *,
    surface: str,
    aliases: dict[str, str] | None = None,
) -> CommandInvocation:
    raw_text = " ".join(str(command_text or "").split()).strip()
    if not raw_text:
        raise CommandParseError("empty command")
    try:
        tokens = shlex.split(raw_text)
    except ValueError as exc:  # pragma: no cover - behavior tested via callers
        raise CommandParseError(str(exc)) from exc
    if not tokens:
        raise CommandParseError("empty command")

    normalized_aliases = {
        normalize_command_name(key): normalize_command_name(value)
        for key, value in dict(aliases or {}).items()
        if normalize_command_name(key) and normalize_command_name(value)
    }

    raw_name = normalize_command_name(tokens[0])
    canonical_name = normalized_aliases.get(raw_name, raw_name)
    alias_name = raw_name if raw_name != canonical_name else None
    return CommandInvocation(
        surface=normalize_command_name(surface),
        raw_text=raw_text,
        raw_name=raw_name,
        name=canonical_name,
        args=list(tokens[1:]),
        tokens=list(tokens),
        alias_name=alias_name,
    )


CommandHandler = Callable[[CommandInvocation], Awaitable[Any] | Any]


class CommandDispatcher:
    """Small async-aware command dispatcher for one surface."""

    def __init__(
        self,
        *,
        surface: str,
        aliases: dict[str, str] | None = None,
    ) -> None:
        self.surface = normalize_command_name(surface)
        self.aliases: dict[str, str] = {
            normalize_command_name(key): normalize_command_name(value)
            for key, value in dict(aliases or {}).items()
            if normalize_command_name(key) and normalize_command_name(value)
        }
        self._handlers: dict[str, CommandHandler] = {}

    def register(
        self,
        name: str,
        handler: CommandHandler,
        *,
        aliases: tuple[str, ...] | list[str] = (),
    ) -> None:
        normalized_name = normalize_command_name(name)
        self._handlers[normalized_name] = handler
        for alias in aliases:
            normalized_alias = normalize_command_name(alias)
            if normalized_alias:
                self.aliases[normalized_alias] = normalized_name

    def known_commands(self) -> list[str]:
        return sorted(self._handlers)

    async def dispatch(self, invocation: CommandInvocation) -> bool:
        handler = self._handlers.get(invocation.name)
        if handler is None:
            return False
        result = handler(invocation)
        if inspect.isawaitable(result):
            await result
        return True


def suggest_command_name(
    value: str,
    *,
    surface: str,
    extra_candidates: list[str] | tuple[str, ...] | set[str] | None = None,
) -> str:
    candidates = {
        normalize_command_name(entry.get("name"))
        for entry in command_entries_for_surface(surface)
        if normalize_command_name(entry.get("name"))
    }
    for item in list(extra_candidates or []):
        normalized = normalize_command_name(item)
        if normalized:
            candidates.add(normalized)
    matches = difflib.get_close_matches(
        normalize_command_name(value),
        sorted(candidates),
        n=3,
        cutoff=0.45,
    )
    if not matches:
        return ""
    return f" Did you mean: {', '.join(matches)}?"


__all__ = [
    "CommandDispatcher",
    "CommandInvocation",
    "CommandParseError",
    "normalize_command_name",
    "parse_command_text",
    "suggest_command_name",
]
