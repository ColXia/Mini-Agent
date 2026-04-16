"""Ops interface-layer DTOs for provider and memory management contracts."""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

from mini_agent.model_manager.provider import normalize_provider_api_type


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
    api_key: str
    models: list[str] = Field(default_factory=list)
    model_display_names: dict[str, str] = Field(default_factory=dict)
    model_id: str | None = None
    model_display_name: str | None = None
    auto_discover_models: bool = False
    selected_model_id: str | None = None
    enabled: bool = True
    priority: int = 0
    timeout: int = 60
    headers: dict[str, str] = Field(default_factory=dict)

    @field_validator("api_type")
    @classmethod
    def _validate_api_type(cls, value: str) -> str:
        return normalize_provider_api_type(value).value


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
    context_window: int | None = None
    learned_token_limit: int | None = None
    supports_tools: bool | None = None
    supports_thinking: bool | None = None
    discovered_at: str | None = None
    discovery_source: str | None = None
    discovery_confidence: str | None = None


class StudioModelProviderSummary(BaseModel):
    source: str
    provider_id: str
    provider_name: str
    api_type: str
    api_base: str
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


class StudioProviderModelDiscoveryRequest(BaseModel):
    api_type: str = "openai"
    api_base: str
    api_key: str

    @field_validator("api_type")
    @classmethod
    def _validate_api_type(cls, value: str) -> str:
        return normalize_provider_api_type(value).value


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
