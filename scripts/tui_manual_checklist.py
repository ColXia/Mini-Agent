"""Scripted TUI manual checklist for terminal real-use validation.

Exercises the core operator paths without requiring a live model key:
- /session
- /model
- /workflow
- /cancel
- /tasks
"""

from __future__ import annotations

import argparse
import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from typing import Any
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from mini_agent.agent import TurnStopReason
from mini_agent.code_agent import InMemoryLoopMessageBus
import mini_agent.tui.app as tui_app_module
from mini_agent.tui.app import MiniAgentTuiApp
from tests.test_tui_app import FakeGatewayClient


@dataclass(frozen=True)
class ChecklistResult:
    name: str
    ok: bool
    note: str
    excerpts: dict[str, str] = field(default_factory=dict)


class _ChecklistRegistry:
    def __init__(self) -> None:
        self.providers: list[dict[str, Any]] = [
            {
                "source": "preset",
                "provider_id": "openai",
                "provider_name": "OpenAI",
                "default_model_id": "gpt-5.4",
                "models": [
                    {"model_id": "gpt-5.4", "display_name": "GPT-5.4", "is_default": True},
                    {"model_id": "gpt-5.3", "display_name": "GPT-5.3", "is_default": False},
                ],
            },
            {
                "source": "preset",
                "provider_id": "anthropic",
                "provider_name": "Anthropic",
                "default_model_id": "claude-3-7-sonnet",
                "models": [
                    {
                        "model_id": "claude-3-7-sonnet",
                        "display_name": "Claude 3.7 Sonnet",
                        "is_default": True,
                    }
                ],
            },
        ]

    def list_registry(self) -> list[dict[str, Any]]:
        import copy

        return copy.deepcopy(self.providers)

    def select_model(self, *, source: str, provider_id: str, model_id: str) -> dict[str, Any]:
        _ = source
        for provider in self.providers:
            if provider.get("provider_id") != provider_id:
                continue
            provider["default_model_id"] = model_id
            reordered: list[dict[str, Any]] = []
            for model in provider.get("models", []):
                if not isinstance(model, dict):
                    continue
                model["is_default"] = model.get("model_id") == model_id
                if model.get("model_id") == model_id:
                    reordered.insert(0, model)
                else:
                    reordered.append(model)
            provider["models"] = reordered
            return provider
        raise ValueError(f"Provider not found: {provider_id}")

    def discover_models(self, *, source: str, provider_id: str) -> dict[str, Any]:
        _ = source
        _ = provider_id
        return {}


class _WorkflowAgent:
    def __init__(self) -> None:
        self.user_messages: list[str] = []
        self.messages = [SimpleNamespace(role="system", content="system")]

    def add_user_message(self, content: str) -> None:
        self.user_messages.append(content)

    async def run_turn(
        self,
        *,
        turn_context: Any = None,
        cancel_event: asyncio.Event | None = None,
        hooks: Any = None,
        start_new_run: bool = True,
    ) -> Any:
        _ = turn_context
        _ = cancel_event
        _ = hooks
        _ = start_new_run
        prompt = self.user_messages[-1] if self.user_messages else ""
        stage_name = "generic"
        for candidate in ("research", "implementation", "verification"):
            if f"Stage: {candidate}" in prompt:
                stage_name = candidate
                break
        return SimpleNamespace(
            stop_reason=TurnStopReason.END_TURN,
            message=f"{stage_name} summary complete",
        )


class _BlockingTurnAgent:
    def __init__(
        self,
        *,
        final_message: str = "ok",
        tool_name: str = "search",
        tool_arguments: dict[str, Any] | None = None,
        tool_result: Any | None = None,
    ) -> None:
        self.final_message = final_message
        self.tool_name = tool_name
        self.tool_arguments = tool_arguments or {}
        self.tool_result = tool_result or SimpleNamespace(success=True)
        self.user_messages: list[str] = []
        self.started = asyncio.Event()
        self.ready_for_cancel = asyncio.Event()
        self.release = asyncio.Event()
        self.cancel_event: asyncio.Event | None = None

    def add_user_message(self, content: str) -> None:
        self.user_messages.append(content)

    async def run_turn(
        self,
        *,
        turn_context: Any = None,
        cancel_event: asyncio.Event | None = None,
        hooks: Any = None,
        start_new_run: bool = True,
    ) -> Any:
        _ = turn_context
        _ = start_new_run
        self.cancel_event = cancel_event
        self.started.set()
        tool_call = SimpleNamespace(
            id=f"call-{self.tool_name}",
            function=SimpleNamespace(name=self.tool_name, arguments=self.tool_arguments),
        )
        if hooks and hooks.on_step_plan:
            await hooks.on_step_plan(SimpleNamespace(step=1, planned_tool_calls=[tool_call]))
        if hooks and hooks.on_tool_call_start:
            await hooks.on_tool_call_start(1, tool_call)
        self.ready_for_cancel.set()
        await self.release.wait()
        if cancel_event is not None and cancel_event.is_set():
            return SimpleNamespace(
                stop_reason=TurnStopReason.CANCELLED,
                message="Task cancelled by user.",
            )
        if hooks and hooks.on_tool_call_result:
            await hooks.on_tool_call_result(1, tool_call, self.tool_result)
        return SimpleNamespace(
            stop_reason=TurnStopReason.END_TURN,
            message=self.final_message,
        )


