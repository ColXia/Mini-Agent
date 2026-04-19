from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any

from mini_agent.commands.execution import CommandExecutionResult, ContextCommandPlan
from mini_agent.tui.session_context_command_coordinator import TuiSessionContextCommandCoordinator


def _session() -> Any:
    return SimpleNamespace(
        projection=SimpleNamespace(
            context_policy={},
        )
    )


def test_tui_context_command_coordinator_handles_non_mutating_show_flow() -> None:
    session = _session()
    refreshed: list[str] = []
    executed_results: list[CommandExecutionResult] = []
    render_calls: list[str] = []
    run_calls: list[tuple[str, tuple[str, ...]]] = []

    async def _refresh(_session: Any) -> None:
        refreshed.append("refreshed")

    async def _run_result(*, session: Any, action: str, args: tuple[str, ...]) -> CommandExecutionResult:
        _ = session
        run_calls.append((action, tuple(args)))
        return CommandExecutionResult(
            command="context show brief",
            summary="policy",
            details="details",
            status_text="Context policy shown.",
        )

    coordinator = TuiSessionContextCommandCoordinator(
        resolve_context_command_plan=lambda args: ContextCommandPlan(
            action="show",
            args=tuple(args),
            refresh_snapshot=True,
            mutate_policy=False,
        ),
        refresh_context_snapshot_if_gateway_bound=_refresh,
        run_context_command_result=_run_result,
        execute_context_result=lambda result: executed_results.append(result),
        runs_via_gateway=lambda _session: True,
        dispatch_remote_context_update=lambda _session, result: asyncio.sleep(0, result=True),
        normalize_context_policy_payload=lambda value: dict(value or {}),
        has_local_runtime_state=lambda _session: False,
        capture_local_runtime_projection=lambda _session: None,
        persist_session_state=lambda: None,
        render_all=lambda: render_calls.append("rendered"),
    )

    asyncio.run(coordinator.handle(session, ["show", "brief"]))

    assert refreshed == ["refreshed"]
    assert run_calls == [("show", ("show", "brief"))]
    assert len(executed_results) == 1
    assert executed_results[0].command == "context show brief"
    assert render_calls == ["rendered"]


def test_tui_context_command_coordinator_handles_local_mutation_flow() -> None:
    session = _session()
    captured_local: list[str] = []
    persisted: list[str] = []
    executed_results: list[CommandExecutionResult] = []
    render_calls: list[str] = []
    run_calls: list[int] = []

    async def _run_result(*, session: Any, action: str, args: tuple[str, ...]) -> CommandExecutionResult:
        _ = (session, action, args)
        run_calls.append(len(run_calls) + 1)
        if len(run_calls) == 1:
            return CommandExecutionResult(
                command="context include",
                summary="updated",
                details="updated",
                status_text="Context updated.",
                payload={
                    "policy": {
                        "include_sources": [" knowledge_base ", "WORKSPACE_MEMORY", "knowledge_base"],
                        "exclude_sources": [" MCP_CATALOG "],
                        "max_items": "6",
                        "max_total_chars": "4200",
                        "max_items_per_source": "2",
                    }
                },
            )
        return CommandExecutionResult(
            command="context include",
            summary="final",
            details="final details",
            status_text="Context policy shown.",
        )

    coordinator = TuiSessionContextCommandCoordinator(
        resolve_context_command_plan=lambda args: ContextCommandPlan(
            action="include",
            args=tuple(args),
            refresh_snapshot=False,
            mutate_policy=True,
        ),
        refresh_context_snapshot_if_gateway_bound=lambda _session: asyncio.sleep(0),
        run_context_command_result=_run_result,
        execute_context_result=lambda result: executed_results.append(result),
        runs_via_gateway=lambda _session: False,
        dispatch_remote_context_update=lambda _session, result: asyncio.sleep(0, result=True),
        normalize_context_policy_payload=lambda _value: {
            "include_sources": ["knowledge_base", "workspace_memory"],
            "exclude_sources": ["mcp_catalog"],
            "max_items": 6,
            "max_total_chars": 4200,
            "max_items_per_source": 2,
            "active": True,
        },
        has_local_runtime_state=lambda _session: True,
        capture_local_runtime_projection=lambda _session: captured_local.append("captured"),
        persist_session_state=lambda: persisted.append("persisted"),
        render_all=lambda: render_calls.append("rendered"),
    )

    asyncio.run(coordinator.handle(session, ["include", "knowledge_base", "workspace_memory"]))

    assert session.projection.context_policy == {
        "include_sources": ["knowledge_base", "workspace_memory"],
        "exclude_sources": ["mcp_catalog"],
        "max_items": 6,
        "max_total_chars": 4200,
        "max_items_per_source": 2,
        "active": True,
    }
    assert captured_local == ["captured"]
    assert persisted == ["persisted"]
    assert run_calls == [1, 2]
    assert len(executed_results) == 1
    assert executed_results[0].summary == "final"
    assert render_calls == ["rendered"]


def test_tui_context_command_coordinator_stops_after_remote_update_failure() -> None:
    session = _session()
    executed_results: list[CommandExecutionResult] = []
    render_calls: list[str] = []
    remote_calls: list[str] = []

    async def _run_result(*, session: Any, action: str, args: tuple[str, ...]) -> CommandExecutionResult:
        _ = (session, action, args)
        return CommandExecutionResult(
            command="context reset",
            summary="updated",
            details="updated",
            status_text="Context updated.",
            payload={"policy": {}, "remote_request": {"action": "reset"}},
        )

    async def _dispatch_remote(_session: Any, result: CommandExecutionResult) -> bool:
        remote_calls.append(result.command)
        return False

    coordinator = TuiSessionContextCommandCoordinator(
        resolve_context_command_plan=lambda args: ContextCommandPlan(
            action="reset",
            args=tuple(args),
            refresh_snapshot=False,
            mutate_policy=True,
        ),
        refresh_context_snapshot_if_gateway_bound=lambda _session: asyncio.sleep(0),
        run_context_command_result=_run_result,
        execute_context_result=lambda result: executed_results.append(result),
        runs_via_gateway=lambda _session: True,
        dispatch_remote_context_update=_dispatch_remote,
        normalize_context_policy_payload=lambda value: dict(value or {}),
        has_local_runtime_state=lambda _session: False,
        capture_local_runtime_projection=lambda _session: None,
        persist_session_state=lambda: None,
        render_all=lambda: render_calls.append("rendered"),
    )

    asyncio.run(coordinator.handle(session, ["reset"]))

    assert remote_calls == ["context reset"]
    assert executed_results == []
    assert render_calls == ["rendered"]
