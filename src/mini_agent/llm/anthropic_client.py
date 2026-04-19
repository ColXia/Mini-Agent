"""Anthropic LLM client implementation."""

import json
import logging
from typing import Any, AsyncIterator

import anthropic

from mini_agent.model_manager.rectifier import rectify_anthropic_request

from ..retry import RetryConfig, async_retry
from ..schema.schema import (
    FunctionCall,
    LLMCompletionResult,
    LLMStreamEvent,
    LLMStreamEventType,
    Message,
    TokenUsage,
    ToolCall,
)
from .base import LLMClientBase, build_sdk_http_client
from .protocol_binding import ProtocolExecutionProfile

logger = logging.getLogger(__name__)


class AnthropicClient(LLMClientBase):
    """LLM client using Anthropic's protocol.

    This client uses the official Anthropic SDK and supports:
    - Extended thinking content
    - Tool calling
    - Retry logic
    """

    def __init__(
        self,
        *,
        profile: ProtocolExecutionProfile,
        retry_config: RetryConfig | None = None,
    ):
        """Initialize Anthropic client.

        Args:
            profile: Bound execution profile for one Anthropic-compatible route
            retry_config: Optional retry configuration
        """
        super().__init__(profile.api_key, profile.api_base, profile.model, retry_config)
        self._profile = profile
        self._sdk_http_client = build_sdk_http_client(
            profile.api_base,
            timeout_seconds=profile.client_timeout_seconds,
        )

        # Initialize Anthropic async client
        client_kwargs: dict[str, Any] = {
            "base_url": profile.api_base,
            "api_key": profile.api_key,
        }
        if profile.client_headers:
            client_kwargs["default_headers"] = profile.client_headers
        if profile.client_timeout_seconds is not None:
            client_kwargs["timeout"] = profile.client_timeout_seconds
        if self._sdk_http_client is not None:
            client_kwargs["http_client"] = self._sdk_http_client
        self.client = anthropic.AsyncAnthropic(**client_kwargs)

    async def _make_api_request(
        self,
        system_message: str | None,
        api_messages: list[dict[str, Any]],
        tools: list[Any] | None = None,
    ) -> anthropic.types.Message:
        """Execute API request (core method that can be retried).

        Args:
            system_message: Optional system message
            api_messages: List of messages in Anthropic format
            tools: Optional list of tools

        Returns:
            Anthropic Message response

        Raises:
            Exception: API call failed
        """
        params = self._build_request_params(
            system_message,
            api_messages,
            tools=tools,
            streaming=False,
        )

        # Use Anthropic SDK's async messages.create
        response = await self.client.messages.create(**params)
        return response

    async def _make_api_stream_request(
        self,
        system_message: str | None,
        api_messages: list[dict[str, Any]],
        tools: list[Any] | None = None,
    ) -> Any:
        """Execute native streaming request against the Anthropic-compatible API."""
        params = self._build_request_params(
            system_message,
            api_messages,
            tools=tools,
            streaming=True,
        )
        return await self.client.messages.create(**params)

    @staticmethod
    def _usage_from_anthropic(value: Any) -> TokenUsage | None:
        if value is None:
            return None
        input_tokens = getattr(value, "input_tokens", 0) or 0
        output_tokens = getattr(value, "output_tokens", 0) or 0
        cache_read_tokens = getattr(value, "cache_read_input_tokens", 0) or 0
        cache_creation_tokens = getattr(value, "cache_creation_input_tokens", 0) or 0
        total_input_tokens = input_tokens + cache_read_tokens + cache_creation_tokens
        total_tokens = total_input_tokens + output_tokens
        if total_tokens <= 0:
            return None
        return TokenUsage(
            prompt_tokens=total_input_tokens,
            completion_tokens=output_tokens,
            total_tokens=total_tokens,
        )

    @staticmethod
    def _parse_stream_tool_arguments(raw_arguments: str, fallback_input: Any) -> dict[str, Any]:
        cleaned = str(raw_arguments or "").strip()
        if cleaned:
            try:
                parsed = json.loads(cleaned)
            except json.JSONDecodeError:
                return {"_raw": cleaned}
            if isinstance(parsed, dict):
                return parsed
            return {"value": parsed}
        if isinstance(fallback_input, dict):
            return fallback_input
        return {}

    def _convert_tools(self, tools: list[Any]) -> list[dict[str, Any]]:
        """Convert tools to Anthropic format.

        Anthropic tool format:
        {
            "name": "tool_name",
            "description": "Tool description",
            "input_schema": {
                "type": "object",
                "properties": {...},
                "required": [...]
            }
        }

        Args:
            tools: List of Tool objects or dicts

        Returns:
            List of tools in Anthropic dict format
        """
        result = []
        for tool in tools:
            if isinstance(tool, dict):
                result.append(tool)
            elif hasattr(tool, "to_schema"):
                # Tool object with to_schema method
                result.append(tool.to_schema())
            else:
                raise TypeError(f"Unsupported tool type: {type(tool)}")
        return result

    def _convert_messages(self, messages: list[Message]) -> tuple[str | None, list[dict[str, Any]]]:
        """Convert internal messages to Anthropic format.

        Args:
            messages: List of internal Message objects

        Returns:
            Tuple of (system_message, api_messages)
        """
        system_message = None
        api_messages = []

        for msg in messages:
            if msg.role == "system":
                system_message = msg.content
                continue

            # For user and assistant messages
            if msg.role in ["user", "assistant"]:
                # Handle assistant messages with thinking or tool calls
                if msg.role == "assistant" and (msg.thinking or msg.tool_calls):
                    # Build content blocks for assistant with thinking and/or tool calls
                    content_blocks = []

                    # Add thinking block if present
                    if msg.thinking:
                        content_blocks.append({"type": "thinking", "thinking": msg.thinking})

                    # Add text content if present
                    if msg.content:
                        content_blocks.append({"type": "text", "text": msg.content})

                    # Add tool use blocks
                    if msg.tool_calls:
                        for tool_call in msg.tool_calls:
                            content_blocks.append(
                                {
                                    "type": "tool_use",
                                    "id": tool_call.id,
                                    "name": tool_call.function.name,
                                    "input": tool_call.function.arguments,
                                }
                            )

                    api_messages.append({"role": "assistant", "content": content_blocks})
                else:
                    api_messages.append({"role": msg.role, "content": msg.content})

            # For tool result messages
            elif msg.role == "tool":
                # Anthropic uses user role with tool_result content blocks
                api_messages.append(
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "tool_result",
                                "tool_use_id": msg.tool_call_id,
                                "content": msg.content,
                            }
                        ],
                    }
                )

        return system_message, api_messages

    def _prepare_request(
        self,
        messages: list[Message],
        tools: list[Any] | None = None,
    ) -> dict[str, Any]:
        """Prepare the request for Anthropic API.

        Args:
            messages: List of conversation messages
            tools: Optional list of available tools

        Returns:
            Dictionary containing request parameters
        """
        system_message, api_messages = self._convert_messages(messages)

        return {
            "system_message": system_message,
            "api_messages": api_messages,
            "tools": tools,
        }

    def _build_request_params(
        self,
        system_message: str | None,
        api_messages: list[dict[str, Any]],
        *,
        tools: list[Any] | None = None,
        streaming: bool,
    ) -> dict[str, Any]:
        params = {
            "model": self.model,
            "messages": api_messages,
        }
        params.update(
            self._profile.request_policy.anthropic_request_kwargs(
                tools_enabled=bool(tools),
                streaming=streaming,
            )
        )
        if system_message:
            params["system"] = system_message
        if tools:
            params["tools"] = self._convert_tools(tools)
        return rectify_anthropic_request(params, options=self._profile.rectifier_options)

    def _parse_response(self, response: anthropic.types.Message) -> LLMCompletionResult:
        """Parse Anthropic response into LLMCompletionResult.

        Args:
            response: Anthropic Message response

        Returns:
            LLMCompletionResult object
        """
        # Extract text content, thinking, and tool calls
        text_content = ""
        thinking_content = ""
        tool_calls = []

        for block in response.content:
            if block.type == "text":
                text_content += block.text
            elif block.type == "thinking":
                thinking_content += block.thinking
            elif block.type == "tool_use":
                # Parse Anthropic tool_use block
                tool_calls.append(
                    ToolCall(
                        id=block.id,
                        type="function",
                        function=FunctionCall(
                            name=block.name,
                            arguments=block.input,
                        ),
                    )
                )

        # Extract token usage from response
        # Anthropic usage includes: input_tokens, output_tokens, cache_read_input_tokens, cache_creation_input_tokens
        usage = None
        if hasattr(response, "usage") and response.usage:
            input_tokens = response.usage.input_tokens or 0
            output_tokens = response.usage.output_tokens or 0
            cache_read_tokens = getattr(response.usage, "cache_read_input_tokens", 0) or 0
            cache_creation_tokens = getattr(response.usage, "cache_creation_input_tokens", 0) or 0
            total_input_tokens = input_tokens + cache_read_tokens + cache_creation_tokens
            usage = TokenUsage(
                prompt_tokens=total_input_tokens,
                completion_tokens=output_tokens,
                total_tokens=total_input_tokens + output_tokens,
            )

        finish_reason = response.stop_reason or "stop"
        events: list[LLMStreamEvent] = [
            LLMStreamEvent(type=LLMStreamEventType.MESSAGE_START),
        ]
        if thinking_content:
            events.append(
                LLMStreamEvent(
                    type=LLMStreamEventType.THINKING_DELTA,
                    delta=thinking_content,
                )
            )
        if text_content:
            events.append(
                LLMStreamEvent(
                    type=LLMStreamEventType.TEXT_DELTA,
                    delta=text_content,
                )
            )
        for tool_call in tool_calls:
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
        events.append(
            LLMStreamEvent(
                type=LLMStreamEventType.MESSAGE_STOP,
                finish_reason=finish_reason,
            )
        )

        return LLMCompletionResult.from_events(
            events,
            metadata={"protocol": "anthropic"},
        )

    async def generate(
        self,
        messages: list[Message],
        tools: list[Any] | None = None,
    ) -> LLMCompletionResult:
        """Generate response from Anthropic LLM.

        Args:
            messages: List of conversation messages
            tools: Optional list of available tools

        Returns:
            LLMCompletionResult containing the generated content
        """
        # Prepare request
        request_params = self._prepare_request(messages, tools)

        # Make API request with retry logic
        if self.retry_config.enabled:
            # Apply retry logic
            retry_decorator = async_retry(config=self.retry_config, on_retry=self.retry_callback)
            api_call = retry_decorator(self._make_api_request)
            response = await api_call(
                request_params["system_message"],
                request_params["api_messages"],
                request_params["tools"],
            )
        else:
            # Don't use retry
            response = await self._make_api_request(
                request_params["system_message"],
                request_params["api_messages"],
                request_params["tools"],
            )

        # Parse and return response
        return self._parse_response(response)

    async def stream_generate(
        self,
        messages: list[Message],
        tools: list[Any] | None = None,
    ) -> AsyncIterator[LLMStreamEvent]:
        if not self._profile.request_policy.streaming_enabled:
            result = await self.generate(messages=messages, tools=tools)
            events = list(result.events)
            if events:
                events[0] = events[0].model_copy(
                    update={"metadata": {"protocol": "anthropic", "streaming_disabled": True}}
                )
            for event in events:
                yield event
            return

        request_params = self._prepare_request(messages, tools)

        if self.retry_config.enabled:
            retry_decorator = async_retry(config=self.retry_config, on_retry=self.retry_callback)
            api_call = retry_decorator(self._make_api_stream_request)
            stream = await api_call(
                request_params["system_message"],
                request_params["api_messages"],
                request_params["tools"],
            )
        else:
            stream = await self._make_api_stream_request(
                request_params["system_message"],
                request_params["api_messages"],
                request_params["tools"],
            )

        tool_use_blocks: dict[int, dict[str, Any]] = {}
        finish_reason = "stop"
        started = False

        try:
            async for event in stream:
                event_type = str(getattr(event, "type", "") or "").strip()
                if event_type == "message_start":
                    started = True
                    message = getattr(event, "message", None)
                    stop_reason = getattr(message, "stop_reason", None)
                    if isinstance(stop_reason, str) and stop_reason:
                        finish_reason = stop_reason
                    yield LLMStreamEvent(
                        type=LLMStreamEventType.MESSAGE_START,
                        metadata={"protocol": "anthropic"},
                    )
                    usage = self._usage_from_anthropic(getattr(message, "usage", None))
                    if usage is not None:
                        yield LLMStreamEvent(type=LLMStreamEventType.USAGE, usage=usage)
                    continue

                if not started:
                    started = True
                    yield LLMStreamEvent(
                        type=LLMStreamEventType.MESSAGE_START,
                        metadata={"protocol": "anthropic"},
                    )

                if event_type == "content_block_start":
                    block = getattr(event, "content_block", None)
                    block_type = str(getattr(block, "type", "") or "").strip()
                    if block_type == "text":
                        text = getattr(block, "text", None)
                        if isinstance(text, str) and text:
                            yield LLMStreamEvent(type=LLMStreamEventType.TEXT_DELTA, delta=text)
                    elif block_type == "thinking":
                        thinking = getattr(block, "thinking", None)
                        if isinstance(thinking, str) and thinking:
                            yield LLMStreamEvent(type=LLMStreamEventType.THINKING_DELTA, delta=thinking)
                    elif block_type in {"tool_use", "server_tool_use"}:
                        index = int(getattr(event, "index", 0) or 0)
                        tool_use_blocks[index] = {
                            "id": getattr(block, "id", None),
                            "name": getattr(block, "name", None),
                            "input": getattr(block, "input", None),
                            "input_parts": [],
                        }
                    continue

                if event_type == "content_block_delta":
                    delta = getattr(event, "delta", None)
                    delta_type = str(getattr(delta, "type", "") or "").strip()
                    if delta_type == "text_delta":
                        text = getattr(delta, "text", None)
                        if isinstance(text, str) and text:
                            yield LLMStreamEvent(type=LLMStreamEventType.TEXT_DELTA, delta=text)
                    elif delta_type == "thinking_delta":
                        thinking = getattr(delta, "thinking", None)
                        if isinstance(thinking, str) and thinking:
                            yield LLMStreamEvent(type=LLMStreamEventType.THINKING_DELTA, delta=thinking)
                    elif delta_type == "input_json_delta":
                        index = int(getattr(event, "index", 0) or 0)
                        tool_use = tool_use_blocks.setdefault(
                            index,
                            {"id": None, "name": None, "input": None, "input_parts": []},
                        )
                        partial_json = getattr(delta, "partial_json", None)
                        if isinstance(partial_json, str) and partial_json:
                            tool_use["input_parts"].append(partial_json)
                    continue

                if event_type == "message_delta":
                    delta = getattr(event, "delta", None)
                    stop_reason = getattr(delta, "stop_reason", None)
                    if isinstance(stop_reason, str) and stop_reason:
                        finish_reason = stop_reason
                    usage = self._usage_from_anthropic(getattr(event, "usage", None))
                    if usage is not None:
                        yield LLMStreamEvent(type=LLMStreamEventType.USAGE, usage=usage)
                    continue

                if event_type == "message_stop":
                    break
        finally:
            close_method = getattr(stream, "close", None)
            if callable(close_method):
                result = close_method()
                if hasattr(result, "__await__"):
                    await result

        if not started:
            yield LLMStreamEvent(
                type=LLMStreamEventType.MESSAGE_START,
                metadata={"protocol": "anthropic"},
            )

        for index in sorted(tool_use_blocks):
            block = tool_use_blocks[index]
            function_name = str(block.get("name") or "").strip()
            if not function_name:
                continue
            raw_arguments = "".join(block.get("input_parts", [])).strip()
            yield LLMStreamEvent(
                type=LLMStreamEventType.TOOL_CALL,
                tool_call=ToolCall(
                    id=str(block.get("id") or f"tool-use-{index}"),
                    type="function",
                    function=FunctionCall(
                        name=function_name,
                        arguments=self._parse_stream_tool_arguments(raw_arguments, block.get("input")),
                    ),
                ),
            )

        yield LLMStreamEvent(
            type=LLMStreamEventType.MESSAGE_STOP,
            finish_reason=finish_reason,
        )

    async def close(self) -> None:
        close_method = getattr(self.client, "close", None)
        if callable(close_method):
            result = close_method()
            if hasattr(result, "__await__"):
                await result
