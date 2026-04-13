"""Runtime-private session snapshot DTOs.

These models are intentionally kept out of the public interface package.
They exist only for runtime persistence/import/export internals.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class RuntimeSessionImportMessage(BaseModel):
    """Serialized transcript item used by runtime snapshot import/export."""

    role: str = Field(min_length=1)
    content: str = ""
    surface: str | None = None
    created_at: str | None = None
    channel_type: str | None = None
    conversation_id: str | None = None
    sender_id: str | None = None
    metadata: dict[str, Any] | None = None


class RuntimeSessionImportRequest(BaseModel):
    """Serialized runtime session payload for persistence import/export."""

    session_id: str | None = None
    workspace_dir: str | None = None
    title: str | None = None
    origin_surface: str | None = None
    active_surface: str | None = None
    reply_enabled: bool = False
    channel_type: str | None = None
    conversation_id: str | None = None
    sender_id: str | None = None
    token_usage: int = Field(ge=0, default=0)
    token_limit: int = Field(ge=0, default=0)
    shared: bool = False
    knowledge_base_enabled: bool | None = None
    selected_model_source: str | None = None
    selected_provider_id: str | None = None
    selected_model_id: str | None = None
    pending_model_source: str | None = None
    pending_provider_id: str | None = None
    pending_model_id: str | None = None
    lineage_parent_session_id: str | None = None
    lineage_root_session_id: str | None = None
    lineage_reason: str | None = None
    lineage_created_at: str | None = None
    lineage_metadata: dict[str, Any] = Field(default_factory=dict)
    pending_skill_reload: bool = False
    pending_skill_reload_reason: str | None = None
    context_policy: dict[str, Any] = Field(default_factory=dict)
    last_prepared_context: dict[str, Any] = Field(default_factory=dict)
    prepared_context_diagnostics: dict[str, Any] = Field(default_factory=dict)
    memory_diagnostics: dict[str, Any] = Field(default_factory=dict)
    sandbox_diagnostics: dict[str, Any] = Field(default_factory=dict)
    runtime_task_memory_payload: dict[str, Any] = Field(default_factory=dict)
    workspace_shared_runtime_memory_payload: dict[str, Any] = Field(default_factory=dict)
    agent_messages: list[dict[str, Any]] = Field(default_factory=list)
    transcript: list[RuntimeSessionImportMessage] = Field(default_factory=list)


class RuntimeSessionSnapshot(RuntimeSessionImportRequest):
    """Serialized runtime session snapshot for runtime-managed persistence."""
