"""Tests for v11.2 model pool core contracts."""

from __future__ import annotations

import pytest
from datetime import datetime, timezone, timedelta

from mini_agent.model_manager.model_pool_contracts import (
    AgentModelBinding,
    AgentModelPolicy,
    CapabilityConfidence,
    CapabilitySource,
    CapabilityTruth,
    ModelCapabilityProfile,
    ModelDescriptor,
    ModelKind,
    ProviderEntry,
    ProviderSource,
    ProtocolFamily,
)


class TestProviderEntry:
    """Tests for ProviderEntry contract."""

    def test_provider_entry_creation(self) -> None:
        entry = ProviderEntry(
            provider_id="openai",
            provider_source=ProviderSource.PRESET,
            protocol_family=ProtocolFamily.OPENAI,
            api_base="https://api.openai.com/v1",
            provider_name="OpenAI",
        )
        assert entry.provider_id == "openai"
        assert entry.provider_source == ProviderSource.PRESET
        assert entry.protocol_family == ProtocolFamily.OPENAI
        assert entry.enabled is True
        assert entry.full_id == "preset.openai"

    def test_provider_entry_custom_source(self) -> None:
        entry = ProviderEntry(
            provider_id="my-custom",
            provider_source=ProviderSource.CUSTOM,
            protocol_family=ProtocolFamily.OPENAI,
            api_base="https://my-api.example.com/v1",
            provider_name="My Custom Provider",
            priority=10,
        )
        assert entry.provider_source == ProviderSource.CUSTOM
        assert entry.full_id == "custom.my-custom"
        assert entry.priority == 10

    def test_provider_entry_validation(self) -> None:
        with pytest.raises(ValueError, match="provider_id is required"):
            ProviderEntry(
                provider_id="",
                provider_source=ProviderSource.PRESET,
                protocol_family=ProtocolFamily.OPENAI,
                api_base="https://api.example.com",
                provider_name="Test",
            )


class TestModelDescriptor:
    """Tests for ModelDescriptor contract."""

    def test_model_descriptor_creation(self) -> None:
        descriptor = ModelDescriptor(
            provider_id="openai",
            model_id="gpt-4",
            display_name="GPT-4",
            context_window=128000,
        )
        assert descriptor.provider_id == "openai"
        assert descriptor.model_id == "gpt-4"
        assert descriptor.full_id == "openai.gpt-4"
        assert descriptor.context_window == 128000

    def test_model_descriptor_token_limit(self) -> None:
        descriptor = ModelDescriptor(
            provider_id="openai",
            model_id="gpt-4",
            display_name="GPT-4",
            context_window=128000,
        )
        assert descriptor.token_limit == int(128000 * 0.8)

        descriptor_with_limit = ModelDescriptor(
            provider_id="openai",
            model_id="gpt-4",
            display_name="GPT-4",
            context_window=128000,
            learned_token_limit=100000,
        )
        assert descriptor_with_limit.token_limit == 100000

    def test_model_descriptor_tools_capability(self) -> None:
        supported = ModelDescriptor(
            provider_id="openai",
            model_id="gpt-4",
            display_name="GPT-4",
            supports_tools_truth=CapabilityTruth.SUPPORTED,
        )
        assert supported.is_tools_capable is True

        unsupported = ModelDescriptor(
            provider_id="test",
            model_id="model-no-tools",
            display_name="No Tools",
            supports_tools_truth=CapabilityTruth.UNSUPPORTED,
        )
        assert unsupported.is_tools_capable is False

        unknown = ModelDescriptor(
            provider_id="test",
            model_id="model-unknown",
            display_name="Unknown",
            supports_tools=True,
        )
        assert unknown.is_tools_capable is True

    def test_model_descriptor_thinking_capability(self) -> None:
        supported = ModelDescriptor(
            provider_id="anthropic",
            model_id="claude-3",
            display_name="Claude 3",
            supports_thinking_truth=CapabilityTruth.SUPPORTED,
        )
        assert supported.is_thinking_capable is True

        unsupported = ModelDescriptor(
            provider_id="test",
            model_id="model-no-thinking",
            display_name="No Thinking",
            supports_thinking_truth=CapabilityTruth.UNSUPPORTED,
        )
        assert unsupported.is_thinking_capable is False

    def test_model_descriptor_validation(self) -> None:
        with pytest.raises(ValueError, match="provider_id is required"):
            ModelDescriptor(
                provider_id="",
                model_id="gpt-4",
                display_name="GPT-4",
            )

        with pytest.raises(ValueError, match="model_id is required"):
            ModelDescriptor(
                provider_id="openai",
                model_id="",
                display_name="GPT-4",
            )


