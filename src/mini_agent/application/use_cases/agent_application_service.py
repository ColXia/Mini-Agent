"""Application service for agent-facing operations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, AsyncIterator

from mini_agent.application.ports.agent_runtime_port import AgentRuntimePort
from mini_agent.application.use_cases.run_control_application_service import RunControlApplicationService
from mini_agent.interfaces.agent import MainAgentChatRequest, MainAgentChatResponse
from mini_agent.interfaces.system import MainAgentRoutingDiagnostics

from .agent_interaction_application_service import AgentInteractionApplicationService


def _require_agent_runtime(runtime: AgentRuntimePort | None) -> AgentRuntimePort:
    if runtime is None:
        raise RuntimeError("Agent runtime port is not configured.")
    return runtime


def _require_run_control(service: RunControlApplicationService | None) -> RunControlApplicationService:
    if service is None:
        raise RuntimeError("Run control application service is not configured.")
    return service


def _require_interaction_service(
    service: AgentInteractionApplicationService | None,
) -> AgentInteractionApplicationService:
    if service is None:
        raise RuntimeError("Agent interaction application service is not configured.")
    return service


@dataclass(slots=True)
class AgentApplicationService:
    """Owns agent-facing application logic above runtime ports and control services."""

    agent_runtime: AgentRuntimePort | None = None
    run_control: RunControlApplicationService | None = None
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

__all__ = ["AgentApplicationService"]
