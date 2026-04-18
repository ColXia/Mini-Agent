"""Main-agent interface-layer DTOs for API v1."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class MainAgentChatRequest(BaseModel):
    """Canonical chat request for main-agent."""

    message: str = Field(min_length=1)
    session_id: str | None = None
    session_title_hint: str | None = None
    workspace_dir: str | None = None
    dry_run: bool = False
    surface: str | None = None
    channel_type: str | None = None
    conversation_id: str | None = None
    sender_id: str | None = None


class MainAgentChatResponse(BaseModel):
    """Canonical chat response for main-agent."""

    session_id: str
    reply: str
    message_count: int = Field(ge=0)
    token_usage: int = Field(ge=0, default=0)
    workspace_dir: str
    updated_at: str
    delegation: dict[str, Any] | None = None


class MainAgentWorkspaceSummary(BaseModel):
    """Canonical workspace summary for main-agent workspace APIs."""

    workspace_id: str = Field(min_length=1)
    workspace_dir: str = Field(min_length=1)
    title: str | None = None
    default: bool = False
    kind: str | None = None
    session_count: int = Field(ge=0, default=0)
    default_session_count: int = Field(ge=0, default=0)
    shared_session_count: int = Field(ge=0, default=0)
    busy_session_count: int = Field(ge=0, default=0)
    last_updated_at: str | None = None
    active: bool = False
    switched: bool = False


class MainAgentWorkspaceRuntimeSummary(MainAgentWorkspaceSummary):
    """Detailed runtime summary for a workspace-bound execution boundary."""

    runtime_policy: dict[str, Any] = Field(default_factory=dict)
    runtime: dict[str, Any] | None = None
    runtime_error: str | None = None


class MainAgentWorkspaceSwitchRequest(BaseModel):
    """Request body for switching the active workspace selection."""

    workspace_id: str = Field(min_length=1)


class MainAgentSessionRecoverySnapshot(BaseModel):
    """Compact recovery snapshot for remote/shared-session operators."""

    state: str
    summary: str
    last_activity: str | None = None
    last_user_message: str | None = None
    last_assistant_message: str | None = None
    pending_approvals: list["MainAgentSessionPendingApproval"] = Field(default_factory=list)


class MainAgentSessionPendingApproval(BaseModel):
    """One live or recovered tool approval request for a shared session."""

    token: str = Field(min_length=1)
    tool_name: str = Field(min_length=1)
    arguments: dict[str, Any] = Field(default_factory=dict)
    kind: str | None = None
    reason: str | None = None
    cache_key: str | None = None
    can_escalate: bool = False
    step: int | None = Field(default=None, ge=0)


class MainAgentRunApprovalWait(BaseModel):
    """Canonical active approval-wait view for one run."""

    wait_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    session_id: str = Field(min_length=1)
    workspace_id: str | None = None
    approval_token: str | None = None
    tool_name: str = Field(min_length=1)
    tool_arguments_summary: dict[str, Any]
    approval_kind: str | None = None
    policy_reason: str | None = None
    cache_key: str | None = None
    can_escalate: bool = False
    wait_state: str = Field(min_length=1)
    decision_result: str | None = None
    created_at: str | None = None
    resolved_at: str | None = None
    invalidated_reason: str | None = None


class MainAgentRunSummary(BaseModel):
    """Canonical run summary for run-level active control APIs."""

    run_id: str = Field(min_length=1)
    session_id: str
    status: str = Field(min_length=1)
    phase: str = Field(min_length=1)
    busy: bool = False
    waiting_on_approval: bool = False
    active_surface: str | None = None
    channel_type: str | None = None
    conversation_id: str | None = None
    sender_id: str | None = None
    running_state: str | None = None
    control_mode: str | None = None
    interrupt_requested: bool = False
    cancel_requested: bool = False
    resumable: bool = False
    active_wait_id: str | None = None
    approval_wait: MainAgentRunApprovalWait | None = None


class MainAgentSessionSummary(BaseModel):
    """Canonical session summary for main-agent session APIs."""

    session_id: str
    workspace_dir: str
    created_at: str
    updated_at: str
    title: str | None = None
    message_count: int = Field(ge=0)
    origin_surface: str
    active_surface: str
    reply_enabled: bool = False
    busy: bool = False
    running_state: str | None = None
    is_default: bool = False
    channel_type: str | None = None
    conversation_id: str | None = None
    sender_id: str | None = None
    token_usage: int = Field(ge=0, default=0)
    token_limit: int = Field(ge=0, default=0)
    shared: bool = False
    knowledge_base_enabled: bool = True
    selected_model_source: str | None = None
    selected_provider_id: str | None = None
    selected_model_id: str | None = None
    pending_model_source: str | None = None
    pending_provider_id: str | None = None
    pending_model_id: str | None = None
    pending_skill_reload: bool = False
    pending_skill_reload_reason: str | None = None
    pending_approvals: list[MainAgentSessionPendingApproval] = Field(default_factory=list)
    recovery: MainAgentSessionRecoverySnapshot | None = None
    remote_recovery_text: str | None = None
    memory_diagnostics: dict[str, Any] = Field(default_factory=dict)
    sandbox_diagnostics: dict[str, Any] = Field(default_factory=dict)


class MainAgentSessionMessage(BaseModel):
    """Canonical session transcript entry for shared session surfaces."""

    index: int = Field(ge=1)
    role: str = Field(min_length=1)
    content: str
    surface: str = Field(min_length=1)
    created_at: str
    channel_type: str | None = None
    conversation_id: str | None = None
    sender_id: str | None = None
    metadata: dict[str, Any] | None = None


class MainAgentSessionDetail(MainAgentSessionSummary):
    """Detailed session view with recent shared transcript entries."""

    context_policy: dict[str, Any] = Field(default_factory=dict)
    last_prepared_context: dict[str, Any] = Field(default_factory=dict)
    prepared_context_diagnostics: dict[str, Any] = Field(default_factory=dict)
    recent_messages: list[MainAgentSessionMessage] = Field(default_factory=list)


class MainAgentSessionCreateRequest(BaseModel):
    """Request body for creating a new runtime-backed session."""

    workspace_dir: str | None = None
    title: str | None = None
    surface: str | None = None
    shared: bool = False


class MainAgentDefaultSessionRequest(BaseModel):
    """Request body for resolving the shared default session."""

    workspace_dir: str | None = None
    surface: str | None = None
    channel_type: str | None = None
    conversation_id: str | None = None
    sender_id: str | None = None


class MainAgentSessionForkRequest(BaseModel):
    """Request body for creating a derived child session from an existing session."""

    title: str | None = None
    surface: str | None = None
    channel_type: str | None = None
    conversation_id: str | None = None
    sender_id: str | None = None


class MainAgentSessionRenameRequest(BaseModel):
    """Request body for renaming an existing runtime-backed session."""

    title: str = Field(min_length=1)


class MainAgentSessionShareRequest(BaseModel):
    """Request body for toggling remote discovery on a runtime-backed session."""

    shared: bool


class MainAgentSessionMutationResponse(BaseModel):
    """Canonical response for session mutation actions."""

    status: str
    session_id: str
    active_surface: str | None = None
    title: str | None = None
    shared: bool | None = None


class MainAgentSessionCancelRequest(BaseModel):
    """Request body for cancelling a running shared-session turn."""

    reason: str | None = None
    surface: str | None = None
    channel_type: str | None = None
    conversation_id: str | None = None
    sender_id: str | None = None


class MainAgentSessionInterruptRequest(BaseModel):
    """Request body for interrupting a running shared-session turn."""

    reason: str | None = None
    surface: str | None = None
    channel_type: str | None = None
    conversation_id: str | None = None
    sender_id: str | None = None


class MainAgentSessionControlRequest(BaseModel):
    """Request body for shared-session control actions."""

    action: str = Field(min_length=1)
    reason: str | None = None
    surface: str | None = None
    channel_type: str | None = None
    conversation_id: str | None = None
    sender_id: str | None = None


class MainAgentSessionControlResponse(BaseModel):
    """Canonical response for context-control actions on a shared session."""

    status: str
    session_id: str
    action: str
    applied: bool = False
    active_surface: str | None = None
    reason: str | None = None
    message_count_before: int = Field(ge=0, default=0)
    message_count_after: int = Field(ge=0, default=0)
    token_count_before: int = Field(ge=0, default=0)
    token_count_after: int = Field(ge=0, default=0)
    knowledge_base_enabled: bool | None = None
    stats: dict[str, Any] | None = None


class MainAgentSessionContextRequest(BaseModel):
    """Request body for remote prepared-context policy updates on a shared session."""

    action: str = Field(min_length=1)
    sources: list[str] = Field(default_factory=list)
    max_items: int | None = Field(default=None, ge=1)
    max_total_chars: int | None = Field(default=None, ge=1)
    max_items_per_source: int | None = Field(default=None, ge=1)
    surface: str | None = None
    channel_type: str | None = None
    conversation_id: str | None = None
    sender_id: str | None = None


class MainAgentSessionContextResponse(BaseModel):
    """Canonical response for prepared-context policy updates on a shared session."""

    status: str
    session_id: str
    action: str
    active_surface: str | None = None
    context_policy: dict[str, Any] = Field(default_factory=dict)


class MainAgentSessionMemoryRequest(BaseModel):
    """Request body for memory diagnostics / control actions on a shared session."""

    action: str = Field(min_length=1)
    engram_id: str | None = None
    content: str | None = None
    query: str | None = None
    day: str | None = None
    export_format: str | None = None
    detail_mode: str | None = None
    surface: str | None = None
    channel_type: str | None = None
    conversation_id: str | None = None
    sender_id: str | None = None


class MainAgentSessionMemoryResponse(BaseModel):
    """Canonical response for shared-session memory diagnostics and control actions."""

    status: str
    session_id: str
    action: str
    active_surface: str | None = None
    memory_diagnostics: dict[str, Any] = Field(default_factory=dict)
    result: dict[str, Any] = Field(default_factory=dict)


class MainAgentSessionSkillRequest(BaseModel):
    """Request body for shared-session skill catalog inspection and refresh."""

    action: str = Field(min_length=1)
    skill_name: str | None = None
    path: str | None = None
    query: str | None = None
    mode: str | None = None
    surface: str | None = None
    channel_type: str | None = None
    conversation_id: str | None = None
    sender_id: str | None = None


class MainAgentSessionSkillResponse(BaseModel):
    """Canonical response for shared-session skill catalog actions."""

    status: str
    session_id: str
    action: str
    active_surface: str | None = None
    result: dict[str, Any] = Field(default_factory=dict)


class MainAgentSessionModelSelectionRequest(BaseModel):
    """Request body for updating a shared session's session-scoped model selection."""

    provider_source: str | None = Field(default=None, min_length=1)
    provider_id: str = Field(min_length=1)
    model_id: str = Field(min_length=1)
    surface: str | None = None
    channel_type: str | None = None
    conversation_id: str | None = None
    sender_id: str | None = None


