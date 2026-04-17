"""Surface-neutral main-agent interaction service."""

from __future__ import annotations

from typing import AsyncIterator, Awaitable, Callable

from mini_agent.application.agent_delegation_execution_handler import AgentDelegationExecutionHandler
from mini_agent.application.surface_chat_flow_handler import (
    SurfaceChatExecutionRequest,
    SurfaceChatFlowHandler,
)
from mini_agent.application.agent_turn_execution_handler import AgentTurnExecutionHandler
from mini_agent.application.agent_route_execution_handler import AgentRouteExecutionHandler
from mini_agent.application.interaction_request_adapter import ApplicationInteractionBinding
from mini_agent.application.managed_session_turn import ManagedSessionTurn
from mini_agent.application.session_service import SessionApplicationService
from mini_agent.application.surface_service_types import (
    FormatBootstrapErrorFn,
    ResolveWorkspaceDirFn,
    SseEventFn,
    ToUtcIsoFn,
)
from mini_agent.application.user_services.agent_user_service import AgentUserService
from mini_agent.application.user_services.model_user_service import ModelUserService
from mini_agent.application.use_cases.session_task_service import SessionTaskService
from mini_agent.interfaces import (
    MainAgentChatRequest,
    MainAgentChatResponse,
    MainAgentRoutingDiagnostics,
    MainAgentSessionApprovalRequest,
    MainAgentSessionApprovalResponse,
    MainAgentSessionCancelRequest,
    MainAgentSessionContextRequest,
    MainAgentSessionContextResponse,
    MainAgentSessionControlRequest,
    MainAgentSessionControlResponse,
    MainAgentSessionCreateRequest,
    MainAgentDefaultSessionRequest,
    MainAgentSessionDetail,
    MainAgentSessionForkRequest,
    MainAgentSessionMemoryRequest,
    MainAgentSessionMemoryResponse,
    MainAgentSessionMessage,
    MainAgentSessionModelSelectionRequest,
    MainAgentSessionModelSelectionResponse,
    MainAgentSessionMutationResponse,
    MainAgentSessionRenameRequest,
    MainAgentSessionRuntimePolicyRequest,
    MainAgentSessionRuntimePolicyResponse,
    MainAgentSessionShareRequest,
    MainAgentSessionSkillRequest,
    MainAgentSessionSkillResponse,
    MainAgentSessionSummary,
)


