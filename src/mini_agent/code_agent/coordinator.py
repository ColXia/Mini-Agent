"""Minimal multi-agent coordinator baseline for code-agent workflows."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Awaitable, Callable, Iterable
from uuid import uuid4


class CoordinatorStage(str, Enum):
    """Coordinator pipeline stages."""

    RESEARCH = "research"
    SYNTHESIS = "synthesis"
    IMPLEMENTATION = "implementation"
    VERIFICATION = "verification"


STAGE_ORDER: tuple[CoordinatorStage, ...] = (
    CoordinatorStage.RESEARCH,
    CoordinatorStage.SYNTHESIS,
    CoordinatorStage.IMPLEMENTATION,
    CoordinatorStage.VERIFICATION,
)


@dataclass(frozen=True)
class WorkerTask:
    """Single worker task in a coordinator run."""

    task_id: str
    stage: CoordinatorStage
    prompt: str
    owner: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class WorkerResult:
    """Worker execution result."""

    task_id: str
    stage: CoordinatorStage
    worker_id: str
    success: bool
    summary: str = ""
    error: str | None = None
    artifacts: tuple[str, ...] = field(default_factory=tuple)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class StageSummary:
    """Aggregated stage result."""

    stage: CoordinatorStage
    total: int
    succeeded: int
    failed: int
    skipped: int = 0


@dataclass(frozen=True)
class CoordinatorRunResult:
    """Final coordinator run status."""

    run_id: str
    status: str
    results: tuple[WorkerResult, ...]
    stage_summaries: tuple[StageSummary, ...]
    error: str | None = None


class InMemoryCoordinatorProgressBus:
    """Simple progress channel for coordinator events."""

    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    async def publish(self, event_type: str, payload: dict[str, Any]) -> None:
        self.events.append({"event_type": event_type, "payload": payload})


WorkerRunner = Callable[[WorkerTask], Awaitable[WorkerResult]]


class MiniCoordinator:
    """Small coordinator that runs stage-grouped worker tasks."""

    def __init__(
        self,
        *,
        worker_runner: WorkerRunner,
        progress_bus: InMemoryCoordinatorProgressBus | None = None,
        max_concurrent_workers: int = 3,
        stop_on_failure: bool = True,
    ) -> None:
        self.worker_runner = worker_runner
        self.progress_bus = progress_bus or InMemoryCoordinatorProgressBus()
        self.max_concurrent_workers = max(1, int(max_concurrent_workers))
        self.stop_on_failure = bool(stop_on_failure)

    def create_task(
        self,
        *,
        stage: CoordinatorStage,
        prompt: str,
        owner: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> WorkerTask:
        return WorkerTask(
            task_id=f"task-{uuid4().hex[:10]}",
            stage=stage,
            prompt=prompt,
            owner=owner,
            metadata=dict(metadata or {}),
        )

    async def _run_one_task(
        self,
        run_id: str,
        semaphore: asyncio.Semaphore,
        task: WorkerTask,
    ) -> WorkerResult:
        async with semaphore:
            await self.progress_bus.publish(
                "coordinator.worker.started",
                {
                    "run_id": run_id,
                    "task_id": task.task_id,
                    "stage": task.stage.value,
                    "owner": task.owner,
                },
            )
            try:
                result = await self.worker_runner(task)
                if result.task_id != task.task_id:
                    result = WorkerResult(
                        task_id=task.task_id,
                        stage=task.stage,
                        worker_id=result.worker_id,
                        success=result.success,
                        summary=result.summary,
                        error=result.error,
                        artifacts=result.artifacts,
                        metadata=result.metadata,
                    )
            except Exception as exc:
                result = WorkerResult(
                    task_id=task.task_id,
                    stage=task.stage,
                    worker_id=task.owner or "worker",
                    success=False,
                    error=f"{type(exc).__name__}: {exc}",
                )
            await self.progress_bus.publish(
                "coordinator.worker.completed",
                {
                    "run_id": run_id,
                    "task_id": task.task_id,
                    "stage": task.stage.value,
                    "success": result.success,
                    "error": result.error,
                },
            )
            return result

    async def _run_stage(
        self,
        *,
        run_id: str,
        stage: CoordinatorStage,
        tasks: list[WorkerTask],
        semaphore: asyncio.Semaphore,
    ) -> tuple[list[WorkerResult], StageSummary]:
        await self.progress_bus.publish(
            "coordinator.stage.started",
            {
                "run_id": run_id,
                "stage": stage.value,
                "task_count": len(tasks),
            },
        )
        results = await asyncio.gather(
            *(self._run_one_task(run_id, semaphore, task) for task in tasks),
        )
        failed = len([item for item in results if not item.success])
        summary = StageSummary(
            stage=stage,
            total=len(results),
            succeeded=len(results) - failed,
            failed=failed,
            skipped=0,
        )
        await self.progress_bus.publish(
            "coordinator.stage.completed",
            {
                "run_id": run_id,
                "stage": stage.value,
                "task_count": summary.total,
                "succeeded": summary.succeeded,
                "failed": summary.failed,
            },
        )
        return results, summary

    async def run(self, tasks: Iterable[WorkerTask]) -> CoordinatorRunResult:
        run_id = f"coord-{uuid4().hex[:10]}"
        stage_map: dict[CoordinatorStage, list[WorkerTask]] = {stage: [] for stage in STAGE_ORDER}
        for task in tasks:
            stage_map.setdefault(task.stage, []).append(task)

        semaphore = asyncio.Semaphore(self.max_concurrent_workers)
        all_results: list[WorkerResult] = []
        stage_summaries: list[StageSummary] = []

        for stage in STAGE_ORDER:
            stage_tasks = stage_map.get(stage, [])
            if not stage_tasks:
                continue

            stage_results, stage_summary = await self._run_stage(
                run_id=run_id,
                stage=stage,
                tasks=stage_tasks,
                semaphore=semaphore,
            )
            all_results.extend(stage_results)
            stage_summaries.append(stage_summary)

            if self.stop_on_failure and stage_summary.failed > 0:
                current_index = STAGE_ORDER.index(stage)
                for remaining_stage in STAGE_ORDER[current_index + 1 :]:
                    pending = stage_map.get(remaining_stage, [])
                    if not pending:
                        continue
                    skipped_summary = StageSummary(
                        stage=remaining_stage,
                        total=len(pending),
                        succeeded=0,
                        failed=0,
                        skipped=len(pending),
                    )
                    stage_summaries.append(skipped_summary)
                    await self.progress_bus.publish(
                        "coordinator.stage.skipped",
                        {
                            "run_id": run_id,
                            "stage": remaining_stage.value,
                            "task_count": len(pending),
                            "reason": "previous_stage_failed",
                        },
                    )
                return CoordinatorRunResult(
                    run_id=run_id,
                    status="failed",
                    results=tuple(all_results),
                    stage_summaries=tuple(stage_summaries),
                    error=f"Stage '{stage.value}' has failed tasks.",
                )

        return CoordinatorRunResult(
            run_id=run_id,
            status="completed",
            results=tuple(all_results),
            stage_summaries=tuple(stage_summaries),
            error=None,
        )
