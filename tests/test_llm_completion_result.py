from __future__ import annotations

from mini_agent.schema import (
    FunctionCall,
    LLMCompletionResult,
    LLMStreamEvent,
    LLMStreamEventType,
    TokenUsage,
    ToolCall,
)


def test_completion_result_synthesizes_events_from_buffered_fields() -> None:
    tool_call = ToolCall(
        id="call-1",
        type="function",
        function=FunctionCall(name="echo", arguments={"text": "hello"}),
    )
    result = LLMCompletionResult(
        content="hello world",
        thinking="planning",
        tool_calls=[tool_call],
        finish_reason="tool_calls",
        usage=TokenUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
    )

    assert [event.type for event in result.events] == [
        LLMStreamEventType.MESSAGE_START,
        LLMStreamEventType.THINKING_DELTA,
        LLMStreamEventType.TEXT_DELTA,
        LLMStreamEventType.TOOL_CALL,
        LLMStreamEventType.USAGE,
        LLMStreamEventType.MESSAGE_STOP,
    ]
    assert result.events[2].delta == "hello world"
    assert result.events[3].tool_call is not None
    assert result.events[5].finish_reason == "tool_calls"


def test_completion_result_aggregates_buffered_fields_from_events() -> None:
    tool_call = ToolCall(
        id="call-2",
        type="function",
        function=FunctionCall(name="search", arguments={"q": "Mini-Agent"}),
    )
    events = [
        LLMStreamEvent(type=LLMStreamEventType.MESSAGE_START),
        LLMStreamEvent(type=LLMStreamEventType.THINKING_DELTA, delta="think-1 "),
        LLMStreamEvent(type=LLMStreamEventType.THINKING_DELTA, delta="think-2"),
        LLMStreamEvent(type=LLMStreamEventType.TEXT_DELTA, delta="hello "),
        LLMStreamEvent(type=LLMStreamEventType.TEXT_DELTA, delta="world"),
        LLMStreamEvent(type=LLMStreamEventType.TOOL_CALL, tool_call=tool_call),
        LLMStreamEvent(
            type=LLMStreamEventType.USAGE,
            usage=TokenUsage(prompt_tokens=20, completion_tokens=7, total_tokens=27),
        ),
        LLMStreamEvent(type=LLMStreamEventType.MESSAGE_STOP, finish_reason="stop"),
    ]

    result = LLMCompletionResult.from_events(events)

    assert result.content == "hello world"
    assert result.thinking == "think-1 think-2"
    assert result.tool_calls == [tool_call]
    assert result.finish_reason == "stop"
    assert result.usage is not None
    assert result.usage.total_tokens == 27


def test_completion_result_merges_incremental_usage_events() -> None:
    result = LLMCompletionResult.from_events(
        [
            LLMStreamEvent(type=LLMStreamEventType.MESSAGE_START),
            LLMStreamEvent(
                type=LLMStreamEventType.USAGE,
                usage=TokenUsage(prompt_tokens=128, completion_tokens=0, total_tokens=128),
            ),
            LLMStreamEvent(
                type=LLMStreamEventType.USAGE,
                usage=TokenUsage(prompt_tokens=0, completion_tokens=32, total_tokens=32),
            ),
            LLMStreamEvent(type=LLMStreamEventType.MESSAGE_STOP, finish_reason="stop"),
        ]
    )

    assert result.usage is not None
    assert result.usage.prompt_tokens == 128
    assert result.usage.completion_tokens == 32
    assert result.usage.total_tokens == 160