class MainAgentSurfaceService:
    """Shared main-agent interaction service for all user surfaces."""

    _ROUTE_AGENT_MAIN = "main-agent"
    _ROUTE_AGENT_DELEGATE = "delegate-agent"
    _DELEGATION_COMMAND = "/delegate"
    _DELEGATION_OWNER = "sub-agent"

    def __init__(
        self,
        *,
        session_service: SessionApplicationService,
        session_task_service: SessionTaskService | None = None,
        agent_service: AgentUserService | None = None,
        model_service: ModelUserService | None = None,
        resolve_workspace_dir: ResolveWorkspaceDirFn,
        to_utc_iso: ToUtcIsoFn,
        sse_event: SseEventFn,
        format_bootstrap_error: FormatBootstrapErrorFn,
        stream_chunk_size: int,
    ) -> None:
        self._session_service = session_service
        self._session_task_service = session_task_service or getattr(
            self._session_service,
            "session_task_service",
            self._session_service,
        )
        self._agent_service = agent_service
        self._model_service = model_service
        self._resolve_workspace_dir = resolve_workspace_dir
        self._to_utc_iso = to_utc_iso
        self._sse_event = sse_event
        self._format_bootstrap_error = format_bootstrap_error
        self._stream_chunk_size = max(1, int(stream_chunk_size))
        self._chat_flow = SurfaceChatFlowHandler(
            session_task_service=self._session_task_service,
            to_utc_iso=self._to_utc_iso,
            sse_event=self._sse_event,
            format_bootstrap_error=self._format_bootstrap_error,
            stream_chunk_size=self._stream_chunk_size,
        )
        self._agent_execution = AgentTurnExecutionHandler()
        self._delegation_execution = AgentDelegationExecutionHandler(
            session_task_service=self._session_task_service,
            agent_execution=self._agent_execution,
            delegation_owner=self._DELEGATION_OWNER,
            fallback_worker_id=self._ROUTE_AGENT_MAIN,
        )
        self._route_execution = AgentRouteExecutionHandler(
            agent_execution=self._agent_execution,
            delegation_execution=self._delegation_execution,
            route_agent_main=self._ROUTE_AGENT_MAIN,
            route_agent_delegate=self._ROUTE_AGENT_DELEGATE,
            delegation_command=self._DELEGATION_COMMAND,
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
        return await self._session_task_service.list_sessions(
            workspace_dir=resolved_workspace,
            shared_only=shared_only,
        )

    async def create_session(self, request: MainAgentSessionCreateRequest) -> MainAgentSessionDetail:
        resolved_workspace = self._resolve_workspace_dir(request.workspace_dir)
        self._session_task_service.validate_workspace(resolved_workspace)
        return await self._session_task_service.create_session(request, workspace_dir=resolved_workspace)

    async def ensure_default_session(self, request: MainAgentDefaultSessionRequest) -> MainAgentSessionDetail:
        resolved_workspace = self._resolve_workspace_dir(request.workspace_dir)
        self._session_task_service.validate_workspace(resolved_workspace)
        return await self._session_task_service.ensure_default_session(request, workspace_dir=resolved_workspace)

    async def create_derived_session(
        self,
        parent_session_id: str,
        request: MainAgentSessionForkRequest,
    ) -> MainAgentSessionDetail:
        return await self._session_task_service.create_derived_session(parent_session_id, request)

    async def get_session_detail(self, session_id: str, *, recent_limit: int = 50) -> MainAgentSessionDetail:
        return await self._session_task_service.get_session_detail(session_id, recent_limit=recent_limit)

    async def get_session_messages(self, session_id: str, *, limit: int = 10) -> list[MainAgentSessionMessage]:
        return await self._session_task_service.get_session_messages(session_id, limit=limit)

    async def delete_session(self, session_id: str) -> MainAgentSessionMutationResponse:
        return await self._session_task_service.delete_session(session_id)

    async def rename_session(
        self,
        session_id: str,
        request: MainAgentSessionRenameRequest,
    ) -> MainAgentSessionMutationResponse:
        return await self._session_task_service.rename_session(session_id, request)

    async def set_session_shared(
        self,
        session_id: str,
        request: MainAgentSessionShareRequest,
    ) -> MainAgentSessionMutationResponse:
        return await self._session_task_service.set_session_shared(session_id, request)

    async def reset_session(self, session_id: str) -> MainAgentSessionMutationResponse:
        return await self._session_task_service.reset_session(session_id)

    async def cancel_session(
        self,
        session_id: str,
        request: MainAgentSessionCancelRequest,
    ) -> MainAgentSessionMutationResponse:
        if self._agent_service is not None:
            binding = ApplicationInteractionBinding.from_request(request)
            return await self._agent_service.cancel_session_run(
                session_id,
                reason=request.reason,
                source=binding.surface,
                **binding.as_kwargs(),
            )
        return await self._session_service.cancel_session(session_id, request)

    async def control_session(
        self,
        session_id: str,
        request: MainAgentSessionControlRequest,
    ) -> MainAgentSessionControlResponse:
        if self._agent_service is not None:
            binding = ApplicationInteractionBinding.from_request(request)
            return await self._agent_service.control_session(
                session_id,
                action=request.action,
                reason=request.reason,
                **binding.as_kwargs(),
            )
        return await self._session_service.control_session(session_id, request)

    async def update_session_context(
        self,
        session_id: str,
        request: MainAgentSessionContextRequest,
    ) -> MainAgentSessionContextResponse:
        if self._agent_service is not None:
            binding = ApplicationInteractionBinding.from_request(request)
            return await self._agent_service.update_session_context(
                session_id,
                action=request.action,
                sources=request.sources,
                max_items=request.max_items,
                max_total_chars=request.max_total_chars,
                max_items_per_source=request.max_items_per_source,
                **binding.as_kwargs(),
            )
        return await self._session_service.update_session_context(session_id, request)

    async def manage_session_memory(
        self,
        session_id: str,
        request: MainAgentSessionMemoryRequest,
    ) -> MainAgentSessionMemoryResponse:
        if self._agent_service is not None:
            binding = ApplicationInteractionBinding.from_request(request)
            return await self._agent_service.manage_session_memory(
                session_id,
                action=request.action,
                engram_id=request.engram_id,
                content=request.content,
                query=request.query,
                day=request.day,
                export_format=request.export_format,
                detail_mode=request.detail_mode,
                **binding.as_kwargs(),
            )
        return await self._session_service.manage_session_memory(session_id, request)

    async def manage_session_skills(
        self,
        session_id: str,
        request: MainAgentSessionSkillRequest,
    ) -> MainAgentSessionSkillResponse:
        if self._agent_service is not None:
            binding = ApplicationInteractionBinding.from_request(request)
            return await self._agent_service.manage_session_skills(
                session_id,
                action=request.action,
                skill_name=request.skill_name,
                path=request.path,
                query=request.query,
                mode=request.mode,
                **binding.as_kwargs(),
            )
        return await self._session_service.manage_session_skills(session_id, request)

    async def update_session_model_selection(
        self,
        session_id: str,
        request: MainAgentSessionModelSelectionRequest,
    ) -> MainAgentSessionModelSelectionResponse:
        if self._model_service is not None:
            binding = ApplicationInteractionBinding.from_request(request)
            return await self._model_service.update_session_model_selection(
                session_id,
                provider_source=request.provider_source,
                provider_id=request.provider_id,
                model_id=request.model_id,
                **binding.as_kwargs(),
            )
        return await self._session_service.update_session_model_selection(session_id, request)

    async def respond_to_approval(
        self,
        session_id: str,
        request: MainAgentSessionApprovalRequest,
    ) -> MainAgentSessionApprovalResponse:
        if self._agent_service is not None:
            binding = ApplicationInteractionBinding.from_request(request)
            if request.approved:
                return await self._agent_service.approve_session_wait(
                    session_id,
                    token=request.token,
                    source=binding.surface,
                    **binding.as_kwargs(),
                )
            return await self._agent_service.deny_session_wait(
                session_id,
                token=request.token,
                source=binding.surface,
                **binding.as_kwargs(),
            )
        return await self._session_service.respond_to_approval(session_id, request)

    async def update_session_runtime_policy(
        self,
        session_id: str,
        request: MainAgentSessionRuntimePolicyRequest,
    ) -> MainAgentSessionRuntimePolicyResponse:
        if self._agent_service is not None:
            binding = ApplicationInteractionBinding.from_request(request)
            return await self._agent_service.update_session_runtime_policy(
                session_id,
                approval_profile=request.approval_profile,
                access_level=request.access_level,
                **binding.as_kwargs(),
            )
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
        activity_emitter: Callable[[str, dict[str, object]], Awaitable[None] | None] | None = None,
    ):
        return await self._route_execution.execute_chat_turn(
            turn,
            request,
            recovery_context=turn.recovery_context,
            activity_emitter=activity_emitter,
        )

__all__ = [
    "MainAgentSurfaceService",
]
