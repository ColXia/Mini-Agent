from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any

from mini_agent.commands.execution import CommandExecutionResult
from mini_agent.tui.session_model_command_coordinator import TuiSessionModelCommandCoordinator


def _session() -> Any:
    return SimpleNamespace(title="Session 1")


def test_tui_model_command_coordinator_handles_plan_error() -> None:
    session = _session()
    feedback_calls: list[dict[str, Any]] = []
    status_calls: list[str] = []
    render_calls: list[str] = []

    coordinator = TuiSessionModelCommandCoordinator(
        resolve_model_command_plan=lambda args: CommandExecutionResult(
            command="model use",
            summary="usage",
            details="usage text",
            status_text="Model use usage shown.",
            kind="usage",
        ),
        provider_inventory=lambda: [],
        render_model_summary=lambda: "  (none)",
        move_model_cursor=lambda delta: None,
        apply_selected_model=lambda: asyncio.sleep(0),
        discover_for_selected_provider=lambda: asyncio.sleep(0),
        refresh_registry=lambda: None,
        apply_session_model_selection=lambda _session, identity: asyncio.sleep(0),
        model_use_usage_details=lambda: "Usage: /model use <provider_id> <model_id>",
        set_model_filter=lambda value: None,
        model_filter_value=lambda: "",
        execute_model_limit_command_plan=lambda plan: None,
        append_command_feedback=lambda command, **kwargs: feedback_calls.append({"command": command, **kwargs}),
        set_status=lambda text: status_calls.append(text),
        render_all=lambda: render_calls.append("rendered"),
    )

    asyncio.run(coordinator.handle(session, ["use"]))

    assert feedback_calls == [
        {
            "command": "model use",
            "summary": "usage",
            "details": "usage text",
            "level": "error",
        }
    ]
    assert status_calls == ["Model use usage shown."]
    assert render_calls == ["rendered"]


def test_tui_model_command_coordinator_handles_list_flow() -> None:
    session = _session()
    feedback_calls: list[dict[str, Any]] = []
    status_calls: list[str] = []
    render_calls: list[str] = []

    coordinator = TuiSessionModelCommandCoordinator(
        resolve_model_command_plan=lambda args: SimpleNamespace(command="model list", action="list"),
        provider_inventory=lambda: [
            {"provider_id": "openai", "models": [{"model_id": "gpt-5.4"}, {"model_id": "gpt-5.3"}]},
            {"provider_id": "ollama", "models": [{"model_id": "qwen3"}, {"model_id": "gemma4"}, {"model_id": "glm"}]},
        ],
        render_model_summary=lambda: "openai\ngpt-5.4",
        move_model_cursor=lambda delta: None,
        apply_selected_model=lambda: asyncio.sleep(0),
        discover_for_selected_provider=lambda: asyncio.sleep(0),
        refresh_registry=lambda: None,
        apply_session_model_selection=lambda _session, identity: asyncio.sleep(0),
        model_use_usage_details=lambda: "Usage: /model use <provider_id> <model_id>",
        set_model_filter=lambda value: None,
        model_filter_value=lambda: "",
        execute_model_limit_command_plan=lambda plan: None,
        append_command_feedback=lambda command, **kwargs: feedback_calls.append({"command": command, **kwargs}),
        set_status=lambda text: status_calls.append(text),
        render_all=lambda: render_calls.append("rendered"),
    )

    asyncio.run(coordinator.handle(session, ["list"]))

    assert feedback_calls == [
        {
            "command": "model list",
            "summary": "2 provider(s), 5 model(s)",
            "details": "Models:\nopenai\ngpt-5.4",
        }
    ]
    assert status_calls == ["Listed providers/models."]
    assert render_calls == ["rendered"]


def test_tui_model_command_coordinator_handles_use_usage_without_request() -> None:
    session = _session()
    feedback_calls: list[dict[str, Any]] = []
    status_calls: list[str] = []
    render_calls: list[str] = []

    coordinator = TuiSessionModelCommandCoordinator(
        resolve_model_command_plan=lambda args: SimpleNamespace(command="model use", action="use", request=None),
        provider_inventory=lambda: [],
        render_model_summary=lambda: "  (none)",
        move_model_cursor=lambda delta: None,
        apply_selected_model=lambda: asyncio.sleep(0),
        discover_for_selected_provider=lambda: asyncio.sleep(0),
        refresh_registry=lambda: None,
        apply_session_model_selection=lambda _session, identity: asyncio.sleep(0),
        model_use_usage_details=lambda: "Usage: /model use <provider_id> <model_id>",
        set_model_filter=lambda value: None,
        model_filter_value=lambda: "",
        execute_model_limit_command_plan=lambda plan: None,
        append_command_feedback=lambda command, **kwargs: feedback_calls.append({"command": command, **kwargs}),
        set_status=lambda text: status_calls.append(text),
        render_all=lambda: render_calls.append("rendered"),
    )

    asyncio.run(coordinator.handle(session, ["use"]))

    assert feedback_calls == [
        {
            "command": "model use",
            "summary": "usage",
            "details": "Usage: /model use <provider_id> <model_id>",
            "level": "error",
        }
    ]
    assert status_calls == ["Model use requires provider_id and model_id."]
    assert render_calls == ["rendered"]


