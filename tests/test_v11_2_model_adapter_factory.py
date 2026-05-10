"""Tests for v11.2 model adapter factory."""

from __future__ import annotations

import pytest

from mini_agent.model_manager.model_pool_contracts import (
    AgentModelBinding,
    ModelCapabilityProfile,
    ProviderSource,
)
from mini_agent.model_manager.model_adapter_factory import (
    ModelAdapterConfig,
    ModelAdapterFactory,
    clear_shared_model_adapter_factory,
    shared_model_adapter_factory,
)


class TestModelAdapterConfig:
    """Tests for ModelAdapterConfig."""

    def test_adapter_config_creation(self) -> None:
        config = ModelAdapterConfig(
            provider_id="openai",
            model_id="gpt-4",
            api_type="openai",
            api_base="https://api.openai.com/v1",
            api_key="test-key",
        )
        assert config.provider_id == "openai"
        assert config.model_id == "gpt-4"
        assert config.is_openai_family is True
        assert config.is_anthropic_family is False

    def test_adapter_config_anthropic_family(self) -> None:
        config = ModelAdapterConfig(
            provider_id="anthropic",
            model_id="claude-3",
            api_type="anthropic",
            api_base="https://api.anthropic.com",
            api_key="test-key",
        )
        assert config.is_anthropic_family is True
        assert config.is_openai_family is False

    def test_adapter_config_with_capability_profile(self) -> None:
        profile = ModelCapabilityProfile(
            model_id="gpt-4",
            provider_id="openai",
            supports_tools=True,
            supports_thinking=False,
            context_window=128000,
            token_limit=100000,
        )
        config = ModelAdapterConfig(
            provider_id="openai",
            model_id="gpt-4",
            api_type="openai",
            api_base="https://api.openai.com/v1",
            api_key="test-key",
            capability_profile=profile,
        )
        assert config.capability_profile is not None
        assert config.capability_profile.supports_tools is True


class TestModelAdapterFactory:
    """Tests for ModelAdapterFactory."""

    def test_factory_creation(self) -> None:
        factory = ModelAdapterFactory()
        assert factory is not None

    def test_factory_create_adapter_config_preset(self) -> None:
        # This test requires preset provider configuration
        # Skip if no preset providers are configured
        factory = ModelAdapterFactory()
        binding = AgentModelBinding(
            agent_id="test-agent",
            provider_id="nonexistent",
            model_id="test-model",
            provider_source=ProviderSource.PRESET,
        )
        with pytest.raises(ValueError, match="Provider not found"):
            factory.create_adapter_config(binding)

    def test_factory_create_adapter_config_from_identity(self) -> None:
        factory = ModelAdapterFactory()
        # This will fail because the provider doesn't exist
        with pytest.raises(ValueError):
            factory.create_adapter_config_from_identity(
                provider_source="preset",
                provider_id="nonexistent",
                model_id="test-model",
            )

    def test_factory_set_secret_resolver(self) -> None:
        factory = ModelAdapterFactory()
        resolver_called = []

        def resolver(ref: str) -> str | None:
            resolver_called.append(ref)
            return f"resolved-{ref}"

        factory.set_secret_resolver(resolver)
        assert factory._secret_resolver is not None
        assert factory._secret_resolver("test-ref") == "resolved-test-ref"
        assert "test-ref" in resolver_called


class TestSharedModelAdapterFactory:
    """Tests for shared model adapter factory."""

    def test_shared_factory_singleton(self) -> None:
        clear_shared_model_adapter_factory()
        factory1 = shared_model_adapter_factory()
        factory2 = shared_model_adapter_factory()
        assert factory1 is factory2

    def test_clear_shared_factory(self) -> None:
        factory1 = shared_model_adapter_factory()
        clear_shared_model_adapter_factory()
        factory2 = shared_model_adapter_factory()
        assert factory1 is not factory2
