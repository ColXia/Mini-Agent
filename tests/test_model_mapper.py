"""Tests for provider model mapping and route selection baseline."""

from __future__ import annotations

from mini_agent.model_manager import (
    ProviderAPIType,
    ProviderCatalog,
    ProviderConfig,
    ProviderRouteSelector,
    RouteRequirementProfile,
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


def test_map_model_for_provider_skips_fallback_for_explicit_request():
    provider = _provider(
        provider_id="p1",
        name="P1",
        api_type="openai",
        base="https://p1.example.com/v1",
        key="sk-p1",
        models=["gpt-4o", "gpt-4o-mini"],
    )

    explicit_miss = map_model_for_provider(
        provider,
        "unknown-model",
        route_intent="explicit",
    )

    assert explicit_miss is None


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


def test_provider_route_selector_filters_non_tool_models_and_prefers_thinking():
    catalog = ProviderCatalog(
        providers=[
            ProviderConfig(
                id="no-tools",
                name="No Tools",
                api_type="openai",
                api_base="https://no-tools.example.com/v1",
                api_key="sk-no-tools",
                models=["gpt-4o-mini"],
                model_metadata={
                    "gpt-4o-mini": {
                        "supports_tools": False,
                        "supports_thinking": False,
                    }
                },
                priority=9,
            ),
            ProviderConfig(
                id="thinking-tools",
                name="Thinking Tools",
                api_type="openai",
                api_base="https://thinking-tools.example.com/v1",
                api_key="sk-thinking-tools",
                models=["gpt-5.4"],
                model_metadata={
                    "gpt-5.4": {
                        "supports_tools": True,
                        "supports_thinking": True,
                    }
                },
                priority=4,
            ),
            ProviderConfig(
                id="tools-only",
                name="Tools Only",
                api_type="openai",
                api_base="https://tools-only.example.com/v1",
                api_key="sk-tools-only",
                models=["gpt-4.1"],
                model_metadata={
                    "gpt-4.1": {
                        "supports_tools": True,
                        "supports_thinking": False,
                    }
                },
                priority=8,
            ),
        ]
    )
    selector = ProviderRouteSelector(catalog)

    ranked = selector.rank(
        requested_model=None,
        requirements=RouteRequirementProfile(
            require_tools=True,
            prefer_thinking=True,
        ),
    )

    assert [route.provider.id for route in ranked] == ["thinking-tools", "tools-only"]
    assert ranked[0].provider.id == "thinking-tools"


def test_provider_route_selector_prefers_confirmed_tool_support_over_unknown_when_tools_required():
    catalog = ProviderCatalog(
        providers=[
            ProviderConfig(
                id="unknown-tools",
                name="Unknown Tools",
                api_type="openai",
                api_base="https://unknown-tools.example.com/v1",
                api_key="sk-unknown-tools",
                models=["gpt-4.1"],
                priority=9,
            ),
            ProviderConfig(
                id="confirmed-tools",
                name="Confirmed Tools",
                api_type="openai",
                api_base="https://confirmed-tools.example.com/v1",
                api_key="sk-confirmed-tools",
                models=["gpt-4o-mini"],
                model_metadata={
                    "gpt-4o-mini": {
                        "supports_tools": True,
                        "supports_thinking": False,
                    }
                },
                priority=1,
            ),
        ]
    )
    selector = ProviderRouteSelector(catalog)

    ranked = selector.rank(
        requested_model=None,
        requirements=RouteRequirementProfile(require_tools=True),
    )

    assert [route.provider.id for route in ranked] == ["confirmed-tools", "unknown-tools"]


def test_provider_route_selector_prefers_unknown_thinking_over_known_unsupported_when_only_preferred():
    catalog = ProviderCatalog(
        providers=[
            ProviderConfig(
                id="unsupported-thinking",
                name="Unsupported Thinking",
                api_type="openai",
                api_base="https://unsupported-thinking.example.com/v1",
                api_key="sk-unsupported-thinking",
                models=["gpt-4.1"],
                model_metadata={
                    "gpt-4.1": {
                        "supports_tools": True,
                        "supports_thinking": False,
                    }
                },
                priority=9,
            ),
            ProviderConfig(
                id="unknown-thinking",
                name="Unknown Thinking",
                api_type="openai",
                api_base="https://unknown-thinking.example.com/v1",
                api_key="sk-unknown-thinking",
                models=["gpt-4o-mini"],
                model_metadata={
                    "gpt-4o-mini": {
                        "supports_tools": True,
                        "supports_thinking_truth": "unknown",
                    }
                },
                priority=1,
            ),
        ]
    )
    selector = ProviderRouteSelector(catalog)

    ranked = selector.rank(
        requested_model=None,
        requirements=RouteRequirementProfile(prefer_thinking=True),
    )

    assert [route.provider.id for route in ranked] == ["unknown-thinking", "unsupported-thinking"]


def test_provider_route_selector_filters_known_undersized_context_window():
    catalog = ProviderCatalog(
        providers=[
            ProviderConfig(
                id="small",
                name="Small",
                api_type="anthropic",
                api_base="https://small.example.com",
                api_key="sk-small",
                models=["claude-small"],
                model_context_windows={"claude-small": 32_000},
                priority=9,
            ),
            ProviderConfig(
                id="large",
                name="Large",
                api_type="anthropic",
                api_base="https://large.example.com",
                api_key="sk-large",
                models=["claude-large"],
                model_context_windows={"claude-large": 200_000},
                priority=1,
            ),
        ]
    )
    selector = ProviderRouteSelector(catalog)

    ranked = selector.rank(
        requested_model=None,
        requirements=RouteRequirementProfile(min_context_window=128_000),
    )

    assert [route.provider.id for route in ranked] == ["large"]


def test_provider_route_selector_raises_for_explicit_miss():
    catalog = ProviderCatalog(
        providers=[
            _provider(
                provider_id="p1",
                name="P1",
                api_type="openai",
                base="https://p1.example.com/v1",
                key="sk-p1",
                models=["gpt-4o", "gpt-4o-mini"],
            ),
        ]
    )
    selector = ProviderRouteSelector(catalog)

    try:
        selector.rank(
            requested_model="unknown-model",
            route_intent="explicit",
        )
    except ValueError as exc:
        assert "explicit requested model 'unknown-model'" in str(exc)
    else:  # pragma: no cover - defensive
        raise AssertionError("Expected explicit routing miss to raise ValueError")
