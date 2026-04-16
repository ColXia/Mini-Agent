from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any

from mini_agent.commands import CommandExecutionResult
from mini_agent.transport import GatewayTransportError
from mini_agent.tui.session_skill_command_coordinator import TuiSessionSkillCommandCoordinator


def _session() -> Any:
    return SimpleNamespace(
        title="Session 1",
        projection=SimpleNamespace(),
        runtime=SimpleNamespace(agent=None),
    )


def test_tui_skill_command_coordinator_handles_plan_error() -> None:
    session = _session()
    feedback_calls: list[dict[str, Any]] = []
    status_calls: list[str] = []
    render_calls: list[str] = []

    coordinator = TuiSessionSkillCommandCoordinator(
        resolve_skill_command_plan=lambda inv: CommandExecutionResult(
            command="skill frob",
            summary="unknown action",
            details="Unknown skill action: frob.",
            status_text="Unknown skill action.",
            kind="error",
        ),
        runs_via_gateway=lambda _session: False,
        resolve_remote_skill_command_plan=lambda plan: plan,
        run_remote_skill_action=lambda _session, _plan: asyncio.sleep(0, result={}),
        apply_remote_skill_response=lambda _session, _plan, _response: None,
        run_local_skill_command_result=lambda _session, _plan: CommandExecutionResult(
            command="skill list",
            summary="skill catalog shown",
            details="details",
            status_text="Skill catalog shown.",
        ),
        apply_local_skill_command_result=lambda _session, _result: asyncio.sleep(0),
        append_command_feedback=lambda command, **kwargs: feedback_calls.append({"command": command, **kwargs}),
        set_status=lambda text: status_calls.append(text),
        render_all=lambda: render_calls.append("rendered"),
    )

    asyncio.run(coordinator.handle(session, ["frob"]))

    assert feedback_calls == [
        {
            "command": "skill frob",
            "summary": "unknown action",
            "details": "Unknown skill action: frob.",
            "level": "error",
            "metadata": {"threads_visible": False},
        }
    ]
    assert status_calls == ["Unknown skill action."]
    assert render_calls == ["rendered"]


def test_tui_skill_command_coordinator_handles_remote_success() -> None:
    session = _session()
    render_calls: list[str] = []
    remote_runs: list[str] = []
    applied: list[tuple[Any, Any, dict[str, Any]]] = []

    async def _run_remote(_session: Any, remote_plan: Any) -> dict[str, Any]:
        remote_runs.append(remote_plan.action)
        return {"status": "ok", "result": {"summary": "installed repo-helper"}}

    coordinator = TuiSessionSkillCommandCoordinator(
        resolve_skill_command_plan=lambda inv: SimpleNamespace(command="skill install repo-helper", action="install"),
        runs_via_gateway=lambda _session: True,
        resolve_remote_skill_command_plan=lambda plan: SimpleNamespace(
            command=plan.command,
            action=plan.action,
            request_kwargs={"path": "C:/skills/repo-helper"},
        ),
        run_remote_skill_action=_run_remote,
        apply_remote_skill_response=lambda _session, remote_plan, response: applied.append(
            (_session, remote_plan, response)
        ),
        run_local_skill_command_result=lambda _session, _plan: CommandExecutionResult(
            command="skill list",
            summary="skill catalog shown",
            details="details",
            status_text="Skill catalog shown.",
        ),
        apply_local_skill_command_result=lambda _session, _result: asyncio.sleep(0),
        append_command_feedback=lambda command, **kwargs: None,
        set_status=lambda text: None,
        render_all=lambda: render_calls.append("rendered"),
    )

    asyncio.run(coordinator.handle(session, ["install", "repo-helper"]))

    assert remote_runs == ["install"]
    assert len(applied) == 1
    assert applied[0][0] is session
    assert applied[0][1].action == "install"
    assert applied[0][2]["status"] == "ok"
    assert render_calls == ["rendered"]


def test_tui_skill_command_coordinator_handles_remote_error() -> None:
    session = _session()
    feedback_calls: list[dict[str, Any]] = []
    status_calls: list[str] = []
    render_calls: list[str] = []

    async def _run_remote(_session: Any, remote_plan: Any) -> dict[str, Any]:
        _ = remote_plan
        raise GatewayTransportError("Gateway HTTP 503: skill gateway unavailable", status_code=503)

    coordinator = TuiSessionSkillCommandCoordinator(
        resolve_skill_command_plan=lambda inv: SimpleNamespace(command="skill refresh", action="refresh"),
        runs_via_gateway=lambda _session: True,
        resolve_remote_skill_command_plan=lambda plan: SimpleNamespace(
            command=plan.command,
            action=plan.action,
            request_kwargs={},
        ),
        run_remote_skill_action=_run_remote,
        apply_remote_skill_response=lambda _session, _plan, _response: None,
        run_local_skill_command_result=lambda _session, _plan: CommandExecutionResult(
            command="skill list",
            summary="skill catalog shown",
            details="details",
            status_text="Skill catalog shown.",
        ),
        apply_local_skill_command_result=lambda _session, _result: asyncio.sleep(0),
        append_command_feedback=lambda command, **kwargs: feedback_calls.append({"command": command, **kwargs}),
        set_status=lambda text: status_calls.append(text),
        render_all=lambda: render_calls.append("rendered"),
    )

    asyncio.run(coordinator.handle(session, ["refresh"]))

    assert feedback_calls == [
        {
            "command": "skill refresh",
            "summary": "command failed",
            "details": "Remote skill command failed: skill gateway unavailable",
            "level": "error",
            "metadata": {"threads_visible": False},
        }
    ]
    assert status_calls == ["Remote skill command failed."]
    assert render_calls == ["rendered"]


def test_tui_skill_command_coordinator_runs_local_flow() -> None:
    session = _session()
    local_runs: list[tuple[Any, str]] = []
    applied_results: list[CommandExecutionResult] = []
    render_calls: list[str] = []

    def _run_local(target_session: Any, plan: Any) -> CommandExecutionResult:
        local_runs.append((target_session, plan.action))
        return CommandExecutionResult(
            command="skill list",
            summary="skill catalog shown",
            details="repo-helper [workspace] active",
            status_text="Skill catalog shown.",
        )

    async def _apply_local(_session: Any, result: CommandExecutionResult) -> None:
        applied_results.append(result)

    coordinator = TuiSessionSkillCommandCoordinator(
        resolve_skill_command_plan=lambda inv: SimpleNamespace(command="skill list", action="list"),
        runs_via_gateway=lambda _session: False,
        resolve_remote_skill_command_plan=lambda plan: plan,
        run_remote_skill_action=lambda _session, _plan: asyncio.sleep(0, result={}),
        apply_remote_skill_response=lambda _session, _plan, _response: None,
        run_local_skill_command_result=_run_local,
        apply_local_skill_command_result=_apply_local,
        append_command_feedback=lambda command, **kwargs: None,
        set_status=lambda text: None,
        render_all=lambda: render_calls.append("rendered"),
    )

    asyncio.run(coordinator.handle(session, ["list"]))

    assert local_runs == [(session, "list")]
    assert len(applied_results) == 1
    assert applied_results[0].command == "skill list"
    assert render_calls == ["rendered"]
