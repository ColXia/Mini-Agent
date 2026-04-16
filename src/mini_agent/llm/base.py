"""Base class for LLM clients."""

from abc import ABC, abstractmethod
from typing import Any, AsyncIterator
from urllib.parse import urlsplit

import httpx

from ..retry import RetryConfig
from ..schema import LLMCompletionResult, LLMStreamEvent, Message


def _should_bypass_proxy_env(api_base: str | None) -> bool:
    normalized = str(api_base or "").strip()
    if not normalized:
        return False
    try:
        parsed = urlsplit(normalized)
    except Exception:
        return False
    host = str(parsed.hostname or "").strip().lower()
    return host in {"localhost", "127.0.0.1", "::1"}


def build_sdk_http_client(
    api_base: str | None,
    *,
    timeout_seconds: float | None = None,
) -> httpx.AsyncClient | None:
    """Build a dedicated SDK transport for loopback endpoints.

    Developer machines may export global proxy env vars. For local compatible
    providers such as Ollama, trusting those env vars can incorrectly send
    `localhost` traffic through the proxy and break runtime calls.
    """

    if not _should_bypass_proxy_env(api_base):
        return None
    request_timeout = float(timeout_seconds) if timeout_seconds is not None else 600.0
    connect_timeout = min(request_timeout, 10.0)
    return httpx.AsyncClient(
        trust_env=False,
        timeout=httpx.Timeout(timeout=request_timeout, connect=connect_timeout),
    )


class LLMClientBase(ABC):
    """Abstract base class for LLM clients.

    This class defines the interface that all LLM clients must implement,
    regardless of the underlying API protocol (Anthropic, OpenAI, etc.).
    """

    def __init__(
        self,
        api_key: str,
        api_base: str,
        model: str,
        retry_config: RetryConfig | None = None,
    ):
        """Initialize the LLM client.

        Args:
            api_key: API key for authentication
            api_base: Base URL for the API
            model: Model name to use
            retry_config: Optional retry configuration
        """
        self.api_key = api_key
        self.api_base = api_base
        self.model = model
        self.retry_config = retry_config or RetryConfig()

        # Callback for tracking retry count
        self.retry_callback = None

    @abstractmethod
    async def generate(
        self,
        messages: list[Message],
        tools: list[Any] | None = None,
    ) -> LLMCompletionResult:
        """Generate response from LLM.

        Args:
            messages: List of conversation messages
            tools: Optional list of Tool objects or dicts

        Returns:
            LLMCompletionResult containing normalized buffered completion output
        """
        pass

    async def stream_generate(
        self,
        messages: list[Message],
        tools: list[Any] | None = None,
    ) -> AsyncIterator[LLMStreamEvent]:
        """Stream normalized events from the provider when supported.

        The default implementation falls back to buffered generation and
        replays the synthesized normalized event list. Protocol clients that
        support native streaming should override this method.
        """

        result = await self.generate(messages=messages, tools=tools)
        for event in result.events:
            yield event

    @abstractmethod
    def _prepare_request(
        self,
        messages: list[Message],
        tools: list[Any] | None = None,
    ) -> dict[str, Any]:
        """Prepare the request payload for the API.

        Args:
            messages: List of conversation messages
            tools: Optional list of available tools

        Returns:
            Dictionary containing the request payload
        """
        pass

    @abstractmethod
    def _convert_messages(self, messages: list[Message]) -> tuple[str | None, list[dict[str, Any]]]:
        """Convert internal message format to API-specific format.

        Args:
            messages: List of internal Message objects

        Returns:
            Tuple of (system_message, api_messages)
        """
        pass

    async def close(self) -> None:
        """Release client resources when supported by the provider SDK."""
        return None
