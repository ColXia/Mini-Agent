"""Surface-neutral main-agent interaction service."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, AsyncIterator, Awaitable, Callable

from fastapi import HTTPException

from mini_agent.application.gateway_chat_flow_handler import (
    SurfaceChatExecutionRequest,
    SurfaceChatFlowHandler,
)
from mini_agent.application.interaction_request_adapter import ApplicationInteractionBinding
from mini_agent.application.gateway_agent_execution_handler import AgentTurnExecutionHandler
from mini_agent.application.gateway_route_execution_handler import AgentRouteExecutionHandler
from mini_agent.application.session_service import ManagedSessionTurn, SessionApplicationService
from mini_agent.interfaces import (
    MainAgentChatRequest,
    MainAgentChatResponse,
    MainAgentSessionApprovalRequest,
    MainAgentSessionApprovalResponse,
    MainAgentSessionContextRequest,
    MainAgentSessionContextResponse,
    MainAgentSessionMemoryRequest,
    MainAgentSessionMemoryResponse,
    MainAgentSessionSkillRequest,
    MainAgentSessionSkillResponse,
    MainAgentSessionCreateRequest,
    MainAgentSessionForkRequest,
    MainAgentRoutingDiagnostics,
    MainAgentSessionCancelRequest,
    MainAgentSessionControlRequest,
    MainAgentSessionControlResponse,
    MainAgentSessionDetail,
    MainAgentSessionMessage,
    MainAgentSessionModelSelectionRequest,
    MainAgentSessionModelSelectionResponse,
    MainAgentSessionMutationResponse,
    MainAgentSessionRenameRequest,
    MainAgentSessionRuntimePolicyRequest,
    MainAgentSessionRuntimePolicyResponse,
    MainAgentSessionShareRequest,
    MainAgentSessionSummary,
)
from mini_agent.runtime.main_agent_runtime_manager import MainAgentRuntimeManager


ResolveWorkspaceDirFn = Callable[[str | None], Path]
ToUtcIsoFn = Callable[[datetime], str]
SseEventFn = Callable[[str, dict[str, Any]], str]
FormatBootstrapErrorFn = Callable[[Exception], HTTPException]


class MainAgentSurfaceService:
    """Shared main-agent interaction service for all user surfaces."""

    _ROUTE_AGENT_MAIN = "main-agent"
    _ROUTE_AGENT_DELEGATE = "delegate-agent"
    _DELEGATION_COMMAND = "/delegate"
    _DELEGATION_OWNER = "sub-agent"

    def __init__(
        self,
        *,
        runtime_manager: MainAgentRuntimeManager,
        resolve_workspace_dir: ResolveWorkspaceDirFn,
        to_utc_iso: ToUtcIsoFn,
        sse_event: SseEventFn,
        format_bootstrap_error: FormatBootstrapErrorFn,
        stream_chunk_size: int,
    ) -> None:
        self._runtime_manager = runtime_manager
        self._session_service = SessionApplicationService(runtime_manager=runtime_manager)
        self._resolve_workspace_dir = resolve_workspace_dir
        self._to_utc_iso = to_utc_iso
        self._sse_event = sse_event
        self._format_bootstrap_error = format_bootstrap_error
        self._stream_chunk_size = max(1, int(stream_chunk_size))
        self._chat_flow = SurfaceChatFlowHandler(
            session_service=self._session_service,
            to_utc_iso=self._to_utc_iso,
            sse_event=self._sse_event,
            format_bootstrap_error=self._format_bootstrap_error,
            stream_chunk_size=self._stream_chunk_size,
        )
        self._route_execution = AgentRouteExecutionHandler(
            session_service=self._session_service,
            agent_execution=AgentTurnExecutionHandler(),
            route_agent_main=self._ROUTE_AGENT_MAIN,
            route_agent_delegate=self._ROUTE_AGENT_DELEGATE,
            delegation_command=self._DELEGATION_COMMAND,
            delegation_owner=self._DELEGATION_OWNER,
        )

    async def run_chat(self, request: MainAgentChatRequest) -> MainAgentChatResponse:
        binding = ApplicationInteractionBinding.from_main_agent_chat_request(request)
        return await self._chat_flow.run_chat(
            binding.to_surface_chat_execution_request(
                message=request.message,
                workspace_dir=self._resolve_workspace_dir(request.workspace_dir),
                session_id=request.session_id,
                session_title_hint=request.session_title_hint,
                dry_run=bool(request.dry_run),
                running_detail=f"{binding.surface or 'api'} request running",
            ),
            execute_turn=self._execute_chat_turn,
        )

    async def get_routing_diagnostics(self) -> MainAgentRoutingDiagnostics:
        return await self._route_execution.get_routing_diagnostics()

    async def list_sessions(
        self,
        *,
        workspace_dir: str | None = None,
        shared_only: bool = False,
    ) -> list[MainAgentSessionSummary]:
        resolved_workspace = self._resolve_workspace_dir(workspace_dir) if workspace_dir else None
        return await self._session_service.list_sessions(
            workspace_dir=resolved_workspace,
            shared_only=shared_only,
        )

    async def create_session(self, request: MainAgentSessionCreateRequest) -> MainAgentSessionDetail:
        resolved_workspace = self._resolve_workspace_dir(request.workspace_dir)
        self._session_service.validate_workspace(resolved_workspace)
        return await self._session_service.create_session(request, workspace_dir=resolved_workspace)

    async def create_derived_session(
        self,
        parent_session_id: str,
        request: MainAgentSessionForkRequest,
    ) -> MainAgentSessionDetail:
        return await self._session_service.create_derived_session(parent_session_id, request)

    async def get_session_detail(self, session_id: str, *, recent_limit: int = 50) -> MainAgentSessionDetail:
        return await self._session_service.get_session_detail(session_id, recent_limit=recent_limit)

    async def get_session_messages(self, session_id: str, *, limit: int = 10) -> list[MainAgentSessionMessage]:
        return await self._session_service.get_session_messages(session_id, limit=limit)

    async def delete_session(self, session_id: str) -> MainAgentSessionMutationResponse:
        return await self._session_service.delete_session(session_id)

    async def rename_session(
        self,
        session_id: str,
        request: MainAgentSessionRenameRequest,
    ) -> MainAgentSessionMutationResponse:
        return await self._session_service.rename_session(session_id, request)

    async def set_session_shared(
        self,
        session_id: str,
        request: MainAgentSessionShareRequest,
    ) -> MainAgentSessionMutationResponse:
        return await self._session_service.set_session_shared(session_id, request)

    async def reset_session(self, session_id: str) -> MainAgentSessionMutationResponse:
        return await self._session_service.reset_session(session_id)

    async def cancel_session(
        self,
        session_id: str,
        request: MainAgentSessionCancelRequest,
    ) -> MainAgentSessionMutationResponse:
        return await self._session_service.cancel_session(
            session_id,
            reason=request.reason,
            surface=request.surface,
            channel_type=request.channel_type,
            conversation_id=request.conversation_id,
            sender_id=request.sender_id,
        )

    async def control_session(
        self,
        session_id: str,
        request: MainAgentSessionControlRequest,
    ) -> MainAgentSessionControlResponse:
        return await self._session_service.control_session(
            session_id,
            action=request.action,
            reason=request.reason,
            surface=request.surface,
            channel_type=request.channel_type,
            conversation_id=request.conversation_id,
            sender_id=request.sender_id,
        )

    async def update_session_context(
        self,
        session_id: str,
        request: MainAgentSessionContextRequest,
    ) -> MainAgentSessionContextResponse:
        return await self._session_service.update_session_context(session_id, request)

    async def manage_session_memory(
        self,
        session_id: str,
        request: MainAgentSessionMemoryRequest,
    ) -> MainAgentSessionMemoryResponse:
        return await self._session_service.manage_session_memory(session_id, request)

    async def manage_session_skills(
        self,
        session_id: str,
        request: MainAgentSessionSkillRequest,
    ) -> MainAgentSessionSkillResponse:
        return await self._session_service.manage_session_skills(session_id, request)

    async def update_session_model_selection(
        self,
        session_id: str,
        request: MainAgentSessionModelSelectionRequest,
    ) -> MainAgentSessionModelSelectionResponse:
        return await self._session_service.update_session_model_selection(session_id, request)

    async def respond_to_approval(
        self,
        session_id: str,
        request: MainAgentSessionApprovalRequest,
    ) -> MainAgentSessionApprovalResponse:
        return await self._session_service.respond_to_approval(
            session_id,
            approved=bool(request.approved),
            token=request.token,
            surface=request.surface,
            channel_type=request.channel_type,
            conversation_id=request.conversation_id,
            sender_id=request.sender_id,
        )

    async def update_session_runtime_policy(
        self,
        session_id: str,
        request: MainAgentSessionRuntimePolicyRequest,
    ) -> MainAgentSessionRuntimePolicyResponse:
        return await self._session_service.update_session_runtime_policy(session_id, request)

    async def stream_chat_events(
        self,
        *,
        message: str,
        session_id: str | None = None,
        session_title_hint: str | None = None,
        workspace_dir: str | None = None,
        dry_run: bool = False,
        surface: str | None = None,
        channel_type: str | None = None,
        conversation_id: str | None = None,
        sender_id: str | None = None,
    ) -> AsyncIterator[str]:
        binding = ApplicationInteractionBinding.from_values(
            surface=surface,
            channel_type=channel_type,
            conversation_id=conversation_id,
            sender_id=sender_id,
        )
        async for item in self._chat_flow.stream_chat_events(
            binding.to_surface_chat_execution_request(
                message=message,
                workspace_dir=self._resolve_workspace_dir(workspace_dir),
                session_id=session_id,
                session_title_hint=session_title_hint,
                dry_run=bool(dry_run),
                running_detail=f"{binding.surface or 'api'} stream running",
            ),
            execute_turn=self._execute_chat_turn,
        ):
            yield item

    async def _execute_chat_turn(
        self,
        turn: ManagedSessionTurn,
        request: SurfaceChatExecutionRequest,
        activity_emitter: Callable[[str, dict[str, Any]], Awaitable[None] | None] | None = None,
    ):
        return await self._route_execution.execute_chat_turn(
            turn,
            request,
            recovery_context=turn.recovery_context,
            activity_emitter=activity_emitter,
        )


MainAgentGatewayUseCases = MainAgentSurfaceService
