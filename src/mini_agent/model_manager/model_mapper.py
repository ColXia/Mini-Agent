"""Provider model mapping and route selection baseline."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from mini_agent.model_manager.provider import ProviderAPIType, ProviderCatalog, ProviderConfig


MappingMode = Literal["exact", "partial", "fallback_default"]


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


def map_model_for_provider(provider: ProviderConfig, requested_model: str | None) -> ModelMappingResult:
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
        preferred_api_type: ProviderAPIType | None = None,
        supported_api_types: set[ProviderAPIType] | None = None,
    ) -> list[ProviderRoute]:
        supported = (
            set(supported_api_types)
            if supported_api_types is not None
            else {
                ProviderAPIType.OPENAI,
                ProviderAPIType.ANTHROPIC,
                ProviderAPIType.GEMINI,
                ProviderAPIType.CUSTOM,
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
            mapping = map_model_for_provider(provider, requested_model)
            routed.append(
                (
                    rank[mapping.mode],
                    int(provider.priority),
                    -index,
                    ProviderRoute(provider=provider, mapping=mapping),
                )
            )

        routed.sort(key=lambda item: (item[0], item[1], item[2]), reverse=True)
        return [item[3] for item in routed]

    def select(
        self,
        *,
        requested_model: str | None = None,
        preferred_api_type: ProviderAPIType | None = None,
        supported_api_types: set[ProviderAPIType] | None = None,
    ) -> ProviderRoute:
        ranked = self.rank(
            requested_model=requested_model,
            preferred_api_type=preferred_api_type,
            supported_api_types=supported_api_types,
        )
        return ranked[0]