class TestModelCapabilityProfile:
    """Tests for ModelCapabilityProfile contract."""

    def test_capability_profile_creation(self) -> None:
        profile = ModelCapabilityProfile(
            model_id="gpt-4",
            provider_id="openai",
            supports_tools=True,
            supports_thinking=False,
            context_window=128000,
            token_limit=100000,
        )
        assert profile.model_id == "gpt-4"
        assert profile.supports_tools is True
        assert profile.supports_thinking is False
        assert profile.is_capable_for_tools is True
        assert profile.is_capable_for_thinking is False

    def test_capability_profile_from_descriptor(self) -> None:
        descriptor = ModelDescriptor(
            provider_id="openai",
            model_id="gpt-4",
            display_name="GPT-4",
            context_window=128000,
            supports_tools_truth=CapabilityTruth.SUPPORTED,
            supports_thinking_truth=CapabilityTruth.UNSUPPORTED,
            supports_tools_confidence=CapabilityConfidence.HIGH,
        )
        profile = ModelCapabilityProfile.from_descriptor(descriptor)
        assert profile.model_id == "gpt-4"
        assert profile.provider_id == "openai"
        assert profile.supports_tools is True
        assert profile.supports_thinking is False
        assert profile.context_window == 128000

    def test_capability_profile_streaming(self) -> None:
        profile = ModelCapabilityProfile(
            model_id="gpt-4",
            provider_id="openai",
            supports_tools=True,
            supports_thinking=False,
            context_window=128000,
            token_limit=100000,
            streaming_support=True,
        )
        assert profile.is_capable_for_streaming is True


class TestAgentModelPolicy:
    """Tests for AgentModelPolicy contract."""

    def test_agent_model_policy_creation(self) -> None:
        policy = AgentModelPolicy(
            agent_id="main-agent",
            default_model_preference="gpt-4",
            local_remote_preference="remote",
        )
        assert policy.agent_id == "main-agent"
        assert policy.default_model_preference == "gpt-4"
        assert policy.fallback_enabled is True

    def test_agent_model_policy_validation(self) -> None:
        with pytest.raises(ValueError, match="agent_id is required"):
            AgentModelPolicy(
                agent_id="",
            )


class TestAgentModelBinding:
    """Tests for AgentModelBinding contract."""

    def test_agent_model_binding_creation(self) -> None:
        profile = ModelCapabilityProfile(
            model_id="gpt-4",
            provider_id="openai",
            supports_tools=True,
            supports_thinking=False,
            context_window=128000,
            token_limit=100000,
        )
        binding = AgentModelBinding(
            agent_id="main-agent",
            provider_id="openai",
            model_id="gpt-4",
            provider_source=ProviderSource.PRESET,
            capability_profile=profile,
        )
        assert binding.agent_id == "main-agent"
        assert binding.provider_id == "openai"
        assert binding.model_id == "gpt-4"
        assert binding.full_model_id == "openai.gpt-4"
        assert binding.is_explicit is True
        assert binding.is_automatic is False
        assert binding.bound_at is not None

    def test_agent_model_binding_automatic(self) -> None:
        binding = AgentModelBinding(
            agent_id="main-agent",
            provider_id="openai",
            model_id="gpt-4",
            provider_source=ProviderSource.PRESET,
            binding_kind="automatic",
        )
        assert binding.is_explicit is False
        assert binding.is_automatic is True

    def test_agent_model_binding_fallback_chain(self) -> None:
        binding = AgentModelBinding(
            agent_id="main-agent",
            provider_id="openai",
            model_id="gpt-4",
            provider_source=ProviderSource.PRESET,
            fallback_chain=("anthropic.claude-3", "openai.gpt-3.5"),
        )
        assert len(binding.fallback_chain) == 2
        assert binding.fallback_chain[0] == "anthropic.claude-3"

    def test_agent_model_binding_validation(self) -> None:
        with pytest.raises(ValueError, match="agent_id is required"):
            AgentModelBinding(
                agent_id="",
                provider_id="openai",
                model_id="gpt-4",
                provider_source=ProviderSource.PRESET,
            )

        with pytest.raises(ValueError, match="provider_id is required"):
            AgentModelBinding(
                agent_id="main-agent",
                provider_id="",
                model_id="gpt-4",
                provider_source=ProviderSource.PRESET,
            )

        with pytest.raises(ValueError, match="model_id is required"):
            AgentModelBinding(
                agent_id="main-agent",
                provider_id="openai",
                model_id="",
                provider_source=ProviderSource.PRESET,
            )
