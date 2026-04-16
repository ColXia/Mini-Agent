"""Model discovery service for fetching available models from providers.

This module provides automatic model discovery capabilities:
- Fetch latest available models from provider APIs
- Cache results to avoid frequent API calls
- Filter and rank models by recency and capability
- Support for runtime model selection UX
"""

from __future__ import annotations

import asyncio
from hashlib import sha256
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Literal
from typing import Any
from urllib.parse import urlsplit

import httpx

logger = logging.getLogger(__name__)


CapabilityTruth = Literal["supported", "unsupported", "unknown"]


class ProviderType(str, Enum):
    """Supported provider types for model discovery."""

    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    MINIMAX = "minimax"
    OLLAMA = "ollama"
    CUSTOM = "custom"


_CURATED_MODEL_ORDERS: dict[ProviderType, list[str]] = {
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
    ProviderType.MINIMAX: [
        "MiniMax-M2.7",
        "MiniMax-M2.5",
        "MiniMax-M1",
        "abab6.5s-chat",
        "abab6.5-chat",
    ],
    ProviderType.OLLAMA: [
        "qwen3-coder",
        "gpt-oss:20b",
        "glm-4.7:cloud",
        "minimax-m2.1:cloud",
    ],
}

_DISCOVERY_CONFIDENCE_BY_SOURCE = {
    "api_discovery": "high",
    "curated_manifest": "high",
    "fallback_manifest": "medium",
    "configured_default": "medium",
    "heuristic_recommendation": "medium",
}


def _normalize_provider_name(provider: str) -> str:
    """Normalize external aliases to internal provider keys."""
    return provider.lower().strip()


def _normalize_provider_type(provider: ProviderType | str) -> ProviderType:
    if isinstance(provider, ProviderType):
        return provider
    try:
        return ProviderType(_normalize_provider_name(str(provider)))
    except ValueError:
        return ProviderType.CUSTOM


def _should_bypass_proxy_env(api_base: str | None) -> bool:
    """Bypass proxy env for loopback/local discovery endpoints.

    Real local runtimes such as Ollama often expose `localhost` / `127.0.0.1`
    endpoints. On developer machines with corporate proxy env vars, letting
    `httpx` trust env can incorrectly route these loopback requests through the
    proxy and break local discovery.
    """

    normalized = str(api_base or "").strip()
    if not normalized:
        return False
    try:
        parsed = urlsplit(normalized)
    except Exception:
        return False
    host = str(parsed.hostname or "").strip().lower()
    return host in {"localhost", "127.0.0.1", "::1"}


def _discovery_protocol_flavor(
    provider: "ProviderType",
    api_base: str | None = None,
) -> str:
    _ = api_base
    if provider == ProviderType.ANTHROPIC:
        return "anthropic-curated-manifest"
    if provider == ProviderType.OLLAMA:
        return "ollama-openai-compat"
    return "openai-models"


def _normalize_discovery_cache_base_url(
    provider: "ProviderType",
    api_base: str | None,
) -> str:
    raw = str(api_base or "").strip()
    if not raw:
        default_endpoint = str(ModelDiscoveryService.PROVIDER_ENDPOINTS.get(provider) or "").strip()
        raw = default_endpoint
    if not raw:
        return f"provider://{provider.value}/default"

    try:
        parsed = urlsplit(raw)
    except Exception:
        return raw.rstrip("/") or f"provider://{provider.value}/default"

    if not parsed.scheme or not parsed.hostname:
        return raw.rstrip("/") or f"provider://{provider.value}/default"

    scheme = parsed.scheme.lower()
    host = str(parsed.hostname or "").strip().lower()
    port = parsed.port
    netloc = f"{host}:{port}" if port is not None else host
    path = str(parsed.path or "").rstrip("/")
    if path.endswith("/models"):
        path = path[: -len("/models")]
    path = path.rstrip("/")
    return f"{scheme}://{netloc}{path}" or f"provider://{provider.value}/default"


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


