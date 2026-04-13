"""Surface-neutral route resolution and delegation execution orchestration."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException

from mini_agent.agent import TurnStopReason
from mini_agent.agent_core.delegation import DelegationManager, DelegationRequest
from mini_agent.agent_core.routing import (
    AgentRouteResolver,
    AgentRouteTable,
    BindingScope,
    RouteResolution,
    RoutingContext,
)
from mini_agent.application.gateway_agent_execution_handler import (
    AgentTurnExecutionHandler,
    SurfaceActivityEmitter,
    SurfaceAgentExecutionRequest,
)
from mini_agent.application.gateway_chat_flow_handler import (
    SurfaceChatExecutionRequest,
    SurfaceChatExecutionResult,
    SurfaceChatStreamEvent,
)
from mini_agent.application.session_service import ManagedSessionTurn, SessionApplicationService
from mini_agent.interfaces import MainAgentRoutingDiagnostics


@dataclass(frozen=True)
class _DelegationExecution:
    reply: str
    used: bool
    fallback_used: bool
    success: bool
    worker_id: str
    child_session_id: str | None
    error: str | None
    events: tuple[dict[str, Any], ...]


@dataclass(frozen=True)
class _ResolvedMessageRoute:
    agent_id: str
    delegate_prompt: str | None
    matched_scope: BindingScope
    matched_key: str
    from_cache: bool


class AgentRouteExecutionHandler:
    """Owns route resolution, route diagnostics, and delegation fallback execution."""

    def __init__(
        self,
        *,
        session_service: SessionApplicationService,
        agent_execution: AgentTurnExecutionHandler,
        route_agent_main: str = "main-agent",
        route_agent_delegate: str = "delegate-agent",
        delegation_command: str = "/delegate",
        delegation_owner: str = "sub-agent",
    ) -> None:
        self._session_service = session_service
        self._agent_execution = agent_execution
        self._route_agent_main = route_agent_main
        self._route_agent_delegate = route_agent_delegate
        self._delegation_command = delegation_command
        self._delegation_owner = delegation_owner
        self._route_table = AgentRouteTable()
        self._route_table.add_binding(
            scope=BindingScope.PEER,
            key="delegate",
            agent_id=self._route_agent_delegate,
        )
        self._route_resolver = AgentRouteResolver(self._route_table, max_cache_entries=512)
        self._route_stats_lock = asyncio.Lock()
        self._route_total = 0
        self._route_cache_hits = 0
        self._route_fallbacks = 0
        self._route_scope_counts: dict[str, int] = {}
        self._route_agent_counts: dict[str, int] = {}

    async def get_routing_diagnostics(self) -> MainAgentRoutingDiagnostics:
        async with self._route_stats_lock:
            return MainAgentRoutingDiagnostics(
                total_resolutions=self._route_total,
                cache_hits=self._route_cache_hits,
                fallback_resolutions=self._route_fallbacks,
                matched_scope_counts=dict(self._route_scope_counts),
                matched_agent_counts=dict(self._route_agent_counts),
            )

    async def execute_chat_turn(
        self,
        turn: ManagedSessionTurn,
        request: SurfaceChatExecutionRequest,
        *,
        recovery_context: dict[str, Any] | None = None,
        activity_emitter: SurfaceActivityEmitter | None = None,
    ) -> SurfaceChatExecutionResult:
        route = await self._resolve_message_route(request.message)
        reply, stop_reason, delegation = await self._run_routed_message(
            turn,
            request=request,
            route=route,
            recovery_context=recovery_context,
            activity_emitter=activity_emitter,
        )
        delegation_payload: dict[str, Any] | None = None
        supplemental_events: list[SurfaceChatStreamEvent] = []
        if delegation is not None and delegation.used:
            delegation_payload = {
                "used": True,
                "success": delegation.success,
                "fallback_used": delegation.fallback_used,
                "worker_id": delegation.worker_id,
                "child_session_id": delegation.child_session_id,
                "error": delegation.error,
                "events": list(delegation.events),
            }
            for event in delegation.events:
                event_type = str(event.get("event_type", "")).strip() or "delegation.event"
                payload = event.get("payload")
                if not isinstance(payload, dict):
                    payload = {}
                supplemental_events.append(
                    SurfaceChatStreamEvent(
                        event_type=event_type,
                        payload=dict(payload),
                    )
                )
        return SurfaceChatExecutionResult(
            reply=reply,
            stop_reason=stop_reason,
            main_route_used=route.agent_id == self._route_agent_main,
            delegation_payload=delegation_payload,
            supplemental_events=tuple(supplemental_events),
        )

    def _parse_delegation_prompt(self, message: str) -> str | None:
        raw = str(message or "").strip()
        if not raw:
            return None
        command = self._delegation_command
        lowered = raw.lower()
        if lowered == command:
            return ""
        if not lowered.startswith(f"{command} "):
            return None
        prompt = raw[len(command) :].strip()
        if prompt.lower().startswith("run "):
            prompt = prompt[4:].strip()
        return prompt

    async def _resolve_message_route(self, message: str) -> _ResolvedMessageRoute:
        delegate_prompt = self._parse_delegation_prompt(message)
        context = RoutingContext(
            peer="delegate" if delegate_prompt is not None else "chat",
            channel="gateway",
        )
        resolved = self._route_resolver.resolve(
            context,
            default_agent_id=self._route_agent_main,
        )
        await self._record_route_resolution(resolved)
        agent_id = resolved.agent_id
        if agent_id not in {self._route_agent_main, self._route_agent_delegate}:
            agent_id = self._route_agent_main
        return _ResolvedMessageRoute(
            agent_id=agent_id,
            delegate_prompt=delegate_prompt,
            matched_scope=resolved.matched_scope,
            matched_key=resolved.matched_key,
            from_cache=resolved.from_cache,
        )

    async def _record_route_resolution(self, resolved: RouteResolution) -> None:
        scope_key = str(getattr(getattr(resolved, "matched_scope", None), "value", "unknown"))
        agent_key = str(getattr(resolved, "agent_id", "unknown") or "unknown")
        fallback = bool(
            getattr(resolved, "matched_scope", None) == BindingScope.DEFAULT
            or str(getattr(resolved, "matched_key", "")) == "fallback"
        )
        async with self._route_stats_lock:
            self._route_total += 1
            if bool(getattr(resolved, "from_cache", False)):
                self._route_cache_hits += 1
            if fallback:
                self._route_fallbacks += 1
            self._route_scope_counts[scope_key] = self._route_scope_counts.get(scope_key, 0) + 1
            self._route_agent_counts[agent_key] = self._route_agent_counts.get(agent_key, 0) + 1

    async def _run_routed_message(
        self,
        turn: ManagedSessionTurn,
        *,
        request: SurfaceChatExecutionRequest,
        route: _ResolvedMessageRoute,
        recovery_context: dict[str, Any] | None = None,
        activity_emitter: SurfaceActivityEmitter | None = None,
    ) -> tuple[str, str, _DelegationExecution | None]:
        if route.agent_id != self._route_agent_delegate:
            turn_result = await self._agent_execution.run_agent_once(
                turn,
                SurfaceAgentExecutionRequest(
                    message=request.message,
                    surface=request.surface,
                    recovery_context=recovery_context,
                    channel_type=request.channel_type,
                    conversation_id=request.conversation_id,
                    sender_id=request.sender_id,
                    activity_emitter=activity_emitter,
                ),
            )
            return turn_result.message, turn_result.stop_reason.value, None
        delegate_prompt = route.delegate_prompt or ""
        if not delegate_prompt:
            raise HTTPException(status_code=400, detail="Delegation command requires a non-empty objective.")
        delegation = await self._run_delegation_with_fallback(
            turn=turn,
            delegate_prompt=delegate_prompt,
        )
        return delegation.reply, TurnStopReason.END_TURN.value, delegation

    async def _run_delegation_with_fallback(
        self,
        *,
        turn: ManagedSessionTurn,
        delegate_prompt: str,
    ) -> _DelegationExecution:
        events: list[dict[str, Any]] = []
        owner = self._delegation_owner
        write_scope = f"workspace:{turn.workspace_dir}"

        def _emit(event_type: str, payload: dict[str, Any]) -> None:
            events.append({"event_type": event_type, "payload": dict(payload)})

        async def _runner(request: DelegationRequest) -> dict[str, Any]:
            child_turn = await self._session_service.prepare_derived_chat_turn(
                parent_session_id=turn.session_id,
                message=request.prompt,
                title=self._delegated_session_title(request.prompt),
                surface=turn.active_surface or turn.origin_surface,
                running_detail="delegated task running",
                reason="delegation",
                metadata={
                    "delegation_task_id": request.task_id,
                    "owner": owner,
                    "write_scope": write_scope,
                },
            )

            async with child_turn:
                try:
                    result = await self._agent_execution.run_agent_once(
                        child_turn,
                        SurfaceAgentExecutionRequest(
                            message=request.prompt,
                            surface=child_turn.active_surface or child_turn.origin_surface,
                            channel_type=child_turn.channel_type,
                            conversation_id=child_turn.conversation_id,
                            sender_id=child_turn.sender_id,
                        ),
                    )
                    child_turn.capture_prepared_context_state()
                    if child_turn.recovery_context is not None:
                        child_turn.clear_recovery_context()
                    child_turn.record_message(
                        role="assistant",
                        content=result.message,
                        surface=child_turn.active_surface or child_turn.origin_surface,
                        channel_type=child_turn.channel_type,
                        conversation_id=child_turn.conversation_id,
                        sender_id=child_turn.sender_id,
                    )
                    child_turn.touch()
                    return {
                        "success": True,
                        "worker_id": owner,
                        "child_session_id": child_turn.session_id,
                        "output": result.message,
                    }
                except Exception as exc:
                    error_text = str(getattr(exc, "detail", "") or str(exc) or "delegation failed")
                    child_turn.record_message(
                        role="assistant",
                        content=f"Delegation failed: {error_text}",
                        surface=child_turn.active_surface or child_turn.origin_surface,
                        metadata={"kind": "delegation_error"},
                        channel_type=child_turn.channel_type,
                        conversation_id=child_turn.conversation_id,
                        sender_id=child_turn.sender_id,
                    )
                    child_turn.touch()
                    return {
                        "success": False,
                        "worker_id": owner,
                        "child_session_id": child_turn.session_id,
                        "output": "",
                        "error": error_text,
                    }

        manager = DelegationManager(
            runner=_runner,
            max_depth=2,
            max_concurrent=1,
        )
        task = manager.create_task(
            prompt=delegate_prompt,
            parent_session_id=turn.session_id,
            metadata={"owner": owner, "write_scope": write_scope},
        )

        _emit(
            "delegation.started",
            {
                "task_id": task.task_id,
                "session_id": turn.session_id,
                "owner": owner,
                "write_scope": write_scope,
            },
        )
        result = await manager.delegate(task, parent_depth=0)
        child_session_id = str(getattr(result, "child_session_id", "") or "")
        normalized_child_session_id = child_session_id or None

        if result.success:
            _emit(
                "delegation.completed",
                {
                    "task_id": task.task_id,
                    "success": True,
                    "worker_id": result.worker_id,
                    "child_session_id": normalized_child_session_id,
                    "fallback_used": False,
                    "duration_seconds": result.duration_seconds,
                },
            )
            turn.touch()
            return _DelegationExecution(
                reply=result.output,
                used=True,
                fallback_used=False,
                success=True,
                worker_id=result.worker_id,
                child_session_id=normalized_child_session_id,
                error=None,
                events=tuple(events),
            )

        _emit(
            "delegation.failed",
            {
                "task_id": task.task_id,
                "success": False,
                "worker_id": result.worker_id,
                "child_session_id": normalized_child_session_id,
                "error": result.error,
                "duration_seconds": result.duration_seconds,
            },
        )
        fallback_turn = await self._agent_execution.run_agent_once(
            turn,
            SurfaceAgentExecutionRequest(
                message=delegate_prompt,
                surface=turn.active_surface or turn.origin_surface,
                channel_type=turn.channel_type,
                conversation_id=turn.conversation_id,
                sender_id=turn.sender_id,
            ),
        )
        _emit(
            "delegation.completed",
            {
                "task_id": task.task_id,
                "success": False,
                "worker_id": self._route_agent_main,
                "child_session_id": normalized_child_session_id,
                "fallback_used": True,
            },
        )
        return _DelegationExecution(
            reply=fallback_turn.message,
            used=True,
            fallback_used=True,
            success=False,
            worker_id=self._route_agent_main,
            child_session_id=normalized_child_session_id,
            error=result.error,
            events=tuple(events),
        )

    @staticmethod
    def _delegated_session_title(prompt: str) -> str:
        preview = " ".join(str(prompt or "").split())
        if not preview:
            return "Task"
        if len(preview) > 48:
            preview = f"{preview[:45]}..."
        return f"Task: {preview}"


GatewayRouteExecutionHandler = AgentRouteExecutionHandler

__all__ = ["AgentRouteExecutionHandler", "GatewayRouteExecutionHandler"]
