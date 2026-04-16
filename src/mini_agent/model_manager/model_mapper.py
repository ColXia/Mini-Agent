"""Provider model mapping and route selection baseline."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from typing import Literal

from mini_agent.model_manager.provider import ProviderAPIType, ProviderCatalog, ProviderConfig


MappingMode = Literal["exact", "partial", "fallback_default"]
RouteIntent = Literal["automatic", "explicit"]
CapabilityTruth = Literal["supported", "unsupported", "unknown"]


def _normalize_text(value: str) -> str:
    return " ".join(value.strip().split())


@dataclass(frozen=True)
class ModelMappingResult:
    """Model mapping result for one provider."""

    requested_model: str | None
    selected_model: str
    mode: MappingMode


@dataclass(frozen=True)
class ProviderRoute:
    """Selected provider route with model mapping metadata."""

    provider: ProviderConfig
    mapping: ModelMappingResult


@dataclass(frozen=True)
class RouteRequirementProfile:
    """Minimal capability-aware route requirements."""

    require_tools: bool = False
    prefer_thinking: bool = False
    min_context_window: int | None = None

    def normalized(self) -> "RouteRequirementProfile":
        minimum = self.min_context_window
        if minimum is not None:
            minimum = max(1, int(minimum))
        return RouteRequirementProfile(
            require_tools=bool(self.require_tools),
            prefer_thinking=bool(self.prefer_thinking),
            min_context_window=minimum,
        )


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


def _provider_model_metadata_value(
    provider: ProviderConfig,
    model_id: str,
    key: str,
) -> Any:
    raw = provider.model_metadata.get(model_id)
    if not isinstance(raw, dict):
        return None
    return raw.get(key)


def _normalize_capability_truth(value: Any) -> CapabilityTruth | None:
    if isinstance(value, str):
        normalized = " ".join(value.strip().split()).lower()
        if normalized in {"supported", "unsupported", "unknown"}:
            return normalized
    return None


def _capability_truth_from_bool(value: bool | None) -> CapabilityTruth | None:
    if value is True:
        return "supported"
    if value is False:
        return "unsupported"
    return None


def _provider_model_capability_truth(
    provider: ProviderConfig,
    model_id: str,
    key: str,
) -> CapabilityTruth:
    explicit = _capability_truth_from_bool(_normalize_bool(_provider_model_metadata_value(provider, model_id, key)))
    if explicit is not None:
        return explicit
    inferred = _normalize_capability_truth(
        _provider_model_metadata_value(provider, model_id, f"{key}_truth")
    )
    return inferred or "unknown"


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


def _provider_model_context_window(provider: ProviderConfig, model_id: str) -> int | None:
    for source in (
        provider.model_learned_token_limits,
        provider.model_context_windows,
    ):
        try:
            value = int(source.get(model_id, 0))
        except Exception:
            continue
        if value > 0:
            return value
    return None


def _route_is_compatible(
    provider: ProviderConfig,
    mapping: ModelMappingResult,
    requirements: RouteRequirementProfile | None,
) -> bool:
    if requirements is None:
        return True

    selected_model = mapping.selected_model
    if requirements.require_tools and _provider_model_capability_truth(
        provider,
        selected_model,
        "supports_tools",
    ) == "unsupported":
        return False

    minimum_context = requirements.min_context_window
    if minimum_context is not None:
        model_context = _provider_model_context_window(provider, selected_model)
        if model_context is not None and model_context < minimum_context:
            return False

    return True


def _required_tools_preference_score(
    provider: ProviderConfig,
    model_id: str,
    requirements: RouteRequirementProfile | None,
) -> int:
    if requirements is None or not requirements.require_tools:
        return 0
    return 1 if _provider_model_capability_truth(provider, model_id, "supports_tools") == "supported" else 0


def _thinking_preference_score(
    provider: ProviderConfig,
    model_id: str,
    requirements: RouteRequirementProfile | None,
) -> int:
    if requirements is None or not requirements.prefer_thinking:
        return 0
    truth = _provider_model_capability_truth(provider, model_id, "supports_thinking")
    if truth == "supported":
        return 2
    if truth == "unknown":
        return 1
    return 0


def _normalize_route_intent(route_intent: RouteIntent | None) -> RouteIntent:
    return "explicit" if route_intent == "explicit" else "automatic"


def map_model_for_provider(
    provider: ProviderConfig,
    requested_model: str | None,
    *,
    route_intent: RouteIntent = "automatic",
) -> ModelMappingResult | None:
    """Map requested model name onto one provider's model list."""
    if requested_model is None or not requested_model.strip():
        return ModelMappingResult(
            requested_model=requested_model,
            selected_model=provider.default_model,
            mode="fallback_default",
        )

    normalized_requested = _normalize_text(requested_model)
    requested_lower = normalized_requested.lower()
    exact_lookup = {model.lower(): model for model in provider.models}
    if requested_lower in exact_lookup:
        return ModelMappingResult(
            requested_model=normalized_requested,
            selected_model=exact_lookup[requested_lower],
            mode="exact",
        )

    # Fuzzy partial matching for practical alias requests.
    partial_candidates: list[tuple[int, int, str]] = []
    for index, model in enumerate(provider.models):
        lowered = model.lower()
        if requested_lower in lowered or lowered in requested_lower:
            partial_candidates.append((len(model), index, model))
    if partial_candidates:
        partial_candidates.sort(key=lambda item: (item[0], item[1], item[2]))
        return ModelMappingResult(
            requested_model=normalized_requested,
            selected_model=partial_candidates[0][2],
            mode="partial",
        )

    if _normalize_route_intent(route_intent) == "explicit":
        return None

    return ModelMappingResult(
        requested_model=normalized_requested,
        selected_model=provider.default_model,
        mode="fallback_default",
    )


