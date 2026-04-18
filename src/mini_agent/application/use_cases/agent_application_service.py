"""Application service for agent-facing operations and session compatibility actions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, AsyncIterator

from mini_agent.application.ports.agent_runtime_port import AgentRuntimePort
from mini_agent.application.ports.session_agent_runtime_port import SessionAgentRuntimePort
from mini_agent.application.use_cases.run_control_application_service import RunControlApplicationService
from mini_agent.interfaces import MainAgentChatRequest, MainAgentChatResponse, MainAgentRoutingDiagnostics

from .agent_interaction_application_service import AgentInteractionApplicationService


def _require_agent_runtime(runtime: AgentRuntimePort | None) -> AgentRuntimePort:
    if runtime is None:
        raise RuntimeError("Agent runtime port is not configured.")
    return runtime


def _require_run_control(service: RunControlApplicationService | None) -> RunControlApplicationService:
    if service is None:
        raise RuntimeError("Run control application service is not configured.")
    return service


def _require_session_agent_runtime(runtime: SessionAgentRuntimePort | None) -> SessionAgentRuntimePort:
    if runtime is None:
        raise RuntimeError("Session agent compatibility runtime is not configured.")
    return runtime


def _require_interaction_service(
    service: AgentInteractionApplicationService | None,
) -> AgentInteractionApplicationService:
    if service is None:
        raise RuntimeError("Agent interaction application service is not configured.")
    return service


@dataclass(slots=True)
class AgentApplicationService:
    """Owns agent-facing application logic above runtime ports and control services.

    Session-scoped compatibility actions remain here only as fallback shims during
    the v11.1 migration. Active session/task routing should prefer `SessionTaskService`.
    """

    agent_runtime: AgentRuntimePort | None = None
    run_control: RunControlApplicationService | None = None
    session_agent_runtime: SessionAgentRuntimePort | None = None
    interaction_service: AgentInteractionApplicationService | None = None

    async def list_agents(self) -> Any:
        return await _require_agent_runtime(self.agent_runtime).list_agents()

    async def get_agent(self, agent_id: str) -> Any:
        return await _require_agent_runtime(self.agent_runtime).get_agent(agent_id)

    async def get_active_agent(self) -> Any:
        return await _require_agent_runtime(self.agent_runtime).get_active_agent()

    async def get_run(self, run_id: str) -> Any:
        return await _require_run_control(self.run_control).get_run(run_id)

    async def submit_message(self, request: MainAgentChatRequest) -> MainAgentChatResponse:
        return await _require_interaction_service(self.interaction_service).submit_message(request)

    async def get_routing_diagnostics(self) -> MainAgentRoutingDiagnostics:
        return await _require_interaction_service(self.interaction_service).get_routing_diagnostics()

    def stream_message(self, **kwargs: Any) -> AsyncIterator[str]:
        return _require_interaction_service(self.interaction_service).stream_message(**kwargs)

    async def interrupt_run(self, run_id: str, *, reason: str | None = None, source: str | None = None) -> Any:
        return await _require_run_control(self.run_control).interrupt_run(run_id, reason=reason, source=source)

    async def resume_run(
        self,
        run_id: str,
        *,
        resume_token: str | None = None,
        source: str | None = None,
    ) -> Any:
        return await _require_run_control(self.run_control).resume_run(
            run_id,
            resume_token=resume_token,
            source=source,
        )

    async def cancel_run(self, run_id: str, *, reason: str | None = None, source: str | None = None) -> Any:
        return await _require_run_control(self.run_control).cancel_run(run_id, reason=reason, source=source)

    async def approve_wait(
        self,
        run_id: str,
        *,
        token: str | None = None,
        source: str | None = None,
        reason: str | None = None,
    ) -> Any:
        return await _require_run_control(self.run_control).approve_wait(
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
        return await _require_run_control(self.run_control).deny_wait(
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
        return await _require_run_control(self.run_control).cancel_session_run(
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
        return await _require_run_control(self.run_control).interrupt_session_run(
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
        return await _require_run_control(self.run_control).approve_session_wait(
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
        return await _require_run_control(self.run_control).deny_session_wait(
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
        return await _require_session_agent_runtime(self.session_agent_runtime).update_session_runtime_policy(
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
        return await _require_session_agent_runtime(self.session_agent_runtime).control_session_context(
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
        return await _require_session_agent_runtime(self.session_agent_runtime).update_session_context_policy(
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
        return await _require_session_agent_runtime(self.session_agent_runtime).manage_session_memory(
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
        return await _require_session_agent_runtime(self.session_agent_runtime).manage_session_skills(
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


__all__ = ["AgentApplicationService"]
