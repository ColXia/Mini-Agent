"""Shared runtime session state models."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mini_agent.agent_core.engine import Agent
from mini_agent.agent_core.session import SessionLifecycleState
from mini_agent.runtime.session_payload_codec import RuntimeSessionPayloadCodec


@dataclass(slots=True)
class MainAgentSessionProjectionState:
    title: str = ""
    origin_surface: str = ""
    active_surface: str = ""
    reply_enabled: bool = False
    busy: bool = False
    running_state: str = ""
    is_default: bool = False
    channel_type: str | None = None
    conversation_id: str | None = None
    sender_id: str | None = None
    shared: bool = False
    knowledge_base_enabled: bool = True
    selected_model_source: str | None = None
    selected_provider_id: str | None = None
    selected_model_id: str | None = None
    pending_model_source: str | None = None
    pending_provider_id: str | None = None
    pending_model_id: str | None = None
    pending_skill_reload: bool = False
    pending_skill_reload_reason: str = ""
    recovery_context_pending: bool = False
    recovery_state: str = ""
    recovery_summary: str = ""
    recovery_last_activity: str | None = None
    recovery_last_user_message: str | None = None
    recovery_last_assistant_message: str | None = None
    recovery_pending_approvals: list[dict[str, Any]] = field(default_factory=list)
    context_policy: dict[str, Any] = field(default_factory=dict)
    last_prepared_context: dict[str, Any] = field(default_factory=dict)
    prepared_context_diagnostics: dict[str, Any] = field(default_factory=dict)
    memory_diagnostics: dict[str, Any] = field(default_factory=dict)
    sandbox_diagnostics: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class MainAgentSessionTranscriptState:
    transcript: list["MainAgentSessionTranscriptEntry"] = field(default_factory=list)
    next_transcript_index: int = 1
    current_turn_id: str | None = None


@dataclass(slots=True)
class MainAgentSessionRuntimeHostState:
    agent: Agent
    cancel_event: asyncio.Event | None = None
    pending_approvals: list[dict[str, Any]] = field(default_factory=list)
    pending_approval_waiters: dict[str, asyncio.Future[bool | None]] = field(default_factory=dict)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


@dataclass(slots=True)
class MainAgentSessionLineageState:
    parent_session_id: str | None = None
    root_session_id: str | None = None
    reason: str = "root"
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class MainAgentSessionState:
    session_id: str
    workspace_dir: Path
    lifecycle_state: SessionLifecycleState
    runtime: MainAgentSessionRuntimeHostState
    lineage_state: MainAgentSessionLineageState = field(default_factory=MainAgentSessionLineageState)
    projection: MainAgentSessionProjectionState = field(default_factory=MainAgentSessionProjectionState)
    transcript_state: MainAgentSessionTranscriptState = field(default_factory=MainAgentSessionTranscriptState)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def touch(self, *, now_utc: datetime | None = None) -> None:
        self.updated_at = (now_utc or datetime.now(timezone.utc)).astimezone(timezone.utc)

    @property
    def agent(self) -> Agent:
        return self.runtime.agent

    @property
    def cancel_event(self) -> asyncio.Event | None:
        return self.runtime.cancel_event

    @property
    def active_surface(self) -> str:
        return self.projection.active_surface

    @property
    def origin_surface(self) -> str:
        return self.projection.origin_surface

    @property
    def channel_type(self) -> str | None:
        return self.projection.channel_type

    @property
    def conversation_id(self) -> str | None:
        return self.projection.conversation_id

    @property
    def sender_id(self) -> str | None:
        return self.projection.sender_id

    @property
    def context_policy(self) -> dict[str, Any]:
        return self.projection.context_policy

    @property
    def busy(self) -> bool:
        return bool(self.projection.busy)

    @property
    def running_state(self) -> str:
        return self.projection.running_state

    @running_state.setter
    def running_state(self, value: str) -> None:
        self.projection.running_state = str(value or "")

    @property
    def pending_approvals(self) -> list[dict[str, Any]]:
        return list(self.runtime.pending_approvals)

    @property
    def token_usage(self) -> int:
        return RuntimeSessionPayloadCodec.agent_token_usage(self.runtime.agent)

    @property
    def message_count(self) -> int:
        return RuntimeSessionPayloadCodec.agent_message_count(self.runtime.agent)


@dataclass
class MainAgentSessionTranscriptEntry:
    index: int
    role: str
    content: str
    surface: str
    created_at: datetime
    channel_type: str | None = None
    conversation_id: str | None = None
    sender_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


__all__ = [
    "MainAgentSessionLineageState",
    "MainAgentSessionProjectionState",
    "MainAgentSessionRuntimeHostState",
    "MainAgentSessionState",
    "MainAgentSessionTranscriptEntry",
    "MainAgentSessionTranscriptState",
]
