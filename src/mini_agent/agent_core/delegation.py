"""Sub-agent delegation baseline with depth and concurrency controls."""

from __future__ import annotations

import asyncio
import inspect
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable
from uuid import uuid4


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class DelegationTask:
    """One delegated task request."""

    task_id: str
    prompt: str
    parent_session_id: str | None = None
    provider_override: str | None = None
    tool_allowlist: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DelegationRequest:
    """Normalized request delivered to delegation runner."""

    task_id: str
    prompt: str
    depth: int
    parent_session_id: str | None
    provider_override: str | None
    tool_allowlist: tuple[str, ...]
    metadata: dict[str, Any]


@dataclass(frozen=True)
class DelegationResult:
    """Delegation execution result."""

    task_id: str
    success: bool
    worker_id: str
    child_session_id: str | None = None
    output: str = ""
    error: str | None = None
    started_utc: datetime = field(default_factory=_utc_now)
    finished_utc: datetime = field(default_factory=_utc_now)
    duration_seconds: float = 0.0


@dataclass(frozen=True)
class DelegationBatchSummary:
    """Batch delegation summary."""

    total: int
    succeeded: int
    failed: int
    results: tuple[DelegationResult, ...]


@dataclass(frozen=True)
class DelegationStateSnapshot:
    """Serializable snapshot of manager runtime state."""

    total_started: int
    total_completed: int
    total_failed: int
    active_task_ids: tuple[str, ...]


class InMemoryDelegationProgressBus:
    """Simple progress event channel for delegation workflows."""

    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    async def publish(self, event_type: str, payload: dict[str, Any]) -> None:
        self.events.append({"event_type": event_type, "payload": payload})


DelegationRunner = Callable[[DelegationRequest], Awaitable[DelegationResult | str | dict[str, Any]]]
ProgressCallback = Callable[[str, dict[str, Any]], Awaitable[None] | None]
DelegationHook = Callable[[str, str | None], Awaitable[None] | None]


@dataclass
class _DelegationRuntimeState:
    total_started: int = 0
    total_completed: int = 0
    total_failed: int = 0
    active_task_ids: set[str] = field(default_factory=set)


