"""Stable owner for session-runtime compatibility adapters."""

from __future__ import annotations

from typing import Any, Protocol

from mini_agent.application.ports.run_runtime_port import RunRuntimePort
from mini_agent.application.ports.session_agent_runtime_port import SessionAgentRuntimePort
from mini_agent.application.ports.session_model_selection_runtime_port import (
    SessionModelSelectionRuntimePort,
)
from mini_agent.application.ports.session_task_port import SessionTaskPort
from mini_agent.interfaces import (
    MainAgentSessionApprovalResponse,
    MainAgentSessionContextResponse,
    MainAgentSessionControlResponse,
    MainAgentSessionMemoryResponse,
    MainAgentSessionModelSelectionResponse,
    MainAgentSessionSkillResponse,
)


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
    async def get_run(self, run_id: str) -> Any: ...

    async def interrupt_run(
        self,
        run_id: str,
        *,
        reason: str | None = None,
        source: str | None = None,
    ) -> Any: ...

    async def resume_run(
        self,
        run_id: str,
        *,
        resume_token: str | None = None,
        source: str | None = None,
    ) -> Any: ...

    async def cancel_run(
        self,
        run_id: str,
        *,
        reason: str | None = None,
        source: str | None = None,
    ) -> Any: ...

    async def resolve_approval_wait(
        self,
        run_id: str,
        *,
        approved: bool,
        token: str | None = None,
        source: str | None = None,
        reason: str | None = None,
    ) -> Any: ...


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
    """Compatibility shell that forwards directly to an explicit run-runtime owner."""

    def __init__(self, runtime_manager: SessionBackedRunRuntimeSupport) -> None:
        self._runtime_manager = runtime_manager

    async def get_run(self, run_id: str) -> Any:
        return await self._require_runtime_method("get_run")(run_id)

    async def interrupt_run(
        self,
        run_id: str,
        *,
        reason: str | None = None,
        source: str | None = None,
    ) -> Any:
        return await self._require_runtime_method("interrupt_run")(run_id, reason=reason, source=source)

    async def resume_run(
        self,
        run_id: str,
        *,
        resume_token: str | None = None,
        source: str | None = None,
    ) -> Any:
        return await self._require_runtime_method("resume_run")(
            run_id,
            resume_token=resume_token,
            source=source,
        )

    async def cancel_run(
        self,
        run_id: str,
        *,
        reason: str | None = None,
        source: str | None = None,
    ) -> Any:
        return await self._require_runtime_method("cancel_run")(run_id, reason=reason, source=source)

    async def resolve_approval_wait(
        self,
        run_id: str,
        *,
        approved: bool,
        token: str | None = None,
        source: str | None = None,
        reason: str | None = None,
    ) -> Any:
        return await self._require_runtime_method("resolve_approval_wait")(
            run_id,
            approved=approved,
            token=token,
            source=source,
            reason=reason,
        )

    def _require_runtime_method(self, name: str):
        method = getattr(self._runtime_manager, name, None)
        if callable(method):
            return method
        raise LookupError(
            f"Run-level control is not wired for method {name!r} on the current runtime owner."
        )


class SessionTaskCompatibilityAdapter(SessionTaskPort):
    """Bridge session-era runtime actions into the run-control compatibility seam."""

    def __init__(self, runtime_manager: SessionTaskCompatibilityRuntimeSupport) -> None:
        self._runtime_manager = runtime_manager

    async def get_session_task(self, session_id: str) -> Any:
        direct = getattr(self._runtime_manager, "get_session_task", None)
        if callable(direct):
            return await direct(session_id)
        return await self._runtime_manager.get_session_detail(session_id, recent_limit=1)

    async def resolve_run_id_for_session(self, session_id: str) -> str | None:
        direct = getattr(self._runtime_manager, "resolve_run_id_for_session", None)
        if callable(direct):
            return await direct(session_id)
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
    "SessionAgentCompatibilityAdapter",
    "SessionAgentCompatibilityRuntimeSupport",
    "SessionBackedRunRuntimeAdapter",
    "SessionBackedRunRuntimeSupport",
    "SessionModelSelectionCompatibilityAdapter",
    "SessionModelSelectionCompatibilityRuntimeSupport",
    "SessionTaskCompatibilityAdapter",
    "SessionTaskCompatibilityRuntimeSupport",
    "UnavailableRunRuntimeAdapter",
]
