from __future__ import annotations

from types import SimpleNamespace

import pytest

from mini_agent.llm import AnthropicClient, OpenAIClient, build_protocol_execution_profile
from mini_agent.schema import LLMCompletionResult, LLMProvider, LLMStreamEventType, Message


class _AsyncStream:
    def __init__(self, items: list[object]) -> None:
        self._items = list(items)
        self.closed = False

    def __aiter__(self) -> "_AsyncStream":
        return self

    async def __anext__(self) -> object:
        if not self._items:
            raise StopAsyncIteration
        return self._items.pop(0)

    async def close(self) -> None:
        self.closed = True


@pytest.mark.asyncio
async def test_openai_stream_generate_emits_normalized_events(monkeypatch: pytest.MonkeyPatch) -> None:
    profile = build_protocol_execution_profile(
        api_key="test-key",
        provider=LLMProvider.OPENAI,
        api_base="https://example.com/v1",
        model="gpt-test",
    )
    client = OpenAIClient(profile=profile)

    stream = _AsyncStream(
        [
            SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        delta=SimpleNamespace(content="Hel", tool_calls=None),
                        finish_reason=None,
                    )
                ],
                usage=None,
            ),
            SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        delta=SimpleNamespace(
                            content="lo",
                            tool_calls=[
                                SimpleNamespace(
                                    index=0,
                                    id="call_1",
                                    function=SimpleNamespace(name="read_file", arguments='{"path":"REA'),
                                )
                            ],
                        ),
                        finish_reason=None,
                    )
                ],
                usage=None,
            ),
            SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        delta=SimpleNamespace(
                            content=None,
                            tool_calls=[
                                SimpleNamespace(
                                    index=0,
                                    id=None,
                                    function=SimpleNamespace(name=None, arguments='DME.md"}'),
                                )
                            ],
                        ),
                        finish_reason="tool_calls",
                    )
                ],
                usage=SimpleNamespace(prompt_tokens=11, completion_tokens=7, total_tokens=18),
            ),
        ]
    )

    async def _fake_stream_request(api_messages, tools=None):  # noqa: ANN001,ARG001
        return stream

    monkeypatch.setattr(client, "_make_api_stream_request", _fake_stream_request)

    events = [event async for event in client.stream_generate(messages=[Message(role="user", content="hello")])]
    result = LLMCompletionResult.from_events(events, metadata=dict(events[0].metadata))

    assert [event.type for event in events] == [
        LLMStreamEventType.MESSAGE_START,
        LLMStreamEventType.TEXT_DELTA,
        LLMStreamEventType.TEXT_DELTA,
        LLMStreamEventType.USAGE,
        LLMStreamEventType.TOOL_CALL,
        LLMStreamEventType.MESSAGE_STOP,
    ]
    assert result.content == "Hello"
    assert result.tool_calls is not None
    assert result.tool_calls[0].function.name == "read_file"
    assert result.tool_calls[0].function.arguments == {"path": "README.md"}
    assert result.usage is not None
    assert result.usage.total_tokens == 18
    assert result.finish_reason == "tool_calls"
    assert result.metadata["protocol"] == "openai"
    assert stream.closed is True

    await client.close()


@pytest.mark.asyncio
async def test_anthropic_stream_generate_emits_normalized_events(monkeypatch: pytest.MonkeyPatch) -> None:
    profile = build_protocol_execution_profile(
        api_key="test-key",
        provider=LLMProvider.ANTHROPIC,
        api_base="https://example.com/anthropic",
        model="claude-test",
    )
    client = AnthropicClient(profile=profile)

    stream = _AsyncStream(
        [
            SimpleNamespace(
                type="message_start",
                message=SimpleNamespace(
                    stop_reason=None,
                    usage=SimpleNamespace(
                        input_tokens=8,
                        output_tokens=0,
                        cache_read_input_tokens=0,
                        cache_creation_input_tokens=0,
                    ),
                ),
            ),
            SimpleNamespace(
                type="content_block_delta",
                index=0,
                delta=SimpleNamespace(type="thinking_delta", thinking="plan "),
            ),
            SimpleNamespace(
                type="content_block_delta",
                index=0,
                delta=SimpleNamespace(type="text_delta", text="Hi "),
            ),
            SimpleNamespace(
                type="content_block_start",
                index=1,
                content_block=SimpleNamespace(type="tool_use", id="toolu_1", name="search_docs", input={}),
            ),
            SimpleNamespace(
                type="content_block_delta",
                index=1,
                delta=SimpleNamespace(type="input_json_delta", partial_json='{"query":"auth'),
            ),
            SimpleNamespace(
                type="content_block_delta",
                index=1,
                delta=SimpleNamespace(type="input_json_delta", partial_json=' flow"}'),
            ),
            SimpleNamespace(
                type="message_delta",
                delta=SimpleNamespace(stop_reason="tool_use"),
                usage=SimpleNamespace(
                    input_tokens=0,
                    output_tokens=5,
                    cache_read_input_tokens=0,
                    cache_creation_input_tokens=0,
                ),
            ),
            SimpleNamespace(type="message_stop"),
        ]
    )

    async def _fake_stream_request(system_message, api_messages, tools=None):  # noqa: ANN001,ARG001
        return stream

    monkeypatch.setattr(client, "_make_api_stream_request", _fake_stream_request)

    events = [event async for event in client.stream_generate(messages=[Message(role="user", content="hello")])]
    result = LLMCompletionResult.from_events(events, metadata=dict(events[0].metadata))

    assert [event.type for event in events] == [
        LLMStreamEventType.MESSAGE_START,
        LLMStreamEventType.USAGE,
        LLMStreamEventType.THINKING_DELTA,
        LLMStreamEventType.TEXT_DELTA,
        LLMStreamEventType.USAGE,
        LLMStreamEventType.TOOL_CALL,
        LLMStreamEventType.MESSAGE_STOP,
    ]
    assert result.thinking == "plan "
    assert result.content == "Hi "
    assert result.tool_calls is not None
    assert result.tool_calls[0].function.name == "search_docs"
    assert result.tool_calls[0].function.arguments == {"query": "auth flow"}
    assert result.usage is not None
    assert result.usage.prompt_tokens == 8
    assert result.usage.completion_tokens == 5
    assert result.usage.total_tokens == 13
    assert result.finish_reason == "tool_use"
    assert result.metadata["protocol"] == "anthropic"
    assert stream.closed is True

    await client.close()
