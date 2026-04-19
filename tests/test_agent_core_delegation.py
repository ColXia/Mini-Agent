"""Tests for P15 T3.4 delegation baseline."""

from __future__ import annotations

import asyncio

import pytest

from mini_agent.agent_core.delegation import (
    DelegationManager,
    DelegationRequest,
    DelegationResult,
    InMemoryDelegationProgressBus,
)


@pytest.mark.asyncio
async def test_delegation_manager_runs_single_task_with_progress_events():
    bus = InMemoryDelegationProgressBus()
    seen_requests: list[DelegationRequest] = []

    async def _runner(request: DelegationRequest):
        seen_requests.append(request)
        return {"success": True, "worker_id": "worker-1", "output": "done"}

    manager = DelegationManager(runner=_runner, progress_bus=bus, max_depth=2, max_concurrent=3)
    task = manager.create_task(
        prompt="Investigate module A",
        parent_session_id="session-1",
        provider_override="provider-x",
        tool_allowlist=("read_file", "delegate", "write_file"),
    )

    result = await manager.delegate(task, parent_depth=0)
    assert result.success is True
    assert result.worker_id == "worker-1"
    assert len(seen_requests) == 1
    assert seen_requests[0].depth == 1
    assert "delegate" not in seen_requests[0].tool_allowlist
    assert "read_file" in seen_requests[0].tool_allowlist

    event_types = [item["event_type"] for item in bus.events]
    assert event_types == ["delegation.task.started", "delegation.task.completed"]


@pytest.mark.asyncio
async def test_delegation_depth_limit_blocks_excessive_nesting():
    async def _runner(_request: DelegationRequest):  # noqa: ARG001
        return {"success": True, "worker_id": "w", "output": "ok"}

    manager = DelegationManager(runner=_runner, max_depth=2, max_concurrent=2)
    task = manager.create_task(prompt="Nested task")
    result = await manager.delegate(task, parent_depth=2)

    assert result.success is False
    assert "depth limit exceeded" in (result.error or "").lower()


@pytest.mark.asyncio
async def test_delegation_batch_respects_concurrency_limit():
    lock = asyncio.Lock()
    active = 0
    max_active = 0

    async def _runner(request: DelegationRequest):
        nonlocal active, max_active
        async with lock:
            active += 1
            max_active = max(max_active, active)
        await asyncio.sleep(0.05)
        async with lock:
            active -= 1
        return {"success": True, "worker_id": f"w-{request.task_id}", "output": "ok"}

    manager = DelegationManager(runner=_runner, max_depth=3, max_concurrent=2)
    tasks = [manager.create_task(prompt=f"Task {index}") for index in range(6)]

    summary = await manager.delegate_batch(tasks, parent_depth=0)
    assert summary.total == 6
    assert summary.succeeded == 6
    assert summary.failed == 0
    assert max_active <= 2


@pytest.mark.asyncio
async def test_delegation_state_snapshot_restore_and_hook():
    hook_calls: list[tuple[str, str | None]] = []

    async def _runner(_request: DelegationRequest):
        return DelegationResult(task_id="manual", success=False, worker_id="w", output="", error="failed")

    async def _hook(task_prompt: str, summary: str | None):
        hook_calls.append((task_prompt, summary))

    manager = DelegationManager(runner=_runner, on_delegation=_hook)
    task = manager.create_task(prompt="Summarize logs")
    result = await manager.delegate(task)
    assert result.success is False

    snapshot = manager.snapshot_state()
    assert snapshot.total_started == 1
    assert snapshot.total_completed == 1
    assert snapshot.total_failed == 1
    assert hook_calls == [("Summarize logs", "failed")]

    manager.restore_state(snapshot)
    restored = manager.snapshot_state()
    assert restored.total_started == 1
    assert restored.total_completed == 1
    assert restored.total_failed == 1
