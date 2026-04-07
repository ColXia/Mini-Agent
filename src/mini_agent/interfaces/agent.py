"""Main-agent interface-layer DTOs for API v1."""

from __future__ import annotations

from pydantic import BaseModel, Field


class MainAgentChatRequest(BaseModel):
    """Canonical chat request for main-agent."""

    message: str = Field(min_length=1)
    session_id: str | None = None
    workspace_dir: str | None = None
    dry_run: bool = False


class MainAgentChatResponse(BaseModel):
    """Canonical chat response for main-agent."""

    session_id: str
    reply: str
    message_count: int = Field(ge=0)
    token_usage: int = Field(ge=0, default=0)
    workspace_dir: str
    updated_at: str


class MainAgentSessionSummary(BaseModel):
    """Canonical session summary for main-agent session APIs."""

    session_id: str
    workspace_dir: str
    created_at: str
    updated_at: str
    message_count: int = Field(ge=0)


class MainAgentSessionMutationResponse(BaseModel):
    """Canonical response for session mutation actions."""

    status: str
    session_id: str
