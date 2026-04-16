from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, model_validator


class LLMProvider(str, Enum):
    """LLM provider types."""

    ANTHROPIC = "anthropic"
    OPENAI = "openai"


class FunctionCall(BaseModel):
    """Function call details."""

    name: str
    arguments: dict[str, Any]  # Function arguments as dict


class ToolCall(BaseModel):
    """Tool call structure."""

    id: str
    type: str  # "function"
    function: FunctionCall


class Message(BaseModel):
    """Chat message."""

    role: str  # "system", "user", "assistant", "tool"
    content: str | list[dict[str, Any]]  # Can be string or list of content blocks
    thinking: str | None = None  # Extended thinking content for assistant messages
    tool_calls: list[ToolCall] | None = None
    tool_call_id: str | None = None
    name: str | None = None  # For tool role


class TokenUsage(BaseModel):
    """Token usage statistics from LLM API response."""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class LLMStreamEventType(str, Enum):
    """Normalized event families for buffered and streamed LLM output."""

    MESSAGE_START = "message_start"
    THINKING_DELTA = "thinking_delta"
    TEXT_DELTA = "text_delta"
    TOOL_CALL = "tool_call"
    USAGE = "usage"
    MESSAGE_STOP = "message_stop"
    ERROR = "error"


class LLMStreamEvent(BaseModel):
    """One normalized LLM output event."""

    type: LLMStreamEventType
    delta: str | None = None
    tool_call: ToolCall | None = None
    usage: TokenUsage | None = None
    finish_reason: str | None = None
    error: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


def _normalize_text(value: str | None) -> str | None:
    if value is None:
        return None
    return value if value else None


def _merge_usage(current: TokenUsage | None, update: TokenUsage) -> TokenUsage:
    if current is None:
        return update
    prompt_tokens = max(int(current.prompt_tokens or 0), int(update.prompt_tokens or 0))
    completion_tokens = max(int(current.completion_tokens or 0), int(update.completion_tokens or 0))
    total_tokens = max(
        int(current.total_tokens or 0),
        int(update.total_tokens or 0),
        prompt_tokens + completion_tokens,
    )
    return TokenUsage(
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
    )


def aggregate_completion_events(events: list[LLMStreamEvent]) -> dict[str, Any]:
    """Aggregate normalized output events into one buffered completion shape."""

    content_parts: list[str] = []
    thinking_parts: list[str] = []
    tool_calls: list[ToolCall] = []
    usage: TokenUsage | None = None
    finish_reason = "stop"
    error: str | None = None

    for event in events:
        if event.type == LLMStreamEventType.TEXT_DELTA and event.delta:
            content_parts.append(event.delta)
        elif event.type == LLMStreamEventType.THINKING_DELTA and event.delta:
            thinking_parts.append(event.delta)
        elif event.type == LLMStreamEventType.TOOL_CALL and event.tool_call is not None:
            tool_calls.append(event.tool_call)
        elif event.type == LLMStreamEventType.USAGE and event.usage is not None:
            usage = _merge_usage(usage, event.usage)
        elif event.type == LLMStreamEventType.MESSAGE_STOP and event.finish_reason:
            finish_reason = event.finish_reason
        elif event.type == LLMStreamEventType.ERROR and event.error:
            error = event.error
            if not event.finish_reason:
                finish_reason = "error"

    return {
        "content": "".join(content_parts),
        "thinking": _normalize_text("".join(thinking_parts)),
        "tool_calls": tool_calls or None,
        "finish_reason": finish_reason,
        "usage": usage,
        "error": _normalize_text(error),
    }


def synthesize_completion_events(
    *,
    content: str,
    thinking: str | None,
    tool_calls: list[ToolCall] | None,
    finish_reason: str,
    usage: TokenUsage | None,
    error: str | None = None,
) -> list[LLMStreamEvent]:
    """Build a normalized event list for one buffered completion."""

    events: list[LLMStreamEvent] = [
        LLMStreamEvent(type=LLMStreamEventType.MESSAGE_START),
    ]
    if thinking:
        events.append(
            LLMStreamEvent(
                type=LLMStreamEventType.THINKING_DELTA,
                delta=thinking,
            )
        )
    if content:
        events.append(
            LLMStreamEvent(
                type=LLMStreamEventType.TEXT_DELTA,
                delta=content,
            )
        )
    for tool_call in tool_calls or []:
        events.append(
            LLMStreamEvent(
                type=LLMStreamEventType.TOOL_CALL,
                tool_call=tool_call,
            )
        )
    if usage is not None:
        events.append(
            LLMStreamEvent(
                type=LLMStreamEventType.USAGE,
                usage=usage,
            )
        )
    if error:
        events.append(
            LLMStreamEvent(
                type=LLMStreamEventType.ERROR,
                error=error,
                finish_reason="error",
            )
        )
    events.append(
        LLMStreamEvent(
            type=LLMStreamEventType.MESSAGE_STOP,
            finish_reason=finish_reason,
        )
    )
    return events


class LLMCompletionResult(BaseModel):
    """Normalized buffered completion built from the same event model as streaming."""

    content: str = ""
    thinking: str | None = None
    tool_calls: list[ToolCall] | None = None
    finish_reason: str = "stop"
    usage: TokenUsage | None = None
    error: str | None = None
    events: list[LLMStreamEvent] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def from_events(
        cls,
        events: list[LLMStreamEvent],
        *,
        metadata: dict[str, Any] | None = None,
    ) -> "LLMCompletionResult":
        aggregated = aggregate_completion_events(events)
        return cls(
            content=aggregated["content"],
            thinking=aggregated["thinking"],
            tool_calls=aggregated["tool_calls"],
            finish_reason=aggregated["finish_reason"],
            usage=aggregated["usage"],
            error=aggregated["error"],
            events=list(events),
            metadata=dict(metadata or {}),
        )

    @model_validator(mode="after")
    def _normalize_events(self) -> "LLMCompletionResult":
        if self.events:
            aggregated = aggregate_completion_events(self.events)
            self.content = aggregated["content"]
            self.thinking = aggregated["thinking"]
            self.tool_calls = aggregated["tool_calls"]
            self.finish_reason = aggregated["finish_reason"]
            self.usage = aggregated["usage"]
            self.error = aggregated["error"]
            return self

        self.thinking = _normalize_text(self.thinking)
        self.error = _normalize_text(self.error)
        if self.tool_calls == []:
            self.tool_calls = None
        self.events = synthesize_completion_events(
            content=self.content,
            thinking=self.thinking,
            tool_calls=self.tool_calls,
            finish_reason=self.finish_reason,
            usage=self.usage,
            error=self.error,
        )
        return self


class LLMResponse(LLMCompletionResult):
    """Backward-compatible buffered response surface for legacy callers."""
