"""Model discovery service for fetching available models from providers.

This module provides automatic model discovery capabilities:
- Fetch latest available models from provider APIs
- Cache results to avoid frequent API calls
- Filter and rank models by recency and capability
- Support for runtime model selection UX
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class ProviderType(str, Enum):
    """Supported provider types for model discovery."""

    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GEMINI = "gemini"
    MINIMAX = "minimax"
    CUSTOM = "custom"


def _normalize_provider_name(provider: str) -> str:
    """Normalize external aliases to internal provider keys."""
    return provider.lower().strip()


_KNOWN_CONTEXT_WINDOWS: dict[ProviderType, dict[str, int]] = {
    ProviderType.OPENAI: {
        "gpt-5.4": 1_050_000,
        "gpt-5.3": 400_000,
        "gpt-5.2": 400_000,
        "gpt-5.1": 400_000,
        "gpt-4.1": 1_047_576,
        "gpt-4o": 128_000,
    },
    ProviderType.ANTHROPIC: {
        "claude-sonnet-4-6": 1_000_000,
        "claude-opus-4-1": 200_000,
        "claude-sonnet-4-5": 200_000,
        "claude-haiku-4-0": 200_000,
    },
}


def _normalize_context_window(value: Any) -> int | None:
    try:
        parsed = int(value)
    except Exception:
        return None
    return parsed if parsed > 0 else None


def resolve_known_context_window(
    provider: ProviderType | str,
    model_id: str,
) -> int | None:
    """Resolve a known context window when provider APIs omit it."""

    normalized_model = str(model_id or "").strip().lower()
    if not normalized_model:
        return None

    if isinstance(provider, ProviderType):
        provider_type = provider
    else:
        try:
            provider_type = ProviderType(_normalize_provider_name(str(provider)))
        except ValueError:
            return None

    exact = _KNOWN_CONTEXT_WINDOWS.get(provider_type, {}).get(normalized_model)
    if exact is not None:
        return exact

    if provider_type == ProviderType.OPENAI:
        if normalized_model.startswith("gpt-4.1"):
            return 1_047_576
        if normalized_model.startswith("gpt-4o"):
            return 128_000
        if normalized_model == "gpt-5":
            return 400_000

    return None


@dataclass
class ModelInfo:
    """Information about a discovered model."""

    id: str
    name: str
    provider: ProviderType
    created: datetime | None = None
    owned_by: str | None = None
    is_deprecated: bool = False
    is_fine_tuned: bool = False
    context_window: int | None = None
    capabilities: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "name": self.name,
            "provider": self.provider.value,
            "created": self.created.isoformat() if self.created else None,
            "owned_by": self.owned_by,
            "is_deprecated": self.is_deprecated,
            "is_fine_tuned": self.is_fine_tuned,
            "context_window": self.context_window,
            "capabilities": self.capabilities,
            "metadata": self.metadata,
        }


@dataclass
class DiscoveryResult:
    """Result of model discovery for a provider."""

    provider: ProviderType
    models: list[ModelInfo]
    fetched_at: datetime
    error: str | None = None
    cache_hit: bool = False

    @property
    def available_models(self) -> list[ModelInfo]:
        """Get list of available (non-deprecated, non-fine-tuned) models."""
        return [m for m in self.models if not m.is_deprecated and not m.is_fine_tuned]

    @property
    def latest_base_model(self) -> ModelInfo | None:
        """Get the latest base model (sorted by creation date)."""
        available = self.available_models
        if not available:
            return None
        # Sort by creation date (newest first)
        sorted_models = sorted(
            [m for m in available if m.created],
            key=lambda m: m.created or datetime.min,
            reverse=True,
        )
        return sorted_models[0] if sorted_models else available[0]


class ModelDiscoveryCache:
    """Cache for model discovery results."""

    def __init__(self, cache_dir: Path | None = None, ttl_hours: int = 24):
        """Initialize cache.

        Args:
            cache_dir: Directory to store cache files
            ttl_hours: Time-to-live in hours for cache entries
        """
        self.cache_dir = cache_dir or (Path.home() / ".mini-agent" / "cache")
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.ttl = timedelta(hours=ttl_hours)

    def get(self, provider: ProviderType) -> DiscoveryResult | None:
        """Get cached discovery result.

        Args:
            provider: Provider type

        Returns:
            Cached result or None if not found/expired
        """
        cache_file = self.cache_dir / f"models_{provider.value}.json"
        if not cache_file.exists():
            return None

        try:
            data = json.loads(cache_file.read_text(encoding="utf-8"))
            fetched_at = datetime.fromisoformat(data["fetched_at"])

            # Check if cache is expired
            if datetime.now() - fetched_at > self.ttl:
                logger.debug(f"Cache expired for {provider.value}")
                return None

            models = [
                ModelInfo(
                    id=m["id"],
                    name=m["name"],
                    provider=ProviderType(m["provider"]),
                    created=datetime.fromisoformat(m["created"])
                    if m.get("created")
                    else None,
                    owned_by=m.get("owned_by"),
                    is_deprecated=m.get("is_deprecated", False),
                    is_fine_tuned=m.get("is_fine_tuned", False),
                    context_window=m.get("context_window"),
                    capabilities=m.get("capabilities", []),
                    metadata=m.get("metadata", {}),
                )
                for m in data.get("models", [])
            ]

            result = DiscoveryResult(
                provider=provider,
                models=models,
                fetched_at=fetched_at,
                error=data.get("error"),
                cache_hit=True,
            )

            logger.debug(f"Cache hit for {provider.value}: {len(models)} models")
            return result

        except Exception as e:
            logger.warning(f"Failed to load cache for {provider.value}: {e}")
            return None

    def set(self, result: DiscoveryResult) -> None:
        """Save discovery result to cache.

        Args:
            result: Discovery result to cache
        """
        cache_file = self.cache_dir / f"models_{result.provider.value}.json"
        try:
            data = {
                "provider": result.provider.value,
                "models": [m.to_dict() for m in result.models],
                "fetched_at": result.fetched_at.isoformat(),
                "error": result.error,
            }
            cache_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
            logger.debug(
                f"Cached {len(result.models)} models for {result.provider.value}"
            )
        except Exception as e:
            logger.warning(f"Failed to cache models for {result.provider.value}: {e}")


class ModelDiscoveryService:
    """Service for discovering available models from providers."""

    # Provider API endpoints for model listing
    PROVIDER_ENDPOINTS = {
        ProviderType.OPENAI: "https://api.openai.com/v1/models",
        ProviderType.GEMINI: "https://generativelanguage.googleapis.com/v1beta/models",
        ProviderType.MINIMAX: "https://api.minimaxi.com/v1/models",  # Assuming similar to OpenAI
    }

    # Fallback model lists (when API is unavailable)
    FALLBACK_MODELS = {
        ProviderType.OPENAI: [
            "gpt-5.4",
            "gpt-5.3",
            "gpt-5.2",
            "gpt-5.1",
            "gpt-4.1",
            "gpt-4o",
        ],
        ProviderType.ANTHROPIC: [
            "claude-sonnet-4-6",
            "claude-opus-4-1",
            "claude-sonnet-4-5",
            "claude-haiku-4-0",
        ],
        ProviderType.GEMINI: [
            "gemini-3.1-pro",
            "gemini-3.1-flash",
            "gemini-2.5-pro",
            "gemini-2.0-flash",
            "gemini-1.5-pro",
        ],
        ProviderType.MINIMAX: [
            "MiniMax-M2.7",
            "MiniMax-M2.5",
            "MiniMax-M1",
            "abab6.5s-chat",
            "abab6.5-chat",
        ],
    }

    def __init__(
        self,
        cache: ModelDiscoveryCache | None = None,
        timeout: float = 10.0,
    ):
        """Initialize discovery service.

        Args:
            cache: Optional cache instance
            timeout: HTTP request timeout in seconds
        """
        self.cache = cache or ModelDiscoveryCache()
        self.timeout = timeout

    async def discover_models(
        self,
        provider: ProviderType,
        api_key: str,
        api_base: str | None = None,
        use_cache: bool = True,
    ) -> DiscoveryResult:
        """Discover available models from a provider.

        Args:
            provider: Provider type
            api_key: API key for authentication
            api_base: Optional custom API base URL
            use_cache: Whether to use cached results

        Returns:
            Discovery result with list of models
        """
        # Check cache first
        if use_cache:
            cached = self.cache.get(provider)
            if cached:
                return cached

        # Fetch from API
        try:
            models = await self._fetch_models(provider, api_key, api_base)
            result = DiscoveryResult(
                provider=provider,
                models=models,
                fetched_at=datetime.now(),
            )
        except Exception as e:
            logger.warning(f"Failed to fetch models from {provider.value}: {e}")
            # Use fallback models
            models = self._get_fallback_models(provider)
            result = DiscoveryResult(
                provider=provider,
                models=models,
                fetched_at=datetime.now(),
                error=str(e),
            )

        # Cache the result
        self.cache.set(result)
        return result

    async def _fetch_models(
        self,
        provider: ProviderType,
        api_key: str,
        api_base: str | None = None,
    ) -> list[ModelInfo]:
        """Fetch models from provider API.

        Args:
            provider: Provider type
            api_key: API key
            api_base: Custom API base URL

        Returns:
            List of model info
        """
        if provider == ProviderType.ANTHROPIC:
            # Anthropic doesn't have a models API, use fallback
            return self._get_fallback_models(provider)

        url = api_base or self.PROVIDER_ENDPOINTS.get(provider)
        if not url:
            return self._get_fallback_models(provider)

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            if provider == ProviderType.OPENAI:
                return await self._fetch_openai_models(client, url, api_key)
            elif provider == ProviderType.GEMINI:
                return await self._fetch_gemini_models(client, url, api_key)
            elif provider == ProviderType.MINIMAX:
                return await self._fetch_minimax_models(client, url, api_key)
            else:
                return self._get_fallback_models(provider)

    async def _fetch_openai_models(
        self,
        client: httpx.AsyncClient,
        url: str,
        api_key: str,
    ) -> list[ModelInfo]:
        """Fetch models from OpenAI API."""
        response = await client.get(url, headers={"Authorization": f"Bearer {api_key}"})
        response.raise_for_status()
        data = response.json()

        models = []
        for model_data in data.get("data", []):
            model_id = model_data.get("id", "")

            # Skip fine-tuned models (contain ":")
            is_fine_tuned = ":" in model_id

            # Skip deprecated models
            is_deprecated = model_data.get("deprecated", False)

            # Parse creation date
            created = None
            if model_data.get("created"):
                try:
                    created = datetime.fromtimestamp(model_data["created"])
                except Exception:
                    pass

            models.append(
                ModelInfo(
                    id=model_id,
                    name=model_id,
                    provider=ProviderType.OPENAI,
                    created=created,
                    owned_by=model_data.get("owned_by"),
                    is_deprecated=is_deprecated,
                    is_fine_tuned=is_fine_tuned,
                    context_window=resolve_known_context_window(
                        ProviderType.OPENAI,
                        model_id,
                    ),
                    metadata=model_data,
                )
            )

        return models

    async def _fetch_gemini_models(
        self,
        client: httpx.AsyncClient,
        url: str,
        api_key: str,
    ) -> list[ModelInfo]:
        """Fetch models from Gemini API."""
        # Gemini uses query parameter for API key
        response = await client.get(f"{url}?key={api_key}")
        response.raise_for_status()
        data = response.json()

        models = []
        for model_data in data.get("models", []):
            model_name = model_data.get("name", "").replace("models/", "")
            if not model_name:
                continue

            # Parse supported methods to determine capabilities
            methods = model_data.get("supportedGenerationMethods", [])

            models.append(
                ModelInfo(
                    id=model_name,
                    name=model_data.get("displayName", model_name),
                    provider=ProviderType.GEMINI,
                    context_window=model_data.get("inputTokenLimit"),
                    capabilities=methods,
                    metadata=model_data,
                )
            )

        return models

    async def _fetch_minimax_models(
        self,
        client: httpx.AsyncClient,
        url: str,
        api_key: str,
    ) -> list[ModelInfo]:
        """Fetch models from MiniMax API."""
        try:
            response = await client.get(
                url,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
            )
            response.raise_for_status()
            data = response.json()

            models = []
            for model_data in data.get("data", []):
                model_id = model_data.get("id", "")
                models.append(
                    ModelInfo(
                        id=model_id,
                        name=model_id,
                        provider=ProviderType.MINIMAX,
                        owned_by=model_data.get("owned_by"),
                        context_window=resolve_known_context_window(
                            ProviderType.MINIMAX,
                            model_id,
                        ),
                        metadata=model_data,
                    )
                )

            return models
        except Exception as e:
            logger.debug(f"MiniMax models API not available: {e}")
            return self._get_fallback_models(ProviderType.MINIMAX)

    def _get_fallback_models(self, provider: ProviderType) -> list[ModelInfo]:
        """Get fallback model list when API is unavailable.

        Args:
            provider: Provider type

        Returns:
            List of fallback models
        """
        model_ids = self.FALLBACK_MODELS.get(provider, [])
        return [
            ModelInfo(
                id=model_id,
                name=model_id,
                provider=provider,
                context_window=resolve_known_context_window(provider, model_id),
            )
            for model_id in model_ids
        ]

    async def discover_all_providers(
        self,
        credentials: dict[ProviderType, str],
        use_cache: bool = True,
    ) -> dict[ProviderType, DiscoveryResult]:
        """Discover models from all configured providers.

        Args:
            credentials: Dict mapping provider to API key
            use_cache: Whether to use cached results

        Returns:
            Dict mapping provider to discovery result
        """
        tasks = {
            provider: self.discover_models(provider, api_key, use_cache=use_cache)
            for provider, api_key in credentials.items()
        }

        results = {}
        for provider, task in tasks.items():
            try:
                results[provider] = await task
            except Exception as e:
                logger.error(f"Failed to discover models for {provider.value}: {e}")
                results[provider] = DiscoveryResult(
                    provider=provider,
                    models=self._get_fallback_models(provider),
                    fetched_at=datetime.now(),
                    error=str(e),
                )

        return results

    def get_latest_base_model(
        self,
        provider: ProviderType,
        api_key: str,
        api_base: str | None = None,
    ) -> asyncio.coroutines.coroutine:
        """Get the latest base model for a provider.

        This is a convenience method that discovers models and returns
        the most recent base model.

        Args:
            provider: Provider type
            api_key: API key
            api_base: Optional custom API base

        Returns:
            Latest base model info or None
        """

        async def _get():
            result = await self.discover_models(provider, api_key, api_base)
            return result.latest_base_model

        return _get()


# CLI helper functions
async def list_available_models(
    provider: str,
    api_key: str,
    api_base: str | None = None,
    show_all: bool = False,
) -> None:
    """List available models for a provider (CLI helper).

    Args:
        provider: Provider name (openai, anthropic, gemini, minimax)
        api_key: API key
        api_base: Optional custom API base
        show_all: Show all models including deprecated/fine-tuned
    """
    try:
        provider_type = ProviderType(_normalize_provider_name(provider))
    except ValueError:
        print(f"Unknown provider: {provider}")
        print(f"Supported providers: {', '.join([p.value for p in ProviderType])}")
        return

    service = ModelDiscoveryService()
    result = await service.discover_models(provider_type, api_key, api_base)

    if result.error:
        print(f"Warning: {result.error}")
        print("Using fallback model list.\n")

    models = result.models if show_all else result.available_models

    if not models:
        print("No models found.")
        return

    print(f"\n{provider_type.value.upper()} Models ({len(models)} found):\n")
    for model in models:
        flags = []
        if model.is_deprecated:
            flags.append("deprecated")
        if model.is_fine_tuned:
            flags.append("fine-tuned")
        flag_str = f" [{', '.join(flags)}]" if flags else ""

        created_str = ""
        if model.created:
            created_str = f" (created: {model.created.strftime('%Y-%m-%d')})"

        print(f"  - {model.id}{flag_str}{created_str}")

    if result.latest_base_model:
        print(f"\n  Recommended: {result.latest_base_model.id}")


async def get_latest_model_id(
    provider: str,
    api_key: str,
    api_base: str | None = None,
) -> str | None:
    """Get the latest base model ID for a provider.

    Args:
        provider: Provider name
        api_key: API key
        api_base: Optional custom API base

    Returns:
        Latest base model ID or None
    """
    try:
        provider_type = ProviderType(_normalize_provider_name(provider))
    except ValueError:
        return None

    service = ModelDiscoveryService()
    result = await service.discover_models(provider_type, api_key, api_base)
    latest = result.latest_base_model
    return latest.id if latest else None
