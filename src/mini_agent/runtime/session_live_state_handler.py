"""Live session state / transcript mutations extracted from the runtime manager."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Callable
from uuid import uuid4

from fastapi import HTTPException

from mini_agent.runtime.interaction_surface import (
    normalize_surface_label,
    resolve_interaction_binding,
)

if TYPE_CHECKING:
    from pathlib import Path

    from mini_agent.agent import Agent
    from mini_agent.interfaces import MainAgentSessionRecoverySnapshot
    from mini_agent.runtime.session_state import (
        MainAgentSessionState,
        MainAgentSessionTranscriptEntry,
    )


def _safe_text(value: object) -> str:
    return " ".join(str(value or "").split())


@dataclass(slots=True)
class RuntimeSessionLiveStateHandler:
    build_memory_diagnostics_for_session: Callable[["MainAgentSessionState"], dict[str, Any]]
    agent_knowledge_base_enabled: Callable[[Any], bool]
    clear_runtime_task_memory_namespace: Callable[["Path", str], bool]
    stored_recovery_snapshot_from_session: Callable[
        ["MainAgentSessionState"],
        "MainAgentSessionRecoverySnapshot | None",
    ]

    @staticmethod
    def normalize_pending_approval(item: Any) -> dict[str, Any] | None:
        if not isinstance(item, dict):
            return None
        token = _safe_text(item.get("token"))
        tool_name = _safe_text(item.get("tool_name")) or "tool"
        if not token:
            return None
        return {
            "token": token,
            "tool_name": tool_name,
            "arguments": dict(item.get("arguments")) if isinstance(item.get("arguments"), dict) else {},
            "kind": _safe_text(item.get("kind")) or None,
            "reason": _safe_text(item.get("reason")) or None,
            "cache_key": _safe_text(item.get("cache_key")) or None,
            "can_escalate": bool(item.get("can_escalate", False)),
            "step": max(0, int(item.get("step") or 0)),
        }

    @classmethod
    def pending_approvals_from_raw(cls, raw_items: Any) -> list[dict[str, Any]]:
        if not isinstance(raw_items, list):
            return []
        approvals: list[dict[str, Any]] = []
        for item in raw_items:
            normalized = cls.normalize_pending_approval(item)
            if normalized is not None:
                approvals.append(normalized)
        return approvals

    def bind_surface(
        self,
        session: "MainAgentSessionState",
        *,
        surface: str | None,
        channel_type: str | None = None,
        conversation_id: str | None = None,
        sender_id: str | None = None,
        reply_enabled: bool | None = None,
        now_utc: datetime | None = None,
    ) -> None:
        binding = self._resolve_session_binding(
            session,
            surface=surface,
            channel_type=channel_type,
            conversation_id=conversation_id,
            sender_id=sender_id,
        )
        normalized_surface = self._resolved_surface_label(
            session,
            binding=binding,
            fallback_surface=surface,
        )
        if not str(session.projection.origin_surface or "").strip():
            session.projection.origin_surface = normalized_surface
        session.projection.active_surface = normalized_surface
        normalized_channel = binding.channel_type
        if normalized_channel:
            session.projection.channel_type = normalized_channel
        if binding.conversation_id:
            session.projection.conversation_id = binding.conversation_id
        if binding.sender_id:
            session.projection.sender_id = binding.sender_id
        if reply_enabled is not None:
            session.projection.reply_enabled = bool(reply_enabled)
        else:
            session.projection.reply_enabled = bool(
                session.projection.channel_type
                and session.projection.conversation_id
                and (
                    normalized_surface == session.projection.channel_type
                    or (
                        normalized_surface == "remote"
                        and binding.remote_channel is not None
                        and binding.remote_channel == session.projection.channel_type
                    )
                )
            )
        session.touch(now_utc=now_utc)

    def append_transcript(
        self,
        session: "MainAgentSessionState",
        *,
        role: str,
        content: str,
        surface: str,
        metadata: dict[str, Any] | None = None,
        channel_type: str | None = None,
        conversation_id: str | None = None,
        sender_id: str | None = None,
        now_utc: datetime | None = None,
    ) -> "MainAgentSessionTranscriptEntry | None":
        from mini_agent.runtime.session_state import MainAgentSessionTranscriptEntry

        text = str(content or "")
        normalized_metadata = dict(metadata) if isinstance(metadata, dict) else {}
        if not text.strip() and not normalized_metadata:
            return None
        binding = self._resolve_session_binding(
            session,
            surface=surface,
            channel_type=channel_type,
            conversation_id=conversation_id,
            sender_id=sender_id,
        )
        created_at = (now_utc or datetime.now(timezone.utc)).astimezone(timezone.utc)
        entry = MainAgentSessionTranscriptEntry(
            index=session.transcript_state.next_transcript_index,
            role=str(role or "").strip().lower() or "assistant",
            content=text,
            surface=self._resolved_surface_label(
                session,
                binding=binding,
                fallback_surface=surface,
            ),
            created_at=created_at,
            channel_type=binding.channel_type,
            conversation_id=binding.conversation_id,
            sender_id=binding.sender_id,
            metadata=normalized_metadata,
        )
        session.transcript_state.transcript.append(entry)
        session.transcript_state.next_transcript_index += 1
        return entry

    def ensure_activity_transcript_entry(
        self,
        session: "MainAgentSessionState",
        *,
        surface: str,
        channel_type: str | None = None,
        conversation_id: str | None = None,
        sender_id: str | None = None,
        now_utc: datetime | None = None,
    ) -> "MainAgentSessionTranscriptEntry":
        current_turn_id = _safe_text(session.transcript_state.current_turn_id)
        if current_turn_id:
            for entry in reversed(session.transcript_state.transcript):
                if entry.role != "tool":
                    continue
                metadata = entry.metadata if isinstance(entry.metadata, dict) else {}
                if metadata.get("kind") != "activity":
                    continue
                if _safe_text(metadata.get("turn_id")) == current_turn_id:
                    return entry
        entry = self.append_transcript(
            session,
            role="tool",
            content="",
            surface=surface,
            metadata={
                "kind": "activity",
                "activity_items": [],
                "threads_visible": True,
                **({"turn_id": current_turn_id} if current_turn_id else {}),
            },
            channel_type=channel_type,
            conversation_id=conversation_id,
            sender_id=sender_id,
            now_utc=now_utc,
        )
        if entry is None:  # pragma: no cover - defensive
            raise RuntimeError("Failed to create activity transcript entry.")
        return entry

    def mark_turn_started(
        self,
        session: "MainAgentSessionState",
        *,
        surface: str | None,
        detail: str | None = None,
        now_utc: datetime | None = None,
    ) -> None:
        normalized_surface = normalize_surface_label(
            surface or session.projection.active_surface or session.projection.origin_surface
        )
        session.projection.busy = True
        session.transcript_state.current_turn_id = uuid4().hex
        session.runtime.cancel_event = asyncio.Event()
        session.runtime.pending_approvals = []
        session.runtime.pending_approval_waiters.clear()
        session.projection.running_state = _safe_text(detail) or f"{normalized_surface} request running"
        session.touch(now_utc=now_utc)

    def mark_turn_finished(
        self,
        session: "MainAgentSessionState",
        *,
        now_utc: datetime | None = None,
    ) -> None:
        session.projection.busy = False
        session.projection.running_state = ""
        session.transcript_state.current_turn_id = None
        session.runtime.cancel_event = None
        session.runtime.pending_approvals = []
        session.runtime.pending_approval_waiters.clear()
        session.touch(now_utc=now_utc)

    def record_message(
        self,
        session: "MainAgentSessionState",
        *,
        role: str,
        content: str,
        surface: str | None,
        metadata: dict[str, Any] | None = None,
        channel_type: str | None = None,
        conversation_id: str | None = None,
        sender_id: str | None = None,
        now_utc: datetime | None = None,
    ) -> None:
        now = (now_utc or datetime.now(timezone.utc)).astimezone(timezone.utc)
        binding = self._resolve_session_binding(
            session,
            surface=surface,
            channel_type=channel_type,
            conversation_id=conversation_id,
            sender_id=sender_id,
        )
        self.bind_surface(
            session,
            surface=binding.surface,
            channel_type=binding.channel_type,
            conversation_id=binding.conversation_id,
            sender_id=binding.sender_id,
            now_utc=now,
        )
        self.append_transcript(
            session,
            role=role,
            content=content,
            surface=self._resolved_surface_label(
                session,
                binding=binding,
                fallback_surface=surface,
            ),
            metadata=metadata,
            channel_type=binding.channel_type,
            conversation_id=binding.conversation_id,
            sender_id=binding.sender_id,
            now_utc=now,
        )
        session.touch(now_utc=now)

    def record_activity(
        self,
        session: "MainAgentSessionState",
        *,
        label: str,
        detail: str,
        surface: str | None,
        activity_id: str | None = None,
        preview: str = "",
        output_text: str = "",
        state: str = "",
        channel_type: str | None = None,
        conversation_id: str | None = None,
        sender_id: str | None = None,
        now_utc: datetime | None = None,
    ) -> dict[str, Any]:
        now = (now_utc or datetime.now(timezone.utc)).astimezone(timezone.utc)
        binding = self._resolve_session_binding(
            session,
            surface=surface,
            channel_type=channel_type,
            conversation_id=conversation_id,
            sender_id=sender_id,
        )
        normalized_surface = self._resolved_surface_label(
            session,
            binding=binding,
            fallback_surface=surface,
        )
        self.bind_surface(
            session,
            surface=binding.surface,
            channel_type=binding.channel_type,
            conversation_id=binding.conversation_id,
            sender_id=binding.sender_id,
            now_utc=now,
        )
        entry = self.ensure_activity_transcript_entry(
            session,
            surface=normalized_surface,
            channel_type=binding.channel_type,
            conversation_id=binding.conversation_id,
            sender_id=binding.sender_id,
            now_utc=now,
        )
        metadata = entry.metadata
        items = metadata.get("activity_items")
        if not isinstance(items, list):
            items = []
            metadata["activity_items"] = items
        metadata["kind"] = "activity"
        metadata["threads_visible"] = True
        if session.transcript_state.current_turn_id:
            metadata["turn_id"] = session.transcript_state.current_turn_id

        normalized_label = self._activity_label(label)
        normalized_detail = self._activity_detail(normalized_label, detail)
        normalized_preview = _safe_text(preview)
        normalized_output = str(output_text or "").strip()
        normalized_state = _safe_text(state).lower()
        item_key = _safe_text(activity_id)

        target: dict[str, Any] | None = None
        if item_key:
            for item in items:
                if _safe_text(item.get("id")) == item_key:
                    target = item
                    break
        if target is None:
            target = {
                "id": item_key or f"activity-{len(items) + 1}",
                "label": normalized_label,
                "detail": normalized_detail,
                "preview": normalized_preview,
                "output_text": normalized_output,
                "output_summary": self._activity_output_summary(normalized_output),
                "state": normalized_state,
            }
            items.append(target)
        else:
            target["label"] = normalized_label
            target["detail"] = normalized_detail
            if normalized_preview:
                target["preview"] = normalized_preview
            if normalized_output:
                target["output_text"] = normalized_output
                target["output_summary"] = self._activity_output_summary(normalized_output)
            if normalized_state:
                target["state"] = normalized_state

        entry.created_at = now
        entry.surface = normalized_surface
        if binding.channel_type:
            entry.channel_type = binding.channel_type
        if binding.conversation_id:
            entry.conversation_id = binding.conversation_id
        if binding.sender_id:
            entry.sender_id = binding.sender_id
        session.touch(now_utc=now)
        return dict(target)

    def record_pending_approval(
        self,
        session: "MainAgentSessionState",
        *,
        payload: dict[str, Any],
        future: asyncio.Future[bool | None],
        now_utc: datetime | None = None,
    ) -> dict[str, Any]:
        normalized = self.normalize_pending_approval(payload)
        if normalized is None:
            raise HTTPException(status_code=400, detail="Invalid pending approval payload.")
        token = normalized["token"]
        existing_index = next(
            (
                index
                for index, item in enumerate(session.runtime.pending_approvals)
                if _safe_text(item.get("token")) == token
            ),
            None,
        )
        if existing_index is None:
            session.runtime.pending_approvals.append(normalized)
        else:
            session.runtime.pending_approvals[existing_index] = normalized
        session.runtime.pending_approval_waiters[token] = future
        session.touch(now_utc=now_utc)
        return dict(normalized)

    def clear_pending_approval(
        self,
        session: "MainAgentSessionState",
        *,
        token: str | None = None,
        now_utc: datetime | None = None,
    ) -> None:
        normalized_token = _safe_text(token)
        if not normalized_token:
            session.runtime.pending_approvals = []
            session.runtime.pending_approval_waiters.clear()
            session.touch(now_utc=now_utc)
            return
        session.runtime.pending_approvals = [
            item
            for item in session.runtime.pending_approvals
            if _safe_text(item.get("token")) != normalized_token
        ]
        session.runtime.pending_approval_waiters.pop(normalized_token, None)
        session.touch(now_utc=now_utc)

    def build_recovery_turn_context(
        self,
        session: "MainAgentSessionState",
    ) -> dict[str, Any] | None:
        snapshot = self.stored_recovery_snapshot_from_session(session)
        if snapshot is None:
            return None
        payload = snapshot.model_dump()
        payload["resume_strategy"] = "next_message"
        payload["continue_hint"] = "Continue from the interrupted shared-session task using restored context."
        if payload.get("pending_approvals"):
            payload["approval_hint"] = "Pending approvals from before restart were lost and must be re-evaluated."
        return payload

    def clear_recovery_context(
        self,
        session: "MainAgentSessionState",
        *,
        now_utc: datetime | None = None,
    ) -> None:
        self._clear_recovery_context(session)
        session.touch(now_utc=now_utc)

    def reset_runtime_state(
        self,
        session: "MainAgentSessionState",
        *,
        clear_runtime_task_memory: bool,
    ) -> None:
        self._reset_agent_messages(session.runtime.agent)
        if clear_runtime_task_memory:
            self.clear_runtime_task_memory_namespace(
                session.workspace_dir,
                session.session_id,
            )
        session.transcript_state.current_turn_id = None
        session.runtime.cancel_event = None
        session.runtime.pending_approvals = []
        for future in list(session.runtime.pending_approval_waiters.values()):
            if not future.done():
                future.set_result(None)
        session.runtime.pending_approval_waiters.clear()
        self._clear_recovery_context(session)
        session.projection.last_prepared_context = {}
        session.projection.prepared_context_diagnostics = {}
        session.projection.busy = False
        session.projection.running_state = ""
        session.projection.knowledge_base_enabled = self.agent_knowledge_base_enabled(session.runtime.agent)
        session.projection.memory_diagnostics = self.build_memory_diagnostics_for_session(session)

    @staticmethod
    def _clear_recovery_context(session: "MainAgentSessionState") -> None:
        session.projection.recovery_context_pending = False
        session.projection.recovery_state = ""
        session.projection.recovery_summary = ""
        session.projection.recovery_last_activity = None
        session.projection.recovery_last_user_message = None
        session.projection.recovery_last_assistant_message = None
        session.projection.recovery_pending_approvals = []

    @staticmethod
    def _reset_agent_messages(agent: "Agent | None") -> None:
        if agent is None:
            return
        messages = getattr(agent, "messages", None)
        if isinstance(messages, list) and messages:
            agent.messages = [messages[0]]
        if hasattr(agent, "api_total_tokens"):
            agent.api_total_tokens = 0
        reset_runtime_state = getattr(agent, "reset_ephemeral_runtime_state", None)
        if callable(reset_runtime_state):
            reset_runtime_state()
            return
        if hasattr(agent, "last_prepared_turn_context"):
            agent.last_prepared_turn_context = None
        if hasattr(agent, "prepared_context_diagnostics"):
            agent.prepared_context_diagnostics = {}
        if hasattr(agent, "last_memory_automation"):
            agent.last_memory_automation = {}
        if hasattr(agent, "last_runtime_task_memory"):
            agent.last_runtime_task_memory = {}

    @staticmethod
    def _activity_label(value: str) -> str:
        normalized = _safe_text(value).lower().replace("_", "-")
        if normalized in {"bash", "powershell", "shell", "shell-command"}:
            return "shell"
        if normalized.startswith("bash-"):
            return normalized.replace("bash-", "shell-", 1)
        return normalized or "activity"

    @staticmethod
    def _activity_detail(label: str, detail: str) -> str:
        normalized_detail = _safe_text(detail)
        if label != "thinking":
            return normalized_detail or "running"
        lowered = normalized_detail.lower()
        if not lowered:
            return "thinking"
        if lowered == "starting run":
            return "starting"
        if "planned" in lowered:
            return "planning"
        if "preparing final response" in lowered:
            return "drafting"
        if lowered == "response ready":
            return "ready"
        if lowered == "agent unavailable":
            return "agent unavailable"
        if lowered == "turn limit reached":
            return "turn limit"
        if lowered == "cancelled":
            return "cancelled"
        if lowered in {"run failed", "exception raised"}:
            return "failed"
        return lowered

    @staticmethod
    def _activity_output_summary(output_text: str) -> str:
        normalized = str(output_text or "").strip()
        if not normalized:
            return ""
        non_empty = [line.strip() for line in normalized.splitlines() if line.strip()]
        if not non_empty:
            return ""
        summary_lines = [
            line
            for line in non_empty
            if not (line.startswith("[") and "]" in line[:20])
        ] or non_empty
        first = summary_lines[0]
        if len(first) > 68:
            first = f"{first[:65]}..."
        remaining = len(summary_lines) - 1
        if remaining > 0:
            return f"{first} (+{remaining} more line(s))"
        return first

    @staticmethod
    def _resolved_surface_label(
        session: "MainAgentSessionState",
        *,
        binding: Any,
        fallback_surface: str | None,
    ) -> str:
        current_surface = str(
            session.projection.active_surface or session.projection.origin_surface or ""
        ).strip()
        if getattr(binding, "surface", None):
            return str(binding.surface)
        if current_surface:
            return current_surface
        return normalize_surface_label(fallback_surface)

    @staticmethod
    def _resolve_session_binding(
        session: "MainAgentSessionState",
        *,
        surface: str | None,
        channel_type: str | None,
        conversation_id: str | None = None,
        sender_id: str | None = None,
    ):
        default_surface = str(session.projection.active_surface or session.projection.origin_surface or "").strip() or None
        return resolve_interaction_binding(
            surface=surface,
            channel_type=channel_type,
            conversation_id=conversation_id,
            sender_id=sender_id,
            default_surface=default_surface,
        )


__all__ = [
    "RuntimeSessionLiveStateHandler",
]