def resolve_curated_model_order(provider: ProviderType | str) -> list[str]:
    """Return the curated model-order manifest for one provider."""

    return list(_CURATED_MODEL_ORDERS.get(_normalize_provider_type(provider), []))


def resolve_official_default_model(provider: ProviderType | str) -> str | None:
    """Return the configured official/default model fallback for one provider."""

    order = resolve_curated_model_order(provider)
    return order[0] if order else None


def discovery_confidence_for_source(source: str | None) -> str:
    """Map one discovery source to a coarse confidence label."""

    normalized = " ".join((source or "").strip().split()).lower()
    return _DISCOVERY_CONFIDENCE_BY_SOURCE.get(normalized, "low")


def is_flagship_model(provider: ProviderType | str, model_id: str) -> bool:
    """Filter obvious non-runtime or non-flagship model ids for preset recommendation."""

    provider_type = _normalize_provider_type(provider)
    normalized = str(model_id or "").strip().lower()
    if not normalized:
        return False

    blocked_tokens = (
        "embedding",
        "moderation",
        "whisper",
        "tts",
        "audio",
        "image",
        "vision",
        "speech",
        "transcribe",
        "rerank",
    )
    if any(token in normalized for token in blocked_tokens):
        return False

    if provider_type == ProviderType.OPENAI:
        return normalized.startswith("gpt-") or normalized.startswith("o")
    if provider_type == ProviderType.ANTHROPIC:
        return "claude" in normalized
    if provider_type == ProviderType.MINIMAX:
        return normalized.startswith("minimax") or normalized.startswith("abab")
    if provider_type == ProviderType.OLLAMA:
        return True
    return True


def _infer_capability_evidence(
    raw_capabilities: set[str],
    *,
    positive_tokens: tuple[str, ...],
    negative_tokens: tuple[str, ...] = (),
) -> dict[str, str | bool | None]:
    positive_match = any(token in capability for capability in raw_capabilities for token in positive_tokens)
    negative_match = any(token in capability for capability in raw_capabilities for token in negative_tokens)

    if positive_match and not negative_match:
        return {
            "value": True,
            "truth": "supported",
            "confidence": "high",
            "source": "api_capabilities",
        }
    if negative_match and not positive_match:
        return {
            "value": False,
            "truth": "unsupported",
            "confidence": "high",
            "source": "api_capabilities",
        }
    if raw_capabilities:
        return {
            "value": None,
            "truth": "unknown",
            "confidence": "medium",
            "source": "ambiguous_capability_evidence",
        }
    return {
        "value": None,
        "truth": "unknown",
        "confidence": "low",
        "source": "no_capability_evidence",
    }


def infer_model_capabilities(
    provider: ProviderType | str,
    model_id: str,
    raw_capabilities: list[str] | None = None,
) -> dict[str, str | bool | None]:
    """Infer minimal routing-relevant capability flags for one model."""

    _ = (provider, model_id)
    raw = {str(item or "").strip().lower() for item in raw_capabilities or [] if str(item or "").strip()}
    tools_evidence = _infer_capability_evidence(
        raw,
        positive_tokens=("tool", "function"),
        negative_tokens=("no_tool", "toolless", "text_only", "text-only"),
    )
    thinking_evidence = _infer_capability_evidence(
        raw,
        positive_tokens=("thinking", "reasoning", "reason"),
        negative_tokens=("no_thinking", "no-thinking", "no_reasoning", "no-reasoning"),
    )

    return {
        "supports_tools": tools_evidence["value"],
        "supports_tools_truth": tools_evidence["truth"],
        "supports_tools_confidence": tools_evidence["confidence"],
        "supports_tools_source": tools_evidence["source"],
        "supports_thinking": thinking_evidence["value"],
        "supports_thinking_truth": thinking_evidence["truth"],
        "supports_thinking_confidence": thinking_evidence["confidence"],
        "supports_thinking_source": thinking_evidence["source"],
    }


