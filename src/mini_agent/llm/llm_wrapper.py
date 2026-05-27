"""Thin protocol-dispatch facade for runtime LLM execution."""

from __future__ import annotations

import importlib
import logging
from typing import AsyncIterator

from ..retry import RetryConfig
from ..schema.schema import LLMCompletionResult, LLMProvider, LLMStreamEvent, Message
from .base import LLMClientBase
from .protocol_binding import ProtocolExecutionProfile

logger = logging.getLogger(__name__)

_CLIENT_MODULES: dict[LLMProvider, str] = {
    LLMProvider.ANTHROPIC: ".anthropic_client",
    LLMProvider.OPENAI: ".openai_client",
}

_CLIENT_CLASSES: dict[LLMProvider, str] = {
    LLMProvider.ANTHROPIC: "AnthropicClient",
    LLMProvider.OPENAI: "OpenAIClient",
}


def _import_client_class(provider: LLMProvider) -> type[LLMClientBase]:
    module_name = _CLIENT_MODULES.get(provider)
    class_name = _CLIENT_CLASSES.get(provider)
    if not module_name or not class_name:
        raise ValueError(f"Unsupported provider: {provider}")
    try:
        mod = importlib.import_module(module_name, package=__package__)
    except ModuleNotFoundError as exc:
        raise ModuleNotFoundError(
            f"Provider SDK for '{provider.value}' is not installed. "
            f"Install it with: uv pip install {provider.value.lower()}"
        ) from exc
    return getattr(mod, class_name)


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

        client_cls = _import_client_class(profile.provider)
        self._client: LLMClientBase = client_cls(
            profile=profile,
            retry_config=retry_config,
        )

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
