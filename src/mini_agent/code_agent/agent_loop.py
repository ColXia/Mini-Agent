"""Submission-loop baseline for code-agent event processing."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
import inspect
import json
from types import SimpleNamespace
from typing import Any, Awaitable, Callable
from uuid import uuid4

from mini_agent.code_agent.context import AgentLoopContext, TurnContext
from mini_agent.code_agent.scheduler import SchedulerResult, SchedulerState, TurnScheduler


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _safe_text(value: Any) -> str:
    return " ".join(str(value or "").split())


def _truncate_inline(value: Any, *, limit: int) -> str:
    cleaned = _safe_text(value)
    if len(cleaned) <= limit:
        return cleaned
    return f"{cleaned[: max(0, limit - 3)]}..."


def _tool_name_from_hook(tool_call: Any) -> str:
    function = getattr(tool_call, "function", None)
    raw_name = getattr(function, "name", None)
    if raw_name is None and isinstance(tool_call, dict):
        function = tool_call.get("function")
        if isinstance(function, dict):
            raw_name = function.get("name")
    normalized = _safe_text(raw_name).lower()
    if normalized == "bash":
        return "shell"
    return normalized or "tool"


def _tool_activity_preview(tool_call: Any) -> str:
    function = getattr(tool_call, "function", None)
    arguments = getattr(function, "arguments", None)
    if arguments is None and isinstance(tool_call, dict):
        function = tool_call.get("function")
        if isinstance(function, dict):
            arguments = function.get("arguments")
    if isinstance(arguments, dict):
        for key in ("command", "path", "pattern", "url", "text"):
            preview = _safe_text(arguments.get(key))
            if preview:
                return _truncate_inline(preview, limit=96)
        raw = json.dumps(arguments, ensure_ascii=False, sort_keys=True)
        return _truncate_inline(raw, limit=96)
    return _truncate_inline(arguments, limit=96)


def _tool_call_key(step: int, tool_call: Any) -> str:
    raw = getattr(tool_call, "id", None)
    if raw is None and isinstance(tool_call, dict):
        raw = tool_call.get("id")
    normalized = _safe_text(raw)
    if normalized:
        return normalized
    return f"tool:{step}:{_tool_name_from_hook(tool_call)}"


def _tool_result_output_text(result: Any) -> str:
    parts: list[str] = []
    for attr in ("stdout", "stderr", "content", "error"):
        value = getattr(result, attr, None)
        if value is None and isinstance(result, dict):
            value = result.get(attr)
        text = str(value or "").strip()
        if text:
            parts.append(text)
    return "\n".join(parts).strip()


def _activity_output_summary(output_text: str) -> str:
    normalized = str(output_text or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if not normalized:
        return ""
    line = next((item.strip() for item in normalized.split("\n") if item.strip()), "")
    return _truncate_inline(line, limit=88)


class SubmissionEventType(str, Enum):
    """Submission-loop event types."""

    USER_INPUT = "user_input"
    INTERRUPT = "interrupt"
    EXEC_APPROVAL = "exec_approval"
    COMPACT = "compact"
    DROP_MEMORIES = "drop_memories"
    LOOP_STOP = "loop_stop"


@dataclass(frozen=True)
class SubmissionEvent:
    """One queued submission-loop event."""

    event_id: str
    event_type: SubmissionEventType
    payload: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=_utc_now)


class InMemoryLoopMessageBus:
    """Simple in-memory message bus for loop events and tests."""

    def __init__(self):
        self.events: list[dict[str, Any]] = []
        self._lock = asyncio.Lock()

    async def publish(self, event_type: str, payload: dict[str, Any]) -> None:
        async with self._lock:
            self.events.append(
                {
                    "event_type": str(event_type),
                    "payload": dict(payload),
                    "timestamp": _utc_now().astimezone(timezone.utc).isoformat(),
                }
            )


@dataclass
class _TurnProgressRecorder:
    submission_id: str
    activity_items: list[dict[str, Any]] = field(default_factory=list)
    running_state: str = ""
    pending_approvals: dict[str, dict[str, Any]] = field(default_factory=dict)

    def _upsert_activity(
        self,
        *,
        activity_id: str,
        label: str,
        detail: str,
        preview: str = "",
        output_text: str = "",
        state: str = "",
        running_state: str = "",
    ) -> dict[str, Any]:
        normalized_id = _safe_text(activity_id) or f"activity-{len(self.activity_items) + 1}"
        normalized_label = _safe_text(label).lower() or "activity"
        normalized_detail = _safe_text(detail) or "running"
        normalized_preview = _safe_text(preview)
        normalized_output = str(output_text or "").strip()
        normalized_state = _safe_text(state).lower()
        target = next((item for item in self.activity_items if _safe_text(item.get("id")) == normalized_id), None)
        if target is None:
            target = {
                "id": normalized_id,
                "label": normalized_label,
                "detail": normalized_detail,
                "preview": normalized_preview,
                "output_text": normalized_output,
                "output_summary": _activity_output_summary(normalized_output),
                "state": normalized_state,
            }
            self.activity_items.append(target)
        else:
            target["label"] = normalized_label
            target["detail"] = normalized_detail
            if normalized_preview:
                target["preview"] = normalized_preview
            if normalized_output or "output_text" not in target:
                target["output_text"] = normalized_output
                target["output_summary"] = _activity_output_summary(normalized_output)
            if normalized_state or "state" not in target:
                target["state"] = normalized_state
        if running_state:
            self.running_state = _safe_text(running_state)
        return dict(target)

    def record_step_plan(self, step_plan: Any) -> dict[str, Any]:
        step = getattr(step_plan, "step", "?")
        planned_tool_calls = getattr(step_plan, "planned_tool_calls", None)
        tool_count = len(planned_tool_calls) if isinstance(planned_tool_calls, list) else 0
        if tool_count > 0:
            detail = f"step {step}: planned {tool_count} tool call(s)"
        else:
            detail = f"step {step}: preparing final response"
        item = self._upsert_activity(
            activity_id=f"thinking:{step}",
            label="thinking",
            detail=detail,
            state="running" if tool_count > 0 else "",
            running_state=detail,
        )
        return {**item, "submission_id": self.submission_id, "activity_id": item["id"], "running_state": detail}

    def record_tool_call_start(self, step: int, tool_call: Any) -> dict[str, Any]:
        tool_name = _tool_name_from_hook(tool_call)
        detail = "running"
        running_state = f"step {step}: running {tool_name}"
        item = self._upsert_activity(
            activity_id=_tool_call_key(step, tool_call),
            label=tool_name,
            detail=detail,
            preview=_tool_activity_preview(tool_call),
            state="running",
            running_state=running_state,
        )
        return {**item, "submission_id": self.submission_id, "activity_id": item["id"], "running_state": running_state}

    def record_tool_call_result(self, step: int, tool_call: Any, result: Any) -> dict[str, Any]:
        tool_name = _tool_name_from_hook(tool_call)
        success = bool(getattr(result, "success", False))
        outcome = "ok" if success else "failed"
        running_state = f"step {step}: {tool_name} {outcome}"
        output_text = _tool_result_output_text(result)
        item = self._upsert_activity(
            activity_id=_tool_call_key(step, tool_call),
            label=tool_name,
            detail=outcome,
            preview=_tool_activity_preview(tool_call),
            output_text=output_text,
            state=outcome,
            running_state=running_state,
        )
        return {**item, "submission_id": self.submission_id, "activity_id": item["id"], "running_state": running_state}

    def record_approval_requested(self, payload: dict[str, Any]) -> dict[str, Any]:
        token = _safe_text(payload.get("token")) or f"approval:{len(self.pending_approvals) + 1}"
        tool_name = _safe_text(payload.get("tool_name")) or "tool"
        detail = f"approval required for {tool_name}"
        self.pending_approvals[token] = dict(payload)
        item = self._upsert_activity(
            activity_id=f"approval:{token}",
            label="approval",
            detail=detail,
            preview=_safe_text(payload.get("arguments")),
            state="pending",
            running_state=detail,
        )
        return {**item, "submission_id": self.submission_id, "activity_id": item["id"], "running_state": detail}

    def record_approval_resolved(self, payload: dict[str, Any]) -> dict[str, Any]:
        token = _safe_text(payload.get("token"))
        if token:
            self.pending_approvals.pop(token, None)
        tool_name = _safe_text(payload.get("tool_name")) or "tool"
        decision = _safe_text(payload.get("decision")) or "resolved"
        detail = f"{decision} for {tool_name}"
        running_state = f"continuing after {decision}" if not self.pending_approvals else detail
        item = self._upsert_activity(
            activity_id=f"approval:{token or tool_name}",
            label="approval",
            detail=detail,
            state="ok" if decision == "approved" else "failed",
            running_state=running_state,
        )
        return {**item, "submission_id": self.submission_id, "activity_id": item["id"], "running_state": running_state}

    def snapshot_payload(self) -> dict[str, Any]:
        last_activity_summary = ""
        if self.activity_items:
            last = self.activity_items[-1]
            parts = [
                _safe_text(last.get("label")),
                _safe_text(last.get("detail")),
                _safe_text(last.get("preview")),
                _safe_text(last.get("output_summary")),
            ]
            last_activity_summary = " | ".join(part for part in parts if part).strip()
        last_tool_activity = next(
            (
                dict(item)
                for item in reversed(self.activity_items)
                if _safe_text(item.get("label")) not in {"thinking", "approval"}
            ),
            None,
        )
        last_tool_activity_summary = ""
        if isinstance(last_tool_activity, dict):
            parts = [
                _safe_text(last_tool_activity.get("label")),
                _safe_text(last_tool_activity.get("detail")),
                _safe_text(last_tool_activity.get("preview")),
                _safe_text(last_tool_activity.get("output_summary")),
            ]
            last_tool_activity_summary = " | ".join(part for part in parts if part).strip()
        return {
            "activity_items": [dict(item) for item in self.activity_items],
            "running_state": self.running_state or None,
            "last_activity_summary": last_activity_summary or None,
            "last_tool_activity": last_tool_activity,
            "last_tool_activity_summary": last_tool_activity_summary or None,
            "pending_approval_count": len(self.pending_approvals),
        }


async def wait_for_submission_completion(
    *,
    bus: InMemoryLoopMessageBus,
    submission_id: str,
    event_start_index: int = 0,
    poll_interval_seconds: float = 0.05,
    on_event: Callable[[str, dict[str, Any]], Awaitable[None] | None] | None = None,
) -> dict[str, Any]:
    """Wait for one submission completion payload while streaming loop events."""
    observed_index = max(0, int(event_start_index))
    target_submission_id = str(submission_id).strip()

    while True:
        pending_events = list(bus.events[observed_index:])
        if pending_events:
            for event in pending_events:
                observed_index += 1
                event_type = str(event.get("event_type", "") or "")
                payload = event.get("payload")
                if not isinstance(payload, dict):
                    payload = {}
                if on_event is not None:
                    maybe_awaitable = on_event(event_type, payload)
                    if inspect.isawaitable(maybe_awaitable):
                        await maybe_awaitable
                if event_type != "loop.turn.completed":
                    continue
                if str(payload.get("submission_id", "") or "").strip() != target_submission_id:
                    continue
                return payload
        await asyncio.sleep(max(0.01, float(poll_interval_seconds)))


async def wait_for_loop_event(
    *,
    bus: InMemoryLoopMessageBus,
    event_type: str,
    event_start_index: int = 0,
    event_id: str | None = None,
    poll_interval_seconds: float = 0.05,
    timeout_seconds: float | None = 10.0,
    on_event: Callable[[str, dict[str, Any]], Awaitable[None] | None] | None = None,
) -> dict[str, Any]:
    """Wait for one non-turn loop event payload, optionally matching one event id."""
    observed_index = max(0, int(event_start_index))
    target_event_type = str(event_type or "").strip()
    target_event_id = str(event_id or "").strip() or None
    deadline = None
    if timeout_seconds is not None:
        deadline = asyncio.get_running_loop().time() + max(0.1, float(timeout_seconds))

    while True:
        pending_events = list(bus.events[observed_index:])
        if pending_events:
            for event in pending_events:
                observed_index += 1
                current_event_type = str(event.get("event_type", "") or "")
                payload = event.get("payload")
                if not isinstance(payload, dict):
                    payload = {}
                if on_event is not None:
                    maybe_awaitable = on_event(current_event_type, payload)
                    if inspect.isawaitable(maybe_awaitable):
                        await maybe_awaitable
                if current_event_type != target_event_type:
                    continue
                if target_event_id is not None and str(payload.get("event_id", "") or "").strip() != target_event_id:
                    continue
                return payload
        if deadline is not None and asyncio.get_running_loop().time() >= deadline:
            raise TimeoutError(f"Timed out waiting for loop event '{target_event_type}'.")
        await asyncio.sleep(max(0.01, float(poll_interval_seconds)))


class AgentSubmissionLoop:
    """Async queue-based submission loop with interrupt support."""

    def __init__(
        self,
        *,
        context: AgentLoopContext,
        agent_factory: Callable[[AgentLoopContext], Any | Awaitable[Any]],
        scheduler: TurnScheduler | None = None,
        hooks: Any | None = None,
        max_queue_size: int = 256,
    ):
        self.context = context
        self._agent_factory = agent_factory
        self._scheduler = scheduler or TurnScheduler()
        self._hooks = hooks
        self._queue: asyncio.Queue[SubmissionEvent] = asyncio.Queue(maxsize=max(1, int(max_queue_size)))
        self._worker_task: asyncio.Task[None] | None = None
        self._agent: Any | None = None
        self._agent_lock = asyncio.Lock()
        self._active_cancel_event: asyncio.Event | None = None
        self._active_submission_id: str | None = None
        self._active_progress: _TurnProgressRecorder | None = None
        self._pending_approvals: dict[str, asyncio.Future[bool | None]] = {}

    async def start(self) -> None:
        if self._worker_task is not None and not self._worker_task.done():
            return
        self._worker_task = asyncio.create_task(self._run_worker())

    async def stop(self) -> None:
        await self._queue.put(
            SubmissionEvent(
                event_id=f"evt_{uuid4().hex}",
                event_type=SubmissionEventType.LOOP_STOP,
            )
        )
        if self._worker_task is not None:
            await self._worker_task
            self._worker_task = None

    async def join(self) -> None:
        await self._queue.join()

    @property
    def queue_size(self) -> int:
        return self._queue.qsize()

    @property
    def current_submission_id(self) -> str | None:
        return self._active_submission_id

    async def submit_user_input(
        self,
        user_input: str,
        *,
        policy_overrides: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
        start_new_run: bool = True,
    ) -> str:
        submission_id = f"sub_{uuid4().hex[:16]}"
        turn_context = self.context.snapshot_turn_context(
            submission_id=submission_id,
            user_input=user_input,
            policy_overrides=policy_overrides,
            metadata=metadata,
            start_new_run=start_new_run,
        )
        event = SubmissionEvent(
            event_id=f"evt_{uuid4().hex}",
            event_type=SubmissionEventType.USER_INPUT,
            payload={"turn_context": turn_context},
        )
        await self._queue.put(event)
        return submission_id

    async def submit_interrupt(self, *, reason: str | None = None) -> str:
        # Interrupt should be immediate even if worker is in one running turn.
        dispatched_immediately = False
        if self._active_cancel_event is not None:
            self._active_cancel_event.set()
            dispatched_immediately = True
        if self._pending_approvals:
            for future in list(self._pending_approvals.values()):
                if not future.done():
                    future.set_result(None)
        event = SubmissionEvent(
            event_id=f"evt_{uuid4().hex}",
            event_type=SubmissionEventType.INTERRUPT,
            payload={
                "reason": (reason or "").strip() or None,
                "dispatched_immediately": dispatched_immediately,
            },
        )
        await self._queue.put(event)
        return event.event_id

    async def submit_exec_approval(self, *, approved: bool, token: str | None = None) -> str:
        event_id = f"evt_{uuid4().hex}"
        resolved_token = self._resolve_pending_approval(
            approved=bool(approved),
            token=token,
        )
        await self._publish(
            "loop.exec_approval",
            {
                "event_id": event_id,
                "approved": bool(approved),
                "token": resolved_token,
                "requested_token": token,
                "matched": resolved_token is not None,
                "active_submission_id": self._active_submission_id,
            },
        )
        return event_id

    async def submit_compact(self, *, reason: str | None = None) -> str:
        event = SubmissionEvent(
            event_id=f"evt_{uuid4().hex}",
            event_type=SubmissionEventType.COMPACT,
            payload={"reason": (reason or "").strip() or None},
        )
        await self._queue.put(event)
        return event.event_id

    async def submit_drop_memories(self, *, reason: str | None = None) -> str:
        event = SubmissionEvent(
            event_id=f"evt_{uuid4().hex}",
            event_type=SubmissionEventType.DROP_MEMORIES,
            payload={"reason": (reason or "").strip() or None},
        )
        await self._queue.put(event)
        return event.event_id

    async def _publish(self, event_type: str, payload: dict[str, Any]) -> None:
        bus = self.context.message_bus
        if bus is None:
            return
        publisher = getattr(bus, "publish", None)
        if publisher is None:
            return
        maybe_awaitable = publisher(event_type, payload)
        if asyncio.iscoroutine(maybe_awaitable):
            await maybe_awaitable

    async def _ensure_agent(self) -> Any:
        if self._agent is not None:
            return self._agent
        async with self._agent_lock:
            if self._agent is not None:
                return self._agent
            created = self._agent_factory(self.context)
            if asyncio.iscoroutine(created):
                created = await created
            try:
                setattr(created, "tool_approval_handler", self._request_exec_approval)
            except Exception:
                pass
            self._agent = created
            return self._agent

    def _resolve_pending_approval(self, *, approved: bool, token: str | None = None) -> str | None:
        normalized_token = str(token or "").strip() or None
        matched_token = normalized_token
        if matched_token is None:
            if len(self._pending_approvals) == 1:
                matched_token = next(iter(self._pending_approvals))
            else:
                return None
        future = self._pending_approvals.get(matched_token)
        if future is None or future.done():
            return None
        future.set_result(bool(approved))
        return matched_token

    async def _request_exec_approval(self, request: Any) -> bool | None:
        token = str(getattr(request, "token", "") or "").strip() or f"approval_{uuid4().hex[:12]}"
        submission_id = self._active_submission_id
        future: asyncio.Future[bool | None] = asyncio.get_running_loop().create_future()
        self._pending_approvals[token] = future

        await self._publish(
            "loop.approval.requested",
            {
                "submission_id": submission_id,
                "token": token,
                "tool_name": str(getattr(request, "tool_name", "") or "").strip(),
                "arguments": dict(getattr(request, "arguments", {}) or {}),
                "kind": str(getattr(request, "kind", "") or "").strip(),
                "reason": str(getattr(request, "reason", "") or "").strip(),
                "cache_key": str(getattr(request, "cache_key", "") or "").strip() or None,
                "can_escalate": bool(getattr(request, "can_escalate", False)),
                "step": int(getattr(request, "step", 0) or 0),
            },
        )
        if self._active_progress is not None:
            await self._publish(
                "loop.activity",
                self._active_progress.record_approval_requested(
                    {
                        "submission_id": submission_id,
                        "token": token,
                        "tool_name": str(getattr(request, "tool_name", "") or "").strip(),
                        "arguments": dict(getattr(request, "arguments", {}) or {}),
                        "kind": str(getattr(request, "kind", "") or "").strip(),
                        "reason": str(getattr(request, "reason", "") or "").strip(),
                    }
                ),
            )

        try:
            decision = await future
        finally:
            current = self._pending_approvals.get(token)
            if current is future:
                self._pending_approvals.pop(token, None)

        decision_label = "approved" if decision is True else ("denied" if decision is False else "cancelled")
        await self._publish(
            "loop.approval.resolved",
            {
                "submission_id": submission_id,
                "token": token,
                "tool_name": str(getattr(request, "tool_name", "") or "").strip(),
                "decision": decision_label,
                "approved": decision is True,
            },
        )
        if self._active_progress is not None:
            await self._publish(
                "loop.activity",
                self._active_progress.record_approval_resolved(
                    {
                        "submission_id": submission_id,
                        "token": token,
                        "tool_name": str(getattr(request, "tool_name", "") or "").strip(),
                        "decision": decision_label,
                    }
                ),
            )
        return decision

    def _compose_hooks(self, external_hooks: Any | None, progress: _TurnProgressRecorder) -> Any:
        async def _call_hook(callback: Any, *args: Any) -> None:
            if callback is None:
                return
            maybe_awaitable = callback(*args)
            if inspect.isawaitable(maybe_awaitable):
                await maybe_awaitable

        async def _on_step_plan(step_plan: Any) -> None:
            await self._publish("loop.activity", progress.record_step_plan(step_plan))
            await _call_hook(getattr(external_hooks, "on_step_plan", None), step_plan)

        async def _on_tool_call_start(step: int, tool_call: Any) -> None:
            await self._publish("loop.activity", progress.record_tool_call_start(step, tool_call))
            await _call_hook(getattr(external_hooks, "on_tool_call_start", None), step, tool_call)

        async def _on_tool_call_result(step: int, tool_call: Any, result: Any) -> None:
            await self._publish("loop.activity", progress.record_tool_call_result(step, tool_call, result))
            await _call_hook(getattr(external_hooks, "on_tool_call_result", None), step, tool_call, result)

        return SimpleNamespace(
            on_step_plan=_on_step_plan,
            on_tool_call_start=_on_tool_call_start,
            on_tool_call_result=_on_tool_call_result,
        )

    async def _run_worker(self) -> None:
        while True:
            event = await self._queue.get()
            try:
                if event.event_type == SubmissionEventType.LOOP_STOP:
                    return
                await self._handle_event(event)
            finally:
                self._queue.task_done()

    async def _handle_event(self, event: SubmissionEvent) -> None:
        if event.event_type == SubmissionEventType.USER_INPUT:
            await self._handle_user_input(event)
            return

        if event.event_type == SubmissionEventType.INTERRUPT:
            dispatched = bool(event.payload.get("dispatched_immediately", False))
            if self._active_submission_id is not None:
                dispatched = True
            await self._publish(
                "loop.interrupt",
                {
                    "event_id": event.event_id,
                    "active_submission_id": self._active_submission_id,
                    "reason": event.payload.get("reason"),
                    "dispatched": dispatched,
                },
            )
            return

        if event.event_type == SubmissionEventType.EXEC_APPROVAL:
            await self._publish(
                "loop.exec_approval",
                {
                    "event_id": event.event_id,
                    "approved": bool(event.payload.get("approved", False)),
                    "token": event.payload.get("token"),
                },
            )
            return

        if event.event_type == SubmissionEventType.COMPACT:
            mutation_payload = {
                "event_id": event.event_id,
                "reason": event.payload.get("reason"),
                "applied": False,
                "unsupported": False,
            }
            try:
                agent = await self._ensure_agent()
                compact_context = getattr(agent, "compact_context", None)
                if compact_context is None:
                    mutation_payload["unsupported"] = True
                else:
                    result = compact_context(reason=event.payload.get("reason"))
                    if inspect.isawaitable(result):
                        result = await result
                    if isinstance(result, dict):
                        mutation_payload.update(result)
                    else:
                        mutation_payload["applied"] = bool(result)
            except Exception as exc:
                mutation_payload["error"] = f"{type(exc).__name__}: {exc}"
            await self._publish("loop.compact", mutation_payload)
            return

        if event.event_type == SubmissionEventType.DROP_MEMORIES:
            mutation_payload = {
                "event_id": event.event_id,
                "reason": event.payload.get("reason"),
                "applied": False,
                "unsupported": False,
            }
            try:
                agent = await self._ensure_agent()
                drop_memories = getattr(agent, "drop_memories", None)
                if drop_memories is None:
                    mutation_payload["unsupported"] = True
                else:
                    result = drop_memories(reason=event.payload.get("reason"))
                    if inspect.isawaitable(result):
                        result = await result
                    if isinstance(result, dict):
                        mutation_payload.update(result)
                    else:
                        mutation_payload["applied"] = bool(result)
            except Exception as exc:
                mutation_payload["error"] = f"{type(exc).__name__}: {exc}"
            await self._publish("loop.drop_memories", mutation_payload)

    async def _handle_user_input(self, event: SubmissionEvent) -> None:
        turn_context = event.payload.get("turn_context")
        if not isinstance(turn_context, TurnContext):
            await self._publish(
                "loop.turn.errored",
                {
                    "event_id": event.event_id,
                    "error": "invalid_turn_context",
                },
            )
            return

        await self._publish(
            "loop.turn.scheduled",
            {
                "submission_id": turn_context.submission_id,
                "session_id": turn_context.session_id,
                "policy": {
                    "max_steps": turn_context.policy.max_steps,
                    "max_tool_calls_per_step": turn_context.policy.max_tool_calls_per_step,
                },
                "start_new_run": turn_context.start_new_run,
                "metadata": dict(turn_context.metadata),
            },
        )

        agent = await self._ensure_agent()
        cancel_event = asyncio.Event()
        progress = _TurnProgressRecorder(turn_context.submission_id)
        self._active_cancel_event = cancel_event
        self._active_submission_id = turn_context.submission_id
        self._active_progress = progress
        try:
            result = await self._scheduler.run(
                agent=agent,
                turn_context=turn_context,
                cancel_event=cancel_event,
                hooks=self._compose_hooks(self._hooks, progress),
            )
        finally:
            self._active_cancel_event = None
            self._active_submission_id = None
            self._active_progress = None

        await self._publish(
            "loop.turn.completed",
            {
                "submission_id": turn_context.submission_id,
                "session_id": turn_context.session_id,
                "state": result.state.value,
                "stop_reason": result.stop_reason,
                "message": result.message,
                "error": result.error,
                "prepared_context": getattr(agent, "last_prepared_turn_context", None),
                "prepared_context_diagnostics": getattr(agent, "prepared_context_diagnostics", None),
                **progress.snapshot_payload(),
            },
        )

        if result.state == SchedulerState.ERRORED:
            await self._publish(
                "loop.turn.errored",
                {
                    "submission_id": turn_context.submission_id,
                    "error": result.error,
                    "message": result.message,
                },
            )
