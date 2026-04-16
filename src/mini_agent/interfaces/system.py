"""System-level interface-layer DTOs for API v1."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class MainAgentRuntimeDiagnostics(BaseModel):
    """Runtime diagnostics for main-agent mode and bounded session capacity."""

    mode: str
    active_sessions: int = Field(ge=0)
    max_active_sessions: int = Field(ge=1)
    available_session_slots: int = Field(ge=0)
    reserved_team_slots: int = Field(ge=1)
    workspace_application_required: bool
    team_saturation_rejections: int = Field(default=0, ge=0)
    team_workspace_conflict_rejections: int = Field(default=0, ge=0)
    lifecycle_auto_resets: int = Field(default=0, ge=0)
    session_reset_mode: str = Field(default="none")
    session_idle_seconds: int = Field(default=1800, ge=1)
    main_workspace_dir: str | None = None


class ModelRouteCandidateDiagnostics(BaseModel):
    """One ranked model-route candidate snapshot."""

    selected: bool = False
    provider: str | None = None
    provider_source: str | None = None
    provider_id: str | None = None
    provider_name: str | None = None
    model: str | None = None
    mapping_mode: str | None = None
    priority: int | None = None
    breaker_state: str | None = None
    breaker_allowed: bool | None = None
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


class ModelRouteDiagnostics(BaseModel):
    """Latest model/provider routing decision snapshot."""

    resolution_kind: str | None = None
    catalog_source: str | None = None
    catalog_path: str | None = None
    route_intent: str | None = None
    requested_model: str | None = None
    requested_provider_source: str | None = None
    requested_provider_id: str | None = None
    require_tools: bool = False
    prefer_thinking: bool = False
    min_context_window: int | None = Field(default=None, ge=1)
    selected_provider: str | None = None
    selected_provider_source: str | None = None
    selected_provider_id: str | None = None
    selected_provider_name: str | None = None
    selected_model: str | None = None
    mapping_mode: str | None = None
    selected_reason: str | None = None
    fallback_reason: str | None = None
    candidate_count: int = Field(default=0, ge=0)
    allowed_candidate_count: int = Field(default=0, ge=0)
    blocked_candidate_count: int = Field(default=0, ge=0)
    selected_context_window: int | None = Field(default=None, ge=1)
    selected_learned_token_limit: int | None = Field(default=None, ge=1)
    selected_token_limit: int | None = Field(default=None, ge=1)
    selected_supports_tools: bool | None = None
    selected_supports_tools_truth: str | None = None
    selected_supports_tools_confidence: str | None = None
    selected_supports_tools_source: str | None = None
    selected_supports_thinking: bool | None = None
    selected_supports_thinking_truth: str | None = None
    selected_supports_thinking_confidence: str | None = None
    selected_supports_thinking_source: str | None = None
    bootstrap_selected_provider: str | None = None
    bootstrap_selection_reason: str | None = None
    bootstrap_selection_policy: str | None = None
    bootstrap_preferred_provider: str | None = None
    bootstrap_preferred_provider_available: bool | None = None
    bootstrap_alternatives: list[dict[str, Any]] = Field(default_factory=list)
    error: str | None = None
    candidates: list[ModelRouteCandidateDiagnostics] = Field(default_factory=list)


class MainAgentRoutingDiagnostics(BaseModel):
    """Routing diagnostics for main-agent request dispatch."""

    total_resolutions: int = Field(default=0, ge=0)
    cache_hits: int = Field(default=0, ge=0)
    fallback_resolutions: int = Field(default=0, ge=0)
    matched_scope_counts: dict[str, int] = Field(default_factory=dict)
    matched_agent_counts: dict[str, int] = Field(default_factory=dict)
    model_route_resolutions: int = Field(default=0, ge=0)
    latest_model_route: ModelRouteDiagnostics | None = None


class SystemHealthResponse(BaseModel):
    """Canonical health contract for API v1 system checks."""

    status: str
    now_utc: str
    workspace_root: str
    runtime: MainAgentRuntimeDiagnostics
