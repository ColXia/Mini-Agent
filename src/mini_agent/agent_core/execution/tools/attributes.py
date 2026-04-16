"""Declarative tool attributes for agent-core execution tool contracts."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Mapping


class ToolKind(str, Enum):
    """High-level tool intent classification."""

    READ = "read"
    WRITE = "write"
    EDIT = "edit"
    DELETE = "delete"
    EXECUTE = "execute"
    SEARCH = "search"
    NETWORK = "network"
    DELEGATE = "delegate"
    OTHER = "other"


class InterruptBehavior(str, Enum):
    """How a tool invocation interacts with turn interruption."""

    WAIT = "wait"
    CANCEL_RUNNING = "cancel_running"
    SAFE_INTERRUPT = "safe_interrupt"


LocationExtractor = Callable[[Mapping[str, Any]], list[str]]
RenderToolUseMessage = Callable[[str, Mapping[str, Any]], str]


def _render_value_preview(value: Any) -> str:
    text = str(value)
    if len(text) > 48:
        return f"{text[:45]}..."
    return text


def _default_render_tool_use_message(tool_name: str, arguments: Mapping[str, Any]) -> str:
    if not arguments:
        return tool_name
    parts: list[str] = []
    for key, value in arguments.items():
        if value in (None, "", [], {}, ()):
            continue
        parts.append(f"{key}={_render_value_preview(value)}")
        if len(parts) >= 2:
            break
    if not parts:
        return tool_name
    suffix = ", ..." if len(arguments) > len(parts) else ""
    return f"{tool_name}({', '.join(parts)}{suffix})"


@dataclass(frozen=True)
class DeclarativeToolAttributes:
    """Extended metadata for declarative tool contracts."""

    kind: ToolKind = ToolKind.OTHER
    is_read_only: bool = False
    concurrency_safe: bool = False
    destructive: bool = False
    interrupt_behavior: InterruptBehavior = InterruptBehavior.WAIT
    max_result_size_chars: int | None = None
    should_defer: bool = False
    always_load: bool = False
    location_extractor: LocationExtractor | None = None
    render_message: RenderToolUseMessage | None = None

    def normalized(self) -> "DeclarativeToolAttributes":
        max_size = self.max_result_size_chars
        if max_size is not None and max_size <= 0:
            max_size = None
        is_read_only = bool(self.is_read_only)
        destructive = bool(self.destructive and not is_read_only)
        return DeclarativeToolAttributes(
            kind=self.kind,
            is_read_only=is_read_only,
            concurrency_safe=bool(self.concurrency_safe),
            destructive=destructive,
            interrupt_behavior=self.interrupt_behavior,
            max_result_size_chars=max_size,
            should_defer=bool(self.should_defer),
            always_load=bool(self.always_load),
            location_extractor=self.location_extractor,
            render_message=self.render_message,
        )

    def is_concurrency_safe(self) -> bool:
        return self.normalized().concurrency_safe

    def is_destructive(self) -> bool:
        return self.normalized().destructive

    def render_tool_use_message(self, tool_name: str, arguments: Mapping[str, Any]) -> str:
        normalized = self.normalized()
        renderer = normalized.render_message or _default_render_tool_use_message
        return renderer(tool_name, arguments)