async def _fake_build_agent_kernel(*, workspace_dir, options):
    _ = workspace_dir
    model_id = options.requested_model or "gpt-test"
    provider_source = options.requested_provider_source or "preset"
    provider_id = options.requested_provider_id or "openai"
    runtime_provider_id = f"preset-{provider_id}" if provider_source == "preset" else provider_id
    return SimpleNamespace(
        llm=SimpleNamespace(model=model_id),
        runtime_route=SimpleNamespace(provider_id=runtime_provider_id, model=model_id),
        messages=[SimpleNamespace(role="system", content="system")],
    )


def _new_app(root: Path) -> MiniAgentTuiApp:
    root.mkdir(parents=True, exist_ok=True)
    tui_app_module.build_agent_kernel = _fake_build_agent_kernel
    app = MiniAgentTuiApp(
        workspace=root,
        registry=_ChecklistRegistry(),
        gateway_client=FakeGatewayClient(profile="local"),
        state_path=root / ".mini-agent" / "tui_sessions.json",
        build_ui=False,
    )
    return _configure_local_session_harness(app)


def _attach_local_runtime_marker(session) -> None:
    if getattr(session, "loop_bus", None) is None:
        session.loop_bus = InMemoryLoopMessageBus()


def _configure_local_session_harness(app: MiniAgentTuiApp) -> MiniAgentTuiApp:
    for session in app.sessions:
        _attach_local_runtime_marker(session)

    original_create_runtime_session = app._create_runtime_session

    async def _create_local_session(*, title: str | None = None, shared: bool = False):
        created = await original_create_runtime_session(title=title, shared=shared)
        if created is not None:
            _attach_local_runtime_marker(created)
        return created

    app._create_runtime_session = _create_local_session  # type: ignore[method-assign]
    app._remote_sync_started = True
    app._ensure_remote_sync_started = lambda: None  # type: ignore[method-assign]
    return app


def _clip(text: str, limit: int = 800) -> str:
    normalized = str(text or "").strip()
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 3] + "..."


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


async def _close_app(app: MiniAgentTuiApp) -> None:
    app._request_exit()
    if app.background_tasks:
        await asyncio.gather(*app.background_tasks, return_exceptions=True)
    await app._shutdown_all_submission_loops()


async def _check_session(root: Path) -> ChecklistResult:
    app = _new_app(root)
    try:
        await app._run_command("session rename Alpha")
        await app._run_command("session new")
        await app._run_command("session rename Beta")
        await app._run_command("session prev")
        _require(app.current_session.title == "Alpha", "session prev did not focus Alpha")
        await app._run_command("session next")
        _require(app.current_session.title == "Beta", "session next did not focus Beta")
        await app._run_command("session list")
        sessions_text = app._render_sessions()
        latest_message = app.current_session.messages[-1].content
        _require("Alpha" in sessions_text and "Beta" in sessions_text, "sessions sidebar missing renamed threads")
        _require("Sessions:" in latest_message, "session list did not emit command summary")
        return ChecklistResult(
            name="session",
            ok=True,
            note="rename/new/prev/next/list behaved as expected",
            excerpts={
                "threads": _clip(sessions_text),
                "command_output": _clip(latest_message),
            },
        )
    finally:
        await _close_app(app)


