"""Prompt-toolkit driven TUI interaction walkthrough.

Runs the real TUI application with pipe input + dummy output and exercises:
- multiline prompt input
- chat history scroll shortcuts
- slash-command driven session/model/workflow/cancel flows
"""

# ruff: noqa: E402

from __future__ import annotations

import argparse
import asyncio
import inspect
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Callable
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from prompt_toolkit.application import create_app_session
from prompt_toolkit.input.defaults import create_pipe_input
from prompt_toolkit.key_binding.key_processor import KeyPress
from prompt_toolkit.keys import Keys
from prompt_toolkit.output import DummyOutput

import mini_agent.tui.app as tui_app_module
from mini_agent.agent_core.context.turn_context import format_prepared_turn_context_details
from mini_agent.tui.app import MiniAgentTuiApp
from scripts.tui_manual_checklist import (
    _BlockingTurnAgent,
    _ChecklistRegistry,
    _WorkflowAgent,
    _configure_local_session_harness,
    _context_runtime_agent,
    _test_config,
    FakeGatewayClient,
)


@dataclass(frozen=True)
class WalkthroughStep:
    name: str
    ok: bool
    note: str
    excerpts: dict[str, str] = field(default_factory=dict)


class _EchoAgent:
    def __init__(self) -> None:
        self.user_messages: list[str] = []
        self.messages = []

    def add_user_message(self, content: str) -> None:
        self.user_messages.append(content)

    async def run_turn(self, **_: object):
        from types import SimpleNamespace

        from mini_agent.agent_core.engine import TurnStopReason

        latest = self.user_messages[-1] if self.user_messages else ""
        return SimpleNamespace(
            stop_reason=TurnStopReason.END_TURN,
            message=f"echo::{latest}",
        )


async def _fake_build_agent_kernel(*, workspace_dir, options):
    _ = workspace_dir
    model_id = options.requested_model or "gpt-test"
    provider_source = options.requested_provider_source or "preset"
    provider_id = options.requested_provider_id or "openai"
    runtime_provider_id = f"preset-{provider_id}" if provider_source == "preset" else provider_id
    from types import SimpleNamespace

    return SimpleNamespace(
        llm=SimpleNamespace(model=model_id),
        runtime_route=SimpleNamespace(provider_id=runtime_provider_id, model=model_id),
        messages=[],
    )


def _clip(text: str, limit: int = 1000) -> str:
    normalized = str(text or "").strip()
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 3] + "..."


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


async def _wait_until(
    predicate: Callable[[], bool],
    *,
    timeout: float = 3.0,
    interval: float = 0.05,
    message: str,
) -> None:
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        if predicate():
            return
        await asyncio.sleep(interval)
    raise AssertionError(message)


async def _close_running_app(app: MiniAgentTuiApp, pipe_input, run_task: asyncio.Task[None]) -> None:
    if not run_task.done():
        pipe_input.send_text("\x11")
        await run_task
    else:
        await run_task
    if app.background_tasks:
        await asyncio.gather(*app.background_tasks, return_exceptions=True)


async def _swap_agent(app: MiniAgentTuiApp, agent: object) -> None:
    await app._shutdown_submission_loop(app.current_session)
    app.current_session.runtime.agent = agent


async def _submit_text(pipe_input, text: str) -> None:
    pipe_input.send_text(text)
    await asyncio.sleep(0.05)
    pipe_input.send_text("\r")


async def _submit_multiline(pipe_input, first: str, second: str) -> None:
    pipe_input.send_text(first)
    await asyncio.sleep(0.05)
    pipe_input.send_text("\x1b\r")
    await asyncio.sleep(0.05)
    pipe_input.send_text(second)
    await asyncio.sleep(0.05)
    pipe_input.send_text("\r")


def _latest_role_entry(app: MiniAgentTuiApp, role: str):
    normalized_role = str(role or "").strip().lower()
    for entry in reversed(app.current_session.view.messages):
        if str(getattr(entry, "role", "") or "").strip().lower() == normalized_role:
            return entry
    return None


