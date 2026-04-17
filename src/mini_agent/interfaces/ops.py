"""Ops interface-layer DTOs for provider and memory management contracts."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator

from mini_agent.model_manager.provider import normalize_model_role, normalize_provider_api_type


def _normalize_ops_api_type(value: str) -> str:
    normalized = " ".join(str(value or "").strip().split()).lower()
    if normalized == "ollama":
        return "openai"
    return normalize_provider_api_type(value).value


class StudioProviderSummary(BaseModel):
    id: str
    name: str
    api_type: str
    api_base: str
    api_key_masked: str
    models: list[str]
    model_display_names: dict[str, str] = Field(default_factory=dict)
    enabled: bool
    priority: int
    timeout: int
    headers: dict[str, str]
    catalog_path: str
    health_status: str
    breaker_state: str
    selected_count: int
    error_rate: float
    consecutive_failures: int


class StudioProviderListResponse(BaseModel):
    catalog_path: str
    provider_count: int
    items: list[StudioProviderSummary]


class StudioProviderUpsertRequest(BaseModel):
    id: str | None = None
    name: str
    api_type: str = "openai"
    api_base: str
    api_key: str | None = None
    models: list[str] = Field(default_factory=list)
    model_display_names: dict[str, str] = Field(default_factory=dict)
    model_id: str | None = None
    model_display_name: str | None = None
    model_role: str | None = None
    model_roles: dict[str, str] = Field(default_factory=dict)
    model_context_window: int | None = None
    model_context_windows: dict[str, int] = Field(default_factory=dict)
    model_learned_token_limit: int | None = None
    model_learned_token_limits: dict[str, int] = Field(default_factory=dict)
    model_metadata: dict[str, dict[str, Any]] = Field(default_factory=dict)
    supports_tools: bool | None = None
    supports_thinking: bool | None = None
    auto_discover_models: bool = False
    selected_model_id: str | None = None
    enabled: bool = True
    priority: int = 0
    timeout: int = 60
    headers: dict[str, str] = Field(default_factory=dict)

    @field_validator("api_type")
    @classmethod
    def _validate_api_type(cls, value: str) -> str:
        return _normalize_ops_api_type(value)

    @field_validator("model_role")
    @classmethod
    def _validate_model_role(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return normalize_model_role(value, allow_unclassified=True).value

    @field_validator("model_roles", mode="before")
    @classmethod
    def _validate_model_roles(cls, value: Any) -> dict[str, str]:
        if value is None:
            return {}
        if not isinstance(value, dict):
            raise ValueError("model_roles must be an object.")
        normalized: dict[str, str] = {}
        for raw_key, raw_val in value.items():
            model_id = " ".join(str(raw_key or "").strip().split())
            if not model_id:
                continue
            normalized[model_id] = normalize_model_role(
                raw_val,
                allow_unclassified=True,
            ).value
        return normalized

    @field_validator("model_context_window", "model_learned_token_limit")
    @classmethod
    def _validate_positive_optional_int(cls, value: int | None) -> int | None:
        if value is None:
            return None
        parsed = int(value)
        if parsed <= 0:
            raise ValueError("value must be greater than 0.")
        return parsed

    @field_validator("model_context_windows", "model_learned_token_limits", mode="before")
    @classmethod
    def _validate_positive_int_maps(cls, value: Any) -> dict[str, int]:
        if value is None:
            return {}
        if not isinstance(value, dict):
            raise ValueError("value must be an object.")
        normalized: dict[str, int] = {}
        for raw_key, raw_val in value.items():
            model_id = " ".join(str(raw_key or "").strip().split())
            if not model_id:
                continue
            parsed = int(raw_val)
            if parsed <= 0:
                raise ValueError("value must be greater than 0.")
            normalized[model_id] = parsed
        return normalized


class StudioProviderHealthResponse(BaseModel):
    provider_id: str
    status: str
    breaker_state: str
    selected_count: int
    total_requests: int
    total_successes: int
    total_failures: int
    consecutive_failures: int
    error_rate: float
    last_selected_at: str | None = None
    last_success_at: str | None = None
    last_failure_at: str | None = None
    last_failure_reason: str | None = None


class StudioProviderDeleteResponse(BaseModel):
    status: str
    provider_id: str
    catalog_path: str


class StudioProviderModelSummary(BaseModel):
    model_id: str
    display_name: str
    is_default: bool
    model_role: str | None = None
    context_window: int | None = None
    learned_token_limit: int | None = None
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


class StudioModelProviderSummary(BaseModel):
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
    models: list[StudioProviderModelSummary] = Field(default_factory=list)
    enabled: bool = True
    priority: int = 0


class StudioModelListResponse(BaseModel):
    items: list[StudioModelProviderSummary] = Field(default_factory=list)


class StudioModelDiscoverRequest(BaseModel):
    source: str
    provider_id: str


class StudioModelSelectionRequest(BaseModel):
    source: str
    provider_id: str
    model_id: str


class StudioModelRoleRequest(BaseModel):
    source: str
    provider_id: str
    model_id: str
    model_role: str

    @field_validator("model_role")
    @classmethod
    def _validate_model_role_value(cls, value: str) -> str:
        return normalize_model_role(value, allow_unclassified=True).value


class StudioModelCapabilityProbeRequest(BaseModel):
    source: str
    provider_id: str
    model_id: str


class StudioModelCapabilityProbeResponse(BaseModel):
    source: str
    provider_id: str
    provider_name: str | None = None
    api_type: str | None = None
    api_base: str | None = None
    model_id: str
    updated_fields: list[str] = Field(default_factory=list)
    discovery_attempted: bool = False
    active_probe_attempted: bool = False
    notes: list[str] = Field(default_factory=list)
    model: StudioProviderModelSummary


class StudioFeatureModelBindingRequest(BaseModel):
    feature_role: str
    source: str
    provider_id: str
    model_id: str

    @field_validator("feature_role")
    @classmethod
    def _validate_feature_role(cls, value: str) -> str:
        normalized = normalize_model_role(value, allow_unclassified=False).value
        if normalized not in {"embedding", "ocr"}:
            raise ValueError("feature_role must be one of: embedding, ocr.")
        return normalized


class StudioFeatureModelBindingSummary(BaseModel):
    feature_role: str
    source: str | None = None
    provider_id: str | None = None
    provider_name: str | None = None
    provider_family: str | None = None
    provider_variant: str | None = None
    api_type: str | None = None
    api_base: str | None = None
    model_id: str | None = None
    display_name: str | None = None
    model_role: str | None = None
    updated_at: str | None = None
    resolved: bool = True


class StudioFeatureModelBindingsResponse(BaseModel):
    items: list[StudioFeatureModelBindingSummary] = Field(default_factory=list)


class StudioFeatureModelBindingClearResponse(BaseModel):
    status: str
    feature_role: str


class StudioProviderModelDiscoveryRequest(BaseModel):
    api_type: str = "openai"
    api_base: str
    api_key: str | None = None

    @field_validator("api_type")
    @classmethod
    def _validate_api_type(cls, value: str) -> str:
        return _normalize_ops_api_type(value)


class StudioProviderValidationRequest(BaseModel):
    api_type: str = "openai"
    api_base: str
    api_key: str | None = None

    @field_validator("api_type")
    @classmethod
    def _validate_api_type(cls, value: str) -> str:
        return _normalize_ops_api_type(value)


class StudioProviderValidationResponse(BaseModel):
    status: str
    api_type: str
    api_base: str
    resolved_provider_type: str
    connection_ok: bool = True
    model_count: int = 0
    latest_model_id: str | None = None
    message: str
    models: list[StudioProviderModelSummary] = Field(default_factory=list)


class StudioProviderModelDiscoveryResponse(BaseModel):
    models: list[StudioProviderModelSummary] = Field(default_factory=list)
    latest_model_id: str | None = None


class StudioMemoryNote(BaseModel):
    timestamp: str
    category: str
    content: str
    path: str


class StudioMemorySummaryResponse(BaseModel):
    workspace_dir: str
    memory_root: str
    long_term_file: str
    daily_dir: str
    daily_files: list[str]
    notes_count: int
    categories: list[str]


class StudioMemorySearchResponse(BaseModel):
    workspace_dir: str
    query: str
    limit: int
    total: int
    items: list[StudioMemoryNote]


class StudioMemoryDailyResponse(BaseModel):
    workspace_dir: str
    day: str
    path: str
    note_count: int
    content: str
    items: list[StudioMemoryNote]
