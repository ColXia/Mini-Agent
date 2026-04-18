"""Gateway runtime/service composition for the unified host."""

from __future__ import annotations

import json
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

from fastapi import HTTPException

from mini_agent.agent_core.engine import Agent
from mini_agent.agent_core.kernel import AgentKernelBuildOptions, build_agent_kernel
from mini_agent.application.facades import MainAgentSurfaceService, build_main_agent_surface_service
from mini_agent.application.session_runtime_compat import AgentModelRuntimeAdapter
from mini_agent.application.user_service_assembly import (
    UserServiceAssembly,
    assemble_runtime_backed_user_services,
)
from mini_agent.application.use_cases import ChannelIngressUseCases, ChannelNovelActionHandler
from mini_agent.application.use_cases.run_control_application_service import RunControlApplicationService
from mini_agent.application.use_cases.session_task_service import SessionTaskService
from mini_agent.application.user_services.agent_user_service import AgentUserService
from mini_agent.application.user_services.model_user_service import ModelUserService
from mini_agent.application.user_services.workspace_user_service import WorkspaceUserService
from mini_agent.config_bootstrap import load_entry_config, load_noninteractive_config
from mini_agent.interfaces import MainAgentChatRequest, MainAgentChatResponse, MainAgentRuntimeDiagnostics, SystemHealthResponse
from mini_agent.model_manager import AgentModelService
from mini_agent.novel.runtime import get_novel_use_cases, reset_novel_runtime_state
from mini_agent.runtime.main_agent_runtime_manager import MainAgentRuntimeManager
from mini_agent.runtime.support.main_agent_runtime_policy_loader import load_main_agent_runtime_policy
from mini_agent.runtime.workspace_runtime_adapter import MainAgentWorkspaceRuntimeAdapter
from mini_agent.session.binding import conversation_binding_store
from mini_agent.session.conversation_binding_service import ConversationBindingService
from mini_agent.tools.mcp_loader import cleanup_mcp_connections
from gateway.security.instance_lock import GatewayInstanceLock, GatewayInstanceLockError

from .main_agent_router import MainAgentRouterDependencies

if TYPE_CHECKING:
    from mini_agent.application.legacy import SessionApplicationService


@dataclass(frozen=True, slots=True)
class GatewayCompositionSettings:
    repo_root: Path
    workspace_root: Path
    session_ttl_seconds: int
    chat_stream_chunk_size: int
    studio_gateway_host: str
    studio_gateway_port: int
    studio_instance_lock_enabled: bool
    session_store_dir: Path


