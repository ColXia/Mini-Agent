"""Tests for provider model mapping and route selection baseline."""

from __future__ import annotations

from mini_agent.model_manager import (
    ProviderAPIType,
    ProviderCatalog,
    ProviderConfig,
    ProviderRouteSelector,
    map_model_for_provider,
)


def _provider(
    *,
    provider_id: str,
    name: str,
    api_type: str,
    base: str,
    key: str,
    models: list[str],
    enabled: bool = True,
    priority: int = 0,
) -> ProviderConfig:
    return ProviderConfig(
        id=provider_id,
        name=name,
        api_type=api_type,
        api_base=base,
        api_key=key,
        models=models,
        enabled=enabled,
        priority=priority,
    )


def test_map_model_for_provider_exact_partial_and_fallback():
    provider = _provider(
        provider_id="p1",
        name="P1",
        api_type="openai",
        base="https://p1.example.com/v1",
        key="sk-p1",
        models=["gpt-4o", "gpt-4o-mini"],
    )

    exact = map_model_for_provider(provider, "GPT-4O")
    assert exact.mode == "exact"
    assert exact.selected_model == "gpt-4o"

    partial = map_model_for_provider(provider, "4o-mini")
    assert partial.mode == "partial"
    assert partial.selected_model == "gpt-4o-mini"

    fallback = map_model_for_provider(provider, "unknown-model")
    assert fallback.mode == "fallback_default"
    assert fallback.selected_model == "gpt-4o"


def test_provider_route_selector_prefers_mapping_quality_then_priority():
    catalog = ProviderCatalog(
        providers=[
            _provider(
                provider_id="high-priority",
                name="High Priority Anthropic",
                api_type="anthropic",
                base="https://anth.example.com",
                key="sk-a",
                models=["claude-3-5-sonnet"],
                priority=100,
            ),
            _provider(
                provider_id="lower-priority",
                name="Lower Priority OpenAI",
                api_type="openai",
                base="https://openai.example.com/v1",
                key="sk-o",
                models=["gpt-4o-mini"],
                priority=1,
            ),
        ]
    )
    selector = ProviderRouteSelector(catalog)

    route = selector.select(requested_model="gpt-4o", preferred_api_type=None)
    assert route.provider.id == "lower-priority"
    assert route.mapping.mode in {"partial", "exact"}


def test_provider_route_selector_prefers_api_type_when_available():
    catalog = ProviderCatalog(
        providers=[
            _provider(
                provider_id="a",
                name="Anth",
                api_type="anthropic",
                base="https://anth.example.com",
                key="sk-a",
                models=["claude-3-5-sonnet"],
                priority=2,
            ),
            _provider(
                provider_id="o",
                name="Open",
                api_type="openai",
                base="https://open.example.com/v1",
                key="sk-o",
                models=["gpt-4o"],
                priority=9,
            ),
        ]
    )
    selector = ProviderRouteSelector(catalog)

    route = selector.select(
        requested_model="claude",
        preferred_api_type=ProviderAPIType.ANTHROPIC,
    )
    assert route.provider.api_type.value == "anthropic"
