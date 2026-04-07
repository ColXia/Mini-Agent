"""Ops interface-layer DTOs for provider and memory management contracts."""

from __future__ import annotations

from pydantic import BaseModel, Field


class StudioProviderSummary(BaseModel):
    id: str
    name: str
    api_type: str
    api_base: str
    api_key_masked: str
    models: list[str]
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
    enabled: bool = True
    priority: int = 0
    timeout: int = 60
    headers: dict[str, str] = Field(default_factory=dict)


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
