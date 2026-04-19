"""Turn-scope lifecycle ownership for managed runtime sessions."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Awaitable, Callable
from uuid import uuid4

from mini_agent.agent_core.contracts.run_control_state import RunControlMode
from mini_agent.runtime.live_control.run_control_store import RuntimeSessionRunControlStore
from mini_agent.runtime.live_control.session_pending_approval_state_handler import (
    RuntimeSessionPendingApprovalStateHandler,
)
from mini_agent.runtime.live_control.session_recovery_reset_handler import (
    RuntimeSessionRecoveryResetHandler,
)
from mini_agent.runtime.live_control.session_transcript_state_handler import (
    RuntimeSessionTranscriptStateHandler,
)
from mini_agent.runtime.support.interaction_surface import normalize_surface_label

if TYPE_CHECKING:
    from pathlib import Path

    from mini_agent.interfaces.agent import MainAgentSessionRecoverySnapshot
    from mini_agent.session.store_records import MainAgentSessionState


def _safe_text(value: object) -> str:
    return " ".join(str(value or "").split())


@dataclass(slots=True)
class RuntimeSessionTurnScopeHandler:
    transcript_state: RuntimeSessionTranscriptStateHandler | None = None
    build_memory_diagnostics_for_session: Callable[["MainAgentSessionState"], dict[str, Any]] | None = None
    agent_knowledge_base_enabled: Callable[[Any], bool] | None = None
    clear_runtime_task_memory_namespace: Callable[["Path", str], bool] | None = None
    stored_recovery_snapshot_from_session: Callable[
        ["MainAgentSessionState"],
        "MainAgentSessionRecoverySnapshot | None",
    ] | None = None
    run_control_store: RuntimeSessionRunControlStore | None = None
    pending_approval_state: RuntimeSessionPendingApprovalStateHandler | None = None
    recovery_reset: RuntimeSessionRecoveryResetHandler | None = None
    restore_prepared_context_state_mutation: Callable[["MainAgentSessionState"], None] | None = None
    capture_prepared_context_state_mutation: Callable[["MainAgentSessionState"], None] | None = None
    ensure_agent_model_binding_for_turn_fn: Callable[["MainAgentSessionState"], Awaitable[bool]] | None = None
    apply_pending_session_skill_reload_fn: Callable[["MainAgentSessionState"], Awaitable[bool]] | None = None
    persist_session_fn: Callable[["MainAgentSessionState"], None] | None = None

    @staticmethod
    def normalize_pending_approval(item: Any) -> dict[str, Any] | None:
        return RuntimeSessionPendingApprovalStateHandler.normalize_pending_approval(item)

    @classmethod
    def pending_approvals_from_raw(cls, raw_items: Any) -> list[dict[str, Any]]:
        return RuntimeSessionPendingApprovalStateHandler.pending_approvals_from_raw(raw_items)

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
        self._run_control_store().begin_turn(
            session,
            surface=normalized_surface,
            detail=detail,
        )
        session.projection.running_state = _safe_text(detail) or f"{normalized_surface} request running"
        session.touch(now_utc=now_utc)
        self._persist_session(session)

    def mark_turn_finished(
        self,
        session: "MainAgentSessionState",
        *,
        now_utc: datetime | None = None,
    ) -> None:
        control_state = self._run_control_store().current_control_state(session)
        running_state = _safe_text(session.projection.running_state) or None
        pending_approvals = self._run_control_store().pending_approval_payloads(session)
        session.projection.busy = False
        session.projection.running_state = ""
        session.transcript_state.current_turn_id = None
        if (
            control_state.control_mode is RunControlMode.INTERRUPT_REQUESTED
            and not control_state.cancel_requested
        ):
            self._run_control_store().pause_turn(
                session,
                reason=running_state or control_state.last_pause_reason,
            )
            self._recovery_reset_handler().apply_interrupted_recovery(
                session,
                summary=self._interrupt_recovery_summary(
                    running_state=running_state,
                    pending_approvals=pending_approvals,
                ),
                last_activity=running_state,
                pending_approvals=pending_approvals,
                now_utc=now_utc,
            )
            self._persist_session(session)
            return
        self._run_control_store().finish_turn(session)
        session.touch(now_utc=now_utc)
        self._persist_session(session)

    def record_message(self, *args, **kwargs) -> None:  # noqa: ANN002, ANN003
        self._transcript_state_handler().record_message(*args, **kwargs)

    def record_activity(self, *args, **kwargs) -> dict[str, Any]:  # noqa: ANN002, ANN003
        return self._transcript_state_handler().record_activity(*args, **kwargs)

    def record_pending_approval(
        self,
        session: "MainAgentSessionState",
        *,
        payload: dict[str, Any],
        future: asyncio.Future[bool | None],
        now_utc: datetime | None = None,
    ) -> dict[str, Any]:
        normalized = self._pending_approval_state_handler().record_pending_approval(
            session,
            payload=payload,
            future=future,
            now_utc=now_utc,
        )
        self._persist_session(session)
        return normalized

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
        self._persist_session(session)

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
        self._persist_session(session)

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
        self._persist_session(session)

    async def enter(
        self,
        session: "MainAgentSessionState",
        *,
        surface: str | None,
        channel_type: str | None,
        conversation_id: str | None,
        sender_id: str | None,
        user_message: str,
        running_detail: str,
    ) -> dict[str, Any] | None:
        await session.runtime.lock.acquire()
        try:
            self._transcript_state_handler().bind_surface(
                session,
                surface=surface,
                channel_type=channel_type,
                conversation_id=conversation_id,
                sender_id=sender_id,
            )
            await self._ensure_agent_model_binding_for_turn(session)
            await self._apply_pending_session_skill_reload(session)
            recovery_context = self.build_recovery_turn_context(session)
            self.mark_turn_started(
                session,
                surface=surface,
                detail=running_detail,
            )
            self._transcript_state_handler().record_message(
                session,
                role="user",
                content=user_message,
                surface=surface,
                channel_type=channel_type,
                conversation_id=conversation_id,
                sender_id=sender_id,
            )
            return recovery_context
        except Exception:
            session.runtime.lock.release()
            raise

    async def exit(self, session: "MainAgentSessionState") -> None:
        try:
            self.mark_turn_finished(session)
            await self._apply_pending_session_skill_reload(session)
        finally:
            session.runtime.lock.release()

    @staticmethod
    def touch(session: "MainAgentSessionState") -> None:
        session.touch()

    def restore_prepared_context_state(self, session: "MainAgentSessionState") -> None:
        if callable(self.restore_prepared_context_state_mutation):
            self.restore_prepared_context_state_mutation(session)

    def capture_prepared_context_state(self, session: "MainAgentSessionState") -> None:
        if callable(self.capture_prepared_context_state_mutation):
            self.capture_prepared_context_state_mutation(session)
        self._persist_session(session)

    @staticmethod
    def _interrupt_recovery_summary(
        *,
        running_state: str | None,
        pending_approvals: list[dict[str, Any]],
    ) -> str:
        normalized_running_state = _safe_text(running_state)
        normalized_pending = [
            item for item in list(pending_approvals or []) if isinstance(item, dict)
        ]
        if normalized_pending:
            if len(normalized_pending) == 1:
                tool_name = _safe_text(normalized_pending[0].get("tool_name")) or "tool"
                return f"interrupted after pause request: approval pending for {tool_name}"
            return f"interrupted after pause request: {len(normalized_pending)} approvals pending"
        if normalized_running_state:
            return f"interrupted after pause request: {normalized_running_state}"
        return "interrupted after pause request"

    def _transcript_state_handler(self) -> RuntimeSessionTranscriptStateHandler:
        if self.transcript_state is None:
            self.transcript_state = RuntimeSessionTranscriptStateHandler(
                persist_session_fn=self.persist_session_fn,
            )
        return self.transcript_state

    def _pending_approval_state_handler(self) -> RuntimeSessionPendingApprovalStateHandler:
        if self.pending_approval_state is not None:
            return self.pending_approval_state
        self.pending_approval_state = RuntimeSessionPendingApprovalStateHandler(
            run_control_store=self._run_control_store(),
        )
        return self.pending_approval_state

    def _recovery_reset_handler(self) -> RuntimeSessionRecoveryResetHandler:
        if self.recovery_reset is not None:
            return self.recovery_reset
        self.recovery_reset = RuntimeSessionRecoveryResetHandler(
            refresh_session_diagnostics=self._refresh_session_diagnostics,
            agent_knowledge_base_enabled=self._resolve_agent_knowledge_base_enabled,
            clear_runtime_task_memory_namespace=self._clear_runtime_task_memory_namespace,
            stored_recovery_snapshot_from_session=self._stored_recovery_snapshot_from_session,
            run_control_store=self._run_control_store(),
        )
        return self.recovery_reset

    def _run_control_store(self) -> RuntimeSessionRunControlStore:
        if self.run_control_store is None:
            self.run_control_store = RuntimeSessionRunControlStore()
        return self.run_control_store

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

    def _clear_runtime_task_memory_namespace(
        self,
        workspace_dir: "Path",
        session_id: str,
    ) -> bool:
        if self.clear_runtime_task_memory_namespace is None:
            return False
        return bool(self.clear_runtime_task_memory_namespace(workspace_dir, session_id))

    def _stored_recovery_snapshot_from_session(
        self,
        session: "MainAgentSessionState",
    ) -> "MainAgentSessionRecoverySnapshot | None":
        if self.stored_recovery_snapshot_from_session is None:
            return None
        return self.stored_recovery_snapshot_from_session(session)

    async def _ensure_agent_model_binding_for_turn(
        self,
        session: "MainAgentSessionState",
    ) -> bool:
        if self.ensure_agent_model_binding_for_turn_fn is None:
            return False
        return bool(await self.ensure_agent_model_binding_for_turn_fn(session))

    async def _apply_pending_session_skill_reload(
        self,
        session: "MainAgentSessionState",
    ) -> bool:
        if self.apply_pending_session_skill_reload_fn is None:
            return False
        return bool(await self.apply_pending_session_skill_reload_fn(session))

    def _persist_session(self, session: "MainAgentSessionState") -> None:
        if self.persist_session_fn is None:
            return
        self.persist_session_fn(session)


__all__ = ["RuntimeSessionTurnScopeHandler"]
