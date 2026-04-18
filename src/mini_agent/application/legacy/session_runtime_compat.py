"""Compatibility adapters for routing session-era runtime actions through typed seams."""

from __future__ import annotations

from typing import Any, Protocol

from mini_agent.application.user_services.model_runtime_adapter import AgentModelRuntimeAdapter
from mini_agent.application.ports.run_runtime_port import RunRuntimePort
from mini_agent.application.ports.session_task_port import SessionTaskPort
from mini_agent.interfaces import (
    MainAgentSessionApprovalResponse,
    MainAgentSessionContextResponse,
    MainAgentSessionControlResponse,
    MainAgentSessionMemoryResponse,
    MainAgentSessionModelSelectionResponse,
    MainAgentSessionSkillResponse,
)
from mini_agent.runtime.live_control.run_control_store import (
    CANCEL_REQUESTED_RUNNING_STATE,
    CANCEL_REQUESTED_STATUS,
    CANCELLING_PHASE,
    INTERRUPT_REQUESTED_RUNNING_STATE,
    INTERRUPT_REQUESTED_STATUS,
    INTERRUPTING_PHASE,
    PAUSED_PHASE,
    PAUSED_STATUS,
    RESUME_REQUESTED_STATUS,
    RESUMING_PHASE,
)
from mini_agent.runtime.support.session_backed_run_id import resolve_session_backed_session_id

from .session_agent_runtime_port import SessionAgentRuntimePort
from .session_model_selection_runtime_port import SessionModelSelectionRuntimePort


class SessionTaskCompatibilityRuntimeSupport(Protocol):
    async def get_session_detail(self, session_id: str, *, recent_limit: int = 50) -> Any: ...

    async def cancel_session_turn(
        self,
        session_id: str,
        *,
        reason: str | None = None,
        surface: str | None = None,
        channel_type: str | None = None,
        conversation_id: str | None = None,
        sender_id: str | None = None,
    ) -> Any: ...

    async def resolve_pending_approval(
        self,
        session_id: str,
        *,
        approved: bool,
        token: str | None = None,
        surface: str | None = None,
        channel_type: str | None = None,
        conversation_id: str | None = None,
        sender_id: str | None = None,
    ) -> MainAgentSessionApprovalResponse: ...


class SessionBackedRunRuntimeSupport(SessionTaskCompatibilityRuntimeSupport, Protocol):
    pass


class SessionModelSelectionCompatibilityRuntimeSupport(Protocol):
    async def update_session_model_selection(
        self,
        session_id: str,
        *,
        provider_source: str | None = None,
        provider_id: str | None = None,
        model_id: str | None = None,
        surface: str | None = None,
        channel_type: str | None = None,
        conversation_id: str | None = None,
        sender_id: str | None = None,
    ) -> MainAgentSessionModelSelectionResponse: ...


class SessionAgentCompatibilityRuntimeSupport(Protocol):
    async def update_session_runtime_policy(
        self,
        session_id: str,
        *,
        approval_profile: str | None = None,
        access_level: str | None = None,
        surface: str | None = None,
        channel_type: str | None = None,
        conversation_id: str | None = None,
        sender_id: str | None = None,
    ) -> Any: ...

    async def control_session_context(
        self,
        session_id: str,
        *,
        action: str,
        reason: str | None = None,
        surface: str | None = None,
        channel_type: str | None = None,
        conversation_id: str | None = None,
        sender_id: str | None = None,
    ) -> MainAgentSessionControlResponse: ...

    async def update_session_context_policy(
        self,
        session_id: str,
        *,
        action: str,
        sources: list[str] | None = None,
        max_items: int | None = None,
        max_total_chars: int | None = None,
        max_items_per_source: int | None = None,
        surface: str | None = None,
        channel_type: str | None = None,
        conversation_id: str | None = None,
        sender_id: str | None = None,
    ) -> MainAgentSessionContextResponse: ...

    async def manage_session_memory(
        self,
        session_id: str,
        *,
        action: str,
        engram_id: str | None = None,
        content: str | None = None,
        query: str | None = None,
        day: str | None = None,
        export_format: str | None = None,
        detail_mode: str | None = None,
        surface: str | None = None,
        channel_type: str | None = None,
        conversation_id: str | None = None,
        sender_id: str | None = None,
    ) -> MainAgentSessionMemoryResponse: ...

    async def manage_session_skills(
        self,
        session_id: str,
        *,
        action: str,
        skill_name: str | None = None,
        path: str | None = None,
        query: str | None = None,
        mode: str | None = None,
        surface: str | None = None,
        channel_type: str | None = None,
        conversation_id: str | None = None,
        sender_id: str | None = None,
    ) -> MainAgentSessionSkillResponse: ...