def test_tui_model_command_coordinator_handles_use_failure() -> None:
    session = _session()
    feedback_calls: list[dict[str, Any]] = []
    status_calls: list[str] = []
    render_calls: list[str] = []

    async def _apply_use(_session: Any, identity: tuple[str, str, str]) -> None:
        _ = identity
        raise RuntimeError("provider unavailable")

    coordinator = TuiSessionModelCommandCoordinator(
        resolve_model_command_plan=lambda args: SimpleNamespace(
            command="model use openai gpt-5.3",
            action="use",
            request=SimpleNamespace(identity=("preset", "openai", "gpt-5.3")),
        ),
        provider_inventory=lambda: [],
        render_model_summary=lambda: "  (none)",
        move_model_cursor=lambda delta: None,
        apply_selected_model=lambda: asyncio.sleep(0),
        discover_for_selected_provider=lambda: asyncio.sleep(0),
        refresh_registry=lambda: None,
        apply_session_model_selection=_apply_use,
        model_use_usage_details=lambda: "Usage: /model use <provider_id> <model_id>",
        set_model_filter=lambda value: None,
        model_filter_value=lambda: "",
        execute_model_limit_command_plan=lambda plan: None,
        append_command_feedback=lambda command, **kwargs: feedback_calls.append({"command": command, **kwargs}),
        set_status=lambda text: status_calls.append(text),
        render_all=lambda: render_calls.append("rendered"),
    )

    asyncio.run(coordinator.handle(session, ["use", "openai", "gpt-5.3"]))

    assert feedback_calls == [
        {
            "command": "model use openai gpt-5.3",
            "summary": "model switch failed",
            "details": "Model switch failed: provider unavailable",
            "level": "error",
        }
    ]
    assert status_calls == ["Model switch failed: provider unavailable"]
    assert render_calls == ["rendered"]


def test_tui_model_command_coordinator_handles_filter_set() -> None:
    session = _session()
    status_calls: list[str] = []
    render_calls: list[str] = []
    applied_filters: list[str] = []
    current_filter = {"value": ""}

    def _set_filter(value: str) -> None:
        applied_filters.append(value)
        current_filter["value"] = value.strip().lower()

    coordinator = TuiSessionModelCommandCoordinator(
        resolve_model_command_plan=lambda args: SimpleNamespace(
            command="model filter Sonnet",
            action="filter_set",
            filter_value="Sonnet",
        ),
        provider_inventory=lambda: [],
        render_model_summary=lambda: "  (none)",
        move_model_cursor=lambda delta: None,
        apply_selected_model=lambda: asyncio.sleep(0),
        discover_for_selected_provider=lambda: asyncio.sleep(0),
        refresh_registry=lambda: None,
        apply_session_model_selection=lambda _session, identity: asyncio.sleep(0),
        model_use_usage_details=lambda: "Usage: /model use <provider_id> <model_id>",
        set_model_filter=_set_filter,
        model_filter_value=lambda: current_filter["value"],
        execute_model_limit_command_plan=lambda plan: None,
        append_command_feedback=lambda command, **kwargs: None,
        set_status=lambda text: status_calls.append(text),
        render_all=lambda: render_calls.append("rendered"),
    )

    asyncio.run(coordinator.handle(session, ["filter", "Sonnet"]))

    assert applied_filters == ["Sonnet"]
    assert status_calls == ["Model filter set to: sonnet"]
    assert render_calls == ["rendered"]


def test_tui_model_command_coordinator_delegates_limit_plan() -> None:
    session = _session()
    delegated: list[str] = []
    render_calls: list[str] = []

    coordinator = TuiSessionModelCommandCoordinator(
        resolve_model_command_plan=lambda args: SimpleNamespace(command="model limit show", action="limit_show"),
        provider_inventory=lambda: [],
        render_model_summary=lambda: "  (none)",
        move_model_cursor=lambda delta: None,
        apply_selected_model=lambda: asyncio.sleep(0),
        discover_for_selected_provider=lambda: asyncio.sleep(0),
        refresh_registry=lambda: None,
        apply_session_model_selection=lambda _session, identity: asyncio.sleep(0),
        model_use_usage_details=lambda: "Usage: /model use <provider_id> <model_id>",
        set_model_filter=lambda value: None,
        model_filter_value=lambda: "",
        execute_model_limit_command_plan=lambda plan: delegated.append(plan.command),
        append_command_feedback=lambda command, **kwargs: None,
        set_status=lambda text: None,
        render_all=lambda: render_calls.append("rendered"),
    )

    asyncio.run(coordinator.handle(session, ["limit", "show"]))

    assert delegated == ["model limit show"]
    assert render_calls == ["rendered"]
