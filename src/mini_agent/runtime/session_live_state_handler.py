"""Live session state / transcript mutations extracted from the runtime manager."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Callable
from uuid import uuid4

try:
    from mini_agent.interaction import (
        normalize_surface_label,
        resolve_interaction_binding,
    )
except Exception:  # pragma: no cover - compatibility path for staged interaction extraction
    from mini_agent.runtime.support.interaction_surface import (
        normalize_surface_label,
        resolve_interaction_binding,
    )
from mini_agent.runtime.live_control.session_pending_approval_state_handler import (
    RuntimeSessionPendingApprovalStateHandler,
)
from mini_agent.runtime.session_recovery_reset_handler import (
    RuntimeSessionRecoveryResetHandler,
)

if TYPE_CHECKING:
    from pathlib import Path

    from mini_agent.interfaces import MainAgentSessionRecoverySnapshot
    from mini_agent.runtime.session_state import (
        MainAgentSessionState,
        MainAgentSessionTranscriptEntry,
    )


def _safe_text(value: object) -> str:
    return " ".join(str(value or "").split())


@dataclass(slots=True)
class RuntimeSessionLiveStateHandler:
    build_memory_diagnostics_for_session: Callable[["MainAgentSessionState"], dict[str, Any]] | None = None
    agent_knowledge_base_enabled: Callable[[Any], bool] | None = None
    clear_runtime_task_memory_namespace: Callable[["Path", str], bool] | None = None
    stored_recovery_snapshot_from_session: Callable[
        ["MainAgentSessionState"],
        "MainAgentSessionRecoverySnapshot | None",
    ] | None = None
    pending_approval_state: RuntimeSessionPendingApprovalStateHandler | None = None
    recovery_reset: RuntimeSessionRecoveryResetHandler | None = None

    @staticmethod
    def normalize_pending_approval(item: Any) -> dict[str, Any] | None:
        return RuntimeSessionPendingApprovalStateHandler.normalize_pending_approval(item)

    @classmethod
    def pending_approvals_from_raw(cls, raw_items: Any) -> list[dict[str, Any]]:
        return RuntimeSessionPendingApprovalStateHandler.pending_approvals_from_raw(raw_items)

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
        return self._pending_approval_state_handler().record_pending_approval(
            session,
            payload=payload,
            future=future,
            now_utc=now_utc,
        )

    def clear_pending_approval(
        self,
        session: "MainAgentSessionState",
        *,
        token: str | None = None,
        now_utc: datetime | None = None,
    ) -> None:
        self._pending_approval_state_handler().clear_pending_approval(
            session,
            token=token,
            now_utc=now_utc,
        )

    def build_recovery_turn_context(
        self,
        session: "MainAgentSessionState",
    ) -> dict[str, Any] | None:
        return self._recovery_reset_handler().build_recovery_turn_context(session)

    def clear_recovery_context(
        self,
        session: "MainAgentSessionState",
        *,
        now_utc: datetime | None = None,
    ) -> None:
        self._recovery_reset_handler().clear_recovery_context(
            session,
            now_utc=now_utc,
        )

    def reset_runtime_state(
        self,
        session: "MainAgentSessionState",
        *,
        clear_runtime_task_memory: bool,
    ) -> None:
        self._recovery_reset_handler().reset_runtime_state(
            session,
            clear_runtime_task_memory=clear_runtime_task_memory,
        )

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

    def _pending_approval_state_handler(self) -> RuntimeSessionPendingApprovalStateHandler:
        if self.pending_approval_state is not None:
            return self.pending_approval_state
        return RuntimeSessionPendingApprovalStateHandler()

    def _recovery_reset_handler(self) -> RuntimeSessionRecoveryResetHandler:
        if self.recovery_reset is not None:
            return self.recovery_reset
        return RuntimeSessionRecoveryResetHandler(
            refresh_session_diagnostics=self._refresh_session_diagnostics,
            agent_knowledge_base_enabled=self._resolve_agent_knowledge_base_enabled,
            clear_runtime_task_memory_namespace=self._clear_runtime_task_memory_namespace_compat,
            stored_recovery_snapshot_from_session=self._stored_recovery_snapshot_from_session_compat,
        )

    def _refresh_session_diagnostics(
        self,
        session: "MainAgentSessionState",
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        current_memory = getattr(session.projection, "memory_diagnostics", {})
        memory: dict[str, Any]
        if self.build_memory_diagnostics_for_session is None:
            memory = dict(current_memory) if isinstance(current_memory, dict) else {}
        else:
            payload = self.build_memory_diagnostics_for_session(session)
            memory = dict(payload) if isinstance(payload, dict) else {}
        current_sandbox = getattr(session.projection, "sandbox_diagnostics", {})
        sandbox = dict(current_sandbox) if isinstance(current_sandbox, dict) else {}
        session.projection.memory_diagnostics = dict(memory)
        session.projection.sandbox_diagnostics = dict(sandbox)
        return dict(memory), dict(sandbox)

    def _resolve_agent_knowledge_base_enabled(self, agent: Any) -> bool:
        if self.agent_knowledge_base_enabled is not None:
            return bool(self.agent_knowledge_base_enabled(agent))
        enabled = getattr(agent, "knowledge_base_enabled", None)
        if callable(enabled):
            try:
                return bool(enabled())
            except Exception:
                return False
        return bool(getattr(agent, "_knowledge_base_enabled", False))

    def _clear_runtime_task_memory_namespace_compat(
        self,
        workspace_dir: "Path",
        session_id: str,
    ) -> bool:
        if self.clear_runtime_task_memory_namespace is None:
            return False
        return bool(self.clear_runtime_task_memory_namespace(workspace_dir, session_id))

    def _stored_recovery_snapshot_from_session_compat(
        self,
        session: "MainAgentSessionState",
    ) -> "MainAgentSessionRecoverySnapshot | None":
        if self.stored_recovery_snapshot_from_session is None:
            return None
        return self.stored_recovery_snapshot_from_session(session)


__all__ = [
    "RuntimeSessionLiveStateHandler",
]

