"""User-facing agent operations facade."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, AsyncIterator

from mini_agent.application.ports.agent_runtime_port import AgentRuntimePort
from mini_agent.application.ports.session_agent_runtime_port import SessionAgentRuntimePort
from mini_agent.application.use_cases.agent_application_service import AgentApplicationService
from mini_agent.application.use_cases.agent_interaction_application_service import AgentInteractionApplicationService
from mini_agent.application.use_cases.run_control_application_service import RunControlApplicationService
from mini_agent.interfaces import MainAgentChatRequest, MainAgentChatResponse, MainAgentRoutingDiagnostics


@dataclass(slots=True)
class AgentUserService:
    """Thin user-service facade for agent and run-facing actions.

    Session-scoped methods below are compatibility-only shims while session/task
    entrypoints migrate behind `SessionTaskService`.
    """

    application_service: AgentApplicationService | None = None
    agent_runtime: AgentRuntimePort | None = None
    run_control: RunControlApplicationService | None = None
    session_agent_runtime: SessionAgentRuntimePort | None = None
    interaction_service: AgentInteractionApplicationService | None = None

    def _application(self) -> AgentApplicationService:
        if self.application_service is None:
            self.application_service = AgentApplicationService(
                agent_runtime=self.agent_runtime,
                run_control=self.run_control,
                session_agent_runtime=self.session_agent_runtime,
                interaction_service=self.interaction_service,
            )
        elif self.interaction_service is not None and self.application_service.interaction_service is None:
            self.application_service.interaction_service = self.interaction_service
        return self.application_service

    async def list_agents(self) -> Any:
        return await self._application().list_agents()

    async def get_agent(self, agent_id: str) -> Any:
        return await self._application().get_agent(agent_id)

    async def get_active_agent(self) -> Any:
        return await self._application().get_active_agent()

    async def get_run(self, run_id: str) -> Any:
        return await self._application().get_run(run_id)

    async def submit_message(self, request: MainAgentChatRequest) -> MainAgentChatResponse:
        return await self._application().submit_message(request)

    async def get_routing_diagnostics(self) -> MainAgentRoutingDiagnostics:
        return await self._application().get_routing_diagnostics()

    def stream_message(self, **kwargs: Any) -> AsyncIterator[str]:
        return self._application().stream_message(**kwargs)

    async def interrupt_run(self, run_id: str, *, reason: str | None = None, source: str | None = None) -> Any:
        return await self._application().interrupt_run(run_id, reason=reason, source=source)

    async def resume_run(
        self,
        run_id: str,
        *,
        resume_token: str | None = None,
        source: str | None = None,
    ) -> Any:
        return await self._application().resume_run(
            run_id,
            resume_token=resume_token,
            source=source,
        )

    async def cancel_run(self, run_id: str, *, reason: str | None = None, source: str | None = None) -> Any:
        return await self._application().cancel_run(run_id, reason=reason, source=source)

    async def approve_wait(
        self,
        run_id: str,
        *,
        token: str | None = None,
        source: str | None = None,
        reason: str | None = None,
    ) -> Any:
        return await self._application().approve_wait(
            run_id,
            token=token,
            source=source,
            reason=reason,
        )

    async def deny_wait(
        self,
        run_id: str,
        *,
        token: str | None = None,
        source: str | None = None,
        reason: str | None = None,
    ) -> Any:
        return await self._application().deny_wait(
            run_id,
            token=token,
            source=source,
            reason=reason,
        )

    async def cancel_session_run(
        self,
        session_id: str,
        *,
        reason: str | None = None,
        source: str | None = None,
        surface: str | None = None,
        channel_type: str | None = None,
        conversation_id: str | None = None,
        sender_id: str | None = None,
    ) -> Any:
        return await self._application().cancel_session_run(
            session_id,
            reason=reason,
            source=source,
            surface=surface,
            channel_type=channel_type,
            conversation_id=conversation_id,
            sender_id=sender_id,
        )

    async def interrupt_session_run(
        self,
        session_id: str,
        *,
        reason: str | None = None,
        source: str | None = None,
    ) -> Any:
        return await self._application().interrupt_session_run(
            session_id,
            reason=reason,
            source=source,
        )

    async def approve_session_wait(
        self,
        session_id: str,
        *,
        token: str | None = None,
        source: str | None = None,
        reason: str | None = None,
        surface: str | None = None,
        channel_type: str | None = None,
        conversation_id: str | None = None,
        sender_id: str | None = None,
    ) -> Any:
        return await self._application().approve_session_wait(
            session_id,
            token=token,
            source=source,
            reason=reason,
            surface=surface,
            channel_type=channel_type,
            conversation_id=conversation_id,
            sender_id=sender_id,
        )

    async def deny_session_wait(
        self,
        session_id: str,
        *,
        token: str | None = None,
        source: str | None = None,
        reason: str | None = None,
        surface: str | None = None,
        channel_type: str | None = None,
        conversation_id: str | None = None,
        sender_id: str | None = None,
    ) -> Any:
        return await self._application().deny_session_wait(
            session_id,
            token=token,
            source=source,
            reason=reason,
            surface=surface,
            channel_type=channel_type,
            conversation_id=conversation_id,
            sender_id=sender_id,
        )

    # Compatibility-only session-scoped entrypoints. Prefer SessionTaskService when available.
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
        return await self._application().update_session_runtime_policy(
            session_id,
            approval_profile=approval_profile,
            access_level=access_level,
            surface=surface,
            channel_type=channel_type,
            conversation_id=conversation_id,
            sender_id=sender_id,
        )

    async def control_session(
        self,
        session_id: str,
        *,
        action: str,
        reason: str | None = None,
        surface: str | None = None,
        channel_type: str | None = None,
        conversation_id: str | None = None,
        sender_id: str | None = None,
    ) -> Any:
        return await self._application().control_session(
            session_id,
            action=action,
            reason=reason,
            surface=surface,
            channel_type=channel_type,
            conversation_id=conversation_id,
            sender_id=sender_id,
        )

    async def update_session_context(
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
    ) -> Any:
        return await self._application().update_session_context(
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
    ) -> Any:
        return await self._application().manage_session_memory(
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
    ) -> Any:
        return await self._application().manage_session_skills(
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


__all__ = ["AgentUserService"]
