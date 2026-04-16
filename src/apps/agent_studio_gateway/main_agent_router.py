"""Main-agent HTTP/SSE transport router for the unified gateway host."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from mini_agent.application.channel_ingress_use_cases import ChannelIngressUseCases
from mini_agent.application.main_agent_surface_service import MainAgentSurfaceService
from mini_agent.interfaces import (
    ApiEnvelope,
    ChannelMessageRequest,
    ChannelMessageResponse,
    MainAgentRoutingDiagnostics,
    MainAgentRuntimeDiagnostics,
    MainAgentSessionApprovalRequest,
    MainAgentSessionApprovalResponse,
    MainAgentChatRequest,
    MainAgentChatResponse,
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
    MainAgentSessionSkillRequest,
    MainAgentSessionSkillResponse,
    MainAgentSessionModelSelectionRequest,
    MainAgentSessionModelSelectionResponse,
    MainAgentSessionMutationResponse,
    MainAgentSessionRenameRequest,
    MainAgentSessionRuntimePolicyRequest,
    MainAgentSessionRuntimePolicyResponse,
    MainAgentSessionShareRequest,
    MainAgentSessionSummary,
    SystemHealthResponse,
    StudioModelListResponse,
)


@dataclass(frozen=True, slots=True)
class MainAgentRouterDependencies:
    build_health_response: Callable[[], Awaitable[SystemHealthResponse]]
    get_runtime_diagnostics: Callable[[], Awaitable[MainAgentRuntimeDiagnostics]]
    get_surface_service: Callable[[], MainAgentSurfaceService]
    get_channel_ingress_use_cases: Callable[[], ChannelIngressUseCases]
    list_models: Callable[[], StudioModelListResponse]
    require_ops_auth: Callable[..., Any]


def create_main_agent_router(deps: MainAgentRouterDependencies) -> APIRouter:
    router = APIRouter(tags=["Main Agent"])

    @router.get("/api/v1/system/health", response_model=ApiEnvelope[SystemHealthResponse])
    async def v1_health() -> ApiEnvelope[SystemHealthResponse]:
        return ApiEnvelope[SystemHealthResponse](ok=True, data=await deps.build_health_response())

    @router.get(
        "/api/v1/ops/diagnostics/runtime",
        response_model=MainAgentRuntimeDiagnostics,
        dependencies=[Depends(deps.require_ops_auth)],
    )
    async def v1_ops_runtime_diagnostics() -> MainAgentRuntimeDiagnostics:
        return await deps.get_runtime_diagnostics()

    @router.get(
        "/api/v1/ops/diagnostics/routing",
        response_model=MainAgentRoutingDiagnostics,
        dependencies=[Depends(deps.require_ops_auth)],
    )
    async def v1_ops_routing_diagnostics() -> MainAgentRoutingDiagnostics:
        return await deps.get_surface_service().get_routing_diagnostics()

    @router.post("/api/v1/agent/chat", response_model=ApiEnvelope[MainAgentChatResponse])
    async def v1_agent_chat(request: MainAgentChatRequest) -> ApiEnvelope[MainAgentChatResponse]:
        return ApiEnvelope[MainAgentChatResponse](ok=True, data=await deps.get_surface_service().run_chat(request))

    @router.post("/api/v1/channel/message", response_model=ApiEnvelope[ChannelMessageResponse])
    async def v1_channel_message(request: ChannelMessageRequest) -> ApiEnvelope[ChannelMessageResponse]:
        data = await deps.get_channel_ingress_use_cases().handle_message(request)
        return ApiEnvelope[ChannelMessageResponse](ok=True, data=data)

    @router.get("/api/v1/agent/sessions", response_model=ApiEnvelope[list[MainAgentSessionSummary]])
    async def v1_list_sessions(
        workspace_dir: str | None = None,
        shared_only: bool = False,
    ) -> ApiEnvelope[list[MainAgentSessionSummary]]:
        data = await deps.get_surface_service().list_sessions(
            workspace_dir=workspace_dir,
            shared_only=shared_only,
        )
        return ApiEnvelope[list[MainAgentSessionSummary]](ok=True, data=data)

    @router.post("/api/v1/agent/sessions", response_model=ApiEnvelope[MainAgentSessionDetail])
    async def v1_create_session(request: MainAgentSessionCreateRequest) -> ApiEnvelope[MainAgentSessionDetail]:
        return ApiEnvelope[MainAgentSessionDetail](ok=True, data=await deps.get_surface_service().create_session(request))

    @router.post("/api/v1/agent/sessions/default", response_model=ApiEnvelope[MainAgentSessionDetail])
    async def v1_ensure_default_session(
        request: MainAgentDefaultSessionRequest,
    ) -> ApiEnvelope[MainAgentSessionDetail]:
        data = await deps.get_surface_service().ensure_default_session(request)
        return ApiEnvelope[MainAgentSessionDetail](ok=True, data=data)

    @router.get("/api/v1/agent/sessions/{session_id}", response_model=ApiEnvelope[MainAgentSessionDetail])
    async def v1_get_session_detail(
        session_id: str,
        recent_limit: int = 50,
    ) -> ApiEnvelope[MainAgentSessionDetail]:
        data = await deps.get_surface_service().get_session_detail(session_id, recent_limit=recent_limit)
        return ApiEnvelope[MainAgentSessionDetail](ok=True, data=data)

    @router.get("/api/v1/agent/sessions/{session_id}/messages", response_model=ApiEnvelope[list[MainAgentSessionMessage]])
    async def v1_get_session_messages(
        session_id: str,
        limit: int = 10,
    ) -> ApiEnvelope[list[MainAgentSessionMessage]]:
        data = await deps.get_surface_service().get_session_messages(session_id, limit=limit)
        return ApiEnvelope[list[MainAgentSessionMessage]](ok=True, data=data)

    @router.get("/api/v1/agent/models", response_model=ApiEnvelope[StudioModelListResponse])
    async def v1_list_agent_models() -> ApiEnvelope[StudioModelListResponse]:
        return ApiEnvelope[StudioModelListResponse](ok=True, data=deps.list_models())

    @router.delete("/api/v1/agent/sessions/{session_id}", response_model=ApiEnvelope[MainAgentSessionMutationResponse])
    async def v1_delete_session(session_id: str) -> ApiEnvelope[MainAgentSessionMutationResponse]:
        data = await deps.get_surface_service().delete_session(session_id)
        return ApiEnvelope[MainAgentSessionMutationResponse](ok=True, data=data)

    @router.patch("/api/v1/agent/sessions/{session_id}", response_model=ApiEnvelope[MainAgentSessionMutationResponse])
    async def v1_rename_session(
        session_id: str,
        request: MainAgentSessionRenameRequest,
    ) -> ApiEnvelope[MainAgentSessionMutationResponse]:
        data = await deps.get_surface_service().rename_session(session_id, request)
        return ApiEnvelope[MainAgentSessionMutationResponse](ok=True, data=data)

    @router.post("/api/v1/agent/sessions/{session_id}/share", response_model=ApiEnvelope[MainAgentSessionMutationResponse])
    async def v1_share_session(
        session_id: str,
        request: MainAgentSessionShareRequest,
    ) -> ApiEnvelope[MainAgentSessionMutationResponse]:
        data = await deps.get_surface_service().set_session_shared(session_id, request)
        return ApiEnvelope[MainAgentSessionMutationResponse](ok=True, data=data)

    @router.post("/api/v1/agent/sessions/{session_id}/fork", response_model=ApiEnvelope[MainAgentSessionDetail])
    async def v1_fork_session(
        session_id: str,
        request: MainAgentSessionForkRequest,
    ) -> ApiEnvelope[MainAgentSessionDetail]:
        data = await deps.get_surface_service().create_derived_session(session_id, request)
        return ApiEnvelope[MainAgentSessionDetail](ok=True, data=data)

    @router.post("/api/v1/agent/sessions/{session_id}/reset", response_model=ApiEnvelope[MainAgentSessionMutationResponse])
    async def v1_reset_session(session_id: str) -> ApiEnvelope[MainAgentSessionMutationResponse]:
        data = await deps.get_surface_service().reset_session(session_id)
        return ApiEnvelope[MainAgentSessionMutationResponse](ok=True, data=data)

    @router.post("/api/v1/agent/sessions/{session_id}/cancel", response_model=ApiEnvelope[MainAgentSessionMutationResponse])
    async def v1_cancel_session(
        session_id: str,
        request: MainAgentSessionCancelRequest,
    ) -> ApiEnvelope[MainAgentSessionMutationResponse]:
        data = await deps.get_surface_service().cancel_session(session_id, request)
        return ApiEnvelope[MainAgentSessionMutationResponse](ok=True, data=data)

    @router.post("/api/v1/agent/sessions/{session_id}/control", response_model=ApiEnvelope[MainAgentSessionControlResponse])
    async def v1_control_session(
        session_id: str,
        request: MainAgentSessionControlRequest,
    ) -> ApiEnvelope[MainAgentSessionControlResponse]:
        data = await deps.get_surface_service().control_session(session_id, request)
        return ApiEnvelope[MainAgentSessionControlResponse](ok=True, data=data)

    @router.post("/api/v1/agent/sessions/{session_id}/context", response_model=ApiEnvelope[MainAgentSessionContextResponse])
    async def v1_update_session_context(
        session_id: str,
        request: MainAgentSessionContextRequest,
    ) -> ApiEnvelope[MainAgentSessionContextResponse]:
        data = await deps.get_surface_service().update_session_context(session_id, request)
        return ApiEnvelope[MainAgentSessionContextResponse](ok=True, data=data)

    @router.post("/api/v1/agent/sessions/{session_id}/memory", response_model=ApiEnvelope[MainAgentSessionMemoryResponse])
    async def v1_manage_session_memory(
        session_id: str,
        request: MainAgentSessionMemoryRequest,
    ) -> ApiEnvelope[MainAgentSessionMemoryResponse]:
        data = await deps.get_surface_service().manage_session_memory(session_id, request)
        return ApiEnvelope[MainAgentSessionMemoryResponse](ok=True, data=data)

    @router.post("/api/v1/agent/sessions/{session_id}/skill", response_model=ApiEnvelope[MainAgentSessionSkillResponse])
    async def v1_manage_session_skill(
        session_id: str,
        request: MainAgentSessionSkillRequest,
    ) -> ApiEnvelope[MainAgentSessionSkillResponse]:
        data = await deps.get_surface_service().manage_session_skills(session_id, request)
        return ApiEnvelope[MainAgentSessionSkillResponse](ok=True, data=data)

    @router.post(
        "/api/v1/agent/sessions/{session_id}/model",
        response_model=ApiEnvelope[MainAgentSessionModelSelectionResponse],
    )
    async def v1_update_session_model(
        session_id: str,
        request: MainAgentSessionModelSelectionRequest,
    ) -> ApiEnvelope[MainAgentSessionModelSelectionResponse]:
        data = await deps.get_surface_service().update_session_model_selection(session_id, request)
        return ApiEnvelope[MainAgentSessionModelSelectionResponse](ok=True, data=data)

    @router.post("/api/v1/agent/sessions/{session_id}/policy", response_model=ApiEnvelope[MainAgentSessionRuntimePolicyResponse])
    async def v1_update_session_runtime_policy(
        session_id: str,
        request: MainAgentSessionRuntimePolicyRequest,
    ) -> ApiEnvelope[MainAgentSessionRuntimePolicyResponse]:
        data = await deps.get_surface_service().update_session_runtime_policy(session_id, request)
        return ApiEnvelope[MainAgentSessionRuntimePolicyResponse](ok=True, data=data)

    @router.post("/api/v1/agent/sessions/{session_id}/approval", response_model=ApiEnvelope[MainAgentSessionApprovalResponse])
    async def v1_respond_session_approval(
        session_id: str,
        request: MainAgentSessionApprovalRequest,
    ) -> ApiEnvelope[MainAgentSessionApprovalResponse]:
        data = await deps.get_surface_service().respond_to_approval(session_id, request)
        return ApiEnvelope[MainAgentSessionApprovalResponse](ok=True, data=data)

    @router.get("/api/v1/agent/chat/stream")
    async def v1_chat_stream(
        message: str,
        session_id: str | None = None,
        session_title_hint: str | None = None,
        workspace_dir: str | None = None,
        dry_run: bool = False,
        surface: str | None = None,
        channel_type: str | None = None,
        conversation_id: str | None = None,
        sender_id: str | None = None,
    ) -> StreamingResponse:
        stream = deps.get_surface_service().stream_chat_events(
            message=message,
            session_id=session_id,
            session_title_hint=session_title_hint,
            workspace_dir=workspace_dir,
            dry_run=dry_run,
            surface=surface,
            channel_type=channel_type,
            conversation_id=conversation_id,
            sender_id=sender_id,
        )
        return StreamingResponse(
            stream,
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
        )

    return router
