"""Application-layer use cases for Studio Gateway main-agent endpoints."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, AsyncIterator, Callable
from uuid import uuid4

from fastapi import HTTPException

from mini_agent.agent import PlannerExecutorHooks, ToolApprovalRequest, TurnExecutionResult, TurnStopReason
from mini_agent.agent_core.delegation import DelegationManager, DelegationRequest
from mini_agent.agent_core.routing import (
    AgentRouteResolver,
    AgentRouteTable,
    BindingScope,
    RouteResolution,
    RoutingContext,
)
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


@dataclass(frozen=True)
class _DelegationExecution:
    reply: str
    used: bool
    fallback_used: bool
    success: bool
    worker_id: str
    error: str | None
    events: tuple[dict[str, Any], ...]


@dataclass(frozen=True)
class _ResolvedMessageRoute:
    agent_id: str
    delegate_prompt: str | None
    matched_scope: BindingScope
    matched_key: str
    from_cache: bool


class MainAgentGatewayUseCases:
    """Main-agent orchestration use cases for chat and session flows."""

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
        self._route_table = AgentRouteTable()
        self._route_table.add_binding(
            scope=BindingScope.PEER,
            key="delegate",
            agent_id=self._ROUTE_AGENT_DELEGATE,
        )
        self._route_resolver = AgentRouteResolver(self._route_table, max_cache_entries=512)
        self._route_stats_lock = asyncio.Lock()
        self._route_total = 0
        self._route_cache_hits = 0
        self._route_fallbacks = 0
        self._route_scope_counts: dict[str, int] = {}
        self._route_agent_counts: dict[str, int] = {}

    async def run_chat(self, request: MainAgentChatRequest) -> MainAgentChatResponse:
        resolved_workspace = self._resolve_workspace_dir(request.workspace_dir)
        self._session_service.validate_workspace(resolved_workspace)

        if request.dry_run:
            now = datetime.now(timezone.utc)
            return MainAgentChatResponse(
                session_id=request.session_id or "dry-run-session",
                reply=f"[Dry Run] Received task: {request.message}",
                message_count=1,
                token_usage=0,
                workspace_dir=str(resolved_workspace),
                updated_at=self._to_utc_iso(now),
            )

        workspace_dir = resolved_workspace
        workspace_dir.mkdir(parents=True, exist_ok=True)
        try:
            turn = await self._session_service.prepare_chat_turn(
                workspace_dir=workspace_dir,
                message=request.message,
                session_id=request.session_id,
                session_title_hint=request.session_title_hint,
                surface=request.surface,
                channel_type=request.channel_type,
                conversation_id=request.conversation_id,
                sender_id=request.sender_id,
                running_detail=f"{request.surface or 'api'} request running",
            )
        except HTTPException:
            raise
        except Exception as exc:
            raise self._format_bootstrap_error(exc) from exc
        async with turn:
            try:
                route = await self._resolve_message_route(request.message)
                reply, stop_reason, delegation = await self._run_routed_message(
                    turn,
                    request.message,
                    route=route,
                    surface=request.surface,
                    channel_type=request.channel_type,
                    conversation_id=request.conversation_id,
                    sender_id=request.sender_id,
                    recovery_context=turn.recovery_context,
                )
                if route.agent_id == self._ROUTE_AGENT_MAIN:
                    turn.capture_prepared_context_state()
            except HTTPException:
                raise
            except Exception as exc:
                raise HTTPException(status_code=500, detail=f"Agent execution failed: {exc}") from exc
            if turn.recovery_context is not None and route.agent_id == self._ROUTE_AGENT_MAIN:
                turn.clear_recovery_context()
            payload: dict[str, Any] = {}
            if delegation is not None and delegation.used:
                payload["delegation"] = {
                    "used": True,
                    "success": delegation.success,
                    "fallback_used": delegation.fallback_used,
                    "worker_id": delegation.worker_id,
                    "error": delegation.error,
                    "events": list(delegation.events),
                }
            turn.record_message(
                role="assistant",
                content=reply,
                surface=request.surface,
                channel_type=request.channel_type,
                conversation_id=request.conversation_id,
                sender_id=request.sender_id,
            )
            turn.touch()
            return MainAgentChatResponse(
                session_id=turn.session_id,
                reply=reply,
                message_count=turn.message_count,
                token_usage=turn.token_usage,
                workspace_dir=str(turn.workspace_dir),
                updated_at=self._to_utc_iso(turn.updated_at),
                **payload,
            )

    async def get_routing_diagnostics(self) -> MainAgentRoutingDiagnostics:
        async with self._route_stats_lock:
            return MainAgentRoutingDiagnostics(
                total_resolutions=self._route_total,
                cache_hits=self._route_cache_hits,
                fallback_resolutions=self._route_fallbacks,
                matched_scope_counts=dict(self._route_scope_counts),
                matched_agent_counts=dict(self._route_agent_counts),
            )

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
        resolved_workspace = self._resolve_workspace_dir(workspace_dir)
        self._session_service.validate_workspace(resolved_workspace)
        resolved_workspace.mkdir(parents=True, exist_ok=True)

        if dry_run:
            now = self._to_utc_iso(datetime.now(timezone.utc))
            sid = session_id or "dry-run-session"
            assistant_id = uuid4().hex
            yield self._sse_event("session", {"session_id": sid, "workspace_dir": str(resolved_workspace)})
            yield self._sse_event("status", {"stage": "running", "at": now})
            text = f"[Dry Run] Received task: {message}"
            for index in range(0, len(text), self._stream_chunk_size):
                chunk = text[index : index + self._stream_chunk_size]
                yield self._sse_event("delta", {"assistant_id": assistant_id, "chunk": chunk})
                await asyncio.sleep(0)
            yield self._sse_event(
                "done",
                {
                    "session_id": sid,
                    "assistant_id": assistant_id,
                    "reply": text,
                    "token_usage": 0,
                    "message_count": 1,
                    "updated_at": now,
                },
            )
            return

        try:
            turn = await self._session_service.prepare_chat_turn(
                workspace_dir=resolved_workspace,
                message=message,
                session_id=session_id,
                session_title_hint=session_title_hint,
                surface=surface,
                channel_type=channel_type,
                conversation_id=conversation_id,
                sender_id=sender_id,
                running_detail=f"{surface or 'api'} stream running",
            )
        except HTTPException:
            raise
        except Exception as exc:
            raise self._format_bootstrap_error(exc) from exc
        assistant_id = uuid4().hex
        yield self._sse_event("session", {"session_id": turn.session_id, "workspace_dir": str(turn.workspace_dir)})
        yield self._sse_event("status", {"stage": "running", "at": self._to_utc_iso(datetime.now(timezone.utc))})

        async with turn:
            try:
                route = await self._resolve_message_route(message)
                if route.agent_id == self._ROUTE_AGENT_MAIN:
                    stream_events: asyncio.Queue[tuple[str, dict[str, Any]]] = asyncio.Queue()

                    async def _emit_stream_activity(event_type: str, payload: dict[str, Any]) -> None:
                        await stream_events.put((event_type, dict(payload)))

                    task = asyncio.create_task(
                        self._run_routed_message(
                            turn,
                            message,
                            route=route,
                            surface=surface,
                            channel_type=channel_type,
                            conversation_id=conversation_id,
                            sender_id=sender_id,
                            recovery_context=turn.recovery_context,
                            activity_emitter=_emit_stream_activity,
                        )
                    )
                    while not task.done():
                        try:
                            event_type, payload = await asyncio.wait_for(stream_events.get(), timeout=0.9)
                            yield self._sse_event(event_type, payload)
                        except asyncio.TimeoutError:
                            yield self._sse_event("heartbeat", {"at": self._to_utc_iso(datetime.now(timezone.utc))})
                    while not stream_events.empty():
                        event_type, payload = await stream_events.get()
                        yield self._sse_event(event_type, payload)
                    reply, stop_reason, delegation = task.result()
                    turn.capture_prepared_context_state()
                else:
                    reply, stop_reason, delegation = await self._run_routed_message(
                        turn,
                        message,
                        route=route,
                        surface=surface,
                        channel_type=channel_type,
                        conversation_id=conversation_id,
                        sender_id=sender_id,
                        recovery_context=turn.recovery_context,
                    )
                    if delegation is not None:
                        for event in delegation.events:
                            event_type = str(event.get("event_type", "")).strip() or "delegation.event"
                            payload = event.get("payload")
                            if not isinstance(payload, dict):
                                payload = {}
                            yield self._sse_event(event_type, payload)
            except HTTPException as exc:
                yield self._sse_event("error", {"message": str(exc.detail or "Request rejected.")})
                return
            except Exception as exc:
                yield self._sse_event("error", {"message": f"Agent execution failed: {exc}"})
                return
            if turn.recovery_context is not None and route.agent_id == self._ROUTE_AGENT_MAIN:
                turn.clear_recovery_context()
            turn.record_message(
                role="assistant",
                content=reply,
                surface=surface,
                channel_type=channel_type,
                conversation_id=conversation_id,
                sender_id=sender_id,
            )
            for index in range(0, len(reply), self._stream_chunk_size):
                chunk = reply[index : index + self._stream_chunk_size]
                yield self._sse_event("delta", {"assistant_id": assistant_id, "chunk": chunk})
                await asyncio.sleep(0)

            yield self._sse_event(
                "done",
                {
                    "session_id": turn.session_id,
                    "assistant_id": assistant_id,
                    "reply": reply,
                    "stop_reason": stop_reason,
                    "token_usage": turn.token_usage,
                    "message_count": turn.message_count,
                    "updated_at": self._to_utc_iso(turn.updated_at),
                },
            )

    async def _run_agent_once(
        self,
        turn: ManagedSessionTurn,
        message: str,
        *,
        surface: str | None,
        recovery_context: dict[str, Any] | None = None,
        channel_type: str | None = None,
        conversation_id: str | None = None,
        sender_id: str | None = None,
        activity_emitter: Callable[[str, dict[str, Any]], Awaitable[None] | None] | None = None,
    ) -> TurnExecutionResult:
        hooks = self._build_runtime_activity_hooks(
            turn,
            surface=surface,
            channel_type=channel_type,
            conversation_id=conversation_id,
            sender_id=sender_id,
            activity_emitter=activity_emitter,
        )
        approval_handler = self._build_runtime_approval_handler(
            turn,
            surface=surface,
            channel_type=channel_type,
            conversation_id=conversation_id,
            sender_id=sender_id,
            activity_emitter=activity_emitter,
        )
        turn.agent.add_user_message(message)
        turn.restore_prepared_context_state()
        cancel_event = turn.cancel_event
        previous_approval_handler = getattr(turn.agent, "tool_approval_handler", None)
        try:
            setattr(turn.agent, "tool_approval_handler", approval_handler)
        except Exception:
            previous_approval_handler = None
        try:
            if hasattr(turn.agent, "run_turn"):
                reply = await turn.agent.run_turn(
                    cancel_event=cancel_event,
                    hooks=hooks,
                    turn_context={
                        "session_id": turn.session_id,
                        "submission_id": f"gateway:{turn.session_id}",
                        "user_input": message,
                        "metadata": {
                            "surface": surface,
                            "channel_type": channel_type,
                            "conversation_id": conversation_id,
                            "sender_id": sender_id,
                            "prepared_context_policy": dict(turn.context_policy),
                            **({"recovery": dict(recovery_context)} if isinstance(recovery_context, dict) else {}),
                        },
                        "workspace_dir": str(turn.workspace_dir),
                    },
                    start_new_run=True,
                )
            else:  # pragma: no cover - legacy defensive branch
                message_text = await turn.agent.run(cancel_event=cancel_event)
                reply = TurnExecutionResult(stop_reason=TurnStopReason.END_TURN, message=message_text)
        finally:
            try:
                setattr(turn.agent, "tool_approval_handler", previous_approval_handler)
            except Exception:
                pass
        turn.touch()
        return reply

    def _build_runtime_approval_handler(
        self,
        turn: ManagedSessionTurn,
        *,
        surface: str | None,
        channel_type: str | None = None,
        conversation_id: str | None = None,
        sender_id: str | None = None,
        activity_emitter: Callable[[str, dict[str, Any]], Awaitable[None] | None] | None = None,
    ) -> Callable[[ToolApprovalRequest], Awaitable[bool | None]]:
        async def _emit(event_type: str, payload: dict[str, Any]) -> None:
            if activity_emitter is None:
                return
            await activity_emitter(event_type, payload)

        async def _handle(request: ToolApprovalRequest) -> bool | None:
            token = str(getattr(request, "token", "") or "").strip() or f"approval_{uuid4().hex[:12]}"
            normalized_payload = {
                "token": token,
                "tool_name": str(getattr(request, "tool_name", "") or "").strip() or "tool",
                "arguments": dict(getattr(request, "arguments", {}) or {}),
                "kind": str(getattr(request, "kind", "") or "").strip() or None,
                "reason": str(getattr(request, "reason", "") or "").strip() or None,
                "cache_key": str(getattr(request, "cache_key", "") or "").strip() or None,
                "can_escalate": bool(getattr(request, "can_escalate", False)),
                "step": int(getattr(request, "step", 0) or 0),
            }
            future: asyncio.Future[bool | None] = asyncio.get_running_loop().create_future()
            turn.record_pending_approval(
                payload=normalized_payload,
                future=future,
            )
            detail = f"approval required for {normalized_payload['tool_name']}"
            item = turn.record_activity(
                label="approval",
                detail=detail,
                surface=surface,
                activity_id=f"approval:{token}",
                preview=self._tool_activity_preview_from_arguments(normalized_payload["arguments"]),
                state="pending",
                channel_type=channel_type,
                conversation_id=conversation_id,
                sender_id=sender_id,
            )
            turn.running_state = detail
            await _emit("approval_requested", normalized_payload)
            await _emit("activity", {**item, "token": token, "tool_name": normalized_payload["tool_name"], "running_state": detail})
            try:
                decision = await future
            finally:
                turn.clear_pending_approval(token=token)
            decision_label = "approved" if decision is True else ("denied" if decision is False else "cancelled")
            resolved_detail = f"{decision_label} for {normalized_payload['tool_name']}"
            resolved_item = turn.record_activity(
                label="approval",
                detail=resolved_detail,
                surface=surface,
                activity_id=f"approval:{token}",
                state="ok" if decision is True else "failed",
                channel_type=channel_type,
                conversation_id=conversation_id,
                sender_id=sender_id,
            )
            if not turn.pending_approvals and turn.busy:
                turn.running_state = f"continuing after {decision_label}"
            await _emit(
                "approval_resolved",
                {
                    "token": token,
                    "tool_name": normalized_payload["tool_name"],
                    "decision": decision_label,
                    "approved": decision is True,
                },
            )
            await _emit(
                "activity",
                {
                    **resolved_item,
                    "token": token,
                    "tool_name": normalized_payload["tool_name"],
                    "running_state": turn.running_state or resolved_detail,
                },
            )
            return decision

        return _handle

    def _build_runtime_activity_hooks(
        self,
        turn: ManagedSessionTurn,
        *,
        surface: str | None,
        channel_type: str | None = None,
        conversation_id: str | None = None,
        sender_id: str | None = None,
        activity_emitter: Callable[[str, dict[str, Any]], Awaitable[None] | None] | None = None,
    ) -> PlannerExecutorHooks:
        async def _emit_activity(payload: dict[str, Any]) -> None:
            if activity_emitter is None:
                return
            await activity_emitter("activity", payload)

        async def _on_step_plan(step_plan: Any) -> None:
            step = getattr(step_plan, "step", "?")
            planned_tool_calls = getattr(step_plan, "planned_tool_calls", None)
            tool_count = len(planned_tool_calls) if isinstance(planned_tool_calls, list) else 0
            if tool_count > 0:
                detail = f"step {step}: planned {tool_count} tool call(s)"
            else:
                detail = f"step {step}: preparing final response"
            item = turn.record_activity(
                label="thinking",
                detail=detail,
                surface=surface,
                channel_type=channel_type,
                conversation_id=conversation_id,
                sender_id=sender_id,
            )
            await _emit_activity({**item, "running_state": detail})

        async def _on_tool_call_start(step: int, tool_call: Any) -> None:
            tool_name = self._tool_name_from_hook(tool_call)
            detail = "running"
            running_state = f"step {step}: running {tool_name}"
            item = turn.record_activity(
                label=tool_name,
                detail=detail,
                surface=surface,
                activity_id=self._tool_call_key(step, tool_call),
                preview=self._tool_activity_preview(tool_call),
                state="running",
                channel_type=channel_type,
                conversation_id=conversation_id,
                sender_id=sender_id,
            )
            await _emit_activity({**item, "running_state": running_state})

        async def _on_tool_call_result(step: int, tool_call: Any, result: Any) -> None:
            tool_name = self._tool_name_from_hook(tool_call)
            outcome = "ok" if bool(getattr(result, "success", False)) else "failed"
            output_text = ""
            if self._activity_has_output(tool_name, result):
                output_text = self._tool_result_output_text(result)
            elif outcome == "failed":
                output_text = str(getattr(result, "error", "") or "")
            running_state = f"step {step}: {tool_name} {outcome}"
            item = turn.record_activity(
                label=tool_name,
                detail=outcome,
                surface=surface,
                activity_id=self._tool_call_key(step, tool_call),
                preview=self._tool_activity_preview(tool_call),
                output_text=output_text,
                state=outcome,
                channel_type=channel_type,
                conversation_id=conversation_id,
                sender_id=sender_id,
            )
            await _emit_activity({**item, "running_state": running_state})

        return PlannerExecutorHooks(
            on_step_plan=_on_step_plan,
            on_tool_call_start=_on_tool_call_start,
            on_tool_call_result=_on_tool_call_result,
        )

    @staticmethod
    def _tool_name_from_hook(tool_call: Any) -> str:
        function_obj = getattr(tool_call, "function", None)
        if function_obj is not None:
            function_name = str(getattr(function_obj, "name", "") or "").strip()
            if function_name:
                return function_name
        return str(getattr(tool_call, "name", "") or "").strip() or "tool"

    @staticmethod
    def _tool_call_key(step: int, tool_call: Any) -> str:
        tool_call_id = str(getattr(tool_call, "id", "") or "").strip()
        if tool_call_id:
            return tool_call_id
        function_obj = getattr(tool_call, "function", None)
        function_name = str(getattr(function_obj, "name", "") or "").strip() or "tool"
        return f"step-{step}:{function_name}"

    @staticmethod
    def _tool_arguments_from_hook(tool_call: Any) -> dict[str, Any]:
        function_obj = getattr(tool_call, "function", None)
        arguments = getattr(function_obj, "arguments", None)
        return arguments if isinstance(arguments, dict) else {}

    def _tool_activity_preview(self, tool_call: Any) -> str:
        arguments = self._tool_arguments_from_hook(tool_call)
        return self._tool_activity_preview_from_arguments(arguments)

    @staticmethod
    def _tool_activity_preview_from_arguments(arguments: dict[str, Any]) -> str:
        if not arguments:
            return ""
        preview_keys = (
            "command",
            "query",
            "q",
            "prompt",
            "pattern",
            "path",
            "url",
            "model",
            "provider_id",
            "name",
        )
        for key in preview_keys:
            if key not in arguments:
                continue
            value = arguments.get(key)
            if isinstance(value, (list, tuple)):
                preview = ", ".join(str(item).strip() for item in value if str(item).strip())
            else:
                preview = str(value or "").strip()
            if not preview:
                continue
            if key == "command" and bool(arguments.get("run_in_background")):
                preview = f"{preview} [bg]"
            return preview[:69] + "..." if len(preview) > 72 else preview
        return ""

    @staticmethod
    def _activity_has_output(label: str, result: Any) -> bool:
        normalized = str(label or "").strip().lower()
        return normalized.startswith("shell") or hasattr(result, "stdout") or hasattr(result, "stderr")

    @staticmethod
    def _tool_result_output_text(result: Any) -> str:
        blocks: list[str] = []
        stdout = str(getattr(result, "stdout", "") or "").strip()
        stderr = str(getattr(result, "stderr", "") or "").strip()
        content = str(getattr(result, "content", "") or "").strip()
        bash_id = str(getattr(result, "bash_id", "") or "").strip()
        exit_code = getattr(result, "exit_code", None)

        if stdout:
            blocks.append(stdout)
        elif content:
            blocks.append(content)
        if stderr:
            blocks.append("[stderr]")
            blocks.append(stderr)
        if bash_id:
            blocks.append(f"[bash_id] {bash_id}")
        if exit_code is not None:
            blocks.append(f"[exit_code] {exit_code}")
        return "\n".join(blocks).strip()

    @classmethod
    def _parse_delegation_prompt(cls, message: str) -> str | None:
        raw = str(message or "").strip()
        if not raw:
            return None
        command = cls._DELEGATION_COMMAND
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
            default_agent_id=self._ROUTE_AGENT_MAIN,
        )
        await self._record_route_resolution(resolved)
        agent_id = resolved.agent_id
        if agent_id not in {self._ROUTE_AGENT_MAIN, self._ROUTE_AGENT_DELEGATE}:
            agent_id = self._ROUTE_AGENT_MAIN
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
        message: str,
        *,
        route: _ResolvedMessageRoute,
        surface: str | None,
        recovery_context: dict[str, Any] | None = None,
        channel_type: str | None = None,
        conversation_id: str | None = None,
        sender_id: str | None = None,
        activity_emitter: Callable[[str, dict[str, Any]], Awaitable[None] | None] | None = None,
    ) -> tuple[str, str, _DelegationExecution | None]:
        if route.agent_id != self._ROUTE_AGENT_DELEGATE:
            turn_result = await self._run_agent_once(
                turn,
                message,
                surface=surface,
                recovery_context=recovery_context,
                channel_type=channel_type,
                conversation_id=conversation_id,
                sender_id=sender_id,
                activity_emitter=activity_emitter,
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
        owner = self._DELEGATION_OWNER
        write_scope = f"workspace:{turn.workspace_dir}"

        def _emit(event_type: str, payload: dict[str, Any]) -> None:
            events.append({"event_type": event_type, "payload": dict(payload)})

        async def _runner(request: DelegationRequest) -> dict[str, Any]:
            worker = await self._session_service.build_ephemeral_agent(turn.workspace_dir)
            worker.add_user_message(request.prompt)
            output = await worker.run()
            return {
                "success": True,
                "worker_id": owner,
                "output": output,
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

        if result.success:
            _emit(
                "delegation.completed",
                {
                    "task_id": task.task_id,
                    "success": True,
                    "worker_id": result.worker_id,
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
                error=None,
                events=tuple(events),
            )

        _emit(
            "delegation.failed",
            {
                "task_id": task.task_id,
                "success": False,
                "worker_id": result.worker_id,
                "error": result.error,
                "duration_seconds": result.duration_seconds,
            },
        )
        fallback_turn = await self._run_agent_once(
            turn,
            delegate_prompt,
            surface=turn.active_surface or turn.origin_surface,
            channel_type=turn.channel_type,
            conversation_id=turn.conversation_id,
            sender_id=turn.sender_id,
        )
        _emit(
            "delegation.completed",
            {
                "task_id": task.task_id,
                "success": False,
                "worker_id": "main-agent",
                "fallback_used": True,
            },
        )
        return _DelegationExecution(
            reply=fallback_turn.message,
            used=True,
            fallback_used=True,
            success=False,
            worker_id="main-agent",
            error=result.error,
            events=tuple(events),
        )
