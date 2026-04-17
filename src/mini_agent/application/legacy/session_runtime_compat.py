"""Compatibility adapters for routing session-era runtime actions through typed seams."""

from __future__ import annotations

from typing import Any

from mini_agent.application.ports.session_agent_runtime_port import SessionAgentRuntimePort
from mini_agent.application.ports.session_model_selection_runtime_port import SessionModelSelectionRuntimePort
from mini_agent.application.ports.session_runtime_port import SessionRuntimePort
from mini_agent.application.ports.session_task_port import SessionTaskPort
from mini_agent.interfaces import (
    MainAgentSessionApprovalResponse,
    MainAgentSessionContextResponse,
    MainAgentSessionControlResponse,
    MainAgentSessionMemoryResponse,
    MainAgentSessionModelSelectionResponse,
    MainAgentSessionSkillResponse,
)


class UnavailableRunRuntimeAdapter:
    """Compatibility placeholder until a real run-runtime port is wired."""

    @staticmethod
    def _unsupported(run_id: str) -> LookupError:
        return LookupError(f"Run-level control is not wired for run {run_id!r}.")

    async def get_run(self, run_id: str) -> Any:
        raise self._unsupported(run_id)

    async def interrupt_run(
        self,
        run_id: str,
        *,
        reason: str | None = None,
        source: str | None = None,
    ) -> Any:
        _ = (reason, source)
        raise self._unsupported(run_id)

    async def resume_run(
        self,
        run_id: str,
        *,
        resume_token: str | None = None,
        source: str | None = None,
    ) -> Any:
        _ = (resume_token, source)
        raise self._unsupported(run_id)

    async def cancel_run(
        self,
        run_id: str,
        *,
        reason: str | None = None,
        source: str | None = None,
    ) -> Any:
        _ = (reason, source)
        raise self._unsupported(run_id)

    async def resolve_approval_wait(
        self,
        run_id: str,
        *,
        approved: bool,
        token: str | None = None,
        source: str | None = None,
        reason: str | None = None,
    ) -> Any:
        _ = (approved, token, source, reason)
        raise self._unsupported(run_id)


class SessionTaskCompatibilityAdapter(SessionTaskPort):
    """Bridge session-era runtime actions into the run-control compatibility seam."""

    def __init__(self, runtime_manager: SessionRuntimePort) -> None:
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

    def __init__(self, runtime_manager: SessionRuntimePort) -> None:
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

    def __init__(self, runtime_manager: SessionRuntimePort) -> None:
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
    "SessionModelSelectionCompatibilityAdapter",
    "SessionTaskCompatibilityAdapter",
    "UnavailableRunRuntimeAdapter",
]
