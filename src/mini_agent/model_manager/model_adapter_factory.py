"""Model adapter factory for v11.2.

This module provides the ModelAdapterFactory that converts AgentModelBinding
to a unified ModelAdapter. Core never directly touches OpenAI/Anthropic/Ollama
clients - it only consumes the unified adapter.

Key responsibilities:
- Find provider configuration
- Resolve secrets
- Construct client
- Adapt protocol
- Output unified ModelAdapter
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from mini_agent.model_manager.model_pool_contracts import (
    AgentModelBinding,
    ModelCapabilityProfile,
    ProviderSource,
)
from mini_agent.model_manager.model_pool import ModelPool, shared_model_pool
from mini_agent.model_manager.preset_providers import get_preset_provider_config, PresetProvider
from mini_agent.model_manager.provider import ProviderConfig
from mini_agent.utils.text import safe_text


def _safe_text(value: Any) -> str:
    return safe_text(value)


@dataclass(frozen=True, slots=True)
class ModelAdapterConfig:
    """Configuration for constructing a model adapter.

    This contains all the information needed to create a model client,
    without exposing provider-specific details to the Core.
    """

    provider_id: str
    model_id: str
    api_type: str
    api_base: str
    api_key: str
    headers: dict[str, str] = field(default_factory=dict)
    timeout: int = 60
    capability_profile: ModelCapabilityProfile | None = None

    @property
    def is_openai_family(self) -> bool:
        """Return True if this is an OpenAI-compatible provider."""
        return self.api_type.lower() == "openai"

    @property
    def is_anthropic_family(self) -> bool:
        """Return True if this is an Anthropic-compatible provider."""
        return self.api_type.lower() == "anthropic"


@dataclass(slots=True)
class ModelAdapterFactory:
    """Factory for creating model adapters from bindings.

    This factory takes an AgentModelBinding and produces a ModelAdapterConfig
    that can be used to construct a model client. It resolves secrets and
    provider configurations internally.
    """

    model_pool: ModelPool | None = None
    _secret_resolver: Callable[[str], str | None] | None = None

    def set_secret_resolver(self, resolver: Callable[[str], str | None]) -> None:
        """Set a custom secret resolver.

        The resolver takes a secret reference and returns the actual secret value.
        """
        self._secret_resolver = resolver

    def create_adapter_config(self, binding: AgentModelBinding) -> ModelAdapterConfig:
        """Create a ModelAdapterConfig from an AgentModelBinding.

        Args:
            binding: The agent model binding

        Returns:
            A ModelAdapterConfig ready for client construction

        Raises:
            ValueError: If the provider or model cannot be resolved
        """
        pool = self.model_pool or shared_model_pool()

        # Get provider configuration
        provider_config = self._resolve_provider_config(binding)
        if provider_config is None:
            raise ValueError(f"Provider not found: {binding.provider_id}")

        # Get capability profile
        capability_profile = pool.get_capability_profile(
            binding.model_id,
            binding.provider_id,
        )

        return ModelAdapterConfig(
            provider_id=binding.provider_id,
            model_id=binding.model_id,
            api_type=provider_config.get("api_type", "openai"),
            api_base=provider_config.get("api_base", ""),
            api_key=provider_config.get("api_key", ""),
            headers=provider_config.get("headers", {}),
            timeout=provider_config.get("timeout", 60),
            capability_profile=capability_profile,
        )

    def create_adapter_config_from_identity(
        self,
        provider_source: str,
        provider_id: str,
        model_id: str,
    ) -> ModelAdapterConfig:
        """Create a ModelAdapterConfig from provider/model identity.

        This is a convenience method for creating adapter configs without
        a full binding object.

        Args:
            provider_source: The provider source (preset/custom)
            provider_id: The provider ID
            model_id: The model ID

        Returns:
            A ModelAdapterConfig ready for client construction
        """
        from mini_agent.model_manager.model_pool_contracts import ProviderSource

        source = ProviderSource.PRESET if provider_source.lower() == "preset" else ProviderSource.CUSTOM
        binding = AgentModelBinding(
            agent_id="temp",
            provider_id=provider_id,
            model_id=model_id,
            provider_source=source,
        )
        return self.create_adapter_config(binding)

    def _resolve_provider_config(self, binding: AgentModelBinding) -> dict[str, Any] | None:
        """Resolve provider configuration from binding."""
        if binding.provider_source == ProviderSource.PRESET:
            return self._resolve_preset_provider(binding.provider_id)
        else:
            return self._resolve_custom_provider(binding.provider_id)

    def _resolve_preset_provider(self, provider_id: str) -> dict[str, Any] | None:
        """Resolve a preset provider configuration."""
        try:
            preset = PresetProvider(provider_id)
        except ValueError:
            return None

        config = get_preset_provider_config(
            preset,
            use_latest_model=False,
            allow_unreachable_local=True,
            discover_inventory=False,
        )
        if not config:
            return None

        return {
            "api_type": str(config.get("api_type", "openai")),
            "api_base": str(config.get("api_base", "")),
            "api_key": str(config.get("api_key", "")),
            "headers": dict(config.get("headers", {})),
            "timeout": int(config.get("timeout", 60)),
        }

    def _resolve_custom_provider(self, provider_id: str) -> dict[str, Any] | None:
        """Resolve a custom provider configuration."""
        pool = self.model_pool or shared_model_pool()
        provider = pool.get_provider(provider_id)
        if provider is None:
            return None

        # For custom providers, we need to get the actual config
        # This would typically come from a catalog file
        # For now, return a basic config from the provider entry
        return {
            "api_type": provider.protocol_family.value,
            "api_base": provider.api_base,
            "api_key": "",  # Custom providers need secret resolution
            "headers": dict(provider.headers),
            "timeout": provider.timeout,
        }


_SHARED_FACTORY: ModelAdapterFactory | None = None


def shared_model_adapter_factory() -> ModelAdapterFactory:
    """Return the process-local shared model adapter factory."""
    global _SHARED_FACTORY
    if _SHARED_FACTORY is None:
        _SHARED_FACTORY = ModelAdapterFactory()
    return _SHARED_FACTORY


def clear_shared_model_adapter_factory() -> None:
    """Clear the process-local shared model adapter factory."""
    global _SHARED_FACTORY
    _SHARED_FACTORY = None


__all__ = [
    "clear_shared_model_adapter_factory",
    "ModelAdapterConfig",
    "ModelAdapterFactory",
    "shared_model_adapter_factory",
]