async def _run_walkthrough(root: Path) -> list[WalkthroughStep]:
    results: list[WalkthroughStep] = []
    workspace = root / "workspace"
    state_path = workspace / ".mini-agent" / "tui_sessions.json"
    agent_model_binding_path = workspace / ".mini-agent" / "agent_model_binding.json"
    workspace.mkdir(parents=True, exist_ok=True)

    with create_pipe_input() as pipe_input:
        with create_app_session(input=pipe_input, output=DummyOutput()):
            tui_app_module.build_agent_kernel = _fake_build_agent_kernel
            original_application_ctor = tui_app_module.Application
            app: MiniAgentTuiApp | None = None
            run_task: asyncio.Task[None] | None = None

            def _application_factory(*args, **kwargs):
                kwargs.setdefault("output", DummyOutput())
                return original_application_ctor(*args, **kwargs)

            tui_app_module.Application = _application_factory
            try:
                init_kwargs = {
                    "workspace": workspace,
                    "registry": _ChecklistRegistry(),
                    "gateway_client": FakeGatewayClient(profile="local"),
                    "state_path": state_path,
                    "build_ui": True,
                }
                if "config_loader" in inspect.signature(MiniAgentTuiApp.__init__).parameters:
                    init_kwargs["config_loader"] = _test_config
                if "agent_model_binding_path" in inspect.signature(MiniAgentTuiApp.__init__).parameters:
                    init_kwargs["agent_model_binding_path"] = agent_model_binding_path
                app = MiniAgentTuiApp(**init_kwargs)
                _configure_local_session_harness(app)
                run_task = asyncio.create_task(app.run())
                await asyncio.sleep(0.2)
                await _wait_until(
                    lambda: len(list(app.application.layout.find_all_windows())) > 1,
                    timeout=5.0,
                    message="tui layout did not initialize",
                )

                await _swap_agent(app, _EchoAgent())
                baseline_messages = len(app.current_session.view.messages)
                await app._run_chat_turn("alpha line\nbeta line", session=app.current_session)
                recent_messages = app.current_session.view.messages[baseline_messages:]
                user_message = next((entry for entry in recent_messages if entry.role == "user"), None)
                assistant_message = next((entry for entry in reversed(recent_messages) if entry.role == "assistant"), None)
                _require(user_message is not None, "multiline prompt user message missing")
                _require(assistant_message is not None, "multiline prompt assistant message missing")
                _require(user_message.content == "alpha line\nbeta line", "multiline prompt content mismatch")
                _require(assistant_message.content == "echo::alpha line\nbeta line", "assistant echo mismatch")
                results.append(
                    WalkthroughStep(
                        name="multiline-input",
                        ok=True,
                        note="multiline prompt preserved the newline and completed through the local session harness",
                        excerpts={
                            "chat": _clip(app._render_chat()),
                        },
                    )
                )

                for index in range(40):
                    app._append_message("user", f"history line {index}", persist=False)
                app._render_all()
                await asyncio.sleep(0.1)
                app.application.key_processor.feed(KeyPress(Keys.PageUp, ""))
                app.application.key_processor.process_keys()
                await asyncio.sleep(0.1)
                _require("chat     | history" in app._render_status_panel(), "PageUp did not switch to history view")
                app.application.key_processor.feed(KeyPress(Keys.ControlEnd, ""))
                app.application.key_processor.process_keys()
                await asyncio.sleep(0.1)
                _require("chat     | live" in app._render_status_panel(), "Ctrl+End did not return to live view")
                results.append(
                    WalkthroughStep(
                        name="scroll-history",
                        ok=True,
                        note="PageUp moved chat to history mode and Ctrl+End restored live tail",
                        excerpts={
                            "status": _clip(app._render_status_panel()),
                        },
                    )
                )

                await _submit_text(pipe_input, "/session rename Alpha")
                await _wait_until(lambda: app.current_session.title == "Alpha", message="session rename failed")
                await _submit_text(pipe_input, "/session new")
                await _wait_until(lambda: len(app.sessions) == 2, message="session new failed")
                await _submit_text(pipe_input, "/session rename Beta")
                await _wait_until(lambda: app.current_session.title == "Beta", message="second session rename failed")
                await _submit_text(pipe_input, "/session prev")
                await _wait_until(lambda: app.current_session.title == "Alpha", message="session prev failed")
                await _submit_text(pipe_input, "/session next")
                await _wait_until(lambda: app.current_session.title == "Beta", message="session next failed")
                app._append_message("assistant", "beta marker", persist=False)
                app.application.key_processor.feed(KeyPress(Keys.ControlPageUp, ""))
                app.application.key_processor.process_keys()
                await asyncio.sleep(0.1)
                _require(app.current_session.title == "Alpha", "Ctrl+PgUp did not switch session")
                _require("> Alpha [TUI] [live] [focus]" in app._render_sessions(), "threads did not update current session after Ctrl+PgUp")
                _require("beta marker" not in app._render_chat(), "chat did not switch away from Beta after Ctrl+PgUp")
                app.application.key_processor.feed(KeyPress(Keys.ControlPageDown, ""))
                app.application.key_processor.process_keys()
                await asyncio.sleep(0.1)
                _require(app.current_session.title == "Beta", "Ctrl+PgDn did not switch session")
                _require("> Beta [TUI] [live] [focus]" in app._render_sessions(), "threads did not update current session after Ctrl+PgDn")
                _require("beta marker" in app._render_chat(), "chat did not return to Beta after Ctrl+PgDn")
                results.append(
                    WalkthroughStep(
                        name="session-commands",
                        ok=True,
                        note="session rename/new/prev/next worked, and Ctrl+PgUp/PgDn kept threads/chat in sync",
                        excerpts={
                            "threads": _clip(app._render_sessions()),
                        },
                    )
                )

                await _submit_text(pipe_input, "/model next")
                await _wait_until(
                    lambda: (
                        (selected := app._selected_provider_and_model()) is not None
                        and selected[0].get("provider_id") == "openai"
                        and selected[1].get("model_id") == "gpt-5.3"
                    ),
                    message="model next did not advance focus",
                )
                await _submit_text(pipe_input, "/model apply")
                await _wait_until(
                    lambda: "openai/gpt-5.3" in app.status and "warmed agent" in app.status.lower(),
                    message="model apply did not update status for gpt-5.3",
                )
                await _submit_text(pipe_input, "/model filter sonnet")
                await _wait_until(
                    lambda: (
                        (selected := app._selected_provider_and_model()) is not None
                        and selected[0].get("provider_id") == "anthropic"
                        and selected[1].get("model_id") == "claude-3-7-sonnet"
                    ),
                    message="model filter did not focus sonnet",
                )
                await _submit_text(pipe_input, "/model apply")
                await _wait_until(
                    lambda: "anthropic" in app.status.lower()
                    and "claude-3-7-sonnet" in app.status
                    and "warmed agent" in app.status.lower(),
                    message="model apply did not update status",
                )
                await _submit_text(pipe_input, "/model filter clear")
                await _wait_until(lambda: app.model_filter == "", message="model filter clear failed")
                await _submit_text(pipe_input, "/model use openai gpt-5.4")
                await _wait_until(
                    lambda: app._current_model_hint() == "openai/gpt-5.4",
                    message="model use did not restore openai default",
                )
                results.append(
                    WalkthroughStep(
                        name="model-commands",
                        ok=True,
                        note="model next/prev/apply/filter behaved through slash commands",
                        excerpts={
                            "models": _clip(app._render_models()),
                            "status": _clip(app._render_status_panel()),
                        },
                    )
                )

                context_agent = _context_runtime_agent()
                await _swap_agent(app, context_agent)
                app.current_session.projection.last_prepared_context = context_agent.last_prepared_turn_context
                app.current_session.projection.prepared_context_diagnostics = context_agent.prepared_context_diagnostics

                await _submit_text(pipe_input, "/context include knowledge_base")
                await _wait_until(
                    lambda: app.current_session.projection.context_policy.get("include_sources") == ["knowledge_base"],
                    message="context include did not update policy",
                )
                await _submit_text(pipe_input, "/context exclude mcp_catalog")
                await _wait_until(
                    lambda: app.current_session.projection.context_policy.get("exclude_sources") == ["mcp_catalog"],
                    message="context exclude did not update policy",
                )
                await _submit_text(pipe_input, "/context budget 2 1200 1")
                await _wait_until(
                    lambda: app.current_session.projection.context_policy.get("max_items") == 2
                    and app.current_session.projection.context_policy.get("max_total_chars") == 1200
                    and app.current_session.projection.context_policy.get("max_items_per_source") == 1,
                    message="context budget did not update policy",
                )
                await _submit_text(pipe_input, "/context show brief")
                await _wait_until(
                    lambda: app.current_session.projection.last_prepared_context.get("item_count") == 1,
                    message="context show brief did not render prepared-context details",
                )
                context_show = format_prepared_turn_context_details(
                    app.current_session.projection.last_prepared_context,
                    include_header=False,
                    detail_mode="brief",
                )
                _require("ranking:" not in context_show, "context show brief should remain compact")
                await _submit_text(pipe_input, "/context stats")
                await _wait_until(
                    lambda: app.current_session.view.messages[-1].role == "system"
                    and "Context diagnostics:" in app.current_session.view.messages[-1].content,
                    message="context stats did not render diagnostics",
                )
                context_stats = app.current_session.view.messages[-1].content
                _require(
                    "Context diagnostics: 2 turn(s) | 1 with context | 1 item(s) | curated 1 | dropped 1"
                    in context_stats,
                    "context stats summary mismatch",
                )
                _require("- knowledge_base: 1 turn(s) | 1 item(s)" in context_stats, "context stats source summary missing")
                _require("- knowledge_base: no_match 1, used 1" in context_stats, "context stats provider summary missing")
                await _submit_text(pipe_input, "/context reset")
                await _wait_until(
                    lambda: app.current_session.projection.context_policy == {
                        "include_sources": [],
                        "exclude_sources": [],
                        "max_items": 4,
                        "max_items_per_source": 1,
                        "max_total_chars": 2400,
                        "active": False,
                    },
                    message="context reset did not clear policy",
                )
                results.append(
                    WalkthroughStep(
                        name="context-commands",
                        ok=True,
                        note="context include/exclude/budget/show/stats/reset all worked through the live slash-command path",
                        excerpts={
                            "status": _clip(app._render_status_panel()),
                            "context_show": _clip(context_show),
                            "context_stats": _clip(context_stats),
                        },
                    )
                )

                await _swap_agent(app, _WorkflowAgent())
                workflow_baseline = len(app.current_session.view.messages)
                await _submit_text(pipe_input, "/workflow run ship p22.5")
                await _wait_until(
                    lambda: len(app.current_session.view.messages) > workflow_baseline
                    and app.current_session.view.messages[-1].role == "assistant"
                    and "Minimal Workflow Report" in app.current_session.view.messages[-1].content,
                    timeout=5.0,
                    message="workflow run did not produce report",
                )
                results.append(
                    WalkthroughStep(
                        name="workflow-command",
                        ok=True,
                        note="workflow command produced the minimal workflow report from the live input path",
                        excerpts={
                            "chat_tail": _clip(app._render_chat()),
                        },
                    )
                )

                blocking_agent = _BlockingTurnAgent(final_message="should-not-complete")
                await _swap_agent(app, blocking_agent)
                cancel_baseline = len(app.current_session.view.messages)
                first_turn = asyncio.create_task(app._run_chat_turn("cancel through input", session=app.current_session))
                await blocking_agent.started.wait()
                await blocking_agent.ready_for_cancel.wait()
                await app._run_command("cancel")
                await _wait_until(
                    lambda: any(
                        entry.role == "system" and "Cancelling turn for" in entry.content
                        for entry in app.current_session.view.messages[cancel_baseline:]
                    ),
                    timeout=5.0,
                    message="cancel command did not emit cancellation request feedback",
                )
                blocking_agent.release.set()
                await first_turn
                await _wait_until(
                    lambda: any(
                        entry.role == "system" and "Task cancelled by user." in entry.content
                        for entry in app.current_session.view.messages[cancel_baseline:]
                    ),
                    timeout=5.0,
                    message="cancel command did not produce cancellation feedback",
                )
                await _wait_until(lambda: app.current_session.projection.busy is False, message="cancelled turn did not settle")

                blocking_agent.started = asyncio.Event()
                blocking_agent.ready_for_cancel = asyncio.Event()
                blocking_agent.release = asyncio.Event()
                blocking_agent.final_message = "recovered after cancel"
                second_turn = asyncio.create_task(app._run_chat_turn("run after cancel", session=app.current_session))
                await blocking_agent.started.wait()
                await blocking_agent.ready_for_cancel.wait()
                blocking_agent.release.set()
                await second_turn
                _require(
                    app.current_session.view.messages[-1].role == "assistant"
                    and app.current_session.view.messages[-1].content == "recovered after cancel",
                    "post-cancel recovery turn did not complete",
                )
                await app._run_command("tasks list")
                _require(
                    app.current_session.view.messages[-1].role == "system"
                    and "Tasks (" in app.current_session.view.messages[-1].content,
                    "tasks list did not render",
                )
                results.append(
                    WalkthroughStep(
                        name="cancel-and-recover",
                        ok=True,
                        note="cancel interrupted a local harness turn and the next prompt recovered normally",
                        excerpts={
                            "tasks": _clip(app.current_session.view.messages[-1].content),
                            "status": _clip(app._render_status_panel()),
                        },
                    )
                )

            finally:
                tui_app_module.Application = original_application_ctor
                if app is not None and run_task is not None:
                    await _close_running_app(app, pipe_input, run_task)

    return results


