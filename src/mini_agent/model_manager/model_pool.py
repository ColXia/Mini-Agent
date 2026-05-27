"""Model pool service for v11.2.

This module provides the ModelPool service that manages the global model
supply. The model pool only serves Agent, not Workspace or Session.

Key responsibilities:
- Provider registry
- Model catalog
- Capability facts
- Health/breaker/failover
- Adapter factory
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from mini_agent.model_manager.model_pool_contracts import (
    CapabilityTruth,
    ModelCapabilityProfile,
    ModelDescriptor,
    ModelKind,
    ProviderEntry,
    ProviderSource,
    ProtocolFamily,
)
from mini_agent.model_manager.preset_providers import PresetProvider, get_preset_provider_config
from mini_agent.utils.text import safe_text


def _safe_text(value: Any) -> str:
    return safe_text(value)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True, slots=True)
class ProviderHealthSnapshot:
    """Health status for a provider."""

    provider_id: str
    is_healthy: bool
    last_check: datetime | None = None
    error_message: str | None = None
    latency_ms: int | None = None


@dataclass(frozen=True, slots=True)
class BreakerStatus:
    """Circuit breaker status for a provider."""

    provider_id: str
    is_open: bool
    failure_count: int = 0
    last_failure: datetime | None = None
    reset_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class ModelPoolSnapshot:
    """Snapshot of the model pool at a point in time.

    This is used by AgentModelService to select models.
    """

    snapshot_id: str
    available_providers: tuple[ProviderEntry, ...]
    available_models: tuple[ModelDescriptor, ...]
    health_status: tuple[ProviderHealthSnapshot, ...] = ()
    breaker_status: tuple[BreakerStatus, ...] = ()
    failover_candidates: dict[str, tuple[str, ...]] = field(default_factory=dict)
    snapshot_timestamp: datetime | None = None

    def __post_init__(self) -> None:
        if self.snapshot_timestamp is None:
            object.__setattr__(self, "snapshot_timestamp", _utc_now())

    @property
    def provider_count(self) -> int:
        """Return the number of available providers."""
        return len(self.available_providers)

    @property
    def model_count(self) -> int:
        """Return the number of available models."""
        return len(self.available_models)

    @property
    def healthy_provider_ids(self) -> list[str]:
        """Return the list of healthy provider IDs."""
        healthy = {s.provider_id for s in self.health_status if s.is_healthy}
        return [p.provider_id for p in self.available_providers if p.provider_id in healthy]

    def get_provider(self, provider_id: str) -> ProviderEntry | None:
        """Get a provider by ID."""
        normalized = _safe_text(provider_id)
        for provider in self.available_providers:
            if provider.provider_id == normalized:
                return provider
        return None

    def get_model(self, model_id: str, provider_id: str | None = None) -> ModelDescriptor | None:
        """Get a model by ID, optionally filtered by provider."""
        normalized_model = _safe_text(model_id)
        for model in self.available_models:
            if model.model_id == normalized_model:
                if provider_id is None or model.provider_id == _safe_text(provider_id):
                    return model
        return None

    def list_models_by_provider(self, provider_id: str) -> list[ModelDescriptor]:
        """List all models for a provider."""
        normalized = _safe_text(provider_id)
        return [m for m in self.available_models if m.provider_id == normalized]

    def list_models_with_tools(self) -> list[ModelDescriptor]:
        """List all models that support tools."""
        return [m for m in self.available_models if m.is_tools_capable]

    def list_models_with_thinking(self) -> list[ModelDescriptor]:
        """List all models that support thinking."""
        return [m for m in self.available_models if m.is_thinking_capable]


@dataclass(slots=True)
class ModelPool:
    """Global model pool service.

    This pool manages the static model supply and does not participate
    in agent binding decisions. It only provides:
    - What providers are available
    - What models are available
    - What capabilities each model has
    - Health and breaker status
    """

    _providers: dict[str, ProviderEntry] = field(default_factory=dict)
    _models: dict[str, ModelDescriptor] = field(default_factory=dict)
    _health_status: dict[str, ProviderHealthSnapshot] = field(default_factory=dict)
    _breaker_status: dict[str, BreakerStatus] = field(default_factory=dict)
    _failover_map: dict[str, tuple[str, ...]] = field(default_factory=dict)

    def register_provider(self, entry: ProviderEntry) -> ProviderEntry:
        """Register a provider entry."""
        self._providers[entry.provider_id] = entry
        return entry

    def unregister_provider(self, provider_id: str) -> ProviderEntry | None:
        """Unregister a provider."""
        provider = self._providers.pop(_safe_text(provider_id), None)
        if provider is not None:
            # Remove associated models
            model_ids_to_remove = [
                mid for mid, m in self._models.items()
                if m.provider_id == provider_id
            ]
            for mid in model_ids_to_remove:
                self._models.pop(mid, None)
            # Remove health/breaker status
            self._health_status.pop(provider_id, None)
            self._breaker_status.pop(provider_id, None)
        return provider

    def register_model(self, descriptor: ModelDescriptor) -> ModelDescriptor:
        """Register a model descriptor."""
        self._models[descriptor.full_id] = descriptor
        return descriptor

    def unregister_model(self, model_id: str, provider_id: str) -> ModelDescriptor | None:
        """Unregister a model."""
        full_id = f"{_safe_text(provider_id)}.{_safe_text(model_id)}"
        return self._models.pop(full_id, None)

    def get_provider(self, provider_id: str) -> ProviderEntry | None:
        """Get a provider by ID."""
        return self._providers.get(_safe_text(provider_id))

    def get_model(self, model_id: str, provider_id: str | None = None) -> ModelDescriptor | None:
        """Get a model by ID."""
        if provider_id is not None:
            full_id = f"{_safe_text(provider_id)}.{_safe_text(model_id)}"
            return self._models.get(full_id)
        # Search by model_id only
        normalized = _safe_text(model_id)
        for model in self._models.values():
            if model.model_id == normalized:
                return model
        return None

    def list_providers(self, enabled_only: bool = True) -> list[ProviderEntry]:
        """List all providers."""
        providers = list(self._providers.values())
        if enabled_only:
            providers = [p for p in providers if p.enabled]
        return sorted(providers, key=lambda p: (-p.priority, p.provider_id))

    def list_models(self, provider_id: str | None = None) -> list[ModelDescriptor]:
        """List all models, optionally filtered by provider."""
        models = list(self._models.values())
        if provider_id is not None:
            normalized = _safe_text(provider_id)
            models = [m for m in models if m.provider_id == normalized]
        return models

    def list_models_with_tools(self) -> list[ModelDescriptor]:
        """List all models that support tools."""
        return [m for m in self._models.values() if m.is_tools_capable]

    def list_models_with_thinking(self) -> list[ModelDescriptor]:
        """List all models that support thinking."""
        return [m for m in self._models.values() if m.is_thinking_capable]

    def update_health_status(self, status: ProviderHealthSnapshot) -> None:
        """Update health status for a provider."""
        self._health_status[status.provider_id] = status

    def update_breaker_status(self, status: BreakerStatus) -> None:
        """Update circuit breaker status for a provider."""
        self._breaker_status[status.provider_id] = status

    def get_health_status(self, provider_id: str) -> ProviderHealthSnapshot | None:
        """Get health status for a provider."""
        return self._health_status.get(_safe_text(provider_id))

    def get_breaker_status(self, provider_id: str) -> BreakerStatus | None:
        """Get circuit breaker status for a provider."""
        return self._breaker_status.get(_safe_text(provider_id))

    def set_failover_candidates(self, provider_id: str, candidates: tuple[str, ...]) -> None:
        """Set failover candidates for a provider."""
        self._failover_map[_safe_text(provider_id)] = candidates

    def get_failover_candidates(self, provider_id: str) -> tuple[str, ...]:
        """Get failover candidates for a provider."""
        return self._failover_map.get(_safe_text(provider_id), ())

    def get_capability_profile(self, model_id: str, provider_id: str | None = None) -> ModelCapabilityProfile | None:
        """Get the capability profile for a model."""
        model = self.get_model(model_id, provider_id)
        if model is None:
            return None
        return ModelCapabilityProfile.from_descriptor(model)

    def create_snapshot(self) -> ModelPoolSnapshot:
        """Create a snapshot of the current pool state."""
        import uuid
        snapshot_id = uuid.uuid4().hex[:16]

        return ModelPoolSnapshot(
            snapshot_id=snapshot_id,
            available_providers=tuple(self.list_providers(enabled_only=True)),
            available_models=tuple(self._models.values()),
            health_status=tuple(self._health_status.values()),
            breaker_status=tuple(self._breaker_status.values()),
            failover_candidates=dict(self._failover_map),
        )

    def clear(self) -> None:
        """Clear all providers and models."""
        self._providers.clear()
        self._models.clear()
        self._health_status.clear()
        self._breaker_status.clear()
        self._failover_map.clear()

    def __len__(self) -> int:
        """Return the number of registered models."""
        return len(self._models)


def build_model_pool_from_preset(
    preset_providers: list[PresetProvider] | None = None,
) -> ModelPool:
    """Build a model pool from preset providers.

    Args:
        preset_providers: List of preset providers to include.
                         If None, uses all available presets.

    Returns:
        A ModelPool populated with preset providers and models.
    """
    pool = ModelPool()

    if preset_providers is None:
        preset_providers = list(PresetProvider)

    for preset in preset_providers:
        try:
            config = get_preset_provider_config(
                preset,
                use_latest_model=False,
                allow_unreachable_local=True,
                discover_inventory=False,
            )
            if not config:
                continue

            provider_id = preset.value
            api_type = str(config.get("api_type", "openai")).lower()

            entry = ProviderEntry(
                provider_id=provider_id,
                provider_source=ProviderSource.PRESET,
                protocol_family=ProtocolFamily.OPENAI if api_type == "openai" else ProtocolFamily.ANTHROPIC,
                api_base=str(config.get("api_base", "")),
                provider_name=str(config.get("provider_name", provider_id)),
                enabled=True,
                priority=int(config.get("priority", 0)),
            )
            pool.register_provider(entry)

            # Register models from config
            models = config.get("models", [])
            default_model = config.get("default_model")
            if default_model and default_model not in models:
                models = [default_model] + models

            for model_id in models:
                model_metadata = config.get("model_metadata", {}).get(model_id, {})
                descriptor = ModelDescriptor(
                    provider_id=provider_id,
                    model_id=model_id,
                    display_name=config.get("model_display_names", {}).get(model_id, model_id),
                    model_kind=ModelKind.CHAT,
                    context_window=config.get("model_context_windows", {}).get(model_id),
                    learned_token_limit=config.get("model_learned_token_limits", {}).get(model_id),
                    supports_tools=model_metadata.get("supports_tools"),
                    supports_tools_truth=CapabilityTruth(model_metadata.get("supports_tools_truth", "unknown"))
                    if model_metadata.get("supports_tools_truth") else CapabilityTruth.UNKNOWN,
                    supports_thinking=model_metadata.get("supports_thinking"),
                    supports_thinking_truth=CapabilityTruth(model_metadata.get("supports_thinking_truth", "unknown"))
                    if model_metadata.get("supports_thinking_truth") else CapabilityTruth.UNKNOWN,
                )
                pool.register_model(descriptor)

        except Exception:
            continue

    return pool


_SHARED_POOL: ModelPool | None = None


def shared_model_pool() -> ModelPool:
    """Return the process-local shared model pool."""
    global _SHARED_POOL
    if _SHARED_POOL is None:
        _SHARED_POOL = build_model_pool_from_preset()
    return _SHARED_POOL


def clear_shared_model_pool() -> None:
    """Clear the process-local shared model pool."""
    global _SHARED_POOL
    if _SHARED_POOL is not None:
        _SHARED_POOL.clear()
    _SHARED_POOL = None


__all__ = [
    "BreakerStatus",
    "build_model_pool_from_preset",
    "clear_shared_model_pool",
    "ProviderHealthSnapshot",
    "ModelPool",
    "ModelPoolSnapshot",
    "shared_model_pool",
]
