"""Runtime helpers for provider-catalog based routing and monitoring."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, replace
import os
from pathlib import Path
from typing import Any

from mini_agent.model_manager.model_mapper import ProviderRouteSelector
from mini_agent.model_manager.model_mapper import RouteIntent
from mini_agent.model_manager.model_mapper import RouteRequirementProfile
from mini_agent.model_manager.bootstrap import BootstrapLLMSettings
from mini_agent.model_manager.circuit_breaker import (
    CircuitBreakerRegistry,
)
from mini_agent.model_manager.health_monitor import ProviderHealthMonitor
from mini_agent.model_manager.provider import (
    ModelRole,
    ProviderAPIType,
    ProviderCatalog,
    ProviderConfig,
)
from mini_agent.schema.schema import LLMProvider


def _normalize_text(value: str | None) -> str:
    if value is None:
        return ""
    return " ".join(value.strip().split())


def _normalize_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = " ".join(value.strip().split()).lower()
        if normalized in {"true", "1", "yes", "on"}:
            return True
        if normalized in {"false", "0", "no", "off"}:
            return False
        return None
    if isinstance(value, int):
        return bool(value)
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


def _provider_model_metadata(provider: ProviderConfig, model_id: str) -> dict[str, Any]:
    raw = provider.model_metadata.get(model_id)
    return raw if isinstance(raw, dict) else {}


def _provider_model_role(provider: ProviderConfig, model_id: str) -> str | None:
    value = _provider_model_metadata(provider, model_id).get("model_role")
    if isinstance(value, str):
        normalized = " ".join(value.strip().split()).lower()
        if normalized in {role.value for role in ModelRole}:
            return normalized
    return None


def _normalize_capability_truth(value: Any) -> str | None:
    if isinstance(value, str):
        normalized = " ".join(value.strip().split()).lower()
        if normalized in {"supported", "unsupported", "unknown"}:
            return normalized
    return None


def _capability_truth_from_bool(value: bool | None) -> str | None:
    if value is True:
        return "supported"
    if value is False:
        return "unsupported"
    return None


def _provider_model_capability_truth(provider: ProviderConfig, model_id: str, key: str) -> str:
    explicit = _capability_truth_from_bool(
        _normalize_bool(_provider_model_metadata(provider, model_id).get(key))
    )
    if explicit is not None:
        return explicit
    inferred = _normalize_capability_truth(
        _provider_model_metadata(provider, model_id).get(f"{key}_truth")
    )
    return inferred or "unknown"


def _provider_model_capability_confidence(provider: ProviderConfig, model_id: str, key: str) -> str | None:
    value = _provider_model_metadata(provider, model_id).get(f"{key}_confidence")
    if isinstance(value, str):
        normalized = " ".join(value.strip().split()).lower()
        return normalized or None
    return None


def _provider_model_supports_tools(provider: ProviderConfig, model_id: str) -> bool | None:
    truth = _provider_model_capability_truth(provider, model_id, "supports_tools")
    if truth == "supported":
        return True
    if truth == "unsupported":
        return False
    return None


def _provider_model_supports_thinking(provider: ProviderConfig, model_id: str) -> bool | None:
    truth = _provider_model_capability_truth(provider, model_id, "supports_thinking")
    if truth == "supported":
        return True
    if truth == "unsupported":
        return False
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

    source: str  # provider_catalog | bootstrap_provider_catalog
    provider: LLMProvider
    api_key: str
    api_base: str
    model: str
    provider_id: str | None = None
    provider_name: str | None = None
    provider_source: str | None = None
    mapping_mode: str | None = None
    requested_model: str | None = None
    catalog_path: str | None = None
    breaker_state: str | None = None
    breaker_allowed: bool | None = None
    priority: int | None = None
    timeout: int | None = None
    headers: dict[str, str] | None = None
    context_window: int | None = None
    learned_token_limit: int | None = None
    token_limit: int | None = None
    model_role: str | None = None
    supports_tools: bool | None = None
    supports_thinking: bool | None = None
    supports_tools_truth: str | None = None
    supports_tools_confidence: str | None = None
    supports_tools_source: str | None = None
    supports_thinking_truth: str | None = None
    supports_thinking_confidence: str | None = None
    supports_thinking_source: str | None = None
    route_diagnostics: dict[str, Any] | None = None


@dataclass(frozen=True)
class ProviderCatalogResolution:
    """Resolved provider catalog source for runtime inspection APIs."""

    source: str  # provider_catalog | bootstrap_provider_catalog
    catalog_path: str | None
    providers: list[ProviderConfig]


_CIRCUIT_BREAKERS = CircuitBreakerRegistry()
_HEALTH_MONITOR = ProviderHealthMonitor()
_MODEL_ROUTE_RESOLUTION_COUNT = 0
_LATEST_MODEL_ROUTE_SNAPSHOT: dict[str, Any] | None = None


def _provider_model_capability_source(provider: ProviderConfig, model_id: str, key: str) -> str | None:
    value = _provider_model_metadata(provider, model_id).get(f"{key}_source")
    if isinstance(value, str):
        normalized = " ".join(value.strip().split()).lower()
        return normalized or None
    return None


def _provider_source_from_runtime_id(provider_id: str | None, *, catalog_source: str | None = None) -> str | None:
    normalized_provider_id = _normalize_text(provider_id)
    if normalized_provider_id == "bootstrap-config":
        return "bootstrap"
    if _normalize_text(catalog_source).lower() == "bootstrap_provider_catalog":
        return "bootstrap"
    if normalized_provider_id.startswith("preset-"):
        return "preset"
    return "custom" if normalized_provider_id else None


def _route_requirements_payload(
    requirements: RouteRequirementProfile | None,
) -> dict[str, Any]:
    normalized = requirements.normalized() if requirements is not None else None
    return {
        "require_tools": bool(getattr(normalized, "require_tools", False)),
        "prefer_thinking": bool(getattr(normalized, "prefer_thinking", False)),
        "min_context_window": (
            int(getattr(normalized, "min_context_window", 0) or 0)
            if getattr(normalized, "min_context_window", None) is not None
            else None
        ),
    }


def _candidate_diagnostics_from_settings(
    candidate: RoutedLLMSettings,
    *,
    selected: bool = False,
) -> dict[str, Any]:
    return {
        "selected": bool(selected),
        "provider": str(getattr(candidate.provider, "value", candidate.provider) or ""),
        "provider_source": candidate.provider_source,
        "provider_id": candidate.provider_id,
        "provider_name": candidate.provider_name,
        "model": candidate.model,
        "mapping_mode": candidate.mapping_mode,
        "priority": candidate.priority,
        "timeout": candidate.timeout,
        "breaker_state": candidate.breaker_state,
        "breaker_allowed": candidate.breaker_allowed,
        "context_window": candidate.context_window,
        "learned_token_limit": candidate.learned_token_limit,
        "token_limit": candidate.token_limit,
        "model_role": candidate.model_role,
        "supports_tools": candidate.supports_tools,
        "supports_tools_truth": candidate.supports_tools_truth,
        "supports_tools_confidence": candidate.supports_tools_confidence,
        "supports_tools_source": candidate.supports_tools_source,
        "supports_thinking": candidate.supports_thinking,
        "supports_thinking_truth": candidate.supports_thinking_truth,
        "supports_thinking_confidence": candidate.supports_thinking_confidence,
        "supports_thinking_source": candidate.supports_thinking_source,
    }


def _bootstrap_diagnostics_payload(
    bootstrap_llm: BootstrapLLMSettings | None,
) -> dict[str, Any]:
    if bootstrap_llm is None:
        return {
            "bootstrap_selected_provider": None,
            "bootstrap_selection_reason": None,
            "bootstrap_selection_policy": None,
            "bootstrap_preferred_provider": None,
            "bootstrap_preferred_provider_available": None,
            "bootstrap_alternatives": [],
        }
    return {
        "bootstrap_selected_provider": bootstrap_llm.bootstrap_selected_provider,
        "bootstrap_selection_reason": bootstrap_llm.bootstrap_selection_reason,
        "bootstrap_selection_policy": bootstrap_llm.bootstrap_selection_policy,
        "bootstrap_preferred_provider": bootstrap_llm.bootstrap_preferred_provider,
        "bootstrap_preferred_provider_available": (
            bootstrap_llm.bootstrap_preferred_provider_available
        ),
        "bootstrap_alternatives": [
            dict(item) for item in bootstrap_llm.bootstrap_alternatives
        ],
    }


def _selected_reason_for_candidate(
    candidate: RoutedLLMSettings | None,
    *,
    resolution_kind: str,
) -> str | None:
    if candidate is None:
        return None
    if resolution_kind == "pinned":
        return "pinned_provider_model"
    if candidate.mapping_mode == "exact":
        return "exact_model_match"
    if candidate.mapping_mode == "partial":
        return "partial_model_match"
    if candidate.mapping_mode == "fallback_default":
        return "automatic_provider_default"
    return "ranked_candidate"


def _fallback_reason_for_candidate(
    candidate: RoutedLLMSettings | None,
    *,
    requested_model: str | None,
    blocked_before_selected: int,
    allowed_candidate_count: int,
    blocked_candidate_count: int,
) -> str | None:
    if candidate is None:
        return None
    if allowed_candidate_count == 0 and blocked_candidate_count > 0:
        return "all_ranked_candidates_blocked_by_circuit_breaker"
    if blocked_before_selected > 0:
        return "higher_ranked_candidates_blocked_by_circuit_breaker"
    if requested_model and candidate.mapping_mode == "fallback_default":
        return "requested_model_unmatched_used_provider_default"
    return None


def _record_model_route_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    global _MODEL_ROUTE_RESOLUTION_COUNT  # noqa: PLW0603
    global _LATEST_MODEL_ROUTE_SNAPSHOT  # noqa: PLW0603

    normalized_snapshot = deepcopy(snapshot)
    _MODEL_ROUTE_RESOLUTION_COUNT += 1
    _LATEST_MODEL_ROUTE_SNAPSHOT = normalized_snapshot
    return deepcopy(normalized_snapshot)


def get_model_route_diagnostics_snapshot() -> dict[str, Any] | None:
    if _LATEST_MODEL_ROUTE_SNAPSHOT is None:
        return None
    return deepcopy(_LATEST_MODEL_ROUTE_SNAPSHOT)


def get_model_route_diagnostics_state() -> dict[str, Any]:
    return {
        "resolution_count": int(_MODEL_ROUTE_RESOLUTION_COUNT),
        "latest_snapshot": get_model_route_diagnostics_snapshot(),
    }


def get_circuit_breaker_registry() -> CircuitBreakerRegistry:
    return _CIRCUIT_BREAKERS


def get_health_monitor() -> ProviderHealthMonitor:
    return _HEALTH_MONITOR


def reset_model_manager_runtime_state() -> None:
    global _CIRCUIT_BREAKERS  # noqa: PLW0603
    global _MODEL_ROUTE_RESOLUTION_COUNT  # noqa: PLW0603
    global _LATEST_MODEL_ROUTE_SNAPSHOT  # noqa: PLW0603
    _CIRCUIT_BREAKERS = CircuitBreakerRegistry()
    _HEALTH_MONITOR.reset()
    _MODEL_ROUTE_RESOLUTION_COUNT = 0
    _LATEST_MODEL_ROUTE_SNAPSHOT = None


def record_provider_success(provider_id: str) -> None:
    _HEALTH_MONITOR.record_success(provider_id)
    _CIRCUIT_BREAKERS.record_success(provider_id)


def record_provider_failure(provider_id: str, *, reason: str | None = None) -> None:
    _HEALTH_MONITOR.record_failure(provider_id, reason=reason)
    _CIRCUIT_BREAKERS.record_failure(provider_id, reason=reason)


def _compose_model_route_snapshot(
    *,
    resolution_kind: str,
    catalog_source: str | None,
    catalog_path: str | None,
    route_intent: str | None,
    requested_model: str | None,
    requested_provider_source: str | None = None,
    requested_provider_id: str | None = None,
    selected: RoutedLLMSettings | None = None,
    candidates: list[RoutedLLMSettings] | None = None,
    route_requirements: RouteRequirementProfile | None = None,
    bootstrap_llm: BootstrapLLMSettings | None = None,
    error: str | None = None,
) -> dict[str, Any]:
    ranked_candidates = list(candidates or [])
    selected_index = (
        next(
            (index for index, item in enumerate(ranked_candidates) if item is selected),
            None,
        )
        if selected is not None
        else None
    )
    blocked_before_selected = 0
    if selected_index is not None:
        blocked_before_selected = sum(
            1
            for item in ranked_candidates[:selected_index]
            if item.breaker_allowed is False
        )
    allowed_candidate_count = sum(1 for item in ranked_candidates if item.breaker_allowed is not False)
    blocked_candidate_count = sum(1 for item in ranked_candidates if item.breaker_allowed is False)
    snapshot = {
        "resolution_kind": _normalize_text(resolution_kind).lower() or None,
        "catalog_source": _normalize_text(catalog_source).lower() or None,
        "catalog_path": _normalize_text(catalog_path),
        "route_intent": _normalize_text(route_intent).lower() or None,
        "requested_model": _normalize_text(requested_model) or None,
        "requested_provider_source": _normalize_text(requested_provider_source).lower() or None,
        "requested_provider_id": _normalize_text(requested_provider_id) or None,
        "selected_provider": (
            str(getattr(selected.provider, "value", selected.provider) or "")
            if selected is not None
            else None
        ),
        "selected_provider_source": (
            selected.provider_source
            if selected is not None
            else None
        ),
        "selected_provider_id": selected.provider_id if selected is not None else None,
        "selected_provider_name": selected.provider_name if selected is not None else None,
        "selected_model": selected.model if selected is not None else None,
        "mapping_mode": selected.mapping_mode if selected is not None else None,
        "selected_reason": _selected_reason_for_candidate(
            selected,
            resolution_kind=resolution_kind,
        ),
        "fallback_reason": _fallback_reason_for_candidate(
            selected,
            requested_model=requested_model,
            blocked_before_selected=blocked_before_selected,
            allowed_candidate_count=allowed_candidate_count,
            blocked_candidate_count=blocked_candidate_count,
        ),
        "candidate_count": len(ranked_candidates),
        "allowed_candidate_count": allowed_candidate_count,
        "blocked_candidate_count": blocked_candidate_count,
        "selected_context_window": selected.context_window if selected is not None else None,
        "selected_learned_token_limit": (
            selected.learned_token_limit if selected is not None else None
        ),
        "selected_token_limit": selected.token_limit if selected is not None else None,
        "selected_supports_tools": selected.supports_tools if selected is not None else None,
        "selected_supports_tools_truth": (
            selected.supports_tools_truth if selected is not None else None
        ),
        "selected_supports_tools_confidence": (
            selected.supports_tools_confidence if selected is not None else None
        ),
        "selected_supports_tools_source": (
            selected.supports_tools_source if selected is not None else None
        ),
        "selected_supports_thinking": (
            selected.supports_thinking if selected is not None else None
        ),
        "selected_supports_thinking_truth": (
            selected.supports_thinking_truth if selected is not None else None
        ),
        "selected_supports_thinking_confidence": (
            selected.supports_thinking_confidence if selected is not None else None
        ),
        "selected_supports_thinking_source": (
            selected.supports_thinking_source if selected is not None else None
        ),
        "error": _normalize_text(error) or None,
        "candidates": [
            _candidate_diagnostics_from_settings(
                item,
                selected=(item is selected),
            )
            for item in ranked_candidates
        ],
    }
    snapshot.update(_route_requirements_payload(route_requirements))
    snapshot.update(_bootstrap_diagnostics_payload(bootstrap_llm))
    return snapshot


def _with_route_diagnostics(
    candidates: list[RoutedLLMSettings],
    *,
    snapshot: dict[str, Any] | None,
) -> list[RoutedLLMSettings]:
    if not candidates or not isinstance(snapshot, dict):
        return list(candidates)
    return [
        replace(candidate, route_diagnostics=deepcopy(snapshot))
        for candidate in candidates
    ]


def resolve_provider_catalog(
    *,
    bootstrap_llm: BootstrapLLMSettings | None = None,
    catalog_path: str | Path | None = None,
    supported_api_types: set[ProviderAPIType] | None = None,
) -> ProviderCatalogResolution:
    """Resolve runtime providers from the registry, synthesizing bootstrap only when empty."""
    from mini_agent.model_manager.model_registry_service import ModelRegistryService

    resolved_path = _resolve_catalog_path(catalog_path)
    service = ModelRegistryService(catalog_path=resolved_path)
    providers = [
        provider
        for provider in service.runtime_provider_catalog(bootstrap_llm=bootstrap_llm).providers
        if provider.enabled
    ]
    if supported_api_types is not None:
        providers = [
            provider
            for provider in providers
            if provider.api_type in supported_api_types
        ]
    source = "provider_catalog"
    if len(providers) == 1 and providers[0].id == "bootstrap-config":
        source = "bootstrap_provider_catalog"
    return ProviderCatalogResolution(
        source=source,
        catalog_path=str(service.catalog_path),
        providers=providers,
    )


def resolve_routed_llm_candidates(
    *,
    bootstrap_llm: BootstrapLLMSettings | None = None,
    requested_model: str | None = None,
    catalog_path: str | Path | None = None,
    route_requirements: RouteRequirementProfile | None = None,
    route_intent: RouteIntent = "automatic",
) -> list[RoutedLLMSettings]:
    """Resolve an ordered provider candidate chain for failover."""
    catalog: ProviderCatalogResolution | None = None
    normalized_requested_model = _normalize_text(requested_model) or None
    try:
        catalog = resolve_provider_catalog(
            bootstrap_llm=bootstrap_llm,
            catalog_path=catalog_path,
            supported_api_types={ProviderAPIType.ANTHROPIC, ProviderAPIType.OPENAI},
        )
        selector = ProviderRouteSelector(ProviderCatalog(providers=catalog.providers))
        ranked_routes = selector.rank(
            requested_model=normalized_requested_model,
            route_intent=route_intent,
            preferred_api_type=None,
            supported_api_types={ProviderAPIType.ANTHROPIC, ProviderAPIType.OPENAI},
            requirements=route_requirements,
        )

        breakers = get_circuit_breaker_registry()
        ranked_candidates: list[RoutedLLMSettings] = []
        allowed_candidates: list[RoutedLLMSettings] = []
        blocked_candidates: list[RoutedLLMSettings] = []
        for route in ranked_routes:
            runtime_provider = _to_runtime_provider(route.provider.api_type)
            if runtime_provider is None:
                continue
            decision = breakers.should_allow(str(route.provider.id))
            candidate = RoutedLLMSettings(
                source=catalog.source,
                provider=runtime_provider,
                api_key=route.provider.api_key,
                api_base=route.provider.api_base,
                model=route.mapping.selected_model,
                provider_id=route.provider.id,
                provider_name=route.provider.name,
                provider_source=_provider_source_from_runtime_id(
                    route.provider.id,
                    catalog_source=catalog.source,
                ),
                mapping_mode=route.mapping.mode,
                requested_model=route.mapping.requested_model,
                catalog_path=catalog.catalog_path,
                breaker_state=decision.state.value,
                breaker_allowed=decision.allowed,
                priority=int(route.provider.priority),
                timeout=int(route.provider.timeout),
                headers=dict(route.provider.headers),
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
                model_role=_provider_model_role(
                    route.provider,
                    route.mapping.selected_model,
                ),
                supports_tools=_provider_model_supports_tools(
                    route.provider,
                    route.mapping.selected_model,
                ),
                supports_thinking=_provider_model_supports_thinking(
                    route.provider,
                    route.mapping.selected_model,
                ),
                supports_tools_truth=_provider_model_capability_truth(
                    route.provider,
                    route.mapping.selected_model,
                    "supports_tools",
                ),
                supports_tools_confidence=_provider_model_capability_confidence(
                    route.provider,
                    route.mapping.selected_model,
                    "supports_tools",
                ),
                supports_tools_source=_provider_model_capability_source(
                    route.provider,
                    route.mapping.selected_model,
                    "supports_tools",
                ),
                supports_thinking_truth=_provider_model_capability_truth(
                    route.provider,
                    route.mapping.selected_model,
                    "supports_thinking",
                ),
                supports_thinking_confidence=_provider_model_capability_confidence(
                    route.provider,
                    route.mapping.selected_model,
                    "supports_thinking",
                ),
                supports_thinking_source=_provider_model_capability_source(
                    route.provider,
                    route.mapping.selected_model,
                    "supports_thinking",
                ),
            )
            ranked_candidates.append(candidate)
            if decision.allowed:
                allowed_candidates.append(candidate)
            else:
                blocked_candidates.append(candidate)

        selected = allowed_candidates[0] if allowed_candidates else (
            blocked_candidates[0] if blocked_candidates else None
        )
        snapshot = _record_model_route_snapshot(
            _compose_model_route_snapshot(
                resolution_kind="routed",
                catalog_source=catalog.source,
                catalog_path=catalog.catalog_path,
                route_intent=route_intent,
                requested_model=normalized_requested_model,
                selected=selected,
                candidates=ranked_candidates,
                route_requirements=route_requirements,
                bootstrap_llm=bootstrap_llm,
            )
        )
        allowed_candidates = _with_route_diagnostics(
            allowed_candidates,
            snapshot=snapshot,
        )
        blocked_candidates = _with_route_diagnostics(
            blocked_candidates,
            snapshot=snapshot,
        )
        if allowed_candidates:
            return allowed_candidates
        if blocked_candidates:
            return blocked_candidates
        raise ValueError("No supported provider routes available for runtime.")
    except Exception as exc:
        _record_model_route_snapshot(
            _compose_model_route_snapshot(
                resolution_kind="routed",
                catalog_source=getattr(catalog, "source", None),
                catalog_path=getattr(catalog, "catalog_path", None),
                route_intent=route_intent,
                requested_model=normalized_requested_model,
                route_requirements=route_requirements,
                bootstrap_llm=bootstrap_llm,
                error=str(exc),
            )
        )
        raise


def resolve_pinned_llm_candidate(
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
    requested_model = _normalize_text(model_id) or None
    catalog = _resolve_catalog_path(catalog_path)
    try:
        if requested_source not in {"custom", "preset"}:
            raise ValueError(f"unsupported provider source: {provider_source}")
        if not requested_provider_id:
            raise ValueError("provider_id must not be empty")

        service = ModelRegistryService(catalog_path=catalog)
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
        requested_model = requested_model or provider.default_model

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
        candidate = RoutedLLMSettings(
            source="provider_catalog",
            provider=runtime_provider,
            api_key=provider.api_key,
            api_base=provider.api_base,
            model=requested_model,
            provider_id=provider.id,
            provider_name=provider.name,
            provider_source=requested_source,
            mapping_mode="exact",
            requested_model=requested_model,
            catalog_path=str(service.catalog_path),
            breaker_state=decision.state.value,
            breaker_allowed=decision.allowed,
            priority=int(provider.priority),
            timeout=int(provider.timeout),
            headers=dict(provider.headers),
            context_window=_provider_model_context_window(provider, requested_model),
            learned_token_limit=_provider_model_learned_token_limit(provider, requested_model),
            token_limit=_effective_provider_model_token_limit(provider, requested_model),
            model_role=_provider_model_role(provider, requested_model),
            supports_tools=_provider_model_supports_tools(provider, requested_model),
            supports_thinking=_provider_model_supports_thinking(provider, requested_model),
            supports_tools_truth=_provider_model_capability_truth(
                provider,
                requested_model,
                "supports_tools",
            ),
            supports_tools_confidence=_provider_model_capability_confidence(
                provider,
                requested_model,
                "supports_tools",
            ),
            supports_tools_source=_provider_model_capability_source(
                provider,
                requested_model,
                "supports_tools",
            ),
            supports_thinking_truth=_provider_model_capability_truth(
                provider,
                requested_model,
                "supports_thinking",
            ),
            supports_thinking_confidence=_provider_model_capability_confidence(
                provider,
                requested_model,
                "supports_thinking",
            ),
            supports_thinking_source=_provider_model_capability_source(
                provider,
                requested_model,
                "supports_thinking",
            ),
        )
        snapshot = _record_model_route_snapshot(
            _compose_model_route_snapshot(
                resolution_kind="pinned",
                catalog_source="provider_catalog",
                catalog_path=str(service.catalog_path),
                route_intent="explicit",
                requested_model=requested_model,
                requested_provider_source=requested_source,
                requested_provider_id=requested_provider_id,
                selected=candidate,
                candidates=[candidate],
            )
        )
        return replace(candidate, route_diagnostics=deepcopy(snapshot))
    except Exception as exc:
        _record_model_route_snapshot(
            _compose_model_route_snapshot(
                resolution_kind="pinned",
                catalog_source="provider_catalog",
                catalog_path=str(catalog) if catalog is not None else None,
                route_intent="explicit",
                requested_model=requested_model,
                requested_provider_source=requested_source,
                requested_provider_id=requested_provider_id,
                error=str(exc),
            )
        )
        raise


def resolve_session_model_selection_identity(
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

    requested_source = _normalize_text(provider_source).lower()
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

    if requested_source:
        matched_provider = next(
            (
                item
                for item in provider_rows
                if _normalize_text(str(item.get("source") or "")).lower() == requested_source
            ),
            None,
        )
        if matched_provider is None:
            raise ValueError(f"provider not configured: {requested_provider_id}")
        requested_model = _normalize_text(model_id) or _normalize_text(
            matched_provider.get("default_model_id")
        )
        if not requested_model:
            raise ValueError("model_id must not be empty")
        resolve_pinned_llm_candidate(
            provider_source=requested_source,
            provider_id=requested_provider_id,
            model_id=requested_model,
            catalog_path=catalog_path,
        )
        return requested_source, requested_provider_id, requested_model

    requested_model = _normalize_text(model_id)
    if not requested_model:
        matched_sources = {
            _normalize_text(str(item.get("source") or "")).lower()
            for item in provider_rows
            if _normalize_text(str(item.get("source") or "")).lower() in {"custom", "preset"}
        }
        if len(matched_sources) > 1:
            raise ValueError(
                f"provider '{requested_provider_id}' is ambiguous across sources; specify provider_source"
            )
        resolved_source = next(iter(matched_sources))
        matched_provider = next(
            item
            for item in provider_rows
            if _normalize_text(str(item.get("source") or "")).lower() == resolved_source
        )
        requested_model = _normalize_text(matched_provider.get("default_model_id"))
        if not requested_model:
            raise ValueError("model_id must not be empty")
        resolve_pinned_llm_candidate(
            provider_source=resolved_source,
            provider_id=requested_provider_id,
            model_id=requested_model,
            catalog_path=catalog_path,
        )
        return resolved_source, requested_provider_id, requested_model

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
        provider_source=resolved_source,
        provider_id=requested_provider_id,
        model_id=requested_model,
        catalog_path=catalog_path,
    )
    return resolved_source, requested_provider_id, requested_model


def resolve_routed_llm_settings(
    *,
    bootstrap_llm: BootstrapLLMSettings | None = None,
    requested_model: str | None = None,
    catalog_path: str | Path | None = None,
    route_requirements: RouteRequirementProfile | None = None,
    route_intent: RouteIntent = "automatic",
) -> RoutedLLMSettings:
    """Resolve routed provider settings with bootstrap-only fallback."""
    candidates = resolve_routed_llm_candidates(
        bootstrap_llm=bootstrap_llm,
        requested_model=requested_model,
        catalog_path=catalog_path,
        route_requirements=route_requirements,
        route_intent=route_intent,
    )
    selected = candidates[0]
    if selected.provider_id:
        _HEALTH_MONITOR.record_route(
            str(selected.provider_id),
            mapping_mode=selected.mapping_mode,
        )
    return selected
