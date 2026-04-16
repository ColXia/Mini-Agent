"""Tests for minimal coordinator workflow entry."""

from __future__ import annotations

import pytest

from mini_agent.agent_core.execution import CoordinatorStage
from mini_agent.agent_core.execution.minimal_workflow import (
    format_minimal_workflow_report,
    run_minimal_workflow_with_runner,
)


def _event_count(events: list[dict[str, object]], event_type: str) -> int:
    return len([event for event in events if event.get("event_type") == event_type])


@pytest.mark.asyncio
async def test_minimal_workflow_runs_research_implement_verify_in_order():
    seen: list[tuple[str, str]] = []

    async def stage_runner(stage: CoordinatorStage, prompt: str) -> tuple[bool, str, str | None]:
        seen.append((stage.value, prompt))
        if stage == CoordinatorStage.RESEARCH:
            return True, "research summary", None
        if stage == CoordinatorStage.IMPLEMENTATION:
            assert "research summary" in prompt
            return True, "implementation summary", None
        if stage == CoordinatorStage.VERIFICATION:
            assert "implementation summary" in prompt
            return True, "verification summary", None
        return False, "", "unexpected stage"

    result, bus = await run_minimal_workflow_with_runner(
        objective="Add a lightweight workflow command",
        stage_runner=stage_runner,
    )

    assert result.status == "completed"
    assert [item.stage for item in result.results] == [
        CoordinatorStage.RESEARCH,
        CoordinatorStage.IMPLEMENTATION,
        CoordinatorStage.VERIFICATION,
    ]
    assert _event_count(bus.events, "coordinator.stage.started") == 3
    assert _event_count(bus.events, "coordinator.stage.completed") == 3
    assert _event_count(bus.events, "coordinator.worker.completed") == 3
    assert [item[0] for item in seen] == ["research", "implementation", "verification"]

    report = format_minimal_workflow_report(
        objective="Add a lightweight workflow command",
        result=result,
    )
    assert "Minimal Workflow Report" in report
    assert "verification summary" in report


@pytest.mark.asyncio
async def test_minimal_workflow_stops_on_failure_and_skips_verify():
    async def stage_runner(stage: CoordinatorStage, prompt: str) -> tuple[bool, str, str | None]:
        _ = prompt
        if stage == CoordinatorStage.RESEARCH:
            return True, "research ok", None
        if stage == CoordinatorStage.IMPLEMENTATION:
            return False, "", "implementation failed"
        return True, "verify ok", None

    result, bus = await run_minimal_workflow_with_runner(
        objective="Refactor module X",
        stage_runner=stage_runner,
        stop_on_failure=True,
    )

    assert result.status == "failed"
    assert any(
        summary.stage == CoordinatorStage.VERIFICATION and summary.skipped == 1
        for summary in result.stage_summaries
    )
    assert _event_count(bus.events, "coordinator.stage.skipped") == 1

    report = format_minimal_workflow_report(objective="Refactor module X", result=result)
    assert "Status: failed" in report
    assert "implementation: FAILED" in report