class ProviderRouteSelector:
    """Choose provider route for one request using mapping quality + priority."""

    def __init__(self, catalog: ProviderCatalog):
        self.catalog = catalog.normalized()

    def rank(
        self,
        *,
        requested_model: str | None = None,
        route_intent: RouteIntent = "automatic",
        preferred_api_type: ProviderAPIType | None = None,
        supported_api_types: set[ProviderAPIType] | None = None,
        requirements: RouteRequirementProfile | None = None,
    ) -> list[ProviderRoute]:
        normalized_requirements = requirements.normalized() if requirements is not None else None
        normalized_route_intent = _normalize_route_intent(route_intent)
        supported = (
            set(supported_api_types)
            if supported_api_types is not None
            else {
                ProviderAPIType.OPENAI,
                ProviderAPIType.ANTHROPIC,
            }
        )
        enabled = [
            provider
            for provider in self.catalog.providers
            if provider.enabled and provider.api_type in supported
        ]
        if preferred_api_type is not None:
            preferred = [provider for provider in enabled if provider.api_type == preferred_api_type]
            if preferred:
                enabled = preferred

        if not enabled:
            raise ValueError("No enabled providers available for routing.")

        rank = {"exact": 3, "partial": 2, "fallback_default": 1}
        routed: list[tuple[int, int, int, ProviderRoute]] = []
        for index, provider in enumerate(enabled):
            mapping = map_model_for_provider(
                provider,
                requested_model,
                route_intent=normalized_route_intent,
            )
            if mapping is None:
                continue
            if not _route_is_compatible(provider, mapping, normalized_requirements):
                continue
            tools_support_score = _required_tools_preference_score(
                provider,
                mapping.selected_model,
                normalized_requirements,
            )
            thinking_score = _thinking_preference_score(
                provider,
                mapping.selected_model,
                normalized_requirements,
            )
            routed.append(
                (
                    rank[mapping.mode],
                    tools_support_score,
                    thinking_score,
                    int(provider.priority),
                    -index,
                    ProviderRoute(provider=provider, mapping=mapping),
                )
            )

        routed.sort(key=lambda item: (item[0], item[1], item[2], item[3]), reverse=True)
        if not routed:
            normalized_requested_model = (
                _normalize_text(requested_model)
                if requested_model is not None and requested_model.strip()
                else ""
            )
            if normalized_requested_model and normalized_route_intent == "explicit":
                raise ValueError(
                    f"explicit requested model '{normalized_requested_model}' did not match any enabled provider route"
                )
            raise ValueError("No enabled providers satisfy the route requirements.")
        return [item[5] for item in routed]

    def select(
        self,
        *,
        requested_model: str | None = None,
        route_intent: RouteIntent = "automatic",
        preferred_api_type: ProviderAPIType | None = None,
        supported_api_types: set[ProviderAPIType] | None = None,
        requirements: RouteRequirementProfile | None = None,
    ) -> ProviderRoute:
        ranked = self.rank(
            requested_model=requested_model,
            route_intent=route_intent,
            preferred_api_type=preferred_api_type,
            supported_api_types=supported_api_types,
            requirements=requirements,
        )
        return ranked[0]