async def _check_model(root: Path) -> ChecklistResult:
    app = _new_app(root)
    try:
        await app._run_command("model next")
        selected = app._selected_provider_and_model()
        _require(
            selected is not None
            and selected[0].get("provider_id") == "openai"
            and selected[1].get("model_id") == "gpt-5.3",
            "model next did not move cursor",
        )
        await app._run_command("model apply")
        _require(
            "openai/gpt-5.3" in app.status and "warmed agent" in app.status.lower(),
            "model apply did not update status",
        )
        await app._run_command("model filter sonnet")
        selected = app._selected_provider_and_model()
        _require(
            selected is not None
            and selected[0].get("provider_id") == "anthropic"
            and selected[1].get("model_id") == "claude-3-7-sonnet",
            "model filter did not focus sonnet",
        )
        await app._run_command("model filter clear")
        await app._run_command("model use openai gpt-5.4")
        _require(app._current_model_hint() == "openai/gpt-5.4", "model use did not restore OpenAI default")
        return ChecklistResult(
            name="model",
            ok=True,
            note="next/apply/filter/use completed with correct focus and status updates",
            excerpts={
                "models": _clip(app._render_models()),
                "status": _clip(app._render_status_panel()),
            },
        )
    finally:
        await _close_app(app)


async def _check_workflow(root: Path) -> ChecklistResult:
    app = _new_app(root)
    try:
        app.current_session.agent = _WorkflowAgent()
        await app._run_command("workflow run ship p22.5")
        latest = app.current_session.messages[-1]
        _require(latest.role == "assistant", "workflow did not emit assistant report")
        _require("Minimal Workflow Report" in latest.content, "workflow report header missing")
        _require("research" in latest.content, "workflow research stage missing")
        _require("implementation" in latest.content, "workflow implementation stage missing")
        _require("verification" in latest.content, "workflow verification stage missing")
        return ChecklistResult(
            name="workflow",
            ok=True,
            note="workflow run completed and rendered minimal workflow report",
            excerpts={
                "status": _clip(app._render_status_panel()),
                "chat_tail": _clip(app._render_chat()),
            },
        )
    finally:
        await _close_app(app)


async def _check_context(root: Path) -> ChecklistResult:
    app = _new_app(root)
    try:
        app.current_session.last_prepared_context = {
            "item_count": 1,
            "sources": ["knowledge_base"],
            "items": [
                {
                    "source": "knowledge_base",
                    "title": "Relevant knowledge base context",
                    "preview": "Hybrid retrieval combines BM25 and RRF.",
                    "metadata": {
                        "ranking_score": 0.88123,
                        "ranking_basis": "knowledge_base_rrf",
                        "ranking_score_raw": 0.02941,
                    },
                }
            ],
            "provider_statuses": [
                {
                    "provider": "knowledge_base",
                    "status": "used",
                    "item_count": 1,
                    "reason": "store ready",
                },
                {
                    "provider": "mcp_catalog",
                    "status": "filtered",
                    "item_count": 0,
                    "reason": "excluded by prepared-context policy",
                },
            ],
            "provider_failures": [],
        }
        app.current_session.prepared_context_diagnostics = {
            "turn_count": 2,
            "turns_with_context": 1,
            "turns_without_context": 1,
            "total_item_count": 1,
            "curated_turn_count": 1,
            "total_dropped_item_count": 1,
            "source_turn_counts": {"knowledge_base": 1},
            "source_item_counts": {"knowledge_base": 1},
            "provider_status_totals": {"used": 1, "no_match": 1},
            "provider_status_by_provider": {"knowledge_base": {"used": 1, "no_match": 1}},
            "last_sources": ["knowledge_base"],
            "last_item_count": 1,
        }

        await app._run_command("context include knowledge_base")
        await app._run_command("context exclude mcp_catalog")
        await app._run_command("context budget 2 1200 1")
        _require(
            app.current_session.context_policy == {
                "include_sources": ["knowledge_base"],
                "exclude_sources": ["mcp_catalog"],
                "max_items": 2,
                "max_items_per_source": 1,
                "max_total_chars": 1200,
                "active": True,
            },
            "context policy did not persist include/exclude/budget updates",
        )

        await app._run_command("context show brief")
        show_message = app.current_session.messages[-1].content
        _require(
            "Relevant knowledge base context -> Hybrid retrieval combines BM25 and RRF." in show_message,
            "context show brief did not render prepared-context details",
        )
        _require("ranking:" not in show_message, "context show brief should stay compact")

        await app._run_command("context stats")
        stats_message = app.current_session.messages[-1].content
        _require(
            "Context diagnostics: 2 turn(s) | 1 with context | 1 item(s) | curated 1 | dropped 1" in stats_message,
            "context stats did not render diagnostics summary",
        )
        _require("- knowledge_base: 1 turn(s) | 1 item(s)" in stats_message, "context stats source summary missing")
        _require("- knowledge_base: no_match 1, used 1" in stats_message, "context stats provider summary missing")

        await app._run_command("context reset")
        _require(app.current_session.context_policy == {}, "context reset did not clear policy")
        latest_message = app.current_session.messages[-1].content
        _require(
            "Policy: budget=4 item(s)/2400 chars/1 per-source" in latest_message,
            "context reset did not report default budget policy",
        )

        return ChecklistResult(
            name="context",
            ok=True,
            note="context include/exclude/budget/show/stats/reset worked and kept operator visibility intact",
            excerpts={
                "status": _clip(app._render_status_panel()),
                "context_show": _clip(show_message),
                "context_stats": _clip(stats_message),
            },
        )
    finally:
        await _close_app(app)


