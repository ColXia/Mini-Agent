"""Thin protocol-dispatch facade for runtime LLM execution."""

from __future__ import annotations

import logging
from typing import AsyncIterator

from ..retry import RetryConfig
from ..schema import LLMCompletionResult, LLMProvider, LLMStreamEvent, Message
from .anthropic_client import AnthropicClient
from .base import LLMClientBase
from .openai_client import OpenAIClient
from .protocol_binding import ProtocolExecutionProfile

logger = logging.getLogger(__name__)


class LLMClient:
    """Thin facade that dispatches to the correct protocol client."""

    def __init__(
        self,
        *,
        profile: ProtocolExecutionProfile,
        retry_config: RetryConfig | None = None,
    ):
        self.profile = profile
        self.provider = profile.provider
        self.api_key = profile.api_key
        self.api_base = profile.api_base
        self.model = profile.model
        self.retry_config = retry_config or RetryConfig()

        self._client: LLMClientBase
        if profile.provider == LLMProvider.ANTHROPIC:
            self._client = AnthropicClient(
                profile=profile,
                retry_config=retry_config,
            )
        elif profile.provider == LLMProvider.OPENAI:
            self._client = OpenAIClient(
                profile=profile,
                retry_config=retry_config,
            )
        else:
            raise ValueError(f"Unsupported provider: {profile.provider}")

        logger.info(
            "Initialized LLM client with provider: %s, api_base: %s",
            profile.provider,
            profile.api_base,
        )

    @property
    def retry_callback(self):
        """Get retry callback."""
        return self._client.retry_callback

    @retry_callback.setter
    def retry_callback(self, value):
        """Set retry callback."""
        self._client.retry_callback = value

    async def generate(
        self,
        messages: list[Message],
        tools: list | None = None,
    ) -> LLMCompletionResult:
        """Generate response from LLM."""
        return await self._client.generate(messages, tools)

    async def stream_generate(
        self,
        messages: list[Message],
        tools: list | None = None,
    ) -> AsyncIterator[LLMStreamEvent]:
        """Stream normalized response events from LLM."""
        async for event in self._client.stream_generate(messages, tools):
            yield event

    async def close(self) -> None:
        close_method = getattr(self._client, "close", None)
        if callable(close_method):
            result = close_method()
            if hasattr(result, "__await__"):
                await result
