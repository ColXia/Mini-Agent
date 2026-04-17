"""Surface-neutral route resolution and routed-execution dispatch orchestration."""

from __future__ import annotations

import asyncio
import importlib
from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException

from mini_agent.agent_core.engine import TurnStopReason
from mini_agent.agent_core.routing import (
    AgentRouteResolver,
    AgentRouteTable,
    BindingScope,
    RouteResolution,
    RoutingContext,
)
from mini_agent.application.support import ManagedSessionTurn
from mini_agent.interfaces import MainAgentRoutingDiagnostics
from mini_agent.model_manager.runtime import get_model_route_diagnostics_state as _get_model_route_diagnostics_state

from .agent_delegation_execution_handler import (
    AgentDelegationExecutionHandler,
    AgentDelegationExecutionResult,
)
from .agent_turn_execution_handler import (
    AgentTurnExecutionHandler,
    SurfaceActivityEmitter,
    SurfaceAgentExecutionRequest,
)
from .surface_chat_flow_handler import (
    SurfaceChatExecutionRequest,
    SurfaceChatExecutionResult,
    SurfaceChatStreamEvent,
)


def _get_model_route_diagnostics_state_compat() -> dict[str, Any]:
    module = importlib.import_module("mini_agent.application.agent_route_execution_handler")
    callback = getattr(module, "get_model_route_diagnostics_state", _get_model_route_diagnostics_state)
    return callback()


@dataclass(frozen=True)
class _ResolvedMessageRoute:
    agent_id: str
    delegate_prompt: str | None
    matched_scope: BindingScope
    matched_key: str
    from_cache: bool


class AgentRouteExecutionHandler:
    """Owns route resolution, route diagnostics, and route-to-executor dispatch."""

    def __init__(
        self,
        *,
        agent_execution: AgentTurnExecutionHandler,
        delegation_execution: AgentDelegationExecutionHandler,
        route_agent_main: str = "main-agent",
        route_agent_delegate: str = "delegate-agent",
        delegation_command: str = "/delegate",
    ) -> None:
        self._agent_execution = agent_execution
        self._delegation_execution = delegation_execution
        self._route_agent_main = route_agent_main
        self._route_agent_delegate = route_agent_delegate
        self._delegation_command = delegation_command
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
        model_route_state = _get_model_route_diagnostics_state_compat()
        async with self._route_stats_lock:
            return MainAgentRoutingDiagnostics(
                total_resolutions=self._route_total,
                cache_hits=self._route_cache_hits,
                fallback_resolutions=self._route_fallbacks,
                matched_scope_counts=dict(self._route_scope_counts),
                matched_agent_counts=dict(self._route_agent_counts),
                model_route_resolutions=int(model_route_state.get("resolution_count", 0) or 0),
                latest_model_route=model_route_state.get("latest_snapshot"),
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
    ) -> tuple[str, str, AgentDelegationExecutionResult | None]:
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
        delegation = await self._delegation_execution.execute(
            turn=turn,
            delegate_prompt=delegate_prompt,
        )
        return delegation.reply, TurnStopReason.END_TURN.value, delegation

__all__ = ["AgentRouteExecutionHandler"]
