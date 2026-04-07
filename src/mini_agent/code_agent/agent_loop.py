"""Submission-loop baseline for code-agent event processing."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Awaitable, Callable
from uuid import uuid4

from mini_agent.code_agent.context import AgentLoopContext, TurnContext
from mini_agent.code_agent.scheduler import SchedulerResult, SchedulerState, TurnScheduler


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


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
        event = SubmissionEvent(
            event_id=f"evt_{uuid4().hex}",
            event_type=SubmissionEventType.EXEC_APPROVAL,
            payload={"approved": bool(approved), "token": token},
        )
        await self._queue.put(event)
        return event.event_id

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
            self._agent = created
            return self._agent

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
            await self._publish(
                "loop.compact",
                {
                    "event_id": event.event_id,
                    "reason": event.payload.get("reason"),
                },
            )
            return

        if event.event_type == SubmissionEventType.DROP_MEMORIES:
            await self._publish(
                "loop.drop_memories",
                {
                    "event_id": event.event_id,
                    "reason": event.payload.get("reason"),
                },
            )

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
        self._active_cancel_event = cancel_event
        self._active_submission_id = turn_context.submission_id
        try:
            result = await self._scheduler.run(
                agent=agent,
                turn_context=turn_context,
                cancel_event=cancel_event,
                hooks=self._hooks,
            )
        finally:
            self._active_cancel_event = None
            self._active_submission_id = None

        await self._publish(
            "loop.turn.completed",
            {
                "submission_id": turn_context.submission_id,
                "session_id": turn_context.session_id,
                "state": result.state.value,
                "stop_reason": result.stop_reason,
                "message": result.message,
                "error": result.error,
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