async def _check_cancel(root: Path) -> ChecklistResult:
    app = _new_app(root)
    try:
        agent = _BlockingTurnAgent(final_message="cancelled-first")
        app.current_session.agent = agent

        first_turn = asyncio.create_task(app._run_chat_turn("cancel this"))
        await agent.started.wait()
        await agent.ready_for_cancel.wait()
        await app._run_command("cancel")
        _require(agent.cancel_event is not None and agent.cancel_event.is_set(), "cancel did not set agent cancel_event")
        agent.release.set()
        await first_turn

        agent.started = asyncio.Event()
        agent.ready_for_cancel = asyncio.Event()
        agent.release = asyncio.Event()
        agent.final_message = "recovered"

        second_turn = asyncio.create_task(app._run_chat_turn("run again"))
        await agent.started.wait()
        await agent.ready_for_cancel.wait()
        agent.release.set()
        await second_turn

        await app._run_command("tasks list")
        tasks_summary = app.current_session.messages[-1].content
        _require(len(app.current_session.tasks) == 2, "expected two tasks after cancel recovery flow")
        _require(app.current_session.tasks[0].status == "cancelled", "first task was not cancelled")
        _require(app.current_session.tasks[1].status == "completed", "second task did not complete")
        _require(app.current_session.messages[-2].content == "recovered", "second turn did not recover")
        _require("status=cancelled" in tasks_summary and "status=completed" in tasks_summary, "tasks list missing final states")
        return ChecklistResult(
            name="cancel-and-tasks",
            ok=True,
            note="cancel interrupted an active turn, tasks reflected the result, and the next turn recovered",
            excerpts={
                "status": _clip(app._render_status_panel()),
                "tasks": _clip(tasks_summary),
                "chat_tail": _clip(app._render_chat()),
            },
        )
    finally:
        await _close_app(app)


def _render_report(*, results: list[ChecklistResult], captured_at: datetime) -> str:
    overall_ok = all(item.ok for item in results)
    lines = [
        f"# TUI Manual Checklist Report - {captured_at.strftime('%Y-%m-%d %H:%M:%S %Z')}",
        "",
        f"- Overall: {'PASS' if overall_ok else 'FAIL'}",
        f"- Captured: {captured_at.isoformat()}",
        f"- Checks: {len(results)}",
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


async def _run_all(root: Path) -> list[ChecklistResult]:
    return [
        await _check_session(root / "session"),
        await _check_model(root / "model"),
        await _check_context(root / "context"),
        await _check_workflow(root / "workflow"),
        await _check_cancel(root / "cancel"),
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description="Run scripted TUI manual checklist.")
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
        else output_dir / f"tui_manual_checklist_{captured_at.strftime('%Y%m%dT%H%M%SZ')}.md"
    )

    try:
        with TemporaryDirectory(prefix="mini-agent-tui-checklist-") as temp_dir:
            results = asyncio.run(_run_all(Path(temp_dir)))
    except Exception as exc:
        results = [
            ChecklistResult(
                name="tui-manual-checklist",
                ok=False,
                note=str(exc),
            )
        ]

    report_path.write_text(
        _render_report(results=results, captured_at=captured_at),
        encoding="utf-8",
    )
    overall_ok = all(item.ok for item in results)
    print(f"[tui-checklist] report={report_path}")
    print(f"[tui-checklist] overall={'PASS' if overall_ok else 'FAIL'}")
    return 0 if overall_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