def _render_report(*, captured_at: datetime, results: list[WalkthroughStep]) -> str:
    overall_ok = all(item.ok for item in results)
    lines = [
        f"# TUI Interaction Walkthrough - {captured_at.strftime('%Y-%m-%d %H:%M:%S %Z')}",
        "",
        f"- Overall: {'PASS' if overall_ok else 'FAIL'}",
        f"- Captured: {captured_at.isoformat()}",
        f"- Steps: {len(results)}",
        "",
    ]
    for item in results:
        lines.append(f"## {item.name}")
        lines.append("")
        lines.append(f"- Status: {'PASS' if item.ok else 'FAIL'}")
        lines.append(f"- Note: {item.note}")
        lines.append("")
        for title, excerpt in item.excerpts.items():
            lines.append(f"### {title}")
            lines.append("")
            lines.append("```text")
            lines.append(excerpt or "(empty)")
            lines.append("```")
            lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run prompt-toolkit driven TUI interaction walkthrough.")
    parser.add_argument(
        "--output-dir",
        default=str((REPO_ROOT / "workspace" / "readiness").resolve()),
        help="Directory for markdown report output.",
    )
    parser.add_argument(
        "--report-file",
        default=None,
        help="Optional explicit report path.",
    )
    args = parser.parse_args()

    captured_at = datetime.now(timezone.utc)
    output_dir = Path(args.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = (
        Path(args.report_file).expanduser().resolve()
        if args.report_file
        else output_dir / f"tui_interaction_walkthrough_{captured_at.strftime('%Y%m%dT%H%M%SZ')}.md"
    )

    try:
        with TemporaryDirectory(prefix="mini-agent-tui-interaction-") as temp_dir:
            results = asyncio.run(_run_walkthrough(Path(temp_dir)))
    except Exception as exc:
        results = [
            WalkthroughStep(
                name="tui-interaction-walkthrough",
                ok=False,
                note=str(exc),
            )
        ]

    report_path.write_text(
        _render_report(captured_at=captured_at, results=results),
        encoding="utf-8",
    )
    overall_ok = all(item.ok for item in results)
    print(f"[tui-interaction] report={report_path}")
    print(f"[tui-interaction] overall={'PASS' if overall_ok else 'FAIL'}")
    return 0 if overall_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
