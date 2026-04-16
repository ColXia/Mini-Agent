from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any

from mini_agent.commands import CommandExecutionResult, MemoryCommandPlan
from mini_agent.tui.session_memory_command_coordinator import TuiSessionMemoryCommandCoordinator


def _session(*, busy: bool = False) -> Any:
    return SimpleNamespace(
        title="Session 1",
        projection=SimpleNamespace(busy=busy),
    )


def test_tui_memory_command_coordinator_handles_command_result_error() -> None:
    session = _session()
    feedback_calls: list[dict[str, Any]] = []
    status_calls: list[str] = []
    render_calls: list[str] = []

    coordinator = TuiSessionMemoryCommandCoordinator(
        resolve_memory_command_plan=lambda args: CommandExecutionResult(
            command="memory show",
            summary="usage",
            details="usage text",
            status_text="Memory show usage shown.",
            kind="usage",
        ),
        has_local_runtime_state=lambda _session: False,
        execute_memory_command_plan=lambda *args, **kwargs: asyncio.sleep(0, result=True),
        append_command_feedback=lambda command, **kwargs: feedback_calls.append({"command": command, **kwargs}),
        set_status=lambda text: status_calls.append(text),
        render_all=lambda: render_calls.append("rendered"),
    )

    asyncio.run(coordinator.handle(session, ["show", "oops"]))

    assert feedback_calls == [
        {
            "command": "memory show",
            "summary": "usage",
            "details": "usage text",
            "level": "error",
        }
    ]
    assert status_calls == ["Memory show usage shown."]
    assert render_calls == ["rendered"]


def test_tui_memory_command_coordinator_blocks_busy_local_runtime_when_required() -> None:
    session = _session(busy=True)
    feedback_calls: list[dict[str, Any]] = []
    status_calls: list[str] = []
    render_calls: list[str] = []
    executed: list[str] = []

    coordinator = TuiSessionMemoryCommandCoordinator(
        resolve_memory_command_plan=lambda args: MemoryCommandPlan(
            command="memory refresh",
            action="refresh",
            success_status="Memory refreshed.",
            failure_summary="refresh failed",
            failure_detail_prefix="Memory refresh failed: ",
            failure_status="Memory refresh failed.",
            requires_idle_local_runtime=True,
        ),
        has_local_runtime_state=lambda _session: True,
        execute_memory_command_plan=lambda *args, **kwargs: (
            executed.append("executed") or asyncio.sleep(0, result=True)
        ),
        append_command_feedback=lambda command, **kwargs: feedback_calls.append({"command": command, **kwargs}),
        set_status=lambda text: status_calls.append(text),
        render_all=lambda: render_calls.append("rendered"),
    )

    asyncio.run(coordinator.handle(session, ["refresh"]))

    assert executed == []
    assert feedback_calls == [
        {
            "command": "memory refresh",
            "summary": "session busy",
            "details": "Session 1 is busy. Wait for the current turn to finish first.",
            "level": "error",
        }
    ]
    assert status_calls == ["Session 1 is busy."]
    assert render_calls == ["rendered"]


def test_tui_memory_command_coordinator_delegates_successful_plan_execution() -> None:
    session = _session()
    executed: list[dict[str, Any]] = []

    async def _execute_memory_command_plan(target_session: Any, **kwargs: Any) -> bool:
        executed.append({"session": target_session, **kwargs})
        return True

    coordinator = TuiSessionMemoryCommandCoordinator(
        resolve_memory_command_plan=lambda args: MemoryCommandPlan(
            command="memory save note",
            action="save_note",
            success_status="Memory note saved.",
            failure_summary="save failed",
            failure_detail_prefix="Memory save failed: ",
            failure_status="Memory save failed.",
            content="remember routing guardrails",
            metadata_builder=lambda result: {"kind": result.get("kind", "memory")},
        ),
        has_local_runtime_state=lambda _session: True,
        execute_memory_command_plan=_execute_memory_command_plan,
        append_command_feedback=lambda command, **kwargs: None,
        set_status=lambda text: None,
        render_all=lambda: None,
    )

    asyncio.run(coordinator.handle(session, ["save", "note", "remember", "routing", "guardrails"]))

    assert len(executed) == 1
    assert executed[0]["session"] is session
    assert executed[0]["command"] == "memory save note"
    assert executed[0]["action"] == "save_note"
    assert executed[0]["content"] == "remember routing guardrails"
    assert executed[0]["success_status"] == "Memory note saved."
    assert executed[0]["failure_summary"] == "save failed"
    assert callable(executed[0]["metadata_builder"])
