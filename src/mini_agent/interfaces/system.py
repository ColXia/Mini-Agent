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
    main_workspace_dir: str | None = None


class SystemHealthResponse(BaseModel):
    """Canonical health contract for API v1 system checks."""

    status: str
    now_utc: str
    workspace_root: str
    runtime: MainAgentRuntimeDiagnostics
