"""User-facing agent operations facade."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from mini_agent.application.ports.agent_runtime_port import AgentRuntimePort
from mini_agent.application.use_cases.run_control_application_service import RunControlApplicationService


def _require_run_control(service: RunControlApplicationService | None) -> RunControlApplicationService:
    if service is None:
        raise RuntimeError("Run control application service is not configured.")
    return service


@dataclass(slots=True)
class AgentUserService:
    """Thin user-service facade for agent and run-facing actions."""

    agent_runtime: AgentRuntimePort
    run_control: RunControlApplicationService | None = None

    async def list_agents(self) -> Any:
        return await self.agent_runtime.list_agents()

    async def get_agent(self, agent_id: str) -> Any:
        return await self.agent_runtime.get_agent(agent_id)

    async def get_active_agent(self) -> Any:
        return await self.agent_runtime.get_active_agent()

    async def get_run(self, run_id: str) -> Any:
        return await _require_run_control(self.run_control).get_run(run_id)

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


__all__ = ["AgentUserService"]
