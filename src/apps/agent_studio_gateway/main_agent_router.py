"""Main-agent HTTP/SSE transport router for the unified gateway host."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, AsyncIterator, Awaitable, Callable

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from mini_agent.application.support import ApplicationInteractionBinding
from mini_agent.application.facades.service_response_dto_adapter import (
    model_binding_diagnostics_response,
    model_binding_summary_response,
    model_candidate_list_response,
    model_capabilities_response,
    run_summary_response,
    workspace_runtime_summary_response,
    workspace_summary_response,
)
from mini_agent.application.use_cases import (
    ChannelIngressUseCases,
    RunControlApplicationService,
    SessionTaskService,
)
from mini_agent.application.user_services import ModelUserService, WorkspaceUserService
from mini_agent.interfaces import (
    ApiEnvelope,
    ChannelMessageRequest,
    ChannelMessageResponse,
    MainAgentRoutingDiagnostics,
    MainAgentRuntimeDiagnostics,
    MainAgentModelBindingDiagnostics,
    MainAgentModelBindingRequest,
    MainAgentModelBindingSummary,
    MainAgentModelCandidateListResponse,
    MainAgentModelCapabilities,
    MainAgentRunApprovalRequest,
    MainAgentRunCancelRequest,
    MainAgentRunInterruptRequest,
    MainAgentRunResumeRequest,
    MainAgentRunSummary,
    MainAgentWorkspaceRuntimeSummary,
    MainAgentWorkspaceSummary,
    MainAgentWorkspaceSwitchRequest,
    MainAgentSessionApprovalRequest,
    MainAgentSessionApprovalResponse,
    MainAgentChatRequest,
    MainAgentChatResponse,
    MainAgentSessionCancelRequest,
    MainAgentSessionInterruptRequest,
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
    MainAgentSessionMutationResponse,
    MainAgentSessionRenameRequest,
    MainAgentSessionRuntimePolicyRequest,
    MainAgentSessionRuntimePolicyResponse,
    MainAgentSessionShareRequest,
    MainAgentSessionSummary,
    SystemHealthResponse,
    StudioModelListResponse,
)


StreamMainAgentChatFn = Callable[..., AsyncIterator[str]]


@dataclass(frozen=True, slots=True)
class MainAgentRouterDependencies:
    build_health_response: Callable[[], Awaitable[SystemHealthResponse]]
    get_runtime_diagnostics: Callable[[], Awaitable[MainAgentRuntimeDiagnostics]]
    get_routing_diagnostics: Callable[[], Awaitable[MainAgentRoutingDiagnostics]]
    run_main_agent_chat: Callable[[MainAgentChatRequest], Awaitable[MainAgentChatResponse]]
    stream_main_agent_chat: StreamMainAgentChatFn
    resolve_workspace_dir: Callable[[str | None], Path]
    get_session_task_service: Callable[[], SessionTaskService]
    get_run_control_service: Callable[[], RunControlApplicationService]
    get_workspace_service: Callable[[], WorkspaceUserService | None]
    get_model_service: Callable[[], ModelUserService]
    get_channel_ingress_use_cases: Callable[[], ChannelIngressUseCases]
    list_models: Callable[[], StudioModelListResponse]
    require_ops_auth: Callable[..., Any]


def create_main_agent_router(deps: MainAgentRouterDependencies) -> APIRouter:
    router = APIRouter(tags=["Main Agent"])

    def _require_workspace_service() -> WorkspaceUserService:
        workspace_service = deps.get_workspace_service()
        if workspace_service is None:
            raise RuntimeError("Workspace service is not configured.")
        return workspace_service

    def _require_session_task_service() -> SessionTaskService:
        return deps.get_session_task_service()

    def _require_run_control_service() -> RunControlApplicationService:
        return deps.get_run_control_service()

    def _resolve_workspace_dir(workspace_dir: str | None) -> Path:
        return deps.resolve_workspace_dir(workspace_dir)

    def _require_model_service() -> ModelUserService:
        return deps.get_model_service()

    def _require_session_task_method(name: str) -> Callable[..., Awaitable[Any]]:
        session_task_service = _require_session_task_service()
        supports_entrypoint = getattr(session_task_service, "supports_entrypoint", None)
        if callable(supports_entrypoint) and not supports_entrypoint(name):
            raise RuntimeError(f"Session task service entrypoint is not configured: {name}")
        method = getattr(session_task_service, name, None)
        if not callable(method):
            raise RuntimeError(f"Session task service entrypoint is not configured: {name}")
        return method

    def _lookup_error_status(detail: str) -> int:
        normalized = " ".join(str(detail or "").split()).lower()
        if "not found" in normalized:
            return 404
        return 409

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
        return await deps.get_routing_diagnostics()

    @router.post("/api/v1/agent/chat", response_model=ApiEnvelope[MainAgentChatResponse])
    async def v1_agent_chat(request: MainAgentChatRequest) -> ApiEnvelope[MainAgentChatResponse]:
        return ApiEnvelope[MainAgentChatResponse](ok=True, data=await deps.run_main_agent_chat(request))

    @router.post("/api/v1/channel/message", response_model=ApiEnvelope[ChannelMessageResponse])
    async def v1_channel_message(request: ChannelMessageRequest) -> ApiEnvelope[ChannelMessageResponse]:
        data = await deps.get_channel_ingress_use_cases().handle_message(request)
        return ApiEnvelope[ChannelMessageResponse](ok=True, data=data)

    @router.get("/api/v1/agent/workspaces", response_model=ApiEnvelope[list[MainAgentWorkspaceSummary]])
    async def v1_list_workspaces() -> ApiEnvelope[list[MainAgentWorkspaceSummary]]:
        payload = await _require_workspace_service().list_workspaces()
        data = [workspace_summary_response(item) for item in list(payload or [])]
        return ApiEnvelope[list[MainAgentWorkspaceSummary]](ok=True, data=data)

    @router.get("/api/v1/agent/workspaces/active", response_model=ApiEnvelope[MainAgentWorkspaceSummary])
    async def v1_get_active_workspace() -> ApiEnvelope[MainAgentWorkspaceSummary]:
        data = workspace_summary_response(await _require_workspace_service().get_active_workspace())
        return ApiEnvelope[MainAgentWorkspaceSummary](ok=True, data=data)

    @router.get("/api/v1/agent/workspaces/resolve", response_model=ApiEnvelope[MainAgentWorkspaceSummary])
    async def v1_get_workspace(workspace_id: str) -> ApiEnvelope[MainAgentWorkspaceSummary]:
        data = workspace_summary_response(await _require_workspace_service().get_workspace(workspace_id))
        return ApiEnvelope[MainAgentWorkspaceSummary](ok=True, data=data)

    @router.post("/api/v1/agent/workspaces/switch", response_model=ApiEnvelope[MainAgentWorkspaceSummary])
    async def v1_switch_workspace(
        request: MainAgentWorkspaceSwitchRequest,
    ) -> ApiEnvelope[MainAgentWorkspaceSummary]:
        data = workspace_summary_response(await _require_workspace_service().switch_workspace(request.workspace_id))
        return ApiEnvelope[MainAgentWorkspaceSummary](ok=True, data=data)

    @router.get(
        "/api/v1/agent/workspaces/runtime",
        response_model=ApiEnvelope[MainAgentWorkspaceRuntimeSummary],
    )
    async def v1_get_workspace_runtime_summary(
        workspace_id: str | None = None,
    ) -> ApiEnvelope[MainAgentWorkspaceRuntimeSummary]:
        data = workspace_runtime_summary_response(
            await _require_workspace_service().get_workspace_runtime_summary(workspace_id=workspace_id)
        )
        return ApiEnvelope[MainAgentWorkspaceRuntimeSummary](ok=True, data=data)

    @router.get("/api/v1/agent/sessions", response_model=ApiEnvelope[list[MainAgentSessionSummary]])
    async def v1_list_sessions(
        workspace_dir: str | None = None,
        shared_only: bool = False,
    ) -> ApiEnvelope[list[MainAgentSessionSummary]]:
        data = await _require_session_task_service().list_sessions(
            workspace_dir=_resolve_workspace_dir(workspace_dir) if workspace_dir else None,
            shared_only=shared_only,
        )
        return ApiEnvelope[list[MainAgentSessionSummary]](ok=True, data=data)

    @router.post("/api/v1/agent/sessions", response_model=ApiEnvelope[MainAgentSessionDetail])
    async def v1_create_session(request: MainAgentSessionCreateRequest) -> ApiEnvelope[MainAgentSessionDetail]:
        resolved_workspace = _resolve_workspace_dir(request.workspace_dir)
        _require_session_task_service().validate_workspace(resolved_workspace)
        data = await _require_session_task_service().create_session(request, workspace_dir=resolved_workspace)
        return ApiEnvelope[MainAgentSessionDetail](ok=True, data=data)

    @router.post("/api/v1/agent/sessions/default", response_model=ApiEnvelope[MainAgentSessionDetail])
    async def v1_ensure_default_session(
        request: MainAgentDefaultSessionRequest,
    ) -> ApiEnvelope[MainAgentSessionDetail]:
        resolved_workspace = _resolve_workspace_dir(request.workspace_dir)
        _require_session_task_service().validate_workspace(resolved_workspace)
        data = await _require_session_task_service().ensure_default_session(
            request,
            workspace_dir=resolved_workspace,
        )
        return ApiEnvelope[MainAgentSessionDetail](ok=True, data=data)

    @router.get("/api/v1/agent/sessions/{session_id}", response_model=ApiEnvelope[MainAgentSessionDetail])
    async def v1_get_session_detail(
        session_id: str,
        recent_limit: int = 50,
    ) -> ApiEnvelope[MainAgentSessionDetail]:
        data = await _require_session_task_service().get_session_detail(session_id, recent_limit=recent_limit)
        return ApiEnvelope[MainAgentSessionDetail](ok=True, data=data)

    @router.get("/api/v1/agent/sessions/{session_id}/messages", response_model=ApiEnvelope[list[MainAgentSessionMessage]])
    async def v1_get_session_messages(
        session_id: str,
        limit: int = 10,
    ) -> ApiEnvelope[list[MainAgentSessionMessage]]:
        data = await _require_session_task_service().get_session_messages(session_id, limit=limit)
        return ApiEnvelope[list[MainAgentSessionMessage]](ok=True, data=data)

    @router.get("/api/v1/agent/models", response_model=ApiEnvelope[StudioModelListResponse])
    async def v1_list_agent_models() -> ApiEnvelope[StudioModelListResponse]:
        return ApiEnvelope[StudioModelListResponse](ok=True, data=deps.list_models())

    @router.get("/api/v1/agent/model/candidates", response_model=ApiEnvelope[MainAgentModelCandidateListResponse])
    async def v1_list_agent_model_candidates() -> ApiEnvelope[MainAgentModelCandidateListResponse]:
        data = model_candidate_list_response(await _require_model_service().list_model_candidates())
        return ApiEnvelope[MainAgentModelCandidateListResponse](ok=True, data=data)

    @router.get("/api/v1/agent/model/binding", response_model=ApiEnvelope[MainAgentModelBindingSummary])
    async def v1_get_agent_model_binding(
        agent_id: str | None = None,
    ) -> ApiEnvelope[MainAgentModelBindingSummary]:
        data = model_binding_summary_response(await _require_model_service().get_current_model_binding(agent_id))
        return ApiEnvelope[MainAgentModelBindingSummary](ok=True, data=data)

    @router.put("/api/v1/agent/model/binding", response_model=ApiEnvelope[MainAgentModelBindingSummary])
    async def v1_set_agent_model_binding(
        request: MainAgentModelBindingRequest,
    ) -> ApiEnvelope[MainAgentModelBindingSummary]:
        data = model_binding_summary_response(
            await _require_model_service().set_agent_model_binding(
                agent_id=request.agent_id,
                provider_source=request.provider_source,
                provider_id=request.provider_id,
                model_id=request.model_id,
            )
        )
        return ApiEnvelope[MainAgentModelBindingSummary](ok=True, data=data)

    @router.get("/api/v1/agent/model/capabilities", response_model=ApiEnvelope[MainAgentModelCapabilities])
    async def v1_get_agent_model_capabilities(
        agent_id: str | None = None,
    ) -> ApiEnvelope[MainAgentModelCapabilities]:
        data = model_capabilities_response(await _require_model_service().get_current_model_capabilities(agent_id))
        return ApiEnvelope[MainAgentModelCapabilities](ok=True, data=data)

    @router.get("/api/v1/agent/model/diagnostics", response_model=ApiEnvelope[MainAgentModelBindingDiagnostics])
    async def v1_get_agent_model_diagnostics(
        agent_id: str | None = None,
    ) -> ApiEnvelope[MainAgentModelBindingDiagnostics]:
        data = model_binding_diagnostics_response(await _require_model_service().get_model_binding_diagnostics(agent_id))
        return ApiEnvelope[MainAgentModelBindingDiagnostics](ok=True, data=data)

    @router.get("/api/v1/agent/runs/{run_id}", response_model=ApiEnvelope[MainAgentRunSummary])
    async def v1_get_run(run_id: str) -> ApiEnvelope[MainAgentRunSummary]:
        try:
            data = run_summary_response(await _require_run_control_service().get_run(run_id))
        except LookupError as exc:
            raise HTTPException(status_code=_lookup_error_status(str(exc)), detail=str(exc)) from exc
        return ApiEnvelope[MainAgentRunSummary](ok=True, data=data)

    @router.post("/api/v1/agent/runs/{run_id}/resume", response_model=ApiEnvelope[MainAgentRunSummary])
    async def v1_resume_run(
        run_id: str,
        request: MainAgentRunResumeRequest,
    ) -> ApiEnvelope[MainAgentRunSummary]:
        binding = ApplicationInteractionBinding.from_request(request)
        try:
            await _require_run_control_service().resume_run(
                run_id,
                resume_token=request.resume_token,
                source=binding.surface,
            )
            data = run_summary_response(await _require_run_control_service().get_run(run_id))
        except LookupError as exc:
            raise HTTPException(status_code=_lookup_error_status(str(exc)), detail=str(exc)) from exc
        return ApiEnvelope[MainAgentRunSummary](ok=True, data=data)

    @router.post("/api/v1/agent/runs/{run_id}/interrupt", response_model=ApiEnvelope[MainAgentRunSummary])
    async def v1_interrupt_run(
        run_id: str,
        request: MainAgentRunInterruptRequest,
    ) -> ApiEnvelope[MainAgentRunSummary]:
        binding = ApplicationInteractionBinding.from_request(request)
        try:
            await _require_run_control_service().interrupt_run(
                run_id,
                reason=request.reason,
                source=binding.surface,
            )
            data = run_summary_response(await _require_run_control_service().get_run(run_id))
        except LookupError as exc:
            raise HTTPException(status_code=_lookup_error_status(str(exc)), detail=str(exc)) from exc
        return ApiEnvelope[MainAgentRunSummary](ok=True, data=data)

    @router.post("/api/v1/agent/runs/{run_id}/cancel", response_model=ApiEnvelope[MainAgentRunSummary])
    async def v1_cancel_run(
        run_id: str,
        request: MainAgentRunCancelRequest,
    ) -> ApiEnvelope[MainAgentRunSummary]:
        binding = ApplicationInteractionBinding.from_request(request)
        try:
            await _require_run_control_service().cancel_run(
                run_id,
                reason=request.reason,
                source=binding.surface,
            )
            data = run_summary_response(await _require_run_control_service().get_run(run_id))
        except LookupError as exc:
            raise HTTPException(status_code=_lookup_error_status(str(exc)), detail=str(exc)) from exc
        return ApiEnvelope[MainAgentRunSummary](ok=True, data=data)

    @router.post("/api/v1/agent/runs/{run_id}/approval", response_model=ApiEnvelope[MainAgentRunSummary])
    async def v1_resolve_run_approval(
        run_id: str,
        request: MainAgentRunApprovalRequest,
    ) -> ApiEnvelope[MainAgentRunSummary]:
        binding = ApplicationInteractionBinding.from_request(request)
        try:
            if request.approved:
                await _require_run_control_service().approve_wait(
                    run_id,
                    token=request.token,
                    source=binding.surface,
                    reason=request.reason,
                )
            else:
                await _require_run_control_service().deny_wait(
                    run_id,
                    token=request.token,
                    source=binding.surface,
                    reason=request.reason,
                )
            data = run_summary_response(await _require_run_control_service().get_run(run_id))
        except LookupError as exc:
            raise HTTPException(status_code=_lookup_error_status(str(exc)), detail=str(exc)) from exc
        return ApiEnvelope[MainAgentRunSummary](ok=True, data=data)

    @router.delete("/api/v1/agent/sessions/{session_id}", response_model=ApiEnvelope[MainAgentSessionMutationResponse])
    async def v1_delete_session(session_id: str) -> ApiEnvelope[MainAgentSessionMutationResponse]:
        data = await _require_session_task_service().delete_session(session_id)
        return ApiEnvelope[MainAgentSessionMutationResponse](ok=True, data=data)

    @router.patch("/api/v1/agent/sessions/{session_id}", response_model=ApiEnvelope[MainAgentSessionMutationResponse])
    async def v1_rename_session(
        session_id: str,
        request: MainAgentSessionRenameRequest,
    ) -> ApiEnvelope[MainAgentSessionMutationResponse]:
        data = await _require_session_task_service().rename_session(session_id, request)
        return ApiEnvelope[MainAgentSessionMutationResponse](ok=True, data=data)

    @router.post("/api/v1/agent/sessions/{session_id}/share", response_model=ApiEnvelope[MainAgentSessionMutationResponse])
    async def v1_share_session(
        session_id: str,
        request: MainAgentSessionShareRequest,
    ) -> ApiEnvelope[MainAgentSessionMutationResponse]:
        data = await _require_session_task_service().set_session_shared(session_id, request)
        return ApiEnvelope[MainAgentSessionMutationResponse](ok=True, data=data)

    @router.post("/api/v1/agent/sessions/{session_id}/fork", response_model=ApiEnvelope[MainAgentSessionDetail])
    async def v1_fork_session(
        session_id: str,
        request: MainAgentSessionForkRequest,
    ) -> ApiEnvelope[MainAgentSessionDetail]:
        data = await _require_session_task_service().create_derived_session(session_id, request)
        return ApiEnvelope[MainAgentSessionDetail](ok=True, data=data)

    @router.post("/api/v1/agent/sessions/{session_id}/reset", response_model=ApiEnvelope[MainAgentSessionMutationResponse])
    async def v1_reset_session(session_id: str) -> ApiEnvelope[MainAgentSessionMutationResponse]:
        data = await _require_session_task_service().reset_session(session_id)
        return ApiEnvelope[MainAgentSessionMutationResponse](ok=True, data=data)

    @router.post("/api/v1/agent/sessions/{session_id}/cancel", response_model=ApiEnvelope[MainAgentSessionMutationResponse])
    async def v1_cancel_session(
        session_id: str,
        request: MainAgentSessionCancelRequest,
    ) -> ApiEnvelope[MainAgentSessionMutationResponse]:
        binding = ApplicationInteractionBinding.from_request(request)
        data = await _require_run_control_service().cancel_session_run(
            session_id,
            reason=request.reason,
            source=binding.surface,
            **binding.as_kwargs(),
        )
        return ApiEnvelope[MainAgentSessionMutationResponse](ok=True, data=data)

    @router.post("/api/v1/agent/sessions/{session_id}/interrupt", response_model=ApiEnvelope[MainAgentSessionMutationResponse])
    async def v1_interrupt_session(
        session_id: str,
        request: MainAgentSessionInterruptRequest,
    ) -> ApiEnvelope[MainAgentSessionMutationResponse]:
        binding = ApplicationInteractionBinding.from_request(request)
        try:
            data = await _require_run_control_service().interrupt_session_run(
                session_id,
                reason=request.reason,
                source=binding.surface,
            )
        except LookupError as exc:
            raise HTTPException(status_code=_lookup_error_status(str(exc)), detail=str(exc)) from exc
        return ApiEnvelope[MainAgentSessionMutationResponse](ok=True, data=data)

    @router.post("/api/v1/agent/sessions/{session_id}/control", response_model=ApiEnvelope[MainAgentSessionControlResponse])
    async def v1_control_session(
        session_id: str,
        request: MainAgentSessionControlRequest,
    ) -> ApiEnvelope[MainAgentSessionControlResponse]:
        binding = ApplicationInteractionBinding.from_request(request)
        data = await _require_session_task_method("control_session")(
            session_id,
            action=request.action,
            reason=request.reason,
            **binding.as_kwargs(),
        )
        return ApiEnvelope[MainAgentSessionControlResponse](ok=True, data=data)

    @router.post("/api/v1/agent/sessions/{session_id}/context", response_model=ApiEnvelope[MainAgentSessionContextResponse])
    async def v1_update_session_context(
        session_id: str,
        request: MainAgentSessionContextRequest,
    ) -> ApiEnvelope[MainAgentSessionContextResponse]:
        binding = ApplicationInteractionBinding.from_request(request)
        data = await _require_session_task_method("update_session_context")(
            session_id,
            action=request.action,
            sources=request.sources,
            max_items=request.max_items,
            max_total_chars=request.max_total_chars,
            max_items_per_source=request.max_items_per_source,
            **binding.as_kwargs(),
        )
        return ApiEnvelope[MainAgentSessionContextResponse](ok=True, data=data)

    @router.post("/api/v1/agent/sessions/{session_id}/memory", response_model=ApiEnvelope[MainAgentSessionMemoryResponse])
    async def v1_manage_session_memory(
        session_id: str,
        request: MainAgentSessionMemoryRequest,
    ) -> ApiEnvelope[MainAgentSessionMemoryResponse]:
        binding = ApplicationInteractionBinding.from_request(request)
        data = await _require_session_task_method("manage_session_memory")(
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
        return ApiEnvelope[MainAgentSessionMemoryResponse](ok=True, data=data)

    @router.post("/api/v1/agent/sessions/{session_id}/skill", response_model=ApiEnvelope[MainAgentSessionSkillResponse])
    async def v1_manage_session_skill(
        session_id: str,
        request: MainAgentSessionSkillRequest,
    ) -> ApiEnvelope[MainAgentSessionSkillResponse]:
        binding = ApplicationInteractionBinding.from_request(request)
        data = await _require_session_task_method("manage_session_skills")(
            session_id,
            action=request.action,
            skill_name=request.skill_name,
            path=request.path,
            query=request.query,
            mode=request.mode,
            **binding.as_kwargs(),
        )
        return ApiEnvelope[MainAgentSessionSkillResponse](ok=True, data=data)

    @router.post("/api/v1/agent/sessions/{session_id}/policy", response_model=ApiEnvelope[MainAgentSessionRuntimePolicyResponse])
    async def v1_update_session_runtime_policy(
        session_id: str,
        request: MainAgentSessionRuntimePolicyRequest,
    ) -> ApiEnvelope[MainAgentSessionRuntimePolicyResponse]:
        binding = ApplicationInteractionBinding.from_request(request)
        data = await _require_session_task_method("update_session_runtime_policy")(
            session_id,
            approval_profile=request.approval_profile,
            access_level=request.access_level,
            **binding.as_kwargs(),
        )
        return ApiEnvelope[MainAgentSessionRuntimePolicyResponse](ok=True, data=data)

    @router.post("/api/v1/agent/sessions/{session_id}/approval", response_model=ApiEnvelope[MainAgentSessionApprovalResponse])
    async def v1_respond_session_approval(
        session_id: str,
        request: MainAgentSessionApprovalRequest,
    ) -> ApiEnvelope[MainAgentSessionApprovalResponse]:
        binding = ApplicationInteractionBinding.from_request(request)
        if request.approved:
            data = await _require_run_control_service().approve_session_wait(
                session_id,
                token=request.token,
                source=binding.surface,
                **binding.as_kwargs(),
            )
        else:
            data = await _require_run_control_service().deny_session_wait(
                session_id,
                token=request.token,
                source=binding.surface,
                **binding.as_kwargs(),
            )
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
        stream = deps.stream_main_agent_chat(
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
