"""System-level interface-layer DTOs for API v1."""

from __future__ import annotations

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


class MainAgentRoutingDiagnostics(BaseModel):
    """Routing diagnostics for main-agent request dispatch."""

    total_resolutions: int = Field(default=0, ge=0)
    cache_hits: int = Field(default=0, ge=0)
    fallback_resolutions: int = Field(default=0, ge=0)
    matched_scope_counts: dict[str, int] = Field(default_factory=dict)
    matched_agent_counts: dict[str, int] = Field(default_factory=dict)


class SystemHealthResponse(BaseModel):
    """Canonical health contract for API v1 system checks."""

    status: str
    now_utc: str
    workspace_root: str
    runtime: MainAgentRuntimeDiagnostics