class MainAgentSessionModelSelectionResponse(BaseModel):
    """Canonical response for session-scoped model selection updates."""

    status: str
    session_id: str
    active_surface: str | None = None
    applied: bool = False
    queued: bool = False
    selected_model_source: str | None = None
    selected_provider_id: str | None = None
    selected_model_id: str | None = None
    pending_model_source: str | None = None
    pending_provider_id: str | None = None
    pending_model_id: str | None = None


class MainAgentSessionApprovalRequest(BaseModel):
    """Request body for approving or denying a pending shared-session tool call."""

    approved: bool
    token: str | None = None
    surface: str | None = None
    channel_type: str | None = None
    conversation_id: str | None = None
    sender_id: str | None = None


class MainAgentSessionApprovalResponse(BaseModel):
    """Canonical response for resolving a pending shared-session approval."""

    status: str
    session_id: str
    token: str
    tool_name: str
    decision: str
    active_surface: str | None = None


class MainAgentSessionRuntimePolicyRequest(BaseModel):
    """Request body for updating a shared session's runtime execution/access mode."""

    approval_profile: str | None = None
    access_level: str | None = None
    surface: str | None = None
    channel_type: str | None = None
    conversation_id: str | None = None
    sender_id: str | None = None


class MainAgentSessionRuntimePolicyResponse(BaseModel):
    """Canonical response for shared-session runtime policy updates."""

    status: str
    session_id: str
    active_surface: str | None = None
    applied: bool = False
    approval_profile: str
    access_level: str
    summary: str | None = None
    details: str | None = None
    status_text: str | None = None
    sandbox_diagnostics: dict[str, Any] = Field(default_factory=dict)


class MainAgentRunResumeRequest(BaseModel):
    """Request body for resuming an existing run."""

    resume_token: str | None = None
    surface: str | None = None
    channel_type: str | None = None
    conversation_id: str | None = None
    sender_id: str | None = None


class MainAgentRunInterruptRequest(BaseModel):
    """Request body for interrupting an existing run."""

    reason: str | None = None
    surface: str | None = None
    channel_type: str | None = None
    conversation_id: str | None = None
    sender_id: str | None = None


class MainAgentRunCancelRequest(BaseModel):
    """Request body for cancelling an existing run."""

    reason: str | None = None
    surface: str | None = None
    channel_type: str | None = None
    conversation_id: str | None = None
    sender_id: str | None = None


class MainAgentRunApprovalRequest(BaseModel):
    """Request body for resolving the active approval wait under a run."""

    approved: bool
    token: str | None = None
    reason: str | None = None
    surface: str | None = None
    channel_type: str | None = None
    conversation_id: str | None = None
    sender_id: str | None = None