class DelegationManager:
    """Delegation manager with bounded depth and concurrency."""

    DEFAULT_BLOCKED_TOOLS = {"delegate", "clarify", "memory", "send_message"}

    def __init__(
        self,
        *,
        runner: DelegationRunner,
        max_depth: int = 2,
        max_concurrent: int = 3,
        blocked_tools: set[str] | None = None,
        progress_bus: InMemoryDelegationProgressBus | None = None,
        progress_callback: ProgressCallback | None = None,
        on_delegation: DelegationHook | None = None,
    ) -> None:
        self.runner = runner
        self.max_depth = max(1, int(max_depth))
        self.max_concurrent = max(1, int(max_concurrent))
        blocked = blocked_tools or self.DEFAULT_BLOCKED_TOOLS
        self.blocked_tools = {item.strip().lower() for item in blocked if item and item.strip()}
        self.progress_bus = progress_bus or InMemoryDelegationProgressBus()
        self.progress_callback = progress_callback
        self.on_delegation = on_delegation
        self._state = _DelegationRuntimeState()
        self._state_lock = asyncio.Lock()

    def create_task(
        self,
        *,
        prompt: str,
        parent_session_id: str | None = None,
        provider_override: str | None = None,
        tool_allowlist: tuple[str, ...] = (),
        metadata: dict[str, Any] | None = None,
    ) -> DelegationTask:
        normalized_prompt = prompt.strip()
        if not normalized_prompt:
            raise ValueError("Delegation task prompt must not be empty.")
        return DelegationTask(
            task_id=f"delegate-{uuid4().hex[:10]}",
            prompt=normalized_prompt,
            parent_session_id=parent_session_id,
            provider_override=(provider_override.strip() if provider_override else None),
            tool_allowlist=tuple(item for item in tool_allowlist if item and item.strip()),
            metadata=dict(metadata or {}),
        )

    def _sanitize_allowlist(self, items: tuple[str, ...]) -> tuple[str, ...]:
        normalized: list[str] = []
        seen: set[str] = set()
        for item in items:
            name = item.strip()
            lowered = name.lower()
            if not name or lowered in self.blocked_tools or lowered in seen:
                continue
            seen.add(lowered)
            normalized.append(name)
        return tuple(normalized)

    async def _emit_progress(self, event_type: str, payload: dict[str, Any]) -> None:
        await self.progress_bus.publish(event_type, payload)
        if self.progress_callback is None:
            return
        maybe = self.progress_callback(event_type, payload)
        if inspect.isawaitable(maybe):
            await maybe

    async def _apply_hook(self, task: DelegationTask, result: DelegationResult) -> None:
        if self.on_delegation is None:
            return
        maybe = self.on_delegation(task.prompt, result.output if result.success else result.error)
        if inspect.isawaitable(maybe):
            await maybe

    async def _run_request(self, task: DelegationTask, *, depth: int) -> DelegationResult:
        if depth > self.max_depth:
            return DelegationResult(
                task_id=task.task_id,
                success=False,
                worker_id="delegation-manager",
                output="",
                error=f"Delegation depth limit exceeded: depth={depth}, max_depth={self.max_depth}",
                started_utc=_utc_now(),
                finished_utc=_utc_now(),
                duration_seconds=0.0,
            )

        request = DelegationRequest(
            task_id=task.task_id,
            prompt=task.prompt,
            depth=depth,
            parent_session_id=task.parent_session_id,
            provider_override=task.provider_override,
            tool_allowlist=self._sanitize_allowlist(task.tool_allowlist),
            metadata=dict(task.metadata),
        )

        started = _utc_now()
        async with self._state_lock:
            self._state.total_started += 1
            self._state.active_task_ids.add(task.task_id)
        await self._emit_progress(
            "delegation.task.started",
            {
                "task_id": task.task_id,
                "depth": depth,
                "parent_session_id": task.parent_session_id,
                "provider_override": task.provider_override,
                "tool_allowlist": list(request.tool_allowlist),
            },
        )

        try:
            raw = await self.runner(request)
            finished = _utc_now()
            if isinstance(raw, DelegationResult):
                result = raw
            elif isinstance(raw, str):
                result = DelegationResult(
                    task_id=task.task_id,
                    success=True,
                    worker_id="sub-agent",
                    child_session_id=None,
                    output=raw,
                    error=None,
                    started_utc=started,
                    finished_utc=finished,
                    duration_seconds=(finished - started).total_seconds(),
                )
            elif isinstance(raw, dict):
                result = DelegationResult(
                    task_id=task.task_id,
                    success=bool(raw.get("success", True)),
                    worker_id=str(raw.get("worker_id", "sub-agent")),
                    child_session_id=(
                        str(raw.get("child_session_id")).strip()
                        if raw.get("child_session_id")
                        else None
                    ),
                    output=str(raw.get("output", "")),
                    error=(str(raw.get("error")) if raw.get("error") else None),
                    started_utc=started,
                    finished_utc=finished,
                    duration_seconds=(finished - started).total_seconds(),
                )
            else:
                raise TypeError("Delegation runner must return DelegationResult, str, or dict.")
        except Exception as exc:
            finished = _utc_now()
            result = DelegationResult(
                task_id=task.task_id,
                success=False,
                worker_id="sub-agent",
                child_session_id=None,
                output="",
                error=f"{type(exc).__name__}: {exc}",
                started_utc=started,
                finished_utc=finished,
                duration_seconds=(finished - started).total_seconds(),
            )

        async with self._state_lock:
            self._state.active_task_ids.discard(task.task_id)
            self._state.total_completed += 1
            if not result.success:
                self._state.total_failed += 1

        await self._emit_progress(
            "delegation.task.completed",
            {
                "task_id": task.task_id,
                "depth": depth,
                "success": result.success,
                "error": result.error,
                "duration_seconds": result.duration_seconds,
            },
        )
        await self._apply_hook(task, result)
        return result

    async def delegate(self, task: DelegationTask, *, parent_depth: int = 0) -> DelegationResult:
        depth = max(1, int(parent_depth) + 1)
        return await self._run_request(task, depth=depth)

    async def delegate_batch(
        self,
        tasks: list[DelegationTask],
        *,
        parent_depth: int = 0,
    ) -> DelegationBatchSummary:
        if not tasks:
            return DelegationBatchSummary(total=0, succeeded=0, failed=0, results=())

        depth = max(1, int(parent_depth) + 1)
        semaphore = asyncio.Semaphore(self.max_concurrent)
        results: list[DelegationResult] = []

        async def _bounded(task: DelegationTask) -> None:
            async with semaphore:
                results.append(await self._run_request(task, depth=depth))

        await asyncio.gather(*(_bounded(task) for task in tasks))
        succeeded = len([item for item in results if item.success])
        failed = len(results) - succeeded
        return DelegationBatchSummary(
            total=len(results),
            succeeded=succeeded,
            failed=failed,
            results=tuple(results),
        )

    def snapshot_state(self) -> DelegationStateSnapshot:
        return DelegationStateSnapshot(
            total_started=self._state.total_started,
            total_completed=self._state.total_completed,
            total_failed=self._state.total_failed,
            active_task_ids=tuple(sorted(self._state.active_task_ids)),
        )

    def restore_state(self, snapshot: DelegationStateSnapshot) -> None:
        self._state.total_started = int(snapshot.total_started)
        self._state.total_completed = int(snapshot.total_completed)
        self._state.total_failed = int(snapshot.total_failed)
        self._state.active_task_ids = set(snapshot.active_task_ids)
