"""Runtime helpers for provider-catalog based routing and monitoring."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
from typing import Any

from mini_agent.model_manager.model_mapper import ProviderRouteSelector
from mini_agent.model_manager.circuit_breaker import (
    CircuitBreakerRegistry,
)
from mini_agent.model_manager.health_monitor import ProviderHealthMonitor
from mini_agent.model_manager.provider import (
    ProviderAPIType,
    ProviderCatalog,
    ProviderConfig,
    normalize_provider_catalog,
)
from mini_agent.schema import LLMProvider


def _normalize_text(value: str | None) -> str:
    if value is None:
        return ""
    return " ".join(value.strip().split())


def _parse_api_type(value: str | None) -> ProviderAPIType | None:
    normalized = _normalize_text(value).lower()
    if not normalized:
        return None
    for item in ProviderAPIType:
        if item.value == normalized:
            return item
    return None


def _to_runtime_provider(api_type: ProviderAPIType) -> LLMProvider | None:
    if api_type == ProviderAPIType.ANTHROPIC:
        return LLMProvider.ANTHROPIC
    if api_type == ProviderAPIType.OPENAI:
        return LLMProvider.OPENAI
    return None


def _fallback_provider(value: str | None) -> LLMProvider:
    if _normalize_text(value).lower() == "anthropic":
        return LLMProvider.ANTHROPIC
    return LLMProvider.OPENAI


def _config_provider_api_type(value: str | None) -> ProviderAPIType:
    normalized = _normalize_text(value).lower()
    if normalized == ProviderAPIType.ANTHROPIC.value:
        return ProviderAPIType.ANTHROPIC
    if normalized == ProviderAPIType.OPENAI.value:
        return ProviderAPIType.OPENAI
    if normalized == ProviderAPIType.GEMINI.value:
        return ProviderAPIType.GEMINI
    return ProviderAPIType.CUSTOM


def _build_config_fallback_provider(config: Any) -> ProviderConfig:
    return ProviderConfig(
        id="config-default",
        name="Config Default Provider",
        api_type=_config_provider_api_type(getattr(config.llm, "provider", None)),
        api_base=str(config.llm.api_base),
        api_key=str(config.llm.api_key),
        models=[str(config.llm.model)],
        enabled=True,
        priority=0,
        timeout=60,
    )


def _load_catalog_payload(path: Path) -> dict[str, Any] | list[dict[str, Any]] | None:
    if not path.exists() or not path.is_file():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if isinstance(raw, dict) or isinstance(raw, list):
        return raw
    return None


def _resolve_catalog_path(catalog_path: str | Path | None) -> Path | None:
    """Resolve provider catalog path.

    Priority:
    1. Explicit catalog_path parameter
    2. Default: ~/.mini-agent/providers.json

    Args:
        catalog_path: Optional explicit catalog path

    Returns:
        Resolved catalog path or None
    """
    explicit_path = _normalize_text(
        str(catalog_path) if catalog_path is not None else ""
    )
    if explicit_path:
        return Path(explicit_path).expanduser().resolve()

    # Default catalog path
    default_path = Path.home() / ".mini-agent" / "providers.json"
    return default_path


@dataclass(frozen=True)
class RoutedLLMSettings:
    """Resolved runtime LLM settings after provider routing."""

    source: str  # config | provider_catalog
    provider: LLMProvider
    api_key: str
    api_base: str
    model: str
    provider_id: str | None = None
    provider_name: str | None = None
    mapping_mode: str | None = None
    requested_model: str | None = None
    catalog_path: str | None = None
    breaker_state: str | None = None
    breaker_allowed: bool | None = None


@dataclass(frozen=True)
class ProviderCatalogResolution:
    """Resolved provider catalog source for runtime inspection APIs."""

    source: str  # provider_catalog | config_fallback
    catalog_path: str | None
    providers: list[ProviderConfig]


_CIRCUIT_BREAKERS = CircuitBreakerRegistry()
_HEALTH_MONITOR = ProviderHealthMonitor()


def get_circuit_breaker_registry() -> CircuitBreakerRegistry:
    return _CIRCUIT_BREAKERS


def get_health_monitor() -> ProviderHealthMonitor:
    return _HEALTH_MONITOR


def reset_model_manager_runtime_state() -> None:
    global _CIRCUIT_BREAKERS  # noqa: PLW0603
    _CIRCUIT_BREAKERS = CircuitBreakerRegistry()
    _HEALTH_MONITOR.reset()


def record_provider_success(provider_id: str) -> None:
    _HEALTH_MONITOR.record_success(provider_id)
    _CIRCUIT_BREAKERS.record_success(provider_id)


def record_provider_failure(provider_id: str, *, reason: str | None = None) -> None:
    _HEALTH_MONITOR.record_failure(provider_id, reason=reason)
    _CIRCUIT_BREAKERS.record_failure(provider_id, reason=reason)


def _build_config_fallback_settings(
    config: Any,
    *,
    requested_model: str | None = None,
    catalog_path: str | None = None,
) -> RoutedLLMSettings:
    return RoutedLLMSettings(
        source="config",
        provider=_fallback_provider(getattr(config.llm, "provider", None)),
        api_key=str(config.llm.api_key),
        api_base=str(config.llm.api_base),
        model=str(requested_model or config.llm.model),
        requested_model=requested_model,
        catalog_path=catalog_path,
    )


def resolve_provider_catalog(
    config: Any,
    *,
    catalog_path: str | Path | None = None,
    supported_api_types: set[ProviderAPIType] | None = None,
) -> ProviderCatalogResolution:
    """Resolve provider list from catalog path or fallback runtime config."""
    resolved_path = _resolve_catalog_path(catalog_path)
    if resolved_path is None:
        return ProviderCatalogResolution(
            source="config_fallback",
            catalog_path=None,
            providers=[_build_config_fallback_provider(config)],
        )

    payload = _load_catalog_payload(resolved_path)
    if payload is None:
        return ProviderCatalogResolution(
            source="config_fallback",
            catalog_path=str(resolved_path),
            providers=[_build_config_fallback_provider(config)],
        )

    try:
        catalog = normalize_provider_catalog(payload)
    except Exception:
        return ProviderCatalogResolution(
            source="config_fallback",
            catalog_path=str(resolved_path),
            providers=[_build_config_fallback_provider(config)],
        )

    providers = [provider for provider in catalog.providers if provider.enabled]
    if supported_api_types is not None:
        providers = [
            provider
            for provider in providers
            if provider.api_type in supported_api_types
        ]
    if not providers:
        return ProviderCatalogResolution(
            source="config_fallback",
            catalog_path=str(resolved_path),
            providers=[_build_config_fallback_provider(config)],
        )
    return ProviderCatalogResolution(
        source="provider_catalog",
        catalog_path=str(resolved_path),
        providers=providers,
    )


def resolve_routed_llm_candidates(
    config: Any,
    *,
    requested_model: str | None = None,
    catalog_path: str | Path | None = None,
) -> list[RoutedLLMSettings]:
    """Resolve an ordered provider candidate chain for failover."""
    fallback = _build_config_fallback_settings(config, requested_model=requested_model)
    catalog = resolve_provider_catalog(
        config,
        catalog_path=catalog_path,
        supported_api_types={ProviderAPIType.ANTHROPIC, ProviderAPIType.OPENAI},
    )
    if catalog.source != "provider_catalog":
        return [fallback]

    preferred = _parse_api_type(getattr(config.llm, "provider", None))
    selector = ProviderRouteSelector(ProviderCatalog(providers=catalog.providers))
    try:
        preferred_ranked_routes = selector.rank(
            requested_model=requested_model or str(config.llm.model),
            preferred_api_type=preferred,
            supported_api_types={ProviderAPIType.ANTHROPIC, ProviderAPIType.OPENAI},
        )
        global_ranked_routes = (
            selector.rank(
                requested_model=requested_model or str(config.llm.model),
                preferred_api_type=None,
                supported_api_types={ProviderAPIType.ANTHROPIC, ProviderAPIType.OPENAI},
            )
            if preferred is not None
            else []
        )
    except Exception:
        return [
            _build_config_fallback_settings(
                config,
                requested_model=requested_model,
                catalog_path=catalog.catalog_path,
            )
        ]

    ranked_routes = []
    seen_provider_ids: set[str] = set()
    for route in [*preferred_ranked_routes, *global_ranked_routes]:
        provider_id = str(route.provider.id)
        if provider_id in seen_provider_ids:
            continue
        seen_provider_ids.add(provider_id)
        ranked_routes.append(route)

    breakers = get_circuit_breaker_registry()
    allowed_candidates: list[RoutedLLMSettings] = []
    blocked_candidates: list[RoutedLLMSettings] = []
    for route in ranked_routes:
        runtime_provider = _to_runtime_provider(route.provider.api_type)
        if runtime_provider is None:
            continue
        decision = breakers.should_allow(str(route.provider.id))
        candidate = RoutedLLMSettings(
            source="provider_catalog",
            provider=runtime_provider,
            api_key=route.provider.api_key,
            api_base=route.provider.api_base,
            model=route.mapping.selected_model,
            provider_id=route.provider.id,
            provider_name=route.provider.name,
            mapping_mode=route.mapping.mode,
            requested_model=route.mapping.requested_model,
            catalog_path=catalog.catalog_path,
            breaker_state=decision.state.value,
            breaker_allowed=decision.allowed,
        )
        if decision.allowed:
            allowed_candidates.append(candidate)
        else:
            blocked_candidates.append(candidate)

    if allowed_candidates:
        return allowed_candidates
    if blocked_candidates:
        return blocked_candidates
    return [
        _build_config_fallback_settings(
            config, requested_model=requested_model, catalog_path=catalog.catalog_path
        )
    ]


def resolve_routed_llm_settings(
    config: Any,
    *,
    requested_model: str | None = None,
    catalog_path: str | Path | None = None,
) -> RoutedLLMSettings:
    """Resolve routed provider settings with config fallback."""
    candidates = resolve_routed_llm_candidates(
        config,
        requested_model=requested_model,
        catalog_path=catalog_path,
    )
    selected = candidates[0]
    if selected.provider_id:
        _HEALTH_MONITOR.record_route(
            str(selected.provider_id),
            mapping_mode=selected.mapping_mode,
        )
    return selected