@dataclass(frozen=True)
class ModelRecommendation:
    """Explicit recommendation result for one provider inventory."""

    model_id: str
    strategy: str
    confidence: str
    discovery_source: str


def recommend_discovered_model(
    provider: ProviderType | str,
    result: "DiscoveryResult",
    *,
    curated_order: list[str] | None = None,
    official_default: str | None = None,
) -> ModelRecommendation | None:
    """Choose one recommended model from a discovery result using explicit policy."""

    provider_type = _normalize_provider_type(provider)
    normalized_curated_order = [
        str(item).strip()
        for item in (curated_order if curated_order is not None else resolve_curated_model_order(provider_type))
        if str(item).strip()
    ]
    official_default_model = str(official_default or resolve_official_default_model(provider_type) or "").strip()
    available_models = [item for item in result.available_models if is_flagship_model(provider_type, item.id)]
    discovered_lookup = {
        str(item.id).strip().lower(): str(item.id).strip()
        for item in available_models
        if str(item.id).strip()
    }
    confidence = discovery_confidence_for_source(result.discovery_source)

    for candidate in normalized_curated_order:
        discovered_id = discovered_lookup.get(candidate.lower())
        if discovered_id:
            return ModelRecommendation(
                model_id=discovered_id,
                strategy="curated_latest",
                confidence=confidence,
                discovery_source=result.discovery_source,
            )

    if official_default_model:
        discovered_id = discovered_lookup.get(official_default_model.lower())
        if discovered_id:
            return ModelRecommendation(
                model_id=discovered_id,
                strategy="official_default",
                confidence=confidence,
                discovery_source=result.discovery_source,
            )

    latest = result.latest_base_model
    if latest and is_flagship_model(provider_type, latest.id):
        return ModelRecommendation(
            model_id=str(latest.id).strip(),
            strategy="discovered_latest",
            confidence=confidence if confidence != "low" else "medium",
            discovery_source=result.discovery_source or "heuristic_recommendation",
        )

    if available_models:
        return ModelRecommendation(
            model_id=str(available_models[0].id).strip(),
            strategy="discovered_latest",
            confidence=confidence if confidence != "low" else "medium",
            discovery_source=result.discovery_source or "heuristic_recommendation",
        )

    if official_default_model:
        return ModelRecommendation(
            model_id=official_default_model,
            strategy="official_default",
            confidence="medium",
            discovery_source="configured_default",
        )

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
    discovery_source: str = "unknown"
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

    def _cache_scope(
        self,
        provider: ProviderType,
        *,
        api_base: str | None = None,
        protocol_flavor: str | None = None,
    ) -> dict[str, str]:
        normalized_base_url = _normalize_discovery_cache_base_url(provider, api_base)
        resolved_protocol_flavor = (
            " ".join(str(protocol_flavor or "").strip().split()).lower()
            or _discovery_protocol_flavor(provider, api_base)
        )
        return {
            "provider": provider.value,
            "base_url": normalized_base_url,
            "protocol_flavor": resolved_protocol_flavor,
        }

    def _cache_file(
        self,
        provider: ProviderType,
        *,
        api_base: str | None = None,
        protocol_flavor: str | None = None,
    ) -> Path:
        scope = self._cache_scope(
            provider,
            api_base=api_base,
            protocol_flavor=protocol_flavor,
        )
        digest = sha256(
            f"{scope['provider']}|{scope['base_url']}|{scope['protocol_flavor']}".encode("utf-8")
        ).hexdigest()[:16]
        return self.cache_dir / f"models_{provider.value}_{digest}.json"

    def get(
        self,
        provider: ProviderType,
        *,
        api_base: str | None = None,
        protocol_flavor: str | None = None,
    ) -> DiscoveryResult | None:
        """Get cached discovery result.

        Args:
            provider: Provider type

        Returns:
            Cached result or None if not found/expired
        """
        scope = self._cache_scope(
            provider,
            api_base=api_base,
            protocol_flavor=protocol_flavor,
        )
        cache_file = self._cache_file(
            provider,
            api_base=api_base,
            protocol_flavor=protocol_flavor,
        )
        if not cache_file.exists():
            return None

        try:
            data = json.loads(cache_file.read_text(encoding="utf-8"))
            fetched_at = datetime.fromisoformat(data["fetched_at"])

            # Check if cache is expired
            if datetime.now() - fetched_at > self.ttl:
                logger.debug(
                    "Cache expired for %s [%s, %s]",
                    provider.value,
                    scope["base_url"],
                    scope["protocol_flavor"],
                )
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
                discovery_source=str(data.get("discovery_source") or "unknown"),
                error=data.get("error"),
                cache_hit=True,
            )

            logger.debug(
                "Cache hit for %s [%s, %s]: %s models",
                provider.value,
                scope["base_url"],
                scope["protocol_flavor"],
                len(models),
            )
            return result

        except Exception as e:
            logger.warning(f"Failed to load cache for {provider.value}: {e}")
            return None

    def set(
        self,
        result: DiscoveryResult,
        *,
        api_base: str | None = None,
        protocol_flavor: str | None = None,
    ) -> None:
        """Save discovery result to cache.

        Args:
            result: Discovery result to cache
        """
        scope = self._cache_scope(
            result.provider,
            api_base=api_base,
            protocol_flavor=protocol_flavor,
        )
        cache_file = self._cache_file(
            result.provider,
            api_base=api_base,
            protocol_flavor=protocol_flavor,
        )
        try:
            data = {
                "provider": result.provider.value,
                "models": [m.to_dict() for m in result.models],
                "fetched_at": result.fetched_at.isoformat(),
                "discovery_source": result.discovery_source,
                "error": result.error,
                "cache_scope": scope,
            }
            cache_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
            logger.debug(
                "Cached %s models for %s [%s, %s]",
                len(result.models),
                result.provider.value,
                scope["base_url"],
                scope["protocol_flavor"],
            )
        except Exception as e:
            logger.warning(f"Failed to cache models for {result.provider.value}: {e}")


