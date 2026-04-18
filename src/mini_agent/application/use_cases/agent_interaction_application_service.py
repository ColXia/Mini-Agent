"""Application service for shared main-agent interaction entrypoints."""

from __future__ import annotations

from pathlib import Path
from typing import Any, AsyncIterator, Awaitable, Callable, Protocol

from mini_agent.application.support import (
    ApplicationInteractionBinding,
    FormatBootstrapErrorFn,
    ManagedSessionTurn,
    ResolveWorkspaceDirFn,
    SseEventFn,
    ToUtcIsoFn,
)
from mini_agent.interfaces import MainAgentChatRequest, MainAgentChatResponse, MainAgentRoutingDiagnostics

from ..facades.agent_delegation_execution_handler import AgentDelegationExecutionHandler
from ..facades.agent_route_execution_handler import AgentRouteExecutionHandler
from ..facades.agent_turn_execution_handler import AgentTurnExecutionHandler
from ..facades.surface_chat_flow_handler import SurfaceChatExecutionRequest, SurfaceChatFlowHandler


class SessionTaskFlowPort(Protocol):
    def validate_workspace(self, workspace_dir: Path) -> None: ...

    async def prepare_chat_turn(
        self,
        *,
        workspace_dir: Path,
        message: str,
        session_id: str | None = None,
        session_title_hint: str | None = None,
        surface: str | None = None,
        channel_type: str | None = None,
        conversation_id: str | None = None,
        sender_id: str | None = None,
        running_detail: str,
    ) -> ManagedSessionTurn: ...

    async def prepare_derived_chat_turn(
        self,
        *,
        parent_session_id: str,
        message: str,
        title: str | None = None,
        surface: str | None = None,
        channel_type: str | None = None,
        conversation_id: str | None = None,
        sender_id: str | None = None,
        running_detail: str,
        reason: str,
        metadata: dict[str, Any] | None = None,
    ) -> ManagedSessionTurn: ...


SurfaceActivityEmitter = Callable[[str, dict[str, object]], Awaitable[None] | None]


class RouteExecutionPort(Protocol):
    async def get_routing_diagnostics(self) -> MainAgentRoutingDiagnostics: ...

    async def execute_chat_turn(
        self,
        turn: ManagedSessionTurn,
        request: SurfaceChatExecutionRequest,
        *,
        recovery_context: dict[str, object] | None = None,
        activity_emitter: SurfaceActivityEmitter | None = None,
    ): ...


class AgentInteractionApplicationService:
    """Owns shared user-facing chat submission, streaming, and routing diagnostics."""

    _ROUTE_AGENT_MAIN = "main-agent"
    _ROUTE_AGENT_DELEGATE = "delegate-agent"
    _DELEGATION_COMMAND = "/delegate"
    _DELEGATION_OWNER = "sub-agent"

    def __init__(
        self,
        *,
        session_task_service: SessionTaskFlowPort,
        resolve_workspace_dir: ResolveWorkspaceDirFn,
        to_utc_iso: ToUtcIsoFn,
        sse_event: SseEventFn,
        format_bootstrap_error: FormatBootstrapErrorFn,
        stream_chunk_size: int,
        route_execution: RouteExecutionPort | None = None,
    ) -> None:
        self._session_task_service = session_task_service
        self._resolve_workspace_dir = resolve_workspace_dir
        self._chat_flow = SurfaceChatFlowHandler(
            session_task_service=self._session_task_service,
            to_utc_iso=to_utc_iso,
            sse_event=sse_event,
            format_bootstrap_error=format_bootstrap_error,
            stream_chunk_size=max(1, int(stream_chunk_size)),
        )
        self._agent_execution = AgentTurnExecutionHandler()
        self._delegation_execution = AgentDelegationExecutionHandler(
            session_task_service=self._session_task_service,
            agent_execution=self._agent_execution,
            delegation_owner=self._DELEGATION_OWNER,
            fallback_worker_id=self._ROUTE_AGENT_MAIN,
        )
        self._route_execution = route_execution or AgentRouteExecutionHandler(
            agent_execution=self._agent_execution,
            delegation_execution=self._delegation_execution,
            route_agent_main=self._ROUTE_AGENT_MAIN,
            route_agent_delegate=self._ROUTE_AGENT_DELEGATE,
            delegation_command=self._DELEGATION_COMMAND,
        )

    @property
    def chat_flow(self) -> SurfaceChatFlowHandler:
        return self._chat_flow

    @property
    def route_execution(self) -> RouteExecutionPort:
        return self._route_execution

    async def submit_message(self, request: MainAgentChatRequest) -> MainAgentChatResponse:
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

    def stream_message(
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
        return self._stream_execution_request(
            binding.to_surface_chat_execution_request(
                message=message,
                workspace_dir=self._resolve_workspace_dir(workspace_dir),
                session_id=session_id,
                session_title_hint=session_title_hint,
                dry_run=bool(dry_run),
                running_detail=f"{binding.surface or 'api'} stream running",
            )
        )

    async def _stream_execution_request(
        self,
        request: SurfaceChatExecutionRequest,
    ) -> AsyncIterator[str]:
        async for item in self._chat_flow.stream_chat_events(
            request,
            execute_turn=self._execute_chat_turn,
        ):
            yield item

    async def _execute_chat_turn(
        self,
        turn: ManagedSessionTurn,
        request: SurfaceChatExecutionRequest,
        activity_emitter: SurfaceActivityEmitter | None = None,
    ):
        return await self._route_execution.execute_chat_turn(
            turn,
            request,
            recovery_context=turn.recovery_context,
            activity_emitter=activity_emitter,
        )


__all__ = ["AgentInteractionApplicationService", "RouteExecutionPort"]
