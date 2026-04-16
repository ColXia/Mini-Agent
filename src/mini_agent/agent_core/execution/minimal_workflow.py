"""Minimal workflow entry built on top of MiniCoordinator.

Pipeline: research -> implement -> verify
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from mini_agent.agent_core.execution.coordinator import (
    CoordinatorRunResult,
    CoordinatorStage,
    InMemoryCoordinatorProgressBus,
    MiniCoordinator,
    WorkerResult,
    WorkerTask,
)

MINIMAL_WORKFLOW_STAGES: tuple[CoordinatorStage, ...] = (
    CoordinatorStage.RESEARCH,
    CoordinatorStage.IMPLEMENTATION,
    CoordinatorStage.VERIFICATION,
)

StageRunner = Callable[[CoordinatorStage, str], Awaitable[tuple[bool, str, str | None]]]


def build_minimal_workflow_tasks(
    *,
    coordinator: MiniCoordinator,
    objective: str,
) -> list[WorkerTask]:
    objective_text = " ".join(str(objective or "").split())
    return [
        coordinator.create_task(
            stage=stage,
            prompt=f"Workflow objective: {objective_text}",
            owner="main-agent",
            metadata={"workflow": "minimal", "objective": objective_text},
        )
        for stage in MINIMAL_WORKFLOW_STAGES
    ]


def compose_stage_prompt(
    *,
    stage: CoordinatorStage,
    objective: str,
    previous_summaries: dict[str, str],
) -> str:
    objective_text = " ".join(str(objective or "").split())
    research_summary = previous_summaries.get(CoordinatorStage.RESEARCH.value, "").strip()
    implementation_summary = previous_summaries.get(CoordinatorStage.IMPLEMENTATION.value, "").strip()

    if stage == CoordinatorStage.RESEARCH:
        return (
            f"Objective: {objective_text}\n\n"
            "Stage: research\n"
            "Please investigate constraints, risks, and concrete implementation directions. "
            "Return a concise actionable research summary."
        )

    if stage == CoordinatorStage.IMPLEMENTATION:
        context = research_summary or "(no research summary available)"
        return (
            f"Objective: {objective_text}\n\n"
            "Stage: implementation\n"
            "Use the research context below to implement the objective with concrete changes.\n\n"
            f"Research context:\n{context}\n\n"
            "Return what was implemented and key decisions."
        )

    if stage == CoordinatorStage.VERIFICATION:
        research_context = research_summary or "(no research summary available)"
        implementation_context = implementation_summary or "(no implementation summary available)"
        return (
            f"Objective: {objective_text}\n\n"
            "Stage: verification\n"
            "Verify the implemented result, mention checks/tests run (or why not), and residual risks.\n\n"
            f"Research context:\n{research_context}\n\n"
            f"Implementation context:\n{implementation_context}"
        )

    return f"Objective: {objective_text}\nStage: {stage.value}\nProceed with this stage."


async def run_minimal_workflow_with_runner(
    *,
    objective: str,
    stage_runner: StageRunner,
    progress_bus: InMemoryCoordinatorProgressBus | None = None,
    stop_on_failure: bool = True,
) -> tuple[CoordinatorRunResult, InMemoryCoordinatorProgressBus]:
    history: dict[str, str] = {}
    workflow_bus = progress_bus or InMemoryCoordinatorProgressBus()

    async def _worker_runner(task: WorkerTask) -> WorkerResult:
        prompt = compose_stage_prompt(
            stage=task.stage,
            objective=objective,
            previous_summaries=history,
        )
        success, summary, error = await stage_runner(task.stage, prompt)
        summary_text = str(summary or "").strip()
        if success and summary_text:
            history[task.stage.value] = summary_text
        return WorkerResult(
            task_id=task.task_id,
            stage=task.stage,
            worker_id=task.owner or "main-agent",
            success=bool(success),
            summary=summary_text,
            error=(str(error).strip() if error else None),
            metadata={
                "workflow": "minimal",
                "objective": " ".join(str(objective or "").split()),
            },
        )

    coordinator = MiniCoordinator(
        worker_runner=_worker_runner,
        progress_bus=workflow_bus,
        max_concurrent_workers=1,
        stop_on_failure=stop_on_failure,
    )
    tasks = build_minimal_workflow_tasks(
        coordinator=coordinator,
        objective=objective,
    )
    result = await coordinator.run(tasks)
    return result, workflow_bus


def format_minimal_workflow_report(*, objective: str, result: CoordinatorRunResult) -> str:
    objective_text = " ".join(str(objective or "").split())
    lines: list[str] = [
        "Minimal Workflow Report",
        f"Objective: {objective_text}",
        f"Run: {result.run_id}",
        f"Status: {result.status}",
    ]

    lines.append("Stage Summary:")
    for summary in result.stage_summaries:
        lines.append(
            "  - "
            f"{summary.stage.value}: total={summary.total}, "
            f"succeeded={summary.succeeded}, failed={summary.failed}, skipped={summary.skipped}"
        )

    lines.append("Stage Outputs:")
    if not result.results:
        lines.append("  - (none)")
    else:
        for item in result.results:
            if item.success:
                snippet = " ".join(str(item.summary or "").split())[:200] or "(empty)"
                lines.append(f"  - {item.stage.value}: {snippet}")
            else:
                error = " ".join(str(item.error or "").split()) or "unknown error"
                lines.append(f"  - {item.stage.value}: FAILED ({error})")

    if result.error:
        lines.append(f"Error: {result.error}")
    return "\n".join(lines)
