from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any

from mini_agent.commands import CommandExecutionResult
from mini_agent.tui.session_model_command_coordinator import TuiSessionModelCommandCoordinator


def test_tui_model_command_coordinator_handles_plan_error() -> None:
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
        model_inventory_summary=lambda: (0, 0, "Models:\n  (none)"),
        move_model_cursor=lambda delta: None,
        apply_selected_model=lambda: asyncio.sleep(0),
        discover_for_selected_provider=lambda: asyncio.sleep(0),
        refresh_registry=lambda: None,
        apply_model_use_plan=lambda plan: asyncio.sleep(0),
        model_use_usage_details=lambda: "Usage: /model use <provider_id> <model_id>",
        set_model_filter=lambda value: None,
        model_filter_value=lambda: "",
        execute_model_limit_command_plan=lambda plan: None,
        append_command_feedback=lambda command, **kwargs: feedback_calls.append({"command": command, **kwargs}),
        set_status=lambda text: status_calls.append(text),
        render_all=lambda: render_calls.append("rendered"),
    )

    asyncio.run(coordinator.handle(["use"]))

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
    feedback_calls: list[dict[str, Any]] = []
    status_calls: list[str] = []
    render_calls: list[str] = []

    coordinator = TuiSessionModelCommandCoordinator(
        resolve_model_command_plan=lambda args: SimpleNamespace(command="model list", action="list"),
        model_inventory_summary=lambda: (2, 5, "Models:\nopenai\ngpt-5.4"),
        move_model_cursor=lambda delta: None,
        apply_selected_model=lambda: asyncio.sleep(0),
        discover_for_selected_provider=lambda: asyncio.sleep(0),
        refresh_registry=lambda: None,
        apply_model_use_plan=lambda plan: asyncio.sleep(0),
        model_use_usage_details=lambda: "Usage: /model use <provider_id> <model_id>",
        set_model_filter=lambda value: None,
        model_filter_value=lambda: "",
        execute_model_limit_command_plan=lambda plan: None,
        append_command_feedback=lambda command, **kwargs: feedback_calls.append({"command": command, **kwargs}),
        set_status=lambda text: status_calls.append(text),
        render_all=lambda: render_calls.append("rendered"),
    )

    asyncio.run(coordinator.handle(["list"]))

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
    feedback_calls: list[dict[str, Any]] = []
    status_calls: list[str] = []
    render_calls: list[str] = []

    coordinator = TuiSessionModelCommandCoordinator(
        resolve_model_command_plan=lambda args: SimpleNamespace(command="model use", action="use", request=None),
        model_inventory_summary=lambda: (0, 0, "Models:\n  (none)"),
        move_model_cursor=lambda delta: None,
        apply_selected_model=lambda: asyncio.sleep(0),
        discover_for_selected_provider=lambda: asyncio.sleep(0),
        refresh_registry=lambda: None,
        apply_model_use_plan=lambda plan: asyncio.sleep(0),
        model_use_usage_details=lambda: "Usage: /model use <provider_id> <model_id>",
        set_model_filter=lambda value: None,
        model_filter_value=lambda: "",
        execute_model_limit_command_plan=lambda plan: None,
        append_command_feedback=lambda command, **kwargs: feedback_calls.append({"command": command, **kwargs}),
        set_status=lambda text: status_calls.append(text),
        render_all=lambda: render_calls.append("rendered"),
    )

    asyncio.run(coordinator.handle(["use"]))

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
    feedback_calls: list[dict[str, Any]] = []
    status_calls: list[str] = []
    render_calls: list[str] = []

    async def _apply_use(_plan: Any) -> None:
        raise RuntimeError("provider unavailable")

    coordinator = TuiSessionModelCommandCoordinator(
        resolve_model_command_plan=lambda args: SimpleNamespace(
            command="model use openai gpt-5.3",
            action="use",
            request=SimpleNamespace(identity=("preset", "openai", "gpt-5.3")),
        ),
        model_inventory_summary=lambda: (0, 0, "Models:\n  (none)"),
        move_model_cursor=lambda delta: None,
        apply_selected_model=lambda: asyncio.sleep(0),
        discover_for_selected_provider=lambda: asyncio.sleep(0),
        refresh_registry=lambda: None,
        apply_model_use_plan=_apply_use,
        model_use_usage_details=lambda: "Usage: /model use <provider_id> <model_id>",
        set_model_filter=lambda value: None,
        model_filter_value=lambda: "",
        execute_model_limit_command_plan=lambda plan: None,
        append_command_feedback=lambda command, **kwargs: feedback_calls.append({"command": command, **kwargs}),
        set_status=lambda text: status_calls.append(text),
        render_all=lambda: render_calls.append("rendered"),
    )

    asyncio.run(coordinator.handle(["use", "openai", "gpt-5.3"]))

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
        model_inventory_summary=lambda: (0, 0, "Models:\n  (none)"),
        move_model_cursor=lambda delta: None,
        apply_selected_model=lambda: asyncio.sleep(0),
        discover_for_selected_provider=lambda: asyncio.sleep(0),
        refresh_registry=lambda: None,
        apply_model_use_plan=lambda plan: asyncio.sleep(0),
        model_use_usage_details=lambda: "Usage: /model use <provider_id> <model_id>",
        set_model_filter=_set_filter,
        model_filter_value=lambda: current_filter["value"],
        execute_model_limit_command_plan=lambda plan: None,
        append_command_feedback=lambda command, **kwargs: None,
        set_status=lambda text: status_calls.append(text),
        render_all=lambda: render_calls.append("rendered"),
    )

    asyncio.run(coordinator.handle(["filter", "Sonnet"]))

    assert applied_filters == ["Sonnet"]
    assert status_calls == ["Model filter set to: sonnet"]
    assert render_calls == ["rendered"]


def test_tui_model_command_coordinator_delegates_limit_plan() -> None:
    delegated: list[str] = []
    render_calls: list[str] = []

    coordinator = TuiSessionModelCommandCoordinator(
        resolve_model_command_plan=lambda args: SimpleNamespace(command="model limit show", action="limit_show"),
        model_inventory_summary=lambda: (0, 0, "Models:\n  (none)"),
        move_model_cursor=lambda delta: None,
        apply_selected_model=lambda: asyncio.sleep(0),
        discover_for_selected_provider=lambda: asyncio.sleep(0),
        refresh_registry=lambda: None,
        apply_model_use_plan=lambda plan: asyncio.sleep(0),
        model_use_usage_details=lambda: "Usage: /model use <provider_id> <model_id>",
        set_model_filter=lambda value: None,
        model_filter_value=lambda: "",
        execute_model_limit_command_plan=lambda plan: delegated.append(plan.command),
        append_command_feedback=lambda command, **kwargs: None,
        set_status=lambda text: None,
        render_all=lambda: render_calls.append("rendered"),
    )

    asyncio.run(coordinator.handle(["limit", "show"]))

    assert delegated == ["model limit show"]
    assert render_calls == ["rendered"]