class UnavailableRunRuntimeAdapter:
    """Compatibility placeholder until a real run-runtime port is wired."""

    @staticmethod
    def _unsupported(run_id: str) -> LookupError:
        return LookupError(f"Run-level control is not wired for run {run_id!r}.")

    async def get_run(self, run_id: str) -> Any:
        raise self._unsupported(run_id)


class SessionBackedRunRuntimeAdapter(RunRuntimePort):
    """Transitional run-runtime adapter backed by session runtime truth."""

    def __init__(self, runtime_manager: SessionBackedRunRuntimeSupport) -> None:
        self._runtime_manager = runtime_manager

    async def get_run(self, run_id: str) -> Any:
        direct = getattr(self._runtime_manager, "get_run", None)
        if callable(direct):
            return await direct(run_id)
        session_id = self._require_session_id(run_id)
        detail = await self._runtime_manager.get_session_detail(session_id, recent_limit=1)
        pending_approvals = list(self._detail_value(detail, "pending_approvals", []) or [])
        busy = bool(self._detail_value(detail, "busy", False))
        recovery = self._detail_value(detail, "recovery", None)
        running_state = str(self._detail_value(detail, "running_state", "") or "").strip().lower()
        control_mode = str(self._detail_value(detail, "control_mode", "") or "").strip().lower()
        interrupt_requested = bool(self._detail_value(detail, "interrupt_requested", False))
        cancel_requested = bool(self._detail_value(detail, "cancel_requested", False))
        if (
            cancel_requested
            or control_mode == CANCEL_REQUESTED_STATUS
            or running_state == CANCEL_REQUESTED_RUNNING_STATE
        ):
            status = CANCEL_REQUESTED_STATUS
            phase = CANCELLING_PHASE
        elif (
            interrupt_requested
            or control_mode == INTERRUPT_REQUESTED_STATUS
            or running_state == INTERRUPT_REQUESTED_RUNNING_STATE
        ):
            status = INTERRUPT_REQUESTED_STATUS
            phase = INTERRUPTING_PHASE
        elif control_mode == RESUME_REQUESTED_STATUS:
            status = RESUME_REQUESTED_STATUS
            phase = RESUMING_PHASE
        elif control_mode == "approval_wait":
            status = "waiting"
            phase = "awaiting_approval"
        elif pending_approvals:
            status = "waiting"
            phase = "awaiting_approval"
        elif control_mode == PAUSED_STATUS or recovery is not None:
            status = PAUSED_STATUS
            phase = PAUSED_PHASE
        elif busy:
            status = "running"
            phase = "executing_tools"
        else:
            status = "completed"
            phase = "terminal"
        return {
            "run_id": run_id,
            "session_id": session_id,
            "status": status,
            "phase": phase,
            "busy": busy,
            "waiting_on_approval": bool(pending_approvals),
            "pending_approvals": pending_approvals,
            "active_surface": self._detail_value(detail, "active_surface", None),
            "channel_type": self._detail_value(detail, "channel_type", None),
            "conversation_id": self._detail_value(detail, "conversation_id", None),
            "sender_id": self._detail_value(detail, "sender_id", None),
            "running_state": self._detail_value(detail, "running_state", None),
        }

    async def interrupt_run(
        self,
        run_id: str,
        *,
        reason: str | None = None,
        source: str | None = None,
    ) -> Any:
        direct = getattr(self._runtime_manager, "interrupt_run", None)
        if callable(direct):
            return await direct(run_id, reason=reason, source=source)
        raise LookupError(
            f"Run {run_id!r} does not support interrupt via the current session-runtime compatibility path."
        )

    async def resume_run(
        self,
        run_id: str,
        *,
        resume_token: str | None = None,
        source: str | None = None,
    ) -> Any:
        direct = getattr(self._runtime_manager, "resume_run", None)
        if callable(direct):
            return await direct(run_id, resume_token=resume_token, source=source)
        session_id = self._require_session_id(run_id)
        detail = await self._runtime_manager.get_session_detail(session_id, recent_limit=1)
        pending_approvals = list(self._detail_value(detail, "pending_approvals", []) or [])
        if pending_approvals:
            return await self._runtime_manager.resolve_pending_approval(
                session_id,
                approved=True,
                token=resume_token,
                surface=self._resolve_surface(detail, source=source),
                channel_type=self._detail_value(detail, "channel_type", None),
                conversation_id=self._detail_value(detail, "conversation_id", None),
                sender_id=self._detail_value(detail, "sender_id", None),
            )

        if self._detail_value(detail, "recovery", None) is not None:
            raise LookupError(
                f"Run {run_id!r} is in recovery state and cannot be resumed directly. "
                "Send a new message to continue with recovery context."
            )

        if bool(self._detail_value(detail, "busy", False)):
            raise LookupError(f"Run {run_id!r} is already active and cannot be resumed.")

        raise LookupError(f"Run {run_id!r} is not waiting for resume input.")

    async def cancel_run(
        self,
        run_id: str,
        *,
        reason: str | None = None,
        source: str | None = None,
    ) -> Any:
        direct = getattr(self._runtime_manager, "cancel_run", None)
        if callable(direct):
            return await direct(run_id, reason=reason, source=source)
        session_id = self._require_session_id(run_id)
        detail = await self._runtime_manager.get_session_detail(session_id, recent_limit=1)
        return await self._runtime_manager.cancel_session_turn(
            session_id,
            reason=reason,
            surface=self._resolve_surface(detail, source=source),
            channel_type=self._detail_value(detail, "channel_type", None),
            conversation_id=self._detail_value(detail, "conversation_id", None),
            sender_id=self._detail_value(detail, "sender_id", None),
        )

    async def resolve_approval_wait(
        self,
        run_id: str,
        *,
        approved: bool,
        token: str | None = None,
        source: str | None = None,
        reason: str | None = None,
    ) -> Any:
        direct = getattr(self._runtime_manager, "resolve_approval_wait", None)
        if callable(direct):
            return await direct(
                run_id,
                approved=approved,
                token=token,
                source=source,
                reason=reason,
            )
        _ = reason
        session_id = self._require_session_id(run_id)
        detail = await self._runtime_manager.get_session_detail(session_id, recent_limit=1)
        return await self._runtime_manager.resolve_pending_approval(
            session_id,
            approved=approved,
            token=token,
            surface=self._resolve_surface(detail, source=source),
            channel_type=self._detail_value(detail, "channel_type", None),
            conversation_id=self._detail_value(detail, "conversation_id", None),
            sender_id=self._detail_value(detail, "sender_id", None),
        )

    @staticmethod
    def _detail_value(detail: Any, field: str, default: Any = None) -> Any:
        if isinstance(detail, dict):
            return detail.get(field, default)
        return getattr(detail, field, default)

    @classmethod
    def _resolve_surface(cls, detail: Any, *, source: str | None = None) -> str | None:
        return str(source or cls._detail_value(detail, "active_surface", None) or "").strip() or None

    @staticmethod
    def _require_session_id(run_id: str) -> str:
        session_id = resolve_session_backed_session_id(run_id)
        if session_id is None:
            raise LookupError(f"Run {run_id!r} is not a session-backed run identifier.")
        return session_id