class ModelDiscoveryService:
    """Service for discovering available models from providers."""

    # Provider API endpoints for model listing
    PROVIDER_ENDPOINTS = {
        ProviderType.OPENAI: "https://api.openai.com/v1/models",
        ProviderType.MINIMAX: "https://api.minimaxi.com/v1/models",  # Assuming similar to OpenAI
        ProviderType.OLLAMA: "http://localhost:11434/v1/models",
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
        ProviderType.MINIMAX: [
            "MiniMax-M2.7",
            "MiniMax-M2.5",
            "MiniMax-M1",
            "abab6.5s-chat",
            "abab6.5-chat",
        ],
        ProviderType.OLLAMA: [],
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
        normalized_api_base = _normalize_discovery_cache_base_url(provider, api_base)
        protocol_flavor = _discovery_protocol_flavor(provider, normalized_api_base)

        # Check cache first
        if use_cache:
            cached = self.cache.get(
                provider,
                api_base=normalized_api_base,
                protocol_flavor=protocol_flavor,
            )
            if cached:
                return cached

        # Fetch from API
        try:
            models = await self._fetch_models(provider, api_key, api_base)
            result = DiscoveryResult(
                provider=provider,
                models=models,
                fetched_at=datetime.now(),
                discovery_source="curated_manifest"
                if provider == ProviderType.ANTHROPIC
                else "api_discovery",
            )
        except Exception as e:
            logger.warning(f"Failed to fetch models from {provider.value}: {e}")
            # Use fallback models
            models = self._get_fallback_models(provider)
            result = DiscoveryResult(
                provider=provider,
                models=models,
                fetched_at=datetime.now(),
                discovery_source="fallback_manifest",
                error=str(e),
            )

        # Cache the result
        self.cache.set(
            result,
            api_base=normalized_api_base,
            protocol_flavor=protocol_flavor,
        )
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

        async with httpx.AsyncClient(
            timeout=self.timeout,
            trust_env=not _should_bypass_proxy_env(url),
        ) as client:
            if provider == ProviderType.OPENAI:
                return await self._fetch_openai_models(client, url, api_key)
            elif provider == ProviderType.MINIMAX:
                return await self._fetch_minimax_models(client, url, api_key)
            elif provider == ProviderType.OLLAMA:
                return await self._fetch_ollama_models(client, url, api_key)
            else:
                return self._get_fallback_models(provider)

    @staticmethod
    def _parse_model_created(value: Any) -> datetime | None:
        if value in {None, ""}:
            return None
        if isinstance(value, (int, float)):
            try:
                return datetime.fromtimestamp(value)
            except Exception:
                return None
        text = str(value).strip()
        if not text:
            return None
        try:
            if text.endswith("Z"):
                text = f"{text[:-1]}+00:00"
            return datetime.fromisoformat(text)
        except Exception:
            return None

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
            raise

    async def _fetch_ollama_models(
        self,
        client: httpx.AsyncClient,
        url: str,
        api_key: str,
    ) -> list[ModelInfo]:
        """Fetch models from Ollama's local compatibility/runtime endpoints."""

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        openai_models_url = url.rstrip("/")
        if not openai_models_url.endswith("/v1/models"):
            if openai_models_url.endswith("/v1"):
                openai_models_url = f"{openai_models_url}/models"
            else:
                openai_models_url = f"{openai_models_url}/v1/models"
        try:
            response = await client.get(openai_models_url, headers=headers)
            response.raise_for_status()
            data = response.json()
            raw_models = data.get("data", [])
            provider_owned_by = "library"
            models: list[ModelInfo] = []
            for model_data in raw_models:
                if not isinstance(model_data, dict):
                    continue
                model_id = str(model_data.get("id") or "").strip()
                if not model_id:
                    continue
                models.append(
                    ModelInfo(
                        id=model_id,
                        name=str(model_data.get("id") or model_id),
                        provider=ProviderType.OLLAMA,
                        created=self._parse_model_created(model_data.get("created")),
                        owned_by=str(model_data.get("owned_by") or provider_owned_by),
                        metadata=model_data,
                    )
                )
            return models
        except Exception:
            # Fall back to the native tags endpoint for older/local daemon layouts.
            native_base = openai_models_url
            if native_base.endswith("/v1/models"):
                native_base = native_base[: -len("/v1/models")]
            tags_response = await client.get(f"{native_base}/api/tags", headers=headers)
            tags_response.raise_for_status()
            data = tags_response.json()
            models = []
            for model_data in data.get("models", []):
                if not isinstance(model_data, dict):
                    continue
                model_id = str(model_data.get("model") or model_data.get("name") or "").strip()
                if not model_id:
                    continue
                display_name = str(model_data.get("name") or model_id).strip() or model_id
                models.append(
                    ModelInfo(
                        id=model_id,
                        name=display_name,
                        provider=ProviderType.OLLAMA,
                        created=self._parse_model_created(
                            model_data.get("modified_at") or model_data.get("created_at")
                        ),
                        owned_by="library",
                        metadata=model_data,
                    )
                )
            return models

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
        provider: Provider name (openai, anthropic, minimax, ollama)
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

    recommended = recommend_discovered_model(provider_type, result)
    if recommended:
        print(
            f"\n  Recommended: {recommended.model_id}"
            f" [{recommended.strategy}, {recommended.discovery_source}]"
        )


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
    recommendation = recommend_discovered_model(provider_type, result)
    return recommendation.model_id if recommendation else None
