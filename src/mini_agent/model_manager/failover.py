"""Provider failover execution for runtime LLM requests."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, AsyncIterator, TYPE_CHECKING

from mini_agent.model_manager.error_classifier import classify_provider_error
from mini_agent.model_manager.runtime import (
    RoutedLLMSettings,
    get_health_monitor,
    record_provider_failure,
    record_provider_success,
)
from mini_agent.model_manager.rectifier import RequestRectifierOptions
from mini_agent.retry import RetryConfig
from mini_agent.schema import LLMCompletionResult, LLMStreamEvent, LLMStreamEventType, Message
from mini_agent.llm.protocol_binding import ProtocolRequestPolicy

if TYPE_CHECKING:
    from mini_agent.llm import LLMClient

# Optional override hook (used in tests); lazily resolved in runtime.
LLMClient = None


@dataclass(frozen=True)
class FailoverAttempt:
    """One failed provider attempt inside one request."""

    provider_id: str | None
    provider_name: str | None
    category: str
    reason: str
    error_type: str
    message: str


class ProviderFailoverError(RuntimeError):
    """Raised when all failover candidates are exhausted."""

    def __init__(self, attempts: list[FailoverAttempt]):
        self.attempts = list(attempts)
        if self.attempts:
            summary = "; ".join(
                f"{item.provider_id or 'config-default'}:{item.reason}" for item in self.attempts
            )
            message = f"All provider routes failed ({summary})"
        else:
            message = "All provider routes failed."
        super().__init__(message)


class FailoverLLMClient:
    """LLM client wrapper with provider-level failover."""

    def __init__(
        self,
        routes: list[RoutedLLMSettings],
        *,
        retry_config: RetryConfig | None = None,
        request_policy: ProtocolRequestPolicy | None = None,
        rectifier_options: RequestRectifierOptions | None = None,
    ):
        if not routes:
            raise ValueError("FailoverLLMClient requires at least one route.")

        deduped: list[RoutedLLMSettings] = []
        seen_keys: set[tuple[str | None, str, str, str]] = set()
        for route in routes:
            key = (route.provider_id, route.api_base, route.model, route.api_key)
            if key in seen_keys:
                continue
            seen_keys.add(key)
            deduped.append(route)

        self._routes = deduped
        self._retry_config = retry_config
        self._request_policy = request_policy
        self._rectifier_options = rectifier_options
        self._retry_callback = None
        self._clients: dict[tuple[str | None, str, str, str], "LLMClient"] = {}
        self._active_index = 0
        self._lock = asyncio.Lock()

        # Compatibility fields used by existing diagnostics/logging paths.
        primary = self._routes[0]
        self.provider = primary.provider
        self.api_base = primary.api_base
        self.model = primary.model

    @property
    def retry_callback(self):
        return self._retry_callback

    @retry_callback.setter
    def retry_callback(self, callback):
        self._retry_callback = callback
        for client in self._clients.values():
            client.retry_callback = callback

    def routes_snapshot(self) -> list[RoutedLLMSettings]:
        return list(self._routes)

    def _route_key(self, route: RoutedLLMSettings) -> tuple[str | None, str, str, str]:
        return (route.provider_id, route.api_base, route.model, route.api_key)

    def _client_for(self, route: RoutedLLMSettings) -> "LLMClient":
        key = self._route_key(route)
        existing = self._clients.get(key)
        if existing is not None:
            return existing

        client_cls = LLMClient
        binding_factory = None
        if client_cls is None:
            from mini_agent.llm import (
                LLMClient as runtime_llm_client,
                build_protocol_execution_profile,
            )

            client_cls = runtime_llm_client
            binding_factory = build_protocol_execution_profile
        else:
            from mini_agent.llm import build_protocol_execution_profile

            binding_factory = build_protocol_execution_profile

        profile = binding_factory(
            api_key=route.api_key,
            provider=route.provider,
            api_base=route.api_base,
            model=route.model,
            client_headers=dict(route.headers or {}),
            request_timeout_seconds=route.timeout,
            request_policy=self._request_policy,
            rectifier_options=self._rectifier_options,
        )
        created = client_cls(
            profile=profile,
            retry_config=self._retry_config,
        )
        if self._retry_callback is not None:
            created.retry_callback = self._retry_callback
        self._clients[key] = created
        return created

    def _attempt_order(self) -> list[int]:
        if not self._routes:
            return []
        start = max(0, min(self._active_index, len(self._routes) - 1))
        return list(range(start, len(self._routes))) + list(range(0, start))

    async def generate(
        self,
        messages: list[Message],
        tools: list[Any] | None = None,
    ) -> LLMCompletionResult:
        async with self._lock:
            health_monitor = get_health_monitor()
            attempts: list[FailoverAttempt] = []
            last_exception: Exception | None = None

            for route_index in self._attempt_order():
                route = self._routes[route_index]
                if route.provider_id:
                    health_monitor.record_route(
                        route.provider_id,
                        mapping_mode=route.mapping_mode,
                    )

                client = self._client_for(route)
                try:
                    response = await client.generate(messages=messages, tools=tools)
                except Exception as exc:
                    last_exception = exc
                    classification = classify_provider_error(exc)
                    if route.provider_id:
                        record_provider_failure(route.provider_id, reason=classification.reason)

                    attempts.append(
                        FailoverAttempt(
                            provider_id=route.provider_id,
                            provider_name=route.provider_name,
                            category=classification.category,
                            reason=classification.reason,
                            error_type=type(exc).__name__,
                            message=str(exc),
                        )
                    )

                    if not classification.failover_allowed:
                        break
                    continue

                if route.provider_id:
                    record_provider_success(route.provider_id)
                self._active_index = route_index
                self.provider = route.provider
                self.api_base = route.api_base
                self.model = route.model
                return response

            if last_exception is not None and len(self._routes) == 1:
                raise last_exception
            if last_exception is not None:
                raise ProviderFailoverError(attempts) from last_exception
            raise ProviderFailoverError(attempts)

    async def stream_generate(
        self,
        messages: list[Message],
        tools: list[Any] | None = None,
    ) -> AsyncIterator[LLMStreamEvent]:
        async with self._lock:
            health_monitor = get_health_monitor()
            attempts: list[FailoverAttempt] = []
            last_exception: Exception | None = None

            for route_index in self._attempt_order():
                route = self._routes[route_index]
                if route.provider_id:
                    health_monitor.record_route(
                        route.provider_id,
                        mapping_mode=route.mapping_mode,
                    )

                client = self._client_for(route)
                streamed_material = False
                try:
                    async for event in client.stream_generate(messages=messages, tools=tools):
                        if event.type in {
                            LLMStreamEventType.THINKING_DELTA,
                            LLMStreamEventType.TEXT_DELTA,
                            LLMStreamEventType.TOOL_CALL,
                            LLMStreamEventType.ERROR,
                        }:
                            streamed_material = True
                        yield event
                except Exception as exc:
                    last_exception = exc
                    classification = classify_provider_error(exc)
                    if route.provider_id:
                        record_provider_failure(route.provider_id, reason=classification.reason)

                    attempts.append(
                        FailoverAttempt(
                            provider_id=route.provider_id,
                            provider_name=route.provider_name,
                            category=classification.category,
                            reason=classification.reason,
                            error_type=type(exc).__name__,
                            message=str(exc),
                        )
                    )

                    if streamed_material or not classification.failover_allowed:
                        break
                    continue

                if route.provider_id:
                    record_provider_success(route.provider_id)
                self._active_index = route_index
                self.provider = route.provider
                self.api_base = route.api_base
                self.model = route.model
                return

            if last_exception is not None and len(self._routes) == 1:
                raise last_exception
            if last_exception is not None:
                raise ProviderFailoverError(attempts) from last_exception
            raise ProviderFailoverError(attempts)

    async def close(self) -> None:
        for client in list(self._clients.values()):
            close_method = getattr(client, "close", None)
            if not callable(close_method):
                continue
            try:
                result = close_method()
                if hasattr(result, "__await__"):
                    await result
            except Exception:
                continue