class SessionTaskCompatibilityAdapter(SessionTaskPort):
    """Bridge session-era runtime actions into the run-control compatibility seam."""

    def __init__(self, runtime_manager: SessionTaskCompatibilityRuntimeSupport) -> None:
        self._runtime_manager = runtime_manager

    async def get_session_task(self, session_id: str) -> Any:
        return await self._runtime_manager.get_session_detail(session_id, recent_limit=1)

    async def resolve_run_id_for_session(self, session_id: str) -> str | None:
        _ = session_id
        return None

    async def cancel_session_turn(
        self,
        session_id: str,
        *,
        reason: str | None = None,
        surface: str | None = None,
        channel_type: str | None = None,
        conversation_id: str | None = None,
        sender_id: str | None = None,
    ) -> Any:
        return await self._runtime_manager.cancel_session_turn(
            session_id,
            reason=reason,
            surface=surface,
            channel_type=channel_type,
            conversation_id=conversation_id,
            sender_id=sender_id,
        )

    async def resolve_pending_approval(
        self,
        session_id: str,
        *,
        approved: bool,
        token: str | None = None,
        surface: str | None = None,
        channel_type: str | None = None,
        conversation_id: str | None = None,
        sender_id: str | None = None,
    ) -> MainAgentSessionApprovalResponse:
        return await self._runtime_manager.resolve_pending_approval(
            session_id,
            approved=approved,
            token=token,
            surface=surface,
            channel_type=channel_type,
            conversation_id=conversation_id,
            sender_id=sender_id,
        )


