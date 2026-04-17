"""Runtime session read-model builders extracted from the runtime manager."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Callable, Sequence
from uuid import uuid4

from mini_agent.interfaces import (
    MainAgentSessionDetail,
    MainAgentSessionMessage,
    MainAgentSessionPendingApproval,
    MainAgentSessionRecoverySnapshot,
    MainAgentSessionSummary,
)
try:
    from mini_agent.interaction import normalize_channel_type
except Exception:  # pragma: no cover - compatibility path for staged interaction extraction
    from mini_agent.runtime.support.interaction_surface import normalize_channel_type
from mini_agent.session import (
    SessionDetailProjection,
    SessionMessageProjection,
    SessionPendingApprovalProjection,
    SessionRecoveryFeedbackService,
    SessionRecoveryProjection,
    SessionSummaryProjection,
)

from .session_snapshot_builder import RuntimeSessionSnapshotBuilder

if TYPE_CHECKING:
    from mini_agent.runtime.session_state import (
        MainAgentSessionState,
        MainAgentSessionTranscriptEntry,
    )


def _safe_text(value: object) -> str:
    return " ".join(str(value or "").split())


def _to_utc_iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


@dataclass(slots=True)
class RuntimeSessionReadModelBuilder:
    normalize_surface: Callable[[object | None], str]
    normalize_model_source: Callable[[object], str | None]
    normalize_context_policy_payload: Callable[[Any], dict[str, Any]]
    normalize_prepared_context_payload: Callable[[Any], dict[str, Any]]
    normalize_prepared_context_diagnostics_payload: Callable[[Any], dict[str, Any]]
    build_memory_diagnostics_for_session: Callable[["MainAgentSessionState"], dict[str, Any]]
    build_memory_diagnostics_from_record: Callable[[dict[str, Any]], dict[str, Any]]
    build_sandbox_diagnostics_for_session: Callable[["MainAgentSessionState"], dict[str, Any]]
    build_sandbox_diagnostics_from_record: Callable[[dict[str, Any]], dict[str, Any]]
    session_token_usage: Callable[["MainAgentSessionState"], int]
    session_token_limit: Callable[["MainAgentSessionState"], int]
    record_token_usage: Callable[[dict[str, Any]], int]
    record_token_limit: Callable[[dict[str, Any]], int]
    transcript_entries_from_record: Callable[[dict[str, Any]], list["MainAgentSessionTranscriptEntry"]]
    pending_approvals_from_raw: Callable[[Any], list[dict[str, Any]]]
    snapshot_runtime_task_memory_payload: Callable[..., dict[str, Any]] | None = None
    snapshot_workspace_shared_runtime_task_memory_payload: Callable[..., dict[str, Any]] | None = None
    serialize_agent_messages: Callable[[Sequence[Any]], list[dict[str, Any]]] | None = None

    def build_session_summary_projection(
        self,
        session: "MainAgentSessionState",
    ) -> SessionSummaryProjection:
        memory_diagnostics = self.build_memory_diagnostics_for_session(session)
        sandbox_diagnostics = self.build_sandbox_diagnostics_for_session(session)
        pending_approvals = tuple(self.build_pending_approval_projections(session.runtime.pending_approvals))
        recovery = self.build_session_recovery_projection(
            transcript=session.transcript_state.transcript,
            origin_surface=session.projection.origin_surface,
            active_surface=session.projection.active_surface,
            reply_enabled=session.projection.reply_enabled,
            channel_type=session.projection.channel_type,
            busy=session.projection.busy,
            running_state=session.projection.running_state,
            pending_approvals=session.runtime.pending_approvals,
            persisted_record=False,
        )
        stored_recovery = self.stored_recovery_snapshot_from_session(session)
        if stored_recovery is not None and not session.projection.busy and not pending_approvals:
            recovery = SessionRecoveryProjection.from_payload(stored_recovery)
        remote_recovery_text = self.build_remote_recovery_text(
            session_id=session.session_id,
            origin_surface=session.projection.origin_surface,
            active_surface=session.projection.active_surface or session.projection.origin_surface,
            reply_enabled=bool(session.projection.reply_enabled),
            recovery=recovery,
            pending_approvals=pending_approvals,
            pending_skill_reload=bool(session.projection.pending_skill_reload),
            pending_skill_reload_reason=_safe_text(session.projection.pending_skill_reload_reason) or None,
        )
        return SessionSummaryProjection(
            session_id=session.session_id,
            workspace_dir=str(session.workspace_dir),
            created_at=_to_utc_iso(session.created_at),
            updated_at=_to_utc_iso(session.updated_at),
            title=_safe_text(session.projection.title) or None,
            message_count=len(session.transcript_state.transcript),
            origin_surface=self.normalize_surface(session.projection.origin_surface),
            active_surface=self.normalize_surface(
                session.projection.active_surface or session.projection.origin_surface
            ),
            reply_enabled=bool(session.projection.reply_enabled),
            busy=bool(session.projection.busy),
            running_state=_safe_text(session.projection.running_state) or None,
            is_default=bool(session.projection.is_default),
            channel_type=session.projection.channel_type,
            conversation_id=session.projection.conversation_id,
            sender_id=session.projection.sender_id,
            token_usage=self.session_token_usage(session),
            token_limit=self.session_token_limit(session),
            shared=bool(session.projection.shared),
            knowledge_base_enabled=bool(session.projection.knowledge_base_enabled),
            selected_model_source=session.projection.selected_model_source,
            selected_provider_id=session.projection.selected_provider_id,
            selected_model_id=session.projection.selected_model_id,
            pending_model_source=session.projection.pending_model_source,
            pending_provider_id=session.projection.pending_provider_id,
            pending_model_id=session.projection.pending_model_id,
            pending_skill_reload=bool(session.projection.pending_skill_reload),
            pending_skill_reload_reason=_safe_text(session.projection.pending_skill_reload_reason) or None,
            pending_approvals=pending_approvals,
            recovery=recovery,
            remote_recovery_text=remote_recovery_text,
            memory_diagnostics=dict(memory_diagnostics),
            sandbox_diagnostics=dict(sandbox_diagnostics),
        )

    def build_session_summary(self, session: "MainAgentSessionState") -> MainAgentSessionSummary:
        return self.build_session_summary_projection(session).to_transport()

    def build_session_detail(
        self,
        session: "MainAgentSessionState",
        *,
        recent_limit: int,
    ) -> MainAgentSessionDetail:
        normalized_limit = max(1, int(recent_limit))
        summary = self.build_session_summary_projection(session)
        return SessionDetailProjection.from_summary(
            summary,
            context_policy=self.normalize_context_policy_payload(session.projection.context_policy),
            last_prepared_context=self.normalize_prepared_context_payload(session.projection.last_prepared_context),
            prepared_context_diagnostics=self.normalize_prepared_context_diagnostics_payload(
                session.projection.prepared_context_diagnostics
            ),
            recent_messages=tuple(
                self.build_session_message_projection(entry)
                for entry in session.transcript_state.transcript[-normalized_limit:]
            ),
        ).to_transport()

    def build_session_summary_projection_from_record(
        self,
        record: dict[str, Any],
    ) -> SessionSummaryProjection:
        memory_diagnostics = self.build_memory_diagnostics_from_record(record)
        sandbox_diagnostics = self.build_sandbox_diagnostics_from_record(record)
        transcript = self.transcript_entries_from_record(record)
        pending_approvals = tuple(self.build_pending_approval_projections(record.get("pending_approvals")))
        recovery = self.build_session_recovery_projection(
            transcript=transcript,
            origin_surface=record.get("origin_surface"),
            active_surface=record.get("active_surface") or record.get("origin_surface"),
            reply_enabled=bool(record.get("reply_enabled", False)),
            channel_type=normalize_channel_type(record.get("channel_type")),
            busy=bool(record.get("busy", False)),
            running_state=_safe_text(record.get("running_state")) or None,
            pending_approvals=record.get("pending_approvals"),
            persisted_record=True,
        )
        stored_recovery = self.stored_recovery_snapshot_from_record(record, transcript=transcript)
        if stored_recovery is not None and not bool(record.get("busy", False)) and not pending_approvals:
            recovery = SessionRecoveryProjection.from_payload(stored_recovery)
        remote_recovery_text = self.build_remote_recovery_text(
            session_id=_safe_text(record.get("session_id")) or None,
            origin_surface=record.get("origin_surface"),
            active_surface=record.get("active_surface") or record.get("origin_surface"),
            reply_enabled=bool(record.get("reply_enabled", False)),
            recovery=recovery,
            pending_approvals=tuple(),
            pending_skill_reload=bool(record.get("pending_skill_reload", False)),
            pending_skill_reload_reason=_safe_text(record.get("pending_skill_reload_reason")) or None,
        )
        return SessionSummaryProjection(
            session_id=_safe_text(record.get("session_id")) or uuid4().hex,
            workspace_dir=str(record.get("workspace_dir", "")),
            created_at=str(record.get("created_at", "")),
            updated_at=str(record.get("updated_at", "")),
            title=_safe_text(record.get("title")) or None,
            message_count=max(0, int(record.get("shared_message_count") or record.get("message_count") or 0)),
            origin_surface=self.normalize_surface(record.get("origin_surface")),
            active_surface=self.normalize_surface(record.get("active_surface") or record.get("origin_surface")),
            reply_enabled=bool(record.get("reply_enabled", False)),
            busy=False,
            running_state=None,
            is_default=bool(record.get("is_default", False)),
            channel_type=normalize_channel_type(record.get("channel_type")),
            conversation_id=_safe_text(record.get("conversation_id")) or None,
            sender_id=_safe_text(record.get("sender_id")) or None,
            token_usage=self.record_token_usage(record),
            token_limit=self.record_token_limit(record),
            shared=bool(record.get("shared", False)),
            knowledge_base_enabled=bool(record.get("knowledge_base_enabled", True)),
            selected_model_source=self.normalize_model_source(record.get("selected_model_source")),
            selected_provider_id=_safe_text(record.get("selected_provider_id")) or None,
            selected_model_id=_safe_text(record.get("selected_model_id")) or None,
            pending_model_source=self.normalize_model_source(record.get("pending_model_source")),
            pending_provider_id=_safe_text(record.get("pending_provider_id")) or None,
            pending_model_id=_safe_text(record.get("pending_model_id")) or None,
            pending_skill_reload=bool(record.get("pending_skill_reload", False)),
            pending_skill_reload_reason=_safe_text(record.get("pending_skill_reload_reason")) or None,
            pending_approvals=tuple(),
            recovery=recovery,
            remote_recovery_text=remote_recovery_text,
            memory_diagnostics=dict(memory_diagnostics),
            sandbox_diagnostics=dict(sandbox_diagnostics),
        )

    def build_session_summary_from_record(self, record: dict[str, Any]) -> MainAgentSessionSummary:
        return self.build_session_summary_projection_from_record(record).to_transport()

    def build_session_detail_from_record(
        self,
        record: dict[str, Any],
        *,
        recent_limit: int,
    ) -> MainAgentSessionDetail:
        normalized_limit = max(1, int(recent_limit))
        summary = self.build_session_summary_projection_from_record(record)
        transcript = self.transcript_entries_from_record(record)
        return SessionDetailProjection.from_summary(
            summary,
            context_policy=self.normalize_context_policy_payload(record.get("context_policy")),
            last_prepared_context=self.normalize_prepared_context_payload(record.get("last_prepared_context")),
            prepared_context_diagnostics=self.normalize_prepared_context_diagnostics_payload(
                record.get("prepared_context_diagnostics")
            ),
            recent_messages=tuple(
                self.build_session_message_projection(entry)
                for entry in transcript[-normalized_limit:]
            ),
        ).to_transport()

    def build_pending_approval_models(
        self,
        raw_items: Sequence[dict[str, Any]] | None,
    ) -> list[MainAgentSessionPendingApproval]:
        return [item.to_transport() for item in self.build_pending_approval_projections(raw_items)]

    def build_session_snapshot(self, session: "MainAgentSessionState"):
        return self._snapshot_builder().build_session_snapshot(session)

    def build_session_snapshot_from_record(self, record: dict[str, Any]):
        return self._snapshot_builder().build_session_snapshot_from_record(record)

    def build_pending_approval_projections(
        self,
        raw_items: Sequence[dict[str, Any]] | None,
    ) -> list[SessionPendingApprovalProjection]:
        approvals: list[SessionPendingApprovalProjection] = []
        for item in self.pending_approvals_from_raw(list(raw_items or [])):
            approvals.append(
                SessionPendingApprovalProjection(
                    token=item["token"],
                    tool_name=item["tool_name"],
                    arguments=dict(item.get("arguments") or {}),
                    kind=item.get("kind"),
                    reason=item.get("reason"),
                    cache_key=item.get("cache_key"),
                    can_escalate=bool(item.get("can_escalate", False)),
                    step=int(item.get("step") or 0),
                )
            )
        return approvals

    def stored_recovery_snapshot_from_record(
        self,
        record: dict[str, Any],
        *,
        transcript: Sequence["MainAgentSessionTranscriptEntry"],
    ) -> MainAgentSessionRecoverySnapshot | None:
        pending = self.pending_approvals_from_raw(record.get("recovery_pending_approvals"))
        state = _safe_text(record.get("recovery_state"))
        summary = _safe_text(record.get("recovery_summary"))
        last_activity = _safe_text(record.get("recovery_last_activity")) or None
        last_user_message = _safe_text(record.get("recovery_last_user_message")) or None
        last_assistant_message = _safe_text(record.get("recovery_last_assistant_message")) or None
        context_pending = bool(record.get("recovery_context_pending"))

        if not context_pending and not state and not summary and not pending:
            busy = bool(record.get("busy", False))
            running_state = _safe_text(record.get("running_state")) or None
            fallback_pending = self.pending_approvals_from_raw(record.get("pending_approvals"))
            fallback = self.build_session_recovery_projection(
                transcript=transcript,
                origin_surface=record.get("origin_surface"),
                active_surface=record.get("active_surface") or record.get("origin_surface"),
                reply_enabled=bool(record.get("reply_enabled", False)),
                channel_type=normalize_channel_type(record.get("channel_type")),
                busy=busy,
                running_state=running_state,
                pending_approvals=fallback_pending,
                persisted_record=True,
            )
            if _safe_text(fallback.state).lower() != "interrupted":
                return None
            return fallback.to_transport()

        normalized_state = state or "interrupted"
        normalized_summary = summary or "interrupted after restart"
        return SessionRecoveryProjection(
            state=normalized_state,
            summary=normalized_summary,
            last_activity=last_activity or self.last_activity_summary(transcript),
            last_user_message=last_user_message or self.last_role_preview(transcript, role="user"),
            last_assistant_message=last_assistant_message or self.last_role_preview(transcript, role="assistant"),
            pending_approvals=tuple(self.build_pending_approval_projections(pending)),
        ).to_transport()

    def stored_recovery_snapshot_from_session(
        self,
        session: "MainAgentSessionState",
    ) -> MainAgentSessionRecoverySnapshot | None:
        if not bool(session.projection.recovery_context_pending):
            return None
        pending = self.pending_approvals_from_raw(session.projection.recovery_pending_approvals)
        state = _safe_text(session.projection.recovery_state) or "interrupted"
        summary = _safe_text(session.projection.recovery_summary) or "interrupted after restart"
        return SessionRecoveryProjection(
            state=state,
            summary=summary,
            last_activity=_safe_text(session.projection.recovery_last_activity)
            or self.last_activity_summary(session.transcript_state.transcript),
            last_user_message=_safe_text(session.projection.recovery_last_user_message)
            or self.last_role_preview(session.transcript_state.transcript, role="user"),
            last_assistant_message=_safe_text(session.projection.recovery_last_assistant_message)
            or self.last_role_preview(session.transcript_state.transcript, role="assistant"),
            pending_approvals=tuple(self.build_pending_approval_projections(pending)),
        ).to_transport()

    def build_session_recovery_snapshot(
        self,
        *,
        transcript: Sequence["MainAgentSessionTranscriptEntry"],
        origin_surface: str | None,
        active_surface: str | None,
        reply_enabled: bool,
        channel_type: str | None,
        busy: bool,
        running_state: str | None,
        pending_approvals: Sequence[dict[str, Any]] | None,
        persisted_record: bool,
    ) -> MainAgentSessionRecoverySnapshot:
        return self.build_session_recovery_projection(
            transcript=transcript,
            origin_surface=origin_surface,
            active_surface=active_surface,
            reply_enabled=reply_enabled,
            channel_type=channel_type,
            busy=busy,
            running_state=running_state,
            pending_approvals=pending_approvals,
            persisted_record=persisted_record,
        ).to_transport()

    @staticmethod
    def build_remote_recovery_text(
        *,
        session_id: str | None,
        origin_surface: str | None,
        active_surface: str | None,
        reply_enabled: bool,
        recovery: SessionRecoveryProjection | None,
        pending_approvals: Sequence[SessionPendingApprovalProjection] | None,
        pending_skill_reload: bool,
        pending_skill_reload_reason: str | None,
    ) -> str:
        return SessionRecoveryFeedbackService.build_remote_recovery_text(
            session_id=session_id,
            origin_surface=origin_surface,
            active_surface=active_surface,
            reply_enabled=reply_enabled,
            recovery=recovery,
            pending_approvals=pending_approvals,
            pending_skill_reload=pending_skill_reload,
            pending_skill_reload_reason=pending_skill_reload_reason,
        )

    def _snapshot_builder(self) -> RuntimeSessionSnapshotBuilder:
        return RuntimeSessionSnapshotBuilder(
            normalize_surface=self.normalize_surface,
            normalize_model_source=self.normalize_model_source,
            normalize_context_policy_payload=self.normalize_context_policy_payload,
            normalize_prepared_context_payload=self.normalize_prepared_context_payload,
            normalize_prepared_context_diagnostics_payload=self.normalize_prepared_context_diagnostics_payload,
            build_memory_diagnostics_for_session=self.build_memory_diagnostics_for_session,
            build_memory_diagnostics_from_record=self.build_memory_diagnostics_from_record,
            build_sandbox_diagnostics_for_session=self.build_sandbox_diagnostics_for_session,
            build_sandbox_diagnostics_from_record=self.build_sandbox_diagnostics_from_record,
            snapshot_runtime_task_memory_payload=(
                self.snapshot_runtime_task_memory_payload or self._empty_runtime_memory_payload
            ),
            snapshot_workspace_shared_runtime_task_memory_payload=(
                self.snapshot_workspace_shared_runtime_task_memory_payload or self._empty_runtime_memory_payload
            ),
            session_token_usage=self.session_token_usage,
            session_token_limit=self.session_token_limit,
            record_token_usage=self.record_token_usage,
            record_token_limit=self.record_token_limit,
            transcript_entries_from_record=self.transcript_entries_from_record,
            agent_messages=self._agent_messages,
            serialize_agent_messages=self.serialize_agent_messages or self._default_serialize_agent_messages,
        )

    @staticmethod
    def _empty_runtime_memory_payload(**_kwargs: Any) -> dict[str, Any]:
        return {}

    @staticmethod
    def _agent_messages(agent: Any) -> list[Any]:
        return list(getattr(agent, "messages", None) or [])

    @staticmethod
    def _default_serialize_agent_messages(messages: Sequence[Any]) -> list[dict[str, Any]]:
        serialized: list[dict[str, Any]] = []
        for item in messages or []:
            if hasattr(item, "model_dump"):
                payload = item.model_dump()
            elif isinstance(item, dict):
                payload = dict(item)
            elif hasattr(item, "__dict__"):
                payload = dict(vars(item))
            else:
                payload = {"role": "assistant", "content": str(item)}
            serialized.append(
                {
                    "role": payload.get("role", "assistant"),
                    "content": payload.get("content", ""),
                    "thinking": payload.get("thinking"),
                    "tool_calls": payload.get("tool_calls"),
                    "tool_call_id": payload.get("tool_call_id"),
                    "name": payload.get("name"),
                }
            )
        return serialized

    @staticmethod
    def build_session_message_projection(entry: "MainAgentSessionTranscriptEntry") -> SessionMessageProjection:
        return SessionMessageProjection(
            index=entry.index,
            role=entry.role,
            content=entry.content,
            surface=entry.surface,
            created_at=_to_utc_iso(entry.created_at),
            channel_type=entry.channel_type,
            conversation_id=entry.conversation_id,
            sender_id=entry.sender_id,
            metadata=dict(entry.metadata) if entry.metadata else None,
        )

    @classmethod
    def build_session_message(cls, entry: "MainAgentSessionTranscriptEntry") -> MainAgentSessionMessage:
        return cls.build_session_message_projection(entry).to_transport()

    def build_session_recovery_projection(
        self,
        *,
        transcript: Sequence["MainAgentSessionTranscriptEntry"],
        origin_surface: str | None,
        active_surface: str | None,
        reply_enabled: bool,
        channel_type: str | None,
        busy: bool,
        running_state: str | None,
        pending_approvals: Sequence[dict[str, Any]] | None,
        persisted_record: bool,
    ) -> SessionRecoveryProjection:
        normalized_origin = self.normalize_surface(origin_surface)
        normalized_active = self.normalize_surface(active_surface or origin_surface)
        normalized_running_state = _safe_text(running_state)
        normalized_pending = self.pending_approvals_from_raw(list(pending_approvals or []))

        state = "idle"
        summary = "idle"
        if persisted_record and normalized_pending:
            state = "interrupted"
            if len(normalized_pending) == 1:
                summary = f"interrupted after restart: approval pending for {normalized_pending[0]['tool_name']}"
            else:
                summary = f"interrupted after restart: {len(normalized_pending)} approvals pending"
        elif persisted_record and (busy or normalized_running_state):
            state = "interrupted"
            summary = (
                f"interrupted after restart: {normalized_running_state}"
                if normalized_running_state
                else "interrupted after restart"
            )
        elif busy:
            state = "running"
            summary = normalized_running_state or f"{normalized_active} request running"
        elif normalized_active != normalized_origin:
            state = "handoff"
            summary = f"active on {normalized_active}; origin {normalized_origin}"
        elif reply_enabled and _safe_text(channel_type):
            state = "reply_enabled"
            summary = f"replying via {_safe_text(channel_type).lower()}"

        return SessionRecoveryProjection(
            state=state,
            summary=summary,
            last_activity=self.last_activity_summary(transcript),
            last_user_message=self.last_role_preview(transcript, role="user"),
            last_assistant_message=self.last_role_preview(transcript, role="assistant"),
            pending_approvals=tuple(
                self.build_pending_approval_projections(normalized_pending if persisted_record else [])
            ),
        )

    @classmethod
    def last_activity_summary(
        cls,
        transcript: Sequence["MainAgentSessionTranscriptEntry"],
    ) -> str | None:
        for entry in reversed(list(transcript or [])):
            metadata = dict(entry.metadata) if isinstance(entry.metadata, dict) else {}
            if entry.role == "tool" and metadata.get("kind") == "activity":
                items = metadata.get("activity_items")
                if isinstance(items, list) and items:
                    item = items[-1]
                    label = cls._activity_label(item.get("label", "activity"))
                    detail = _safe_text(item.get("detail")) or "running"
                    preview = _safe_text(item.get("preview"))
                    output_summary = _safe_text(item.get("output_summary"))
                    parts = [f"{label} {detail}"]
                    if preview:
                        parts.append(preview)
                    if output_summary and label == "shell":
                        parts.append(output_summary)
                    return " | ".join(part for part in parts if part).strip() or None
                text = _safe_text(entry.content)
                if text:
                    return text
            if metadata.get("kind") == "command":
                command = _safe_text(metadata.get("command")) or "command"
                command_summary = _safe_text(metadata.get("summary")) or _safe_text(entry.content) or "applied"
                return f"{command} | {command_summary}"
        return None

    @staticmethod
    def last_role_preview(
        transcript: Sequence["MainAgentSessionTranscriptEntry"],
        *,
        role: str,
        limit: int = 160,
    ) -> str | None:
        normalized_role = _safe_text(role).lower()
        for entry in reversed(list(transcript or [])):
            if _safe_text(entry.role).lower() != normalized_role:
                continue
            text = _safe_text(entry.content)
            if not text:
                continue
            if len(text) <= limit:
                return text
            return text[: limit - 3] + "..."
        return None

    @staticmethod
    def _activity_label(value: str) -> str:
        normalized = _safe_text(value).lower().replace("_", "-")
        if normalized in {"bash", "powershell", "shell", "shell-command"}:
            return "shell"
        if normalized.startswith("bash-"):
            return normalized.replace("bash-", "shell-", 1)
        return normalized or "activity"


__all__ = ["RuntimeSessionReadModelBuilder"]
