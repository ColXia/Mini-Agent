"""User-facing agent operations facade."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, AsyncIterator

from mini_agent.application.ports.agent_runtime_port import AgentRuntimePort
from mini_agent.application.use_cases.agent_application_service import AgentApplicationService
from mini_agent.application.use_cases.agent_interaction_application_service import AgentInteractionApplicationService
from mini_agent.application.use_cases.run_control_application_service import RunControlApplicationService
from mini_agent.interfaces.agent import MainAgentChatRequest, MainAgentChatResponse
from mini_agent.interfaces.system import MainAgentRoutingDiagnostics


@dataclass(slots=True)
class AgentUserService:
    """Thin user-service facade for agent and run-facing actions."""

    application_service: AgentApplicationService | None = None
    agent_runtime: AgentRuntimePort | None = None
    run_control: RunControlApplicationService | None = None
    interaction_service: AgentInteractionApplicationService | None = None

    def _application(self) -> AgentApplicationService:
        if self.application_service is None:
            self.application_service = AgentApplicationService(
                agent_runtime=self.agent_runtime,
                run_control=self.run_control,
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

__all__ = ["AgentUserService"]
