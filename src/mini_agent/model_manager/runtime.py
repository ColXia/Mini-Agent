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


def _runtime_catalog_provider_id(*, source: str, provider_id: str) -> str:
    normalized_source = _normalize_text(source).lower()
    normalized_provider_id = _normalize_text(provider_id)
    if normalized_source == "preset":
        return f"preset-{normalized_provider_id}"
    return normalized_provider_id


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


def _provider_model_context_window(provider: ProviderConfig, model_id: str) -> int | None:
    try:
        value = int(provider.model_context_windows.get(model_id, 0))
    except Exception:
        return None
    return value if value > 0 else None


def _provider_model_learned_token_limit(provider: ProviderConfig, model_id: str) -> int | None:
    try:
        value = int(provider.model_learned_token_limits.get(model_id, 0))
    except Exception:
        return None
    return value if value > 0 else None


def _effective_provider_model_token_limit(provider: ProviderConfig, model_id: str) -> int | None:
    learned = _provider_model_learned_token_limit(provider, model_id)
    if learned is not None:
        return learned
    return _provider_model_context_window(provider, model_id)


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
    2. Environment: MINI_AGENT_PROVIDER_CATALOG_PATH
    3. Default: ~/.mini-agent/providers.json

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

    env_path = _normalize_text(os.getenv("MINI_AGENT_PROVIDER_CATALOG_PATH"))
    if env_path:
        return Path(env_path).expanduser().resolve()

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
    context_window: int | None = None
    learned_token_limit: int | None = None
    token_limit: int | None = None


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
        token_limit=80_000,
    )


def resolve_provider_catalog(
    config: Any,
    *,
    catalog_path: str | Path | None = None,
    supported_api_types: set[ProviderAPIType] | None = None,
) -> ProviderCatalogResolution:
    """Resolve provider list from catalog path or fallback runtime config."""
    from mini_agent.model_manager.model_registry_service import ModelRegistryService

    resolved_path = _resolve_catalog_path(catalog_path)
    service = ModelRegistryService(catalog_path=resolved_path)
    providers = [provider for provider in service.runtime_provider_catalog().providers if provider.enabled]
    if supported_api_types is not None:
        providers = [
            provider
            for provider in providers
            if provider.api_type in supported_api_types
        ]
    if not providers:
        return ProviderCatalogResolution(
            source="config_fallback",
            catalog_path=str(service.catalog_path),
            providers=[_build_config_fallback_provider(config)],
        )
    return ProviderCatalogResolution(
        source="provider_catalog",
        catalog_path=str(service.catalog_path),
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
            context_window=_provider_model_context_window(
                route.provider,
                route.mapping.selected_model,
            ),
            learned_token_limit=_provider_model_learned_token_limit(
                route.provider,
                route.mapping.selected_model,
            ),
            token_limit=_effective_provider_model_token_limit(
                route.provider,
                route.mapping.selected_model,
            ),
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


def resolve_pinned_llm_candidate(
    config: Any,
    *,
    provider_source: str,
    provider_id: str,
    model_id: str | None = None,
    catalog_path: str | Path | None = None,
) -> RoutedLLMSettings:
    """Resolve one exact provider/model route for session-scoped selection."""
    from mini_agent.model_manager.model_registry_service import ModelRegistryService

    requested_provider_id = _normalize_text(provider_id)
    requested_source = _normalize_text(provider_source).lower()
    if requested_source not in {"custom", "preset"}:
        raise ValueError(f"unsupported provider source: {provider_source}")
    if not requested_provider_id:
        raise ValueError("provider_id must not be empty")

    requested_model = _normalize_text(model_id or str(config.llm.model))
    if not requested_model:
        raise ValueError("model_id must not be empty")

    resolved_path = _resolve_catalog_path(catalog_path)
    service = ModelRegistryService(catalog_path=resolved_path)
    runtime_provider_id = _runtime_catalog_provider_id(
        source=requested_source,
        provider_id=requested_provider_id,
    )
    provider = next(
        (
            item
            for item in service.runtime_provider_catalog().providers
            if item.enabled and item.id == runtime_provider_id
        ),
        None,
    )
    if provider is None:
        raise ValueError(f"provider not configured: {requested_provider_id}")

    runtime_provider = _to_runtime_provider(provider.api_type)
    if runtime_provider is None:
        raise ValueError(
            f"provider '{requested_provider_id}' is not supported in terminal runtime"
        )
    if requested_model not in provider.models:
        raise ValueError(
            f"model '{requested_model}' is not available in provider '{requested_provider_id}'"
        )

    decision = get_circuit_breaker_registry().should_allow(provider.id)
    return RoutedLLMSettings(
        source="provider_catalog",
        provider=runtime_provider,
        api_key=provider.api_key,
        api_base=provider.api_base,
        model=requested_model,
        provider_id=provider.id,
        provider_name=provider.name,
        mapping_mode="exact",
        requested_model=requested_model,
        catalog_path=str(service.catalog_path),
        breaker_state=decision.state.value,
        breaker_allowed=decision.allowed,
        context_window=_provider_model_context_window(provider, requested_model),
        learned_token_limit=_provider_model_learned_token_limit(provider, requested_model),
        token_limit=_effective_provider_model_token_limit(provider, requested_model),
    )


def resolve_session_model_selection_identity(
    config: Any,
    *,
    provider_id: str,
    model_id: str | None = None,
    provider_source: str | None = None,
    catalog_path: str | Path | None = None,
) -> tuple[str, str, str]:
    """Resolve one session-scoped model-selection identity, inferring source when unique."""

    requested_provider_id = _normalize_text(provider_id)
    if not requested_provider_id:
        raise ValueError("provider_id must not be empty")

    requested_model = _normalize_text(model_id or str(config.llm.model))
    if not requested_model:
        raise ValueError("model_id must not be empty")

    requested_source = _normalize_text(provider_source).lower()
    if requested_source:
        resolve_pinned_llm_candidate(
            config,
            provider_source=requested_source,
            provider_id=requested_provider_id,
            model_id=requested_model,
            catalog_path=catalog_path,
        )
        return requested_source, requested_provider_id, requested_model

    from mini_agent.model_manager.model_registry_service import ModelRegistryService

    service = ModelRegistryService(catalog_path=_resolve_catalog_path(catalog_path))
    provider_rows = [
        item
        for item in service.list_registry()
        if bool(item.get("enabled", True))
        and _normalize_text(str(item.get("provider_id") or "")) == requested_provider_id
    ]
    if not provider_rows:
        raise ValueError(f"provider not configured: {requested_provider_id}")

    matched_sources: set[str] = set()
    for item in provider_rows:
        source = _normalize_text(str(item.get("source") or "")).lower()
        if source not in {"custom", "preset"}:
            continue
        models = item.get("models")
        if not isinstance(models, list):
            continue
        for model in models:
            if not isinstance(model, dict):
                continue
            current_model_id = _normalize_text(str(model.get("model_id") or ""))
            if current_model_id == requested_model:
                matched_sources.add(source)
                break

    if not matched_sources:
        raise ValueError(
            f"model '{requested_model}' is not available in provider '{requested_provider_id}'"
        )
    if len(matched_sources) > 1:
        raise ValueError(
            f"provider '{requested_provider_id}' with model '{requested_model}' is ambiguous across sources; specify provider_source"
        )

    resolved_source = next(iter(matched_sources))
    resolve_pinned_llm_candidate(
        config,
        provider_source=resolved_source,
        provider_id=requested_provider_id,
        model_id=requested_model,
        catalog_path=catalog_path,
    )
    return resolved_source, requested_provider_id, requested_model


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
