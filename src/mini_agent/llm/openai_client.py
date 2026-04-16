"""OpenAI LLM client implementation."""

import json
import logging
from typing import Any, AsyncIterator

from openai import AsyncOpenAI

from mini_agent.model_manager.rectifier import rectify_openai_request

from ..retry import RetryConfig, async_retry
from ..schema import (
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


class OpenAIClient(LLMClientBase):
    """LLM client using OpenAI's protocol.

    This client uses the official OpenAI SDK and supports:
    - Reasoning content (via reasoning_split=True)
    - Tool calling
    - Retry logic
    """

    def __init__(
        self,
        *,
        profile: ProtocolExecutionProfile,
        retry_config: RetryConfig | None = None,
    ):
        """Initialize OpenAI client.

        Args:
            profile: Bound execution profile for one OpenAI-compatible route
            retry_config: Optional retry configuration
        """
        super().__init__(profile.api_key, profile.api_base, profile.model, retry_config)
        self._profile = profile
        self._sdk_http_client = build_sdk_http_client(
            profile.api_base,
            timeout_seconds=profile.client_timeout_seconds,
        )

        # Initialize OpenAI client
        client_kwargs: dict[str, Any] = {
            "api_key": profile.api_key,
            "base_url": profile.api_base,
            "default_headers": profile.client_headers or None,
        }
        if profile.client_timeout_seconds is not None:
            client_kwargs["timeout"] = profile.client_timeout_seconds
        if self._sdk_http_client is not None:
            client_kwargs["http_client"] = self._sdk_http_client
        self.client = AsyncOpenAI(
            **client_kwargs,
        )

    async def _make_api_request(
        self,
        api_messages: list[dict[str, Any]],
        tools: list[Any] | None = None,
    ) -> Any:
        """Execute API request (core method that can be retried).

        Args:
            api_messages: List of messages in OpenAI format
            tools: Optional list of tools

        Returns:
            OpenAI ChatCompletion response (full response including usage)

        Raises:
            Exception: API call failed
        """
        params = self._build_request_params(
            api_messages,
            tools=tools,
            streaming=False,
        )

        # Use OpenAI SDK's chat.completions.create
        response = await self.client.chat.completions.create(**params)
        # Return full response to access usage info
        return response

    async def _make_api_stream_request(
        self,
        api_messages: list[dict[str, Any]],
        tools: list[Any] | None = None,
    ) -> Any:
        """Execute native streaming request against the OpenAI-compatible API."""
        params = self._build_request_params(
            api_messages,
            tools=tools,
            streaming=True,
        )
        return await self.client.chat.completions.create(**params)

    @staticmethod
    def _extract_text_delta(delta: Any) -> str:
        raw = getattr(delta, "content", None)
        if isinstance(raw, str):
            return raw
        if isinstance(raw, list):
            parts: list[str] = []
            for item in raw:
                if isinstance(item, str):
                    parts.append(item)
                    continue
                if isinstance(item, dict):
                    text = item.get("text") or item.get("content")
                    if isinstance(text, str):
                        parts.append(text)
                    continue
                text = getattr(item, "text", None) or getattr(item, "content", None)
                if isinstance(text, str):
                    parts.append(text)
            return "".join(parts)
        return ""

    @staticmethod
    def _extract_reasoning_delta(delta: Any) -> str:
        parts: list[str] = []

        raw_reasoning = getattr(delta, "reasoning_content", None)
        if isinstance(raw_reasoning, str) and raw_reasoning:
            parts.append(raw_reasoning)

        raw_reasoning = getattr(delta, "reasoning", None)
        if isinstance(raw_reasoning, str) and raw_reasoning:
            parts.append(raw_reasoning)

        details = getattr(delta, "reasoning_details", None)
        if isinstance(details, list):
            for item in details:
                if isinstance(item, dict):
                    text = item.get("text")
                    if isinstance(text, str) and text:
                        parts.append(text)
                    continue
                text = getattr(item, "text", None)
                if isinstance(text, str) and text:
                    parts.append(text)

        return "".join(parts)

    @staticmethod
    def _parse_stream_tool_arguments(raw_arguments: str) -> dict[str, Any]:
        cleaned = str(raw_arguments or "").strip()
        if not cleaned:
            return {}
        try:
            parsed = json.loads(cleaned)
        except json.JSONDecodeError:
            return {"_raw": cleaned}
        if isinstance(parsed, dict):
            return parsed
        return {"value": parsed}

    def _convert_tools(self, tools: list[Any]) -> list[dict[str, Any]]:
        """Convert tools to OpenAI format.

        Args:
            tools: List of Tool objects or dicts

        Returns:
            List of tools in OpenAI dict format
        """
        result = []
        for tool in tools:
            if isinstance(tool, dict):
                # If already a dict, check if it's in OpenAI format
                if "type" in tool and tool["type"] == "function":
                    result.append(tool)
                else:
                    # Assume it's in Anthropic format, convert to OpenAI
                    result.append(
                        {
                            "type": "function",
                            "function": {
                                "name": tool["name"],
                                "description": tool["description"],
                                "parameters": tool["input_schema"],
                            },
                        }
                    )
            elif hasattr(tool, "to_openai_schema"):
                # Tool object with to_openai_schema method
                result.append(tool.to_openai_schema())
            else:
                raise TypeError(f"Unsupported tool type: {type(tool)}")
        return result

    def _convert_messages(self, messages: list[Message]) -> tuple[str | None, list[dict[str, Any]]]:
        """Convert internal messages to OpenAI format.

        Args:
            messages: List of internal Message objects

        Returns:
            Tuple of (system_message, api_messages)
            Note: OpenAI includes system message in the messages array
        """
        api_messages = []

        for msg in messages:
            if msg.role == "system":
                # OpenAI includes system message in messages array
                api_messages.append({"role": "system", "content": msg.content})
                continue

            # For user messages
            if msg.role == "user":
                api_messages.append({"role": "user", "content": msg.content})

            # For assistant messages
            elif msg.role == "assistant":
                assistant_msg = {"role": "assistant"}

                # Add content if present
                if msg.content:
                    assistant_msg["content"] = msg.content

                # Add tool calls if present
                if msg.tool_calls:
                    tool_calls_list = []
                    for tool_call in msg.tool_calls:
                        tool_calls_list.append(
                            {
                                "id": tool_call.id,
                                "type": "function",
                                "function": {
                                    "name": tool_call.function.name,
                                    "arguments": json.dumps(tool_call.function.arguments),
                                },
                            }
                        )
                    assistant_msg["tool_calls"] = tool_calls_list

                # IMPORTANT: Add reasoning_details if thinking is present
                # This is CRITICAL for Interleaved Thinking to work properly!
                # The complete response_message (including reasoning_details) must be
                # preserved in Message History and passed back to the model in the next turn.
                # This ensures the model's chain of thought is not interrupted.
                if msg.thinking:
                    assistant_msg["reasoning_details"] = [{"text": msg.thinking}]

                api_messages.append(assistant_msg)

            # For tool result messages
            elif msg.role == "tool":
                api_messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": msg.tool_call_id,
                        "content": msg.content,
                    }
                )

        return None, api_messages

    def _prepare_request(
        self,
        messages: list[Message],
        tools: list[Any] | None = None,
    ) -> dict[str, Any]:
        """Prepare the request for OpenAI API.

        Args:
            messages: List of conversation messages
            tools: Optional list of available tools

        Returns:
            Dictionary containing request parameters
        """
        _, api_messages = self._convert_messages(messages)

        return {
            "api_messages": api_messages,
            "tools": tools,
        }

    def _build_request_params(
        self,
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
            self._profile.request_policy.openai_request_kwargs(
                tools_enabled=bool(tools),
                streaming=streaming,
            )
        )
        if tools:
            params["tools"] = self._convert_tools(tools)
        return rectify_openai_request(params, options=self._profile.rectifier_options)

    def _parse_response(self, response: Any) -> LLMCompletionResult:
        """Parse OpenAI response into LLMCompletionResult.

        Args:
            response: OpenAI ChatCompletion response (full response object)

        Returns:
            LLMCompletionResult object
        """
        # Get message from response
        choice = response.choices[0]
        message = choice.message

        # Extract text content
        text_content = message.content or ""

        # Extract thinking content from reasoning_details
        thinking_content = ""
        if hasattr(message, "reasoning_details") and message.reasoning_details:
            # reasoning_details is a list of reasoning blocks
            for detail in message.reasoning_details:
                if hasattr(detail, "text"):
                    thinking_content += detail.text

        # Extract tool calls
        tool_calls = []
        if message.tool_calls:
            for tool_call in message.tool_calls:
                # Parse arguments from JSON string
                arguments = json.loads(tool_call.function.arguments)

                tool_calls.append(
                    ToolCall(
                        id=tool_call.id,
                        type="function",
                        function=FunctionCall(
                            name=tool_call.function.name,
                            arguments=arguments,
                        ),
                    )
                )

        # Extract token usage from response
        usage = None
        if hasattr(response, "usage") and response.usage:
            usage = TokenUsage(
                prompt_tokens=response.usage.prompt_tokens or 0,
                completion_tokens=response.usage.completion_tokens or 0,
                total_tokens=response.usage.total_tokens or 0,
            )

        finish_reason = getattr(choice, "finish_reason", None) or "stop"
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
            metadata={"protocol": "openai"},
        )

    async def generate(
        self,
        messages: list[Message],
        tools: list[Any] | None = None,
    ) -> LLMCompletionResult:
        """Generate response from OpenAI LLM.

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
                request_params["api_messages"],
                request_params["tools"],
            )
        else:
            # Don't use retry
            response = await self._make_api_request(
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
                    update={"metadata": {"protocol": "openai", "streaming_disabled": True}}
                )
            for event in events:
                yield event
            return

        request_params = self._prepare_request(messages, tools)

        if self.retry_config.enabled:
            retry_decorator = async_retry(config=self.retry_config, on_retry=self.retry_callback)
            api_call = retry_decorator(self._make_api_stream_request)
            stream = await api_call(
                request_params["api_messages"],
                request_params["tools"],
            )
        else:
            stream = await self._make_api_stream_request(
                request_params["api_messages"],
                request_params["tools"],
            )

        tool_call_fragments: dict[int, dict[str, Any]] = {}
        finish_reason = "stop"
        yield LLMStreamEvent(
            type=LLMStreamEventType.MESSAGE_START,
            metadata={"protocol": "openai"},
        )

        try:
            async for chunk in stream:
                usage = getattr(chunk, "usage", None)
                if usage is not None:
                    yield LLMStreamEvent(
                        type=LLMStreamEventType.USAGE,
                        usage=TokenUsage(
                            prompt_tokens=getattr(usage, "prompt_tokens", 0) or 0,
                            completion_tokens=getattr(usage, "completion_tokens", 0) or 0,
                            total_tokens=getattr(usage, "total_tokens", 0) or 0,
                        ),
                    )

                for choice in list(getattr(chunk, "choices", None) or []):
                    delta = getattr(choice, "delta", None)
                    if delta is not None:
                        thinking_delta = self._extract_reasoning_delta(delta)
                        if thinking_delta:
                            yield LLMStreamEvent(
                                type=LLMStreamEventType.THINKING_DELTA,
                                delta=thinking_delta,
                            )

                        text_delta = self._extract_text_delta(delta)
                        if text_delta:
                            yield LLMStreamEvent(
                                type=LLMStreamEventType.TEXT_DELTA,
                                delta=text_delta,
                            )

                        for tool_call_delta in list(getattr(delta, "tool_calls", None) or []):
                            index = int(getattr(tool_call_delta, "index", 0) or 0)
                            target = tool_call_fragments.setdefault(
                                index,
                                {
                                    "id": None,
                                    "name": None,
                                    "arguments_parts": [],
                                },
                            )
                            tool_call_id = getattr(tool_call_delta, "id", None)
                            if isinstance(tool_call_id, str) and tool_call_id:
                                target["id"] = tool_call_id
                            function = getattr(tool_call_delta, "function", None)
                            function_name = getattr(function, "name", None)
                            if isinstance(function_name, str) and function_name:
                                target["name"] = function_name
                            arguments_part = getattr(function, "arguments", None)
                            if isinstance(arguments_part, str) and arguments_part:
                                target["arguments_parts"].append(arguments_part)

                    choice_finish_reason = getattr(choice, "finish_reason", None)
                    if isinstance(choice_finish_reason, str) and choice_finish_reason:
                        finish_reason = choice_finish_reason
        finally:
            close_method = getattr(stream, "close", None)
            if callable(close_method):
                result = close_method()
                if hasattr(result, "__await__"):
                    await result

        for index in sorted(tool_call_fragments):
            fragment = tool_call_fragments[index]
            function_name = str(fragment.get("name") or "").strip()
            if not function_name:
                continue
            raw_arguments = "".join(fragment.get("arguments_parts", [])).strip()
            yield LLMStreamEvent(
                type=LLMStreamEventType.TOOL_CALL,
                tool_call=ToolCall(
                    id=str(fragment.get("id") or f"tool-call-{index}"),
                    type="function",
                    function=FunctionCall(
                        name=function_name,
                        arguments=self._parse_stream_tool_arguments(raw_arguments),
                    ),
                ),
            )

        yield LLMStreamEvent(
            type=LLMStreamEventType.MESSAGE_STOP,
            finish_reason=finish_reason,
        )

    async def close(self) -> None:
        await self.client.close()
