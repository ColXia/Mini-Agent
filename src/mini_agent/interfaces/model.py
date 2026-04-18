"""Model-focused interface-layer DTOs for API v1."""

from __future__ import annotations

from pydantic import BaseModel, Field

from .system import ModelRouteDiagnostics


class MainAgentModelCandidateSummary(BaseModel):
    """One model candidate entry visible to the agent-side model selector."""

    model_id: str
    display_name: str
    is_default: bool
    is_current_binding: bool = False
    model_role: str | None = None
    context_window: int | None = Field(default=None, ge=1)
    learned_token_limit: int | None = Field(default=None, ge=1)
    token_limit: int | None = Field(default=None, ge=1)
    supports_tools: bool | None = None
    supports_tools_truth: str | None = None
    supports_tools_confidence: str | None = None
    supports_tools_source: str | None = None
    supports_thinking: bool | None = None
    supports_thinking_truth: str | None = None
    supports_thinking_confidence: str | None = None
    supports_thinking_source: str | None = None
    discovered_at: str | None = None
    discovery_source: str | None = None
    discovery_confidence: str | None = None


class MainAgentModelCandidateProviderSummary(BaseModel):
    """One provider bucket of agent-visible model candidates."""

    source: str
    provider_id: str
    provider_name: str
    api_type: str
    api_base: str
    provider_family: str | None = None
    provider_variant: str | None = None
    default_model_id: str | None = None
    default_model_strategy: str | None = None
    default_model_confidence: str | None = None
    models: list[MainAgentModelCandidateSummary] = Field(default_factory=list)
    enabled: bool = True
    priority: int = 0


class MainAgentModelCandidateListResponse(BaseModel):
    """Typed agent-side model candidate listing."""

    items: list[MainAgentModelCandidateProviderSummary] = Field(default_factory=list)


class MainAgentModelBindingRequest(BaseModel):
    """Request body for setting the explicit agent-owned main model binding."""

    agent_id: str | None = None
    provider_source: str | None = Field(default=None, min_length=1)
    provider_id: str = Field(min_length=1)
    model_id: str = Field(min_length=1)


class MainAgentModelBindingRecord(BaseModel):
    """Persisted explicit agent-owned binding record."""

    agent_id: str
    provider_source: str
    provider_id: str
    model_id: str
    binding_kind: str
    bound_at: str | None = None
    switch_generation: int = Field(default=0, ge=0)


class MainAgentModelBindingSummary(BaseModel):
    """Current resolved main model binding for the agent."""

    agent_id: str
    binding_kind: str
    provider: str | None = None
    provider_source: str | None = None
    provider_id: str | None = None
    runtime_provider_id: str | None = None
    provider_name: str | None = None
    model_id: str | None = None
    display_name: str | None = None
    api_base: str | None = None
    mapping_mode: str | None = None
    priority: int | None = None
    context_window: int | None = Field(default=None, ge=1)
    learned_token_limit: int | None = Field(default=None, ge=1)
    token_limit: int | None = Field(default=None, ge=1)
    supports_tools: bool | None = None
    supports_tools_truth: str | None = None
    supports_tools_confidence: str | None = None
    supports_tools_source: str | None = None
    supports_thinking: bool | None = None
    supports_thinking_truth: str | None = None
    supports_thinking_confidence: str | None = None
    supports_thinking_source: str | None = None
    bound_at: str | None = None
    switch_generation: int = Field(default=0, ge=0)


class MainAgentModelCapabilities(BaseModel):
    """Capability-focused view of the current main model binding."""

    agent_id: str | None = None
    binding_kind: str | None = None
    provider_source: str | None = None
    provider_id: str | None = None
    model_id: str | None = None
    context_window: int | None = Field(default=None, ge=1)
    learned_token_limit: int | None = Field(default=None, ge=1)
    token_limit: int | None = Field(default=None, ge=1)
    supports_tools: bool | None = None
    supports_tools_truth: str | None = None
    supports_tools_confidence: str | None = None
    supports_tools_source: str | None = None
    supports_thinking: bool | None = None
    supports_thinking_truth: str | None = None
    supports_thinking_confidence: str | None = None
    supports_thinking_source: str | None = None


class MainAgentModelBindingDiagnostics(BaseModel):
    """Detailed diagnostics around the current main-model binding resolution."""

    agent_id: str | None = None
    current_binding: MainAgentModelBindingSummary
    configured_binding: MainAgentModelBindingRecord | None = None
    configured_binding_error: str | None = None
    latest_route: ModelRouteDiagnostics | None = None


__all__ = [
    "MainAgentModelBindingDiagnostics",
    "MainAgentModelBindingRecord",
    "MainAgentModelBindingRequest",
    "MainAgentModelBindingSummary",
    "MainAgentModelCandidateListResponse",
    "MainAgentModelCandidateProviderSummary",
    "MainAgentModelCandidateSummary",
    "MainAgentModelCapabilities",
]
