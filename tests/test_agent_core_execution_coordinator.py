"""Tests for P14 T2.4 coordinator baseline."""

from __future__ import annotations

import asyncio

import pytest

from mini_agent.agent_core.execution.coordinator import (
    CoordinatorStage,
    InMemoryCoordinatorProgressBus,
    MiniCoordinator,
    WorkerResult,
)


def _event_count(bus: InMemoryCoordinatorProgressBus, event_type: str) -> int:
    return len([event for event in bus.events if event["event_type"] == event_type])


@pytest.mark.asyncio
async def test_coordinator_runs_staged_plan_and_emits_progress():
    bus = InMemoryCoordinatorProgressBus()
    seen_stages: list[CoordinatorStage] = []

    async def worker_runner(task):  # noqa: ANN001
        seen_stages.append(task.stage)
        return WorkerResult(
            task_id=task.task_id,
            stage=task.stage,
            worker_id=task.owner or "worker-a",
            success=True,
            summary=f"done-{task.stage.value}",
        )

    coordinator = MiniCoordinator(worker_runner=worker_runner, progress_bus=bus, max_concurrent_workers=2)
    tasks = [
        coordinator.create_task(stage=CoordinatorStage.RESEARCH, prompt="research topic"),
        coordinator.create_task(stage=CoordinatorStage.SYNTHESIS, prompt="synthesize findings"),
        coordinator.create_task(stage=CoordinatorStage.IMPLEMENTATION, prompt="implement patch"),
        coordinator.create_task(stage=CoordinatorStage.VERIFICATION, prompt="verify results"),
    ]

    result = await coordinator.run(tasks)

    assert result.status == "completed"
    assert len(result.results) == 4
    assert seen_stages == [
        CoordinatorStage.RESEARCH,
        CoordinatorStage.SYNTHESIS,
        CoordinatorStage.IMPLEMENTATION,
        CoordinatorStage.VERIFICATION,
    ]
    assert _event_count(bus, "coordinator.stage.started") == 4
    assert _event_count(bus, "coordinator.stage.completed") == 4
    assert _event_count(bus, "coordinator.worker.started") == 4
    assert _event_count(bus, "coordinator.worker.completed") == 4


@pytest.mark.asyncio
async def test_coordinator_stops_next_stages_on_failure():
    bus = InMemoryCoordinatorProgressBus()
    seen_stages: list[CoordinatorStage] = []

    async def worker_runner(task):  # noqa: ANN001
        seen_stages.append(task.stage)
        success = task.stage != CoordinatorStage.RESEARCH
        return WorkerResult(
            task_id=task.task_id,
            stage=task.stage,
            worker_id="worker-x",
            success=success,
            summary="ok" if success else "",
            error=None if success else "research failed",
        )

    coordinator = MiniCoordinator(worker_runner=worker_runner, progress_bus=bus, stop_on_failure=True)
    tasks = [
        coordinator.create_task(stage=CoordinatorStage.RESEARCH, prompt="r1"),
        coordinator.create_task(stage=CoordinatorStage.IMPLEMENTATION, prompt="i1"),
        coordinator.create_task(stage=CoordinatorStage.VERIFICATION, prompt="v1"),
    ]

    result = await coordinator.run(tasks)

    assert result.status == "failed"
    assert seen_stages == [CoordinatorStage.RESEARCH]
    assert any(summary.stage == CoordinatorStage.IMPLEMENTATION and summary.skipped == 1 for summary in result.stage_summaries)
    assert any(summary.stage == CoordinatorStage.VERIFICATION and summary.skipped == 1 for summary in result.stage_summaries)
    assert _event_count(bus, "coordinator.stage.skipped") == 2


@pytest.mark.asyncio
async def test_coordinator_respects_worker_concurrency_limit():
    lock = asyncio.Lock()
    active_workers = 0
    max_active_workers = 0

    async def worker_runner(task):  # noqa: ANN001
        nonlocal active_workers, max_active_workers
        async with lock:
            active_workers += 1
            max_active_workers = max(max_active_workers, active_workers)
        await asyncio.sleep(0.05)
        async with lock:
            active_workers -= 1
        return WorkerResult(
            task_id=task.task_id,
            stage=task.stage,
            worker_id="worker-y",
            success=True,
            summary="ok",
        )

    coordinator = MiniCoordinator(worker_runner=worker_runner, max_concurrent_workers=2)
    tasks = [
        coordinator.create_task(stage=CoordinatorStage.IMPLEMENTATION, prompt=f"impl-{index}")
        for index in range(5)
    ]

    result = await coordinator.run(tasks)

    assert result.status == "completed"
    assert len(result.results) == 5
    assert max_active_workers <= 2
