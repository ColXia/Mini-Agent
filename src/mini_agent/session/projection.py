"""Shared session read-model projections for transport/application layers."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from mini_agent.interfaces.agent import (
    MainAgentSessionDetail,
    MainAgentSessionMessage,
    MainAgentSessionPendingApproval,
    MainAgentSessionRecoverySnapshot,
    MainAgentSessionSummary,
)


def _safe_text(value: object | None) -> str:
    return " ".join(str(value or "").split())


def _nonnegative_int(value: Any, *, default: int = 0) -> int:
    try:
        return max(0, int(value))
    except Exception:
        return max(0, int(default))


def _payload_dict(payload: Any) -> dict[str, Any]:
    if payload is None:
        return {}
    if hasattr(payload, "model_dump"):
        dumped = payload.model_dump()
        if isinstance(dumped, dict):
            return dumped
    if isinstance(payload, Mapping):
        return dict(payload)
    return {}


def _copy_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    return {}


@dataclass(frozen=True)
class SessionPendingApprovalProjection:
    token: str
    tool_name: str
    arguments: dict[str, Any] = field(default_factory=dict)
    kind: str | None = None
    reason: str | None = None
    cache_key: str | None = None
    can_escalate: bool = False
    step: int | None = None

    @classmethod
    def from_payload(cls, payload: Any) -> SessionPendingApprovalProjection | None:
        data = _payload_dict(payload)
        token = _safe_text(data.get("token"))
        tool_name = _safe_text(data.get("tool_name"))
        if not token or not tool_name:
            return None
        step = data.get("step")
        normalized_step = None if step is None else _nonnegative_int(step)
        return cls(
            token=token,
            tool_name=tool_name,
            arguments=_copy_dict(data.get("arguments")),
            kind=_safe_text(data.get("kind")) or None,
            reason=_safe_text(data.get("reason")) or None,
            cache_key=_safe_text(data.get("cache_key")) or None,
            can_escalate=bool(data.get("can_escalate", False)),
            step=normalized_step,
        )

    @classmethod
    def from_payloads(cls, items: Sequence[Any] | None) -> tuple[SessionPendingApprovalProjection, ...]:
        approvals: list[SessionPendingApprovalProjection] = []
        for item in items or []:
            projection = cls.from_payload(item)
            if projection is not None:
                approvals.append(projection)
        return tuple(approvals)

    def to_transport(self) -> MainAgentSessionPendingApproval:
        return MainAgentSessionPendingApproval(
            token=self.token,
            tool_name=self.tool_name,
            arguments=dict(self.arguments),
            kind=self.kind,
            reason=self.reason,
            cache_key=self.cache_key,
            can_escalate=bool(self.can_escalate),
            step=self.step,
        )


@dataclass(frozen=True)
class SessionRecoveryProjection:
    state: str
    summary: str
    last_activity: str | None = None
    last_user_message: str | None = None
    last_assistant_message: str | None = None
    pending_approvals: tuple[SessionPendingApprovalProjection, ...] = ()

    @classmethod
    def from_payload(cls, payload: Any) -> SessionRecoveryProjection | None:
        data = _payload_dict(payload)
        if not data:
            return None
        state = _safe_text(data.get("state"))
        summary = _safe_text(data.get("summary"))
        last_activity = _safe_text(data.get("last_activity")) or None
        last_user_message = _safe_text(data.get("last_user_message")) or None
        last_assistant_message = _safe_text(data.get("last_assistant_message")) or None
        pending_approvals = SessionPendingApprovalProjection.from_payloads(data.get("pending_approvals"))
        if not any((state, summary, last_activity, last_user_message, last_assistant_message, pending_approvals)):
            return None
        return cls(
            state=state or "idle",
            summary=summary or state or "idle",
            last_activity=last_activity,
            last_user_message=last_user_message,
            last_assistant_message=last_assistant_message,
            pending_approvals=pending_approvals,
        )

    def to_transport(self) -> MainAgentSessionRecoverySnapshot:
        return MainAgentSessionRecoverySnapshot(
            state=self.state,
            summary=self.summary,
            last_activity=self.last_activity,
            last_user_message=self.last_user_message,
            last_assistant_message=self.last_assistant_message,
            pending_approvals=[item.to_transport() for item in self.pending_approvals],
        )


@dataclass(frozen=True)
class SessionMessageProjection:
    index: int
    role: str
    content: str
    surface: str
    created_at: str
    channel_type: str | None = None
    conversation_id: str | None = None
    sender_id: str | None = None
    metadata: dict[str, Any] | None = None

    @classmethod
    def from_payload(cls, payload: Any) -> SessionMessageProjection | None:
        data = _payload_dict(payload)
        if not data:
            return None
        index = _nonnegative_int(data.get("index"))
        role = _safe_text(data.get("role")) or "assistant"
        surface = _safe_text(data.get("surface")) or "remote"
        created_at = _safe_text(data.get("created_at"))
        if index <= 0 or not created_at:
            return None
        metadata = _copy_dict(data.get("metadata")) or None
        return cls(
            index=index,
            role=role,
            content=str(data.get("content", "")),
            surface=surface,
            created_at=created_at,
            channel_type=_safe_text(data.get("channel_type")) or None,
            conversation_id=_safe_text(data.get("conversation_id")) or None,
            sender_id=_safe_text(data.get("sender_id")) or None,
            metadata=metadata,
        )

    @classmethod
    def from_payloads(cls, items: Sequence[Any] | None) -> tuple[SessionMessageProjection, ...]:
        messages: list[SessionMessageProjection] = []
        for item in items or []:
            projection = cls.from_payload(item)
            if projection is not None:
                messages.append(projection)
        return tuple(messages)

    def to_transport(self) -> MainAgentSessionMessage:
        return MainAgentSessionMessage(
            index=self.index,
            role=self.role,
            content=self.content,
            surface=self.surface,
            created_at=self.created_at,
            channel_type=self.channel_type,
            conversation_id=self.conversation_id,
            sender_id=self.sender_id,
            metadata=dict(self.metadata) if isinstance(self.metadata, dict) else None,
        )


@dataclass(frozen=True)
class SessionSummaryProjection:
    session_id: str
    workspace_dir: str
    created_at: str
    updated_at: str
    title: str | None = None
    message_count: int = 0
    origin_surface: str = "tui"
    active_surface: str = "tui"
    reply_enabled: bool = False
    busy: bool = False
    running_state: str | None = None
    channel_type: str | None = None
    conversation_id: str | None = None
    sender_id: str | None = None
    token_usage: int = 0
    token_limit: int = 0
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
    pending_approvals: tuple[SessionPendingApprovalProjection, ...] = ()
    recovery: SessionRecoveryProjection | None = None
    memory_diagnostics: dict[str, Any] = field(default_factory=dict)
    sandbox_diagnostics: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_transport_payload(cls, payload: Any) -> SessionSummaryProjection | None:
        data = _payload_dict(payload)
        session_id = _safe_text(data.get("session_id"))
        if not session_id:
            return None
        return cls(
            session_id=session_id,
            workspace_dir=str(data.get("workspace_dir", "")),
            created_at=_safe_text(data.get("created_at")),
            updated_at=_safe_text(data.get("updated_at")),
            title=_safe_text(data.get("title")) or None,
            message_count=_nonnegative_int(data.get("message_count")),
            origin_surface=_safe_text(data.get("origin_surface")) or "tui",
            active_surface=_safe_text(data.get("active_surface")) or _safe_text(data.get("origin_surface")) or "tui",
            reply_enabled=bool(data.get("reply_enabled", False)),
            busy=bool(data.get("busy", False)),
            running_state=_safe_text(data.get("running_state")) or None,
            channel_type=_safe_text(data.get("channel_type")) or None,
            conversation_id=_safe_text(data.get("conversation_id")) or None,
            sender_id=_safe_text(data.get("sender_id")) or None,
            token_usage=_nonnegative_int(data.get("token_usage")),
            token_limit=_nonnegative_int(data.get("token_limit")),
            shared=bool(data.get("shared", False)),
            knowledge_base_enabled=bool(data.get("knowledge_base_enabled", True)),
            selected_model_source=_safe_text(data.get("selected_model_source")) or None,
            selected_provider_id=_safe_text(data.get("selected_provider_id")) or None,
            selected_model_id=_safe_text(data.get("selected_model_id")) or None,
            pending_model_source=_safe_text(data.get("pending_model_source")) or None,
            pending_provider_id=_safe_text(data.get("pending_provider_id")) or None,
            pending_model_id=_safe_text(data.get("pending_model_id")) or None,
            pending_skill_reload=bool(data.get("pending_skill_reload", False)),
            pending_skill_reload_reason=_safe_text(data.get("pending_skill_reload_reason")) or None,
            pending_approvals=SessionPendingApprovalProjection.from_payloads(data.get("pending_approvals")),
            recovery=SessionRecoveryProjection.from_payload(data.get("recovery")),
            memory_diagnostics=_copy_dict(data.get("memory_diagnostics")),
            sandbox_diagnostics=_copy_dict(data.get("sandbox_diagnostics")),
        )

    def to_transport(self) -> MainAgentSessionSummary:
        return MainAgentSessionSummary(
            session_id=self.session_id,
            workspace_dir=self.workspace_dir,
            created_at=self.created_at,
            updated_at=self.updated_at,
            title=self.title,
            message_count=self.message_count,
            origin_surface=self.origin_surface,
            active_surface=self.active_surface,
            reply_enabled=bool(self.reply_enabled),
            busy=bool(self.busy),
            running_state=self.running_state,
            channel_type=self.channel_type,
            conversation_id=self.conversation_id,
            sender_id=self.sender_id,
            token_usage=self.token_usage,
            token_limit=self.token_limit,
            shared=bool(self.shared),
            knowledge_base_enabled=bool(self.knowledge_base_enabled),
            selected_model_source=self.selected_model_source,
            selected_provider_id=self.selected_provider_id,
            selected_model_id=self.selected_model_id,
            pending_model_source=self.pending_model_source,
            pending_provider_id=self.pending_provider_id,
            pending_model_id=self.pending_model_id,
            pending_skill_reload=bool(self.pending_skill_reload),
            pending_skill_reload_reason=self.pending_skill_reload_reason,
            pending_approvals=[item.to_transport() for item in self.pending_approvals],
            recovery=self.recovery.to_transport() if self.recovery is not None else None,
            memory_diagnostics=dict(self.memory_diagnostics),
            sandbox_diagnostics=dict(self.sandbox_diagnostics),
        )


@dataclass(frozen=True)
class SessionDetailProjection(SessionSummaryProjection):
    context_policy: dict[str, Any] = field(default_factory=dict)
    last_prepared_context: dict[str, Any] = field(default_factory=dict)
    prepared_context_diagnostics: dict[str, Any] = field(default_factory=dict)
    recent_messages: tuple[SessionMessageProjection, ...] = ()

    @classmethod
    def from_summary(
        cls,
        summary: SessionSummaryProjection,
        *,
        context_policy: Mapping[str, Any] | None = None,
        last_prepared_context: Mapping[str, Any] | None = None,
        prepared_context_diagnostics: Mapping[str, Any] | None = None,
        recent_messages: Sequence[SessionMessageProjection] | None = None,
    ) -> SessionDetailProjection:
        return cls(
            session_id=summary.session_id,
            workspace_dir=summary.workspace_dir,
            created_at=summary.created_at,
            updated_at=summary.updated_at,
            title=summary.title,
            message_count=summary.message_count,
            origin_surface=summary.origin_surface,
            active_surface=summary.active_surface,
            reply_enabled=bool(summary.reply_enabled),
            busy=bool(summary.busy),
            running_state=summary.running_state,
            channel_type=summary.channel_type,
            conversation_id=summary.conversation_id,
            sender_id=summary.sender_id,
            token_usage=summary.token_usage,
            token_limit=summary.token_limit,
            shared=bool(summary.shared),
            knowledge_base_enabled=bool(summary.knowledge_base_enabled),
            selected_model_source=summary.selected_model_source,
            selected_provider_id=summary.selected_provider_id,
            selected_model_id=summary.selected_model_id,
            pending_model_source=summary.pending_model_source,
            pending_provider_id=summary.pending_provider_id,
            pending_model_id=summary.pending_model_id,
            pending_skill_reload=bool(summary.pending_skill_reload),
            pending_skill_reload_reason=summary.pending_skill_reload_reason,
            pending_approvals=tuple(summary.pending_approvals),
            recovery=summary.recovery,
            memory_diagnostics=dict(summary.memory_diagnostics),
            sandbox_diagnostics=dict(summary.sandbox_diagnostics),
            context_policy=_copy_dict(context_policy),
            last_prepared_context=_copy_dict(last_prepared_context),
            prepared_context_diagnostics=_copy_dict(prepared_context_diagnostics),
            recent_messages=tuple(recent_messages or ()),
        )

    @classmethod
    def from_transport_payload(cls, payload: Any) -> SessionDetailProjection | None:
        summary = SessionSummaryProjection.from_transport_payload(payload)
        if summary is None:
            return None
        data = _payload_dict(payload)
        return cls.from_summary(
            summary,
            context_policy=_copy_dict(data.get("context_policy")),
            last_prepared_context=_copy_dict(data.get("last_prepared_context")),
            prepared_context_diagnostics=_copy_dict(data.get("prepared_context_diagnostics")),
            recent_messages=SessionMessageProjection.from_payloads(data.get("recent_messages")),
        )

    def to_transport(self) -> MainAgentSessionDetail:
        return MainAgentSessionDetail(
            **super().to_transport().model_dump(),
            context_policy=dict(self.context_policy),
            last_prepared_context=dict(self.last_prepared_context),
            prepared_context_diagnostics=dict(self.prepared_context_diagnostics),
            recent_messages=[item.to_transport() for item in self.recent_messages],
        )

__all__ = [
    "SessionDetailProjection",
    "SessionMessageProjection",
    "SessionPendingApprovalProjection",
    "SessionRecoveryProjection",
    "SessionSummaryProjection",
]
