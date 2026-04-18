"""Typed client-side remote run client over the shared gateway transport."""

from __future__ import annotations

from mini_agent.interfaces import (
    MainAgentRunApprovalRequest,
    MainAgentRunCancelRequest,
    MainAgentRunInterruptRequest,
    MainAgentRunResumeRequest,
    MainAgentRunSummary,
)

from .run_transport_port import RemoteRunTransportPort


class RemoteRunClient:
    """Typed client-side facade over remote run query and control transport."""

    def __init__(self, *, run_transport: RemoteRunTransportPort) -> None:
        self._run_transport = run_transport

    async def get_run(self, run_id: str) -> MainAgentRunSummary:
        payload = await self._run_transport.get_run(run_id)
        return MainAgentRunSummary.model_validate(payload)

    def get_run_sync(self, run_id: str) -> MainAgentRunSummary:
        payload = self._run_transport.get_run_sync(run_id)
        return MainAgentRunSummary.model_validate(payload)

    async def interrupt_run(
        self,
        run_id: str,
        request: MainAgentRunInterruptRequest,
    ) -> MainAgentRunSummary:
        payload = await self._run_transport.interrupt_run(
            run_id,
            reason=request.reason,
            surface=request.surface,
            channel_type=request.channel_type,
            conversation_id=request.conversation_id,
            sender_id=request.sender_id,
        )
        return MainAgentRunSummary.model_validate(payload)

    def interrupt_run_sync(
        self,
        run_id: str,
        request: MainAgentRunInterruptRequest,
    ) -> MainAgentRunSummary:
        payload = self._run_transport.interrupt_run_sync(
            run_id,
            reason=request.reason,
            surface=request.surface,
            channel_type=request.channel_type,
            conversation_id=request.conversation_id,
            sender_id=request.sender_id,
        )
        return MainAgentRunSummary.model_validate(payload)

    async def resume_run(
        self,
        run_id: str,
        request: MainAgentRunResumeRequest,
    ) -> MainAgentRunSummary:
        payload = await self._run_transport.resume_run(
            run_id,
            resume_token=request.resume_token,
            surface=request.surface,
            channel_type=request.channel_type,
            conversation_id=request.conversation_id,
            sender_id=request.sender_id,
        )
        return MainAgentRunSummary.model_validate(payload)

    def resume_run_sync(
        self,
        run_id: str,
        request: MainAgentRunResumeRequest,
    ) -> MainAgentRunSummary:
        payload = self._run_transport.resume_run_sync(
            run_id,
            resume_token=request.resume_token,
            surface=request.surface,
            channel_type=request.channel_type,
            conversation_id=request.conversation_id,
            sender_id=request.sender_id,
        )
        return MainAgentRunSummary.model_validate(payload)

    async def cancel_run(
        self,
        run_id: str,
        request: MainAgentRunCancelRequest,
    ) -> MainAgentRunSummary:
        payload = await self._run_transport.cancel_run(
            run_id,
            reason=request.reason,
            surface=request.surface,
            channel_type=request.channel_type,
            conversation_id=request.conversation_id,
            sender_id=request.sender_id,
        )
        return MainAgentRunSummary.model_validate(payload)

    def cancel_run_sync(
        self,
        run_id: str,
        request: MainAgentRunCancelRequest,
    ) -> MainAgentRunSummary:
        payload = self._run_transport.cancel_run_sync(
            run_id,
            reason=request.reason,
            surface=request.surface,
            channel_type=request.channel_type,
            conversation_id=request.conversation_id,
            sender_id=request.sender_id,
        )
        return MainAgentRunSummary.model_validate(payload)

    async def respond_to_approval(
        self,
        run_id: str,
        request: MainAgentRunApprovalRequest,
    ) -> MainAgentRunSummary:
        payload = await self._run_transport.resolve_run_approval(
            run_id,
            approved=request.approved,
            token=request.token,
            reason=request.reason,
            surface=request.surface,
            channel_type=request.channel_type,
            conversation_id=request.conversation_id,
            sender_id=request.sender_id,
        )
        return MainAgentRunSummary.model_validate(payload)

    def respond_to_approval_sync(
        self,
        run_id: str,
        request: MainAgentRunApprovalRequest,
    ) -> MainAgentRunSummary:
        payload = self._run_transport.resolve_run_approval_sync(
            run_id,
            approved=request.approved,
            token=request.token,
            reason=request.reason,
            surface=request.surface,
            channel_type=request.channel_type,
            conversation_id=request.conversation_id,
            sender_id=request.sender_id,
        )
        return MainAgentRunSummary.model_validate(payload)


__all__ = ["RemoteRunClient"]