class GatewayComposition:
    def __init__(
        self,
        *,
        settings: GatewayCompositionSettings,
        require_ops_auth: Any,
    ) -> None:
        self.settings = settings
        self._require_ops_auth = require_ops_auth
        self._instance_lock: GatewayInstanceLock | None = None
        self._runtime_manager: MainAgentRuntimeManager | None = None
        self._session_task_service: SessionTaskService | None = None
        self._user_service_assembly: UserServiceAssembly | None = None
        # Legacy/transitional facade: surfaces now assemble from explicit owners directly.
        self._session_service: SessionApplicationService | None = None
        self._run_control_service: RunControlApplicationService | None = None
        self._agent_service: AgentUserService | None = None
        self._model_service: ModelUserService | None = None
        self._workspace_service: WorkspaceUserService | None = None
        self._workspace_runtime: MainAgentWorkspaceRuntimeAdapter | None = None
        self._agent_model_binding_service: AgentModelService | None = None
        self._model_runtime_adapter: AgentModelRuntimeAdapter | None = None
        self._surface_service: MainAgentSurfaceService | Any | None = None
        self._channel_ingress_use_cases: ChannelIngressUseCases | Any | None = None

    def to_utc_iso(self, value: datetime) -> str:
        return value.astimezone(timezone.utc).isoformat()

    def resolve_workspace_dir(self, workspace_dir: str | None) -> Path:
        if not workspace_dir:
            return self.settings.repo_root
        raw = Path(workspace_dir).expanduser()
        return (raw if raw.is_absolute() else (self.settings.repo_root / raw)).resolve()

    def sse_event(self, event: str, data: dict[str, Any]) -> str:
        payload = json.dumps(data, ensure_ascii=False)
        return f"event: {event}\ndata: {payload}\n\n"

    def format_agent_bootstrap_error(self, exc: Exception) -> HTTPException:
        raw = str(exc).strip() or exc.__class__.__name__
        if "API Key" in raw or "api key" in raw.lower():
            detail = (
                "Mini-Agent bootstrap failed: valid API key not detected. "
                "Check OPENAI_API_KEY / ANTHROPIC_API_KEY / MINIMAX_API_KEY "
                "or local .env.local fallback."
            )
        elif "Configuration file not found" in raw:
            detail = (
                "Mini-Agent bootstrap failed: configuration assets were not found. "
                "Expected config.yaml in src/mini_agent/config/, ~/.mini-agent/config/, "
                "or the installed package config directory."
            )
        else:
            detail = f"Mini-Agent bootstrap failed: {raw}"
        return HTTPException(status_code=503, detail=detail)

    async def build_agent(self, workspace_dir: Path) -> Agent:
        return await build_agent_kernel(
            workspace_dir=workspace_dir,
            options=AgentKernelBuildOptions(
                config_loader=load_entry_config,
                console_output=False,
                allow_interactive_setup=False,
                session_store_dir=self.settings.session_store_dir,
            ),
        )

    async def build_agent_with_selection(
        self,
        workspace_dir: Path,
        provider_source: str | None,
        provider_id: str | None,
        model_id: str | None,
    ) -> Agent:
        return await build_agent_kernel(
            workspace_dir=workspace_dir,
            options=AgentKernelBuildOptions(
                config_loader=load_entry_config,
                requested_provider_source=provider_source,
                requested_provider_id=provider_id,
                requested_model=model_id,
                console_output=False,
                allow_interactive_setup=False,
                session_store_dir=self.settings.session_store_dir,
            ),
        )

    def get_runtime_manager(self) -> MainAgentRuntimeManager:
        if self._runtime_manager is None:
            self._runtime_manager = MainAgentRuntimeManager(
                ttl_seconds=self.settings.session_ttl_seconds,
                build_agent=self.build_agent,
                build_agent_with_selection=self.build_agent_with_selection,
                load_runtime_config=load_noninteractive_config,
                policy=load_main_agent_runtime_policy(self.settings.repo_root),
                storage_dir=self.settings.session_store_dir,
                resolve_agent_model_identity=self.get_agent_model_binding_service().explicit_model_identity,
            )
        return self._runtime_manager

    def get_session_task_service(self) -> SessionTaskService:
        if self._session_task_service is None:
            self._session_task_service = SessionTaskService(runtime_manager=self.get_runtime_manager())
        return self._session_task_service

    def get_workspace_runtime(self) -> MainAgentWorkspaceRuntimeAdapter:
        if self._workspace_runtime is None:
            self._workspace_runtime = MainAgentWorkspaceRuntimeAdapter(
                runtime_manager=self.get_runtime_manager(),
                config_loader=load_noninteractive_config,
                repo_root=self.settings.repo_root,
            )
        return self._workspace_runtime

    def get_agent_model_binding_service(self) -> AgentModelService:
        if self._agent_model_binding_service is None:
            self._agent_model_binding_service = AgentModelService(
                load_runtime_config=load_noninteractive_config,
            )
        return self._agent_model_binding_service

    def get_model_runtime_adapter(self) -> AgentModelRuntimeAdapter:
        if self._model_runtime_adapter is None:
            self._model_runtime_adapter = AgentModelRuntimeAdapter(
                self.get_agent_model_binding_service()
            )
        return self._model_runtime_adapter

    def _ensure_user_service_assembly(self) -> UserServiceAssembly:
        if self._user_service_assembly is None:
            self._user_service_assembly = assemble_runtime_backed_user_services(
                runtime_manager=self.get_runtime_manager(),
                session_task_service=self.get_session_task_service(),
                model_runtime=self.get_model_runtime_adapter(),
                workspace_runtime=self.get_workspace_runtime(),
            )
            self._run_control_service = self._user_service_assembly.run_control_service
            self._agent_service = self._user_service_assembly.agent_service
            self._model_service = self._user_service_assembly.model_service
            self._workspace_service = self._user_service_assembly.workspace_service
        return self._user_service_assembly

    def get_session_service(self) -> SessionApplicationService:
        if self._session_service is None:
            from mini_agent.application.legacy import SessionApplicationService

            assembly = self._ensure_user_service_assembly()
            self._session_service = SessionApplicationService.from_services(
                session_task_service=assembly.session_task_service,
                run_control_service=assembly.run_control_service,
                agent_service=assembly.agent_service,
                model_service=assembly.model_service,
                runtime_manager=self.get_runtime_manager(),
            )
        return self._session_service

    def get_run_control_service(self) -> RunControlApplicationService:
        if self._run_control_service is None:
            self._run_control_service = self._ensure_user_service_assembly().run_control_service
        return self._run_control_service

    def get_agent_service(self) -> AgentUserService:
        if self._agent_service is None:
            self._agent_service = self._ensure_user_service_assembly().agent_service
        return self._agent_service

    def get_model_service(self) -> ModelUserService:
        if self._model_service is None:
            self._model_service = self._ensure_user_service_assembly().model_service
        return self._model_service

    def get_workspace_service(self) -> WorkspaceUserService | None:
        if self._workspace_service is None:
            self._workspace_service = self._ensure_user_service_assembly().workspace_service
        return self._workspace_service

    def get_surface_service(self) -> MainAgentSurfaceService:
        if self._surface_service is None:
            self._surface_service = build_main_agent_surface_service(
                user_service_assembly=self._ensure_user_service_assembly(),
                resolve_workspace_dir=self.resolve_workspace_dir,
                to_utc_iso=self.to_utc_iso,
                sse_event=self.sse_event,
                format_bootstrap_error=self.format_agent_bootstrap_error,
                stream_chunk_size=self.settings.chat_stream_chunk_size,
            )
        return self._surface_service

    async def run_main_agent_chat(self, request: MainAgentChatRequest) -> MainAgentChatResponse:
        return await self.get_surface_service().run_chat(request)

    def get_channel_ingress_use_cases(self) -> ChannelIngressUseCases:
        if self._channel_ingress_use_cases is None:
            self._channel_ingress_use_cases = ChannelIngressUseCases(
                run_main_agent_chat=self.run_main_agent_chat,
                novel_action_handler=ChannelNovelActionHandler(
                    novel_use_cases=get_novel_use_cases(
                        repo_root=self.settings.repo_root,
                        workspace_root=self.settings.workspace_root,
                    ),
                    resolve_workspace_dir=self.resolve_workspace_dir,
                    to_utc_iso=self.to_utc_iso,
                ),
                conversation_binding=ConversationBindingService(
                    binding_store=conversation_binding_store,
                ),
            )
        return self._channel_ingress_use_cases

    async def get_runtime_diagnostics(self) -> MainAgentRuntimeDiagnostics:
        runtime = await self.get_runtime_manager().get_runtime_diagnostics()
        return MainAgentRuntimeDiagnostics(**runtime.__dict__)

    async def build_health_response(self) -> SystemHealthResponse:
        return SystemHealthResponse(
            status="ok",
            now_utc=self.to_utc_iso(datetime.now(timezone.utc)),
            workspace_root=str(self.settings.workspace_root),
            runtime=await self.get_runtime_diagnostics(),
        )

    async def startup(self) -> None:
        if not self.settings.studio_instance_lock_enabled:
            return
        lock = GatewayInstanceLock(
            host=self.settings.studio_gateway_host,
            port=self.settings.studio_gateway_port,
        )
        try:
            lock.acquire()
        except GatewayInstanceLockError as exc:
            raise RuntimeError(str(exc)) from exc
        self._instance_lock = lock

    async def shutdown(self) -> None:
        try:
            await cleanup_mcp_connections()
        finally:
            try:
                if self._runtime_manager is not None:
                    await self._runtime_manager.clear()
                self._runtime_manager = None
                self._session_task_service = None
                self._user_service_assembly = None
                self._session_service = None
                self._run_control_service = None
                self._agent_service = None
                self._model_service = None
                self._workspace_service = None
                self._workspace_runtime = None
                self._agent_model_binding_service = None
                self._model_runtime_adapter = None
                self._surface_service = None
                self._channel_ingress_use_cases = None
                reset_novel_runtime_state()
            finally:
                if self._instance_lock is not None:
                    self._instance_lock.release()
                    self._instance_lock = None

    @asynccontextmanager
    async def lifespan(self, _: Any):
        await self.startup()
        try:
            yield
        finally:
            await self.shutdown()

    def build_main_agent_router_dependencies(self, *, list_models: Any) -> MainAgentRouterDependencies:
        return MainAgentRouterDependencies(
            build_health_response=self.build_health_response,
            get_runtime_diagnostics=self.get_runtime_diagnostics,
            resolve_workspace_dir=self.resolve_workspace_dir,
            get_surface_service=self.get_surface_service,
            get_session_task_service=self.get_session_task_service,
            get_agent_service=self.get_agent_service,
            get_workspace_service=self.get_workspace_service,
            get_model_service=self.get_model_service,
            get_channel_ingress_use_cases=self.get_channel_ingress_use_cases,
            list_models=list_models,
            require_ops_auth=self._require_ops_auth,
        )