class SessionModelSelectionCompatibilityAdapter(SessionModelSelectionRuntimePort):
    """Bridge session-era model selection actions into the typed model seam."""

    def __init__(self, runtime_manager: SessionModelSelectionCompatibilityRuntimeSupport) -> None:
        self._runtime_manager = runtime_manager

    async def update_session_model_selection(
        self,
        session_id: str,
        *,
        provider_source: str | None = None,
        provider_id: str | None = None,
        model_id: str | None = None,
        surface: str | None = None,
        channel_type: str | None = None,
        conversation_id: str | None = None,
        sender_id: str | None = None,
    ) -> MainAgentSessionModelSelectionResponse:
        return await self._runtime_manager.update_session_model_selection(
            session_id,
            provider_source=provider_source,
            provider_id=provider_id,
            model_id=model_id,
            surface=surface,
            channel_type=channel_type,
            conversation_id=conversation_id,
            sender_id=sender_id,
        )


class SessionAgentCompatibilityAdapter(SessionAgentRuntimePort):
    """Bridge session-era agent actions into the typed agent compatibility seam."""

    def __init__(self, runtime_manager: SessionAgentCompatibilityRuntimeSupport) -> None:
        self._runtime_manager = runtime_manager

    async def update_session_runtime_policy(
        self,
        session_id: str,
        *,
        approval_profile: str | None = None,
        access_level: str | None = None,
        surface: str | None = None,
        channel_type: str | None = None,
        conversation_id: str | None = None,
        sender_id: str | None = None,
    ) -> Any:
        return await self._runtime_manager.update_session_runtime_policy(
            session_id,
            approval_profile=approval_profile,
            access_level=access_level,
            surface=surface,
            channel_type=channel_type,
            conversation_id=conversation_id,
            sender_id=sender_id,
        )

    async def control_session_context(
        self,
        session_id: str,
        *,
        action: str,
        reason: str | None = None,
        surface: str | None = None,
        channel_type: str | None = None,
        conversation_id: str | None = None,
        sender_id: str | None = None,
    ) -> MainAgentSessionControlResponse:
        return await self._runtime_manager.control_session_context(
            session_id,
            action=action,
            reason=reason,
            surface=surface,
            channel_type=channel_type,
            conversation_id=conversation_id,
            sender_id=sender_id,
        )

    async def update_session_context_policy(
        self,
        session_id: str,
        *,
        action: str,
        sources: list[str] | None = None,
        max_items: int | None = None,
        max_total_chars: int | None = None,
        max_items_per_source: int | None = None,
        surface: str | None = None,
        channel_type: str | None = None,
        conversation_id: str | None = None,
        sender_id: str | None = None,
    ) -> MainAgentSessionContextResponse:
        return await self._runtime_manager.update_session_context_policy(
            session_id,
            action=action,
            sources=sources,
            max_items=max_items,
            max_total_chars=max_total_chars,
            max_items_per_source=max_items_per_source,
            surface=surface,
            channel_type=channel_type,
            conversation_id=conversation_id,
            sender_id=sender_id,
        )

    async def manage_session_memory(
        self,
        session_id: str,
        *,
        action: str,
        engram_id: str | None = None,
        content: str | None = None,
        query: str | None = None,
        day: str | None = None,
        export_format: str | None = None,
        detail_mode: str | None = None,
        surface: str | None = None,
        channel_type: str | None = None,
        conversation_id: str | None = None,
        sender_id: str | None = None,
    ) -> MainAgentSessionMemoryResponse:
        return await self._runtime_manager.manage_session_memory(
            session_id,
            action=action,
            engram_id=engram_id,
            content=content,
            query=query,
            day=day,
            export_format=export_format,
            detail_mode=detail_mode,
            surface=surface,
            channel_type=channel_type,
            conversation_id=conversation_id,
            sender_id=sender_id,
        )

    async def manage_session_skills(
        self,
        session_id: str,
        *,
        action: str,
        skill_name: str | None = None,
        path: str | None = None,
        query: str | None = None,
        mode: str | None = None,
        surface: str | None = None,
        channel_type: str | None = None,
        conversation_id: str | None = None,
        sender_id: str | None = None,
    ) -> MainAgentSessionSkillResponse:
        return await self._runtime_manager.manage_session_skills(
            session_id,
            action=action,
            skill_name=skill_name,
            path=path,
            query=query,
            mode=mode,
            surface=surface,
            channel_type=channel_type,
            conversation_id=conversation_id,
            sender_id=sender_id,
        )


__all__ = [
    "AgentModelRuntimeAdapter",
    "SessionBackedRunRuntimeAdapter",
    "SessionAgentCompatibilityAdapter",
    "SessionModelSelectionCompatibilityAdapter",
    "SessionTaskCompatibilityAdapter",
    "UnavailableRunRuntimeAdapter",
]
