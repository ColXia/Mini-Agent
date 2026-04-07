"""Channel ingress interface-layer DTOs for API v1."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ChannelMessageRequest(BaseModel):
    """Canonical ingress payload for QQ/WeChat channels."""

    channel_type: str = Field(min_length=1)
    conversation_id: str = Field(min_length=1)
    sender_id: str | None = None
    message: str = Field(min_length=1)
    workspace_dir: str | None = None
    session_id: str | None = None
    metadata: dict[str, Any] | None = None
    dry_run: bool = False


class ChannelMessageResponse(BaseModel):
    """Canonical channel response payload."""

    session_id: str
    reply: str
    message_count: int = Field(ge=0)
    token_usage: int = Field(ge=0, default=0)
    workspace_dir: str
    updated_at: str
