"""Model-manager configuration primitives."""

from mini_agent.model_manager.provider import (
    ProviderAPIType,
    ProviderCatalog,
    ProviderConfig,
    normalize_provider_catalog,
    normalize_provider_config,
)
from mini_agent.model_manager.bootstrap import (
    BootstrapLLMSettings,
    bootstrap_llm_settings_from_config,
)
from mini_agent.model_manager.model_mapper import (
    ModelMappingResult,
    ProviderRoute,
    ProviderRouteSelector,
    RouteIntent,
    RouteRequirementProfile,
    map_model_for_provider,
)
from mini_agent.model_manager.circuit_breaker import (
    CircuitBreakerConfig,
    CircuitBreakerDecision,
    CircuitBreakerRegistry,
    CircuitBreakerState,
    ProviderCircuitBreaker,
)
from mini_agent.model_manager.health_monitor import ProviderHealthMonitor
from mini_agent.model_manager.error_classifier import (
    ProviderErrorClassification,
    classify_provider_error,
)
from mini_agent.model_manager.failover import (
    FailoverAttempt,
    FailoverLLMClient,
    ProviderFailoverError,
)
from mini_agent.model_manager.rectifier import (
    RequestRectifierOptions,
    anthropic_messages_to_openai,
    openai_messages_to_anthropic,
    reset_rectifier_metrics,
    rectify_anthropic_request,
    rectify_openai_request,
    snapshot_rectifier_metrics,
)
from mini_agent.model_manager.runtime import (
    ProviderCatalogResolution,
    RoutedLLMSettings,
    get_circuit_breaker_registry,
    get_health_monitor,
    record_provider_failure,
    record_provider_success,
    reset_model_manager_runtime_state,
    resolve_routed_llm_candidates,
    resolve_provider_catalog,
    resolve_pinned_llm_candidate,
    resolve_routed_llm_settings,
)
from mini_agent.model_manager.agent_model_binding import (
    AgentModelBindingRecord,
    AgentModelBindingStore,
)
from mini_agent.model_manager.agent_model_service import AgentModelService
from mini_agent.model_manager.model_registry_service import ModelRegistryService

__all__ = [
    "AgentModelBindingRecord",
    "AgentModelBindingStore",
    "AgentModelService",
    "ProviderAPIType",
    "ProviderConfig",
    "ProviderCatalog",
    "BootstrapLLMSettings",
    "bootstrap_llm_settings_from_config",
    "normalize_provider_config",
    "normalize_provider_catalog",
    "ModelMappingResult",
    "ProviderRoute",
    "ProviderRouteSelector",
    "RouteIntent",
    "RouteRequirementProfile",
    "map_model_for_provider",
    "CircuitBreakerState",
    "CircuitBreakerConfig",
    "CircuitBreakerDecision",
    "ProviderCircuitBreaker",
    "CircuitBreakerRegistry",
    "ProviderHealthMonitor",
    "ProviderErrorClassification",
    "classify_provider_error",
    "FailoverAttempt",
    "ProviderFailoverError",
    "FailoverLLMClient",
    "RequestRectifierOptions",
    "rectify_openai_request",
    "rectify_anthropic_request",
    "openai_messages_to_anthropic",
    "anthropic_messages_to_openai",
    "snapshot_rectifier_metrics",
    "reset_rectifier_metrics",
    "ProviderCatalogResolution",
    "RoutedLLMSettings",
    "resolve_pinned_llm_candidate",
    "resolve_provider_catalog",
    "resolve_routed_llm_candidates",
    "resolve_routed_llm_settings",
    "get_circuit_breaker_registry",
    "get_health_monitor",
    "record_provider_success",
    "record_provider_failure",
    "reset_model_manager_runtime_state",
    "ModelRegistryService",
]
