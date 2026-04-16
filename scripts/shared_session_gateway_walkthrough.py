"""Scripted shared-session gateway walkthrough for readiness validation.

Exercises the gateway/runtime shared-session mainline without requiring
real QQ credentials:
- QQ-origin session creation and metadata
- remote activity transcript surfacing
- TUI takeover and continued work on the same session
- shared-session context controls and remote cancel
- TUI local-share import/export roundtrip
- gateway persistence across runtime restart
"""

from __future__ import annotations

import argparse
import asyncio
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from mini_agent.agent_core.engine import TurnExecutionResult, TurnStopReason  # noqa: E402
from mini_agent.application import MainAgentSurfaceService, SessionApplicationService  # noqa: E402
from mini_agent.config import AgentConfig, Config, LLMConfig, ToolsConfig  # noqa: E402
from mini_agent.interfaces import (  # noqa: E402
    MainAgentChatRequest,
    MainAgentSessionCancelRequest,
    MainAgentSessionControlRequest,
    MainAgentSessionModelSelectionRequest,
)
from mini_agent.runtime.main_agent_runtime_manager import MainAgentRuntimeManager  # noqa: E402
from mini_agent.runtime.session_snapshot_handler import RuntimeSessionSnapshotImportCommand  # noqa: E402


@dataclass(frozen=True)
class WalkthroughResult:
    name: str
    ok: bool
    note: str
    excerpts: dict[str, str] = field(default_factory=dict)


class _DummyAgent:
    def __init__(self, *, prefix: str = "mock") -> None:
        self._prefix = prefix
        self.messages = [SimpleNamespace(role="system", content="system")]
        self.api_total_tokens = 0

    def add_user_message(self, content: str) -> None:
        self.messages.append(SimpleNamespace(role="user", content=content))

    async def run(self) -> str:
        text = f"{self._prefix}:{self.messages[-1].content}"
        self.messages.append(SimpleNamespace(role="assistant", content=text))
        self.api_total_tokens += 7
        return text

    async def run_turn(
        self,
        *,
        cancel_event: asyncio.Event | None = None,
        hooks: Any = None,
        turn_context: Any = None,
        start_new_run: bool = True,
    ) -> TurnExecutionResult:
        _ = cancel_event
        _ = hooks
        _ = turn_context
        _ = start_new_run
        text = await self.run()
        return TurnExecutionResult(stop_reason=TurnStopReason.END_TURN, message=text)


class _HookedAgent(_DummyAgent):
    def __init__(self, *, prefix: str = "mock") -> None:
        super().__init__(prefix=prefix)
        self.captured_turn_contexts: list[dict[str, Any] | None] = []

    async def run_turn(
        self,
        *,
        cancel_event: asyncio.Event | None = None,
        hooks: Any = None,
        turn_context: Any = None,
        start_new_run: bool = True,
    ) -> TurnExecutionResult:
        _ = cancel_event
        _ = start_new_run
        self.captured_turn_contexts.append(turn_context if isinstance(turn_context, dict) else None)
        tool_call = SimpleNamespace(
            id="call-shell",
            function=SimpleNamespace(name="bash", arguments={"command": "pytest -q"}),
        )
        if hooks and hooks.on_step_plan:
            await hooks.on_step_plan(SimpleNamespace(step=1, planned_tool_calls=[tool_call]))
        if hooks and hooks.on_tool_call_start:
            await hooks.on_tool_call_start(1, tool_call)
        if hooks and hooks.on_tool_call_result:
            await hooks.on_tool_call_result(
                1,
                tool_call,
                SimpleNamespace(
                    success=True,
                    stdout="32 passed",
                    stderr="",
                    content="32 passed",
                    exit_code=0,
                ),
            )
        text = await self.run()
        return TurnExecutionResult(stop_reason=TurnStopReason.END_TURN, message=text)


class _ControllableAgent(_DummyAgent):
    def __init__(self) -> None:
        super().__init__(prefix="mock")
        self.control_calls: list[tuple[str, str | None]] = []

    def compact_context(self, *, reason: str | None = None) -> dict[str, object]:
        self.control_calls.append(("compact", reason))
        return {
            "applied": True,
            "message_count_before": 5,
            "message_count_after": 3,
            "token_count_before": 220,
            "token_count_after": 120,
            "stats": {"masked_messages": 1, "snipped_messages": 1, "merged_messages": 0},
        }

    def drop_memories(self, *, reason: str | None = None) -> dict[str, object]:
        self.control_calls.append(("drop_memories", reason))
        return {
            "applied": True,
            "message_count_before": 8,
            "message_count_after": 4,
            "token_count_before": 360,
            "token_count_after": 140,
            "stats": {"masked_messages": 0, "snipped_messages": 2, "merged_messages": 1},
        }


class _SelectableAgent(_DummyAgent):
    def __init__(self, *, provider_source: str, provider_id: str, model_id: str) -> None:
        super().__init__(prefix=model_id)
        runtime_provider_id = f"preset-{provider_id}" if provider_source == "preset" else provider_id
        self.runtime_route = SimpleNamespace(provider_id=runtime_provider_id, model=model_id)
        self.llm = SimpleNamespace(model=model_id)


class _BlockingCancelableAgent(_DummyAgent):
    def __init__(self) -> None:
        super().__init__(prefix="mock")
        self.started = asyncio.Event()
        self.received_cancel_event: asyncio.Event | None = None

    async def run_turn(
        self,
        *,
        cancel_event: asyncio.Event | None = None,
        hooks: Any = None,
        turn_context: Any = None,
        start_new_run: bool = True,
    ) -> TurnExecutionResult:
        _ = hooks
        _ = turn_context
        _ = start_new_run
        self.received_cancel_event = cancel_event
        self.started.set()
        if cancel_event is None:
            raise AssertionError("cancel_event should be supplied for shared-session cancel support")
        await cancel_event.wait()
        text = "Task cancelled by user."
        self.messages.append(SimpleNamespace(role="assistant", content=text))
        return TurnExecutionResult(stop_reason=TurnStopReason.CANCELLED, message=text)


def _resolve_workspace_dir(workspace_dir: str | None) -> Path:
    return Path(workspace_dir or ".").resolve()


def _to_utc_iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _sse_event(event: str, data: dict[str, object]) -> str:
    return f"{event}:{data}"


def _format_bootstrap_error(exc: Exception) -> Exception:
    raise RuntimeError(str(exc))


def _test_runtime_config() -> Config:
    return Config(
        llm=LLMConfig(
            api_key="sk-test",
            api_base="https://api.example.com/v1",
            model="gpt-5.4",
            provider="openai",
        ),
        agent=AgentConfig(
            max_steps=8,
            max_tool_calls_per_step=2,
            system_prompt_path="system_prompt.md",
        ),
        tools=ToolsConfig(
            enable_file_tools=False,
            enable_bash=False,
            enable_note=False,
            enable_skills=False,
            enable_mcp=False,
        ),
    )


async def _import_runtime_session(
    use_cases: MainAgentSurfaceService,
    *,
    workspace_dir: str | None,
    session_id: str | None = None,
    **kwargs: object,
):
    resolved_workspace = use_cases._resolve_workspace_dir(workspace_dir)
    runtime_manager = use_cases._session_service._runtime_manager
    runtime_manager.validate_workspace(resolved_workspace)
    session = await runtime_manager.import_session_snapshot(
        RuntimeSessionSnapshotImportCommand(
            session_id=session_id,
            workspace_dir=resolved_workspace,
            **kwargs,
        )
    )
    transcript = kwargs.get("transcript")
    recent_limit = max(50, len(transcript) if isinstance(transcript, list) else 0)
    return await runtime_manager.get_session_detail(session.session_id, recent_limit=recent_limit)


async def _export_runtime_session(use_cases: MainAgentSurfaceService, session_id: str):
    return await use_cases._session_service._runtime_manager.export_session_snapshot(session_id)


async def _activate_runtime_surface(
    use_cases: MainAgentSurfaceService,
    session_id: str,
    *,
    surface: str,
):
    return await use_cases._session_service._runtime_manager.set_active_surface(session_id, surface=surface)


def _clip(text: str, limit: int = 1000) -> str:
    normalized = str(text or "").strip()
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 3] + "..."


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _format_detail(detail: Any) -> str:
    selected_source = str(getattr(detail, "selected_model_source", "") or "").strip()
    selected_provider = str(getattr(detail, "selected_provider_id", "") or "").strip()
    selected_model = str(getattr(detail, "selected_model_id", "") or "").strip()
    pending_source = str(getattr(detail, "pending_model_source", "") or "").strip()
    pending_provider = str(getattr(detail, "pending_provider_id", "") or "").strip()
    pending_model = str(getattr(detail, "pending_model_id", "") or "").strip()
    summary_lines = [
        f"session={getattr(detail, 'session_id', '')}",
        f"origin={getattr(detail, 'origin_surface', '')} active={getattr(detail, 'active_surface', '')}",
        f"reply_enabled={getattr(detail, 'reply_enabled', False)} messages={getattr(detail, 'message_count', 0)}",
    ]
    if selected_source and selected_provider and selected_model:
        summary_lines.append(f"selected_model={selected_source}:{selected_provider}/{selected_model}")
    if pending_source and pending_provider and pending_model:
        summary_lines.append(f"pending_model={pending_source}:{pending_provider}/{pending_model}")
    recovery = getattr(detail, "recovery", None)
    if recovery is not None:
        recovery_state = str(getattr(recovery, "state", "") or "").strip()
        recovery_summary = str(getattr(recovery, "summary", "") or "").strip()
        last_activity = str(getattr(recovery, "last_activity", "") or "").strip()
        if recovery_state or recovery_summary:
            summary_lines.append(f"recovery={recovery_state}: {recovery_summary}".rstrip(": "))
        if last_activity:
            summary_lines.append(f"last_activity={last_activity}")
    recent_messages = list(getattr(detail, "recent_messages", []) or [])
    if recent_messages:
        summary_lines.append("recent:")
        for item in recent_messages[-6:]:
            role = str(getattr(item, "role", "") or "")
            surface = str(getattr(item, "surface", "") or "")
            content = str(getattr(item, "content", "") or "").strip()
            summary_lines.append(f"- {role}@{surface}: {content}")
    return "\n".join(summary_lines)


def _format_snapshot(snapshot: Any) -> str:
    lines = [
        f"session={getattr(snapshot, 'session_id', '')}",
        f"title={getattr(snapshot, 'title', '')}",
        f"origin={getattr(snapshot, 'origin_surface', '')} active={getattr(snapshot, 'active_surface', '')}",
    ]
    transcript = list(getattr(snapshot, "transcript", []) or [])
    if transcript:
        lines.append("transcript:")
        for item in transcript[-6:]:
            role = str(getattr(item, "role", "") or "")
            surface = str(getattr(item, "surface", "") or "")
            content = str(getattr(item, "content", "") or "").strip()
            lines.append(f"- {role}@{surface}: {content}")
    return "\n".join(lines)


def _new_use_cases(
    *,
    storage_dir: Path,
    build_agent,
    build_agent_with_selection=None,
) -> MainAgentSurfaceService:
    runtime = MainAgentRuntimeManager(
        ttl_seconds=3600,
        build_agent=build_agent,
        build_agent_with_selection=build_agent_with_selection,
        storage_dir=storage_dir,
        load_runtime_config=_test_runtime_config,
    )
    return MainAgentSurfaceService(
        session_service=SessionApplicationService(runtime_manager=runtime),
        resolve_workspace_dir=_resolve_workspace_dir,
        to_utc_iso=_to_utc_iso,
        sse_event=_sse_event,
        format_bootstrap_error=_format_bootstrap_error,
        stream_chunk_size=64,
    )


async def _check_shared_activity_and_takeover(root: Path) -> WalkthroughResult:
    workspace = root / "workspace"
    storage_dir = root / "runtime-store"

    async def _build_agent(_workspace: Path):
        return _HookedAgent(prefix="hooked")

    use_cases = _new_use_cases(storage_dir=storage_dir, build_agent=_build_agent)

    first = await use_cases.run_chat(
        MainAgentChatRequest(
            message="hello from qq",
            workspace_dir=str(workspace),
            session_id="sess-shared",
            surface="qq",
            channel_type="qq",
            conversation_id="group:demo",
            sender_id="user-1",
        )
    )
    _require(first.reply == "hooked:hello from qq", "qq-origin shared session reply mismatch")

    detail = await use_cases.get_session_detail("sess-shared", recent_limit=10)
    _require(detail.origin_surface == "qq", "origin surface should remain qq")
    _require(detail.active_surface == "qq", "active surface should start as qq")
    _require(detail.reply_enabled is True, "qq-origin session should reply back to qq")
    _require([item.role for item in detail.recent_messages] == ["user", "tool", "assistant"], "shared activity transcript mismatch")
    activity_entry = detail.recent_messages[1]
    metadata = activity_entry.metadata or {}
    _require(metadata.get("kind") == "activity", "shared activity entry missing activity metadata")
    labels = [item.get("label") for item in metadata.get("activity_items", [])]
    _require(labels == ["thinking", "shell"], "shared activity labels mismatch")

    latest = await use_cases.get_session_messages("sess-shared", limit=3)
    _require([item.role for item in latest] == ["user", "tool", "assistant"], "latest shared messages mismatch")

    activated = await _activate_runtime_surface(use_cases, "sess-shared", surface="tui")
    _require(activated.active_surface == "tui", "surface activation should switch active surface to tui")

    second = await use_cases.run_chat(
        MainAgentChatRequest(
            message="continue in tui",
            workspace_dir=str(workspace),
            session_id="sess-shared",
            surface="tui",
        )
    )
    _require(second.reply == "hooked:continue in tui", "tui follow-up reply mismatch")

    detail_after = await use_cases.get_session_detail("sess-shared", recent_limit=10)
    _require(detail_after.origin_surface == "qq", "origin surface should stay qq after takeover")
    _require(detail_after.active_surface == "tui", "active surface should become tui after takeover")
    _require(detail_after.reply_enabled is False, "tui-owned continuation should not auto-reply to qq")
    tail_roles = [item.role for item in detail_after.recent_messages[-3:]]
    tail_surfaces = [item.surface for item in detail_after.recent_messages[-3:]]
    _require(tail_roles == ["user", "tool", "assistant"], "tui continuation transcript mismatch")
    _require(tail_surfaces == ["tui", "tui", "tui"], "tui continuation surfaces mismatch")
    _require(detail_after.recent_messages[-3].content == "continue in tui", "tui continuation user message missing")
    _require(detail_after.recent_messages[-1].content == "hooked:continue in tui", "tui continuation assistant reply missing")

    return WalkthroughResult(
        name="shared-activity-and-takeover",
        ok=True,
        note="qq-origin session exposed activity transcript, then TUI took over the same session and continued on the shared transcript",
        excerpts={
            "detail_before_takeover": _clip(_format_detail(detail)),
            "detail_after_takeover": _clip(_format_detail(detail_after)),
        },
    )


async def _check_shared_control_and_cancel(root: Path) -> WalkthroughResult:
    workspace = root / "workspace"
    control_agent = _ControllableAgent()
    cancel_agent = _BlockingCancelableAgent()

    async def _build_control_agent(_workspace: Path):
        return control_agent

    control_use_cases = _new_use_cases(
        storage_dir=root / "control-runtime-store",
        build_agent=_build_control_agent,
    )

    response = await control_use_cases.run_chat(
        MainAgentChatRequest(
            message="hello from qq",
            workspace_dir=str(workspace),
            session_id="sess-control",
            surface="qq",
            channel_type="qq",
            conversation_id="group:control",
            sender_id="user-2",
        )
    )
    _require(response.reply == "mock:hello from qq", "control seed reply mismatch")

    compact = await control_use_cases.control_session(
        "sess-control",
        MainAgentSessionControlRequest(
            action="compact",
            reason="keep freshest context",
            surface="tui",
        ),
    )
    _require(compact.action == "compact" and compact.applied is True, "compact control failed")

    drop = await control_use_cases.control_session(
        "sess-control",
        MainAgentSessionControlRequest(
            action="drop_memories",
            reason="clear older context",
            surface="qq",
            channel_type="qq",
            conversation_id="group:control",
            sender_id="user-2",
        ),
    )
    _require(drop.action == "drop_memories" and drop.applied is True, "drop_memories control failed")
    _require(
        control_agent.control_calls == [
            ("compact", "keep freshest context"),
            ("drop_memories", "clear older context"),
        ],
        "control methods were not routed to the shared-session agent",
    )

    control_detail = await control_use_cases.get_session_detail("sess-control", recent_limit=10)
    compact_entry = next(
        item
        for item in control_detail.recent_messages
        if item.role == "system" and isinstance(item.metadata, dict) and item.metadata.get("command") == "compact"
    )
    _require(compact_entry.surface == "tui", "compact command transcript should keep invoker surface")
    _require(control_detail.active_surface == "qq", "control should not silently change active surface")

    async def _build_cancel_agent(_workspace: Path):
        return cancel_agent

    cancel_use_cases = _new_use_cases(
        storage_dir=root / "cancel-runtime-store",
        build_agent=_build_cancel_agent,
    )

    cancel_task = asyncio.create_task(
        cancel_use_cases.run_chat(
            MainAgentChatRequest(
                message="long running task",
                workspace_dir=str(workspace),
                session_id="sess-cancel",
                surface="qq",
                channel_type="qq",
                conversation_id="group:cancel",
                sender_id="user-cancel",
            )
        )
    )
    await asyncio.wait_for(cancel_agent.started.wait(), timeout=1.0)

    cancel = await asyncio.wait_for(
        cancel_use_cases.cancel_session(
            "sess-cancel",
            MainAgentSessionCancelRequest(
                reason="stop now",
                surface="tui",
                channel_type="qq",
                conversation_id="group:cancel",
                sender_id="user-cancel",
            ),
        ),
        timeout=1.0,
    )
    _require(cancel.status == "cancel_requested", "shared cancel request status mismatch")
    _require(cancel_agent.received_cancel_event is not None and cancel_agent.received_cancel_event.is_set(), "cancel event not delivered to running shared session")

    cancelled_reply = await asyncio.wait_for(cancel_task, timeout=1.0)
    _require(cancelled_reply.reply == "Task cancelled by user.", "shared cancel reply mismatch")
    cancel_detail = await cancel_use_cases.get_session_detail("sess-cancel", recent_limit=10)
    cancel_entry = next(
        item
        for item in cancel_detail.recent_messages
        if item.role == "system" and isinstance(item.metadata, dict) and item.metadata.get("command") == "cancel"
    )
    _require(cancel_entry.surface == "tui", "cancel command transcript should keep invoker surface")
    _require(cancel_detail.recent_messages[-1].content == "Task cancelled by user.", "cancel transcript tail mismatch")

    return WalkthroughResult(
        name="shared-control-and-cancel",
        ok=True,
        note="shared context controls preserved routing ownership, and remote cancel interrupted a running gateway-managed turn",
        excerpts={
            "control_detail": _clip(_format_detail(control_detail)),
            "cancel_detail": _clip(_format_detail(cancel_detail)),
        },
    )


async def _check_shared_model_selection(root: Path) -> WalkthroughResult:
    workspace = root / "workspace"
    build_calls: list[tuple[str | None, str | None, str | None]] = []

    async def _build_agent(_workspace: Path):
        build_calls.append((None, None, None))
        return _SelectableAgent(provider_source="preset", provider_id="openai", model_id="gpt-5.4")

    async def _build_agent_with_selection(
        _workspace: Path,
        provider_source: str | None,
        provider_id: str | None,
        model_id: str | None,
    ):
        build_calls.append((provider_source, provider_id, model_id))
        return _SelectableAgent(
            provider_source=provider_source or "preset",
            provider_id=provider_id or "openai",
            model_id=model_id or "gpt-5.4",
        )

    use_cases = _new_use_cases(
        storage_dir=root / "model-runtime-store",
        build_agent=_build_agent,
        build_agent_with_selection=_build_agent_with_selection,
    )

    first = await use_cases.run_chat(
        MainAgentChatRequest(
            message="hello from qq",
            workspace_dir=str(workspace),
            session_id="sess-model",
            surface="qq",
            channel_type="qq",
            conversation_id="group:model",
            sender_id="user-model",
        )
    )
    _require(first.reply == "gpt-5.4:hello from qq", "seed shared model reply mismatch")

    detail_before = await use_cases.get_session_detail("sess-model", recent_limit=10)
    _require(detail_before.selected_model_id == "gpt-5.4", "default shared selected model mismatch")

    selected = await use_cases.update_session_model_selection(
        "sess-model",
        MainAgentSessionModelSelectionRequest(
            provider_source="preset",
            provider_id="openai",
            model_id="gpt-5.3",
            surface="tui",
        ),
    )
    _require(selected.applied is True and selected.queued is False, "idle shared model switch should apply immediately")
    _require(build_calls[-1] == ("preset", "openai", "gpt-5.3"), "shared model rebuild call mismatch")

    detail_after_select = await use_cases.get_session_detail("sess-model", recent_limit=10)
    _require(detail_after_select.selected_model_id == "gpt-5.3", "selected model detail mismatch after immediate switch")
    _require(detail_after_select.pending_model_id is None, "pending model should be empty after immediate switch")

    managed_session = await use_cases._session_service._runtime_manager.get_or_create_session("sess-model", workspace)
    managed_session.projection.busy = True
    managed_session.projection.running_state = "qq request running"
    queued = await use_cases.update_session_model_selection(
        "sess-model",
        MainAgentSessionModelSelectionRequest(
            provider_source="preset",
            provider_id="openai",
            model_id="gpt-5.4",
            surface="qq",
            channel_type="qq",
            conversation_id="group:model",
            sender_id="user-model",
        ),
    )
    _require(queued.applied is False and queued.queued is True, "busy shared model switch should queue")
    _require(queued.pending_model_id == "gpt-5.4", "queued shared model id mismatch")

    detail_after_queue = await use_cases.get_session_detail("sess-model", recent_limit=10)
    _require(detail_after_queue.selected_model_id == "gpt-5.3", "selected model should stay active while queued")
    _require(detail_after_queue.pending_model_id == "gpt-5.4", "pending model detail mismatch while queued")

    managed_session.projection.busy = False
    managed_session.projection.running_state = ""
    second = await use_cases.run_chat(
        MainAgentChatRequest(
            message="continue after queued switch",
            workspace_dir=str(workspace),
            session_id="sess-model",
            surface="qq",
            channel_type="qq",
            conversation_id="group:model",
            sender_id="user-model",
        )
    )
    _require(
        second.reply == "gpt-5.4:continue after queued switch",
        "queued shared model did not apply on the next turn",
    )

    detail_after_continue = await use_cases.get_session_detail("sess-model", recent_limit=10)
    _require(detail_after_continue.selected_model_id == "gpt-5.4", "selected model mismatch after queued continuation")
    _require(detail_after_continue.pending_model_id is None, "pending model should clear after queued continuation")

    return WalkthroughResult(
        name="shared-model-selection",
        ok=True,
        note="shared-session model switching applied immediately when idle and queued correctly when the session was busy",
        excerpts={
            "detail_before": _clip(_format_detail(detail_before)),
            "detail_after_select": _clip(_format_detail(detail_after_select)),
            "detail_after_queue": _clip(_format_detail(detail_after_queue)),
            "detail_after_continue": _clip(_format_detail(detail_after_continue)),
        },
    )


async def _check_import_export_roundtrip(root: Path) -> WalkthroughResult:
    workspace = root / "workspace"
    storage_dir = root / "runtime-store"

    async def _build_agent(_workspace: Path):
        return _DummyAgent(prefix="mock")

    use_cases = _new_use_cases(storage_dir=storage_dir, build_agent=_build_agent)

    detail = await _import_runtime_session(
        use_cases,
        workspace_dir=str(workspace),
        title="Local Draft",
        origin_surface="tui",
        active_surface="tui",
        agent_messages=[
            {"role": "system", "content": "system"},
            {"role": "user", "content": "hello local"},
            {"role": "assistant", "content": "hello shared"},
        ],
        transcript=[
            {"role": "user", "content": "hello local", "surface": "tui"},
            {"role": "assistant", "content": "hello shared", "surface": "tui"},
        ],
    )
    _require(detail.title == "Local Draft", "imported shared session title mismatch")
    _require(detail.origin_surface == "tui" and detail.active_surface == "tui", "imported shared session surfaces mismatch")

    snapshot = await _export_runtime_session(use_cases, detail.session_id)
    _require(snapshot.title == "Local Draft", "exported shared session title mismatch")
    _require([item.content for item in snapshot.transcript] == ["hello local", "hello shared"], "exported transcript mismatch")

    deleted = await use_cases.delete_session(detail.session_id)
    _require(deleted.status == "deleted", "shared session delete failed")
    sessions_after = await use_cases.list_sessions()
    _require(sessions_after == [], "shared session should be gone after delete/unshare")

    return WalkthroughResult(
        name="import-export-roundtrip",
        ok=True,
        note="tui-origin share/import, export, and delete/unshare roundtrip kept transcript fidelity",
        excerpts={
            "snapshot": _clip(_format_snapshot(snapshot)),
        },
    )


async def _check_restart_persistence(root: Path) -> WalkthroughResult:
    workspace = root / "workspace"
    storage_dir = root / "runtime-store"

    async def _build_agent(_workspace: Path):
        return _DummyAgent(prefix="mock")

    use_cases_first = _new_use_cases(storage_dir=storage_dir, build_agent=_build_agent)
    first = await use_cases_first.run_chat(
        MainAgentChatRequest(
            message="hello from qq",
            workspace_dir=str(workspace),
            session_id="sess-persist",
            surface="qq",
            channel_type="qq",
            conversation_id="group:persist",
            sender_id="user-1",
        )
    )
    _require(first.session_id == "sess-persist", "persisted session id mismatch")

    use_cases_second = _new_use_cases(storage_dir=storage_dir, build_agent=_build_agent)
    sessions = await use_cases_second.list_sessions()
    _require([item.session_id for item in sessions] == ["sess-persist"], "persisted shared session list mismatch after restart")

    detail = await use_cases_second.get_session_detail("sess-persist", recent_limit=10)
    _require([item.content for item in detail.recent_messages] == ["hello from qq", "mock:hello from qq"], "persisted transcript mismatch after restart")

    activated = await _activate_runtime_surface(use_cases_second, "sess-persist", surface="tui")
    _require(activated.active_surface == "tui", "post-restart surface activation failed")

    second = await use_cases_second.run_chat(
        MainAgentChatRequest(
            message="continue after restart",
            workspace_dir=str(workspace),
            session_id="sess-persist",
            surface="tui",
        )
    )
    _require(second.reply == "mock:continue after restart", "post-restart shared continuation mismatch")

    detail_after = await use_cases_second.get_session_detail("sess-persist", recent_limit=10)
    _require(detail_after.active_surface == "tui", "active surface mismatch after restart continuation")
    _require([item.content for item in detail_after.recent_messages[-2:]] == ["continue after restart", "mock:continue after restart"], "persisted continuation transcript mismatch")

    return WalkthroughResult(
        name="restart-persistence",
        ok=True,
        note="gateway-managed shared sessions survived restart, remained discoverable, and continued on the same session after takeover",
        excerpts={
            "detail_after_restart": _clip(_format_detail(detail)),
            "detail_after_continue": _clip(_format_detail(detail_after)),
        },
    )


async def _check_restart_recovery_snapshot(root: Path) -> WalkthroughResult:
    workspace = root / "workspace"
    storage_dir = root / "runtime-store"

    async def _build_agent(_workspace: Path):
        return _HookedAgent(prefix="hooked")

    runtime_first = MainAgentRuntimeManager(
        ttl_seconds=3600,
        build_agent=_build_agent,
        storage_dir=storage_dir,
        load_runtime_config=_test_runtime_config,
    )
    _use_cases_first = MainAgentSurfaceService(
        session_service=SessionApplicationService(runtime_manager=runtime_first),
        resolve_workspace_dir=_resolve_workspace_dir,
        to_utc_iso=_to_utc_iso,
        sse_event=_sse_event,
        format_bootstrap_error=_format_bootstrap_error,
        stream_chunk_size=64,
    )
    session = await runtime_first.get_or_create_session("sess-recovery", workspace)
    runtime_first.bind_session_surface(
        session,
        surface="qq",
        channel_type="qq",
        conversation_id="group:recovery",
        sender_id="user-recovery",
    )
    runtime_first.mark_turn_started(session, surface="qq", detail="qq request running")
    runtime_first.record_message(
        session,
        role="user",
        content="inspect tests",
        surface="qq",
        channel_type="qq",
        conversation_id="group:recovery",
        sender_id="user-recovery",
    )
    runtime_first.record_activity(
        session,
        label="thinking",
        detail="step 1: planned 1 tool call(s)",
        surface="qq",
        channel_type="qq",
        conversation_id="group:recovery",
        sender_id="user-recovery",
    )
    runtime_first.record_activity(
        session,
        label="bash",
        detail="ok",
        surface="qq",
        preview="pytest -q",
        output_text="32 passed",
        state="ok",
        channel_type="qq",
        conversation_id="group:recovery",
        sender_id="user-recovery",
    )
    approval_future: asyncio.Future[bool | None] = asyncio.get_running_loop().create_future()
    runtime_first.record_pending_approval(
        session,
        payload={
            "token": "approval-recovery-1",
            "tool_name": "shell",
            "arguments": {"command": "pytest -q"},
            "kind": "exec",
            "reason": "needs manual approval",
            "step": 1,
        },
        future=approval_future,
    )

    use_cases_second = _new_use_cases(storage_dir=storage_dir, build_agent=_build_agent)
    sessions = await use_cases_second.list_sessions()
    _require([item.session_id for item in sessions] == ["sess-recovery"], "restart recovery session list mismatch")
    summary = sessions[0]
    _require(summary.busy is False, "persisted interrupted session should not remain actively busy after restart")
    _require(summary.recovery is not None, "recovery snapshot missing from persisted session summary")
    _require(summary.recovery.state == "interrupted", "persisted interrupted session should expose interrupted recovery state")
    _require(
        "approval pending for shell" in str(summary.recovery.summary or ""),
        "recovery summary should prioritize lost pending approvals after restart",
    )

    detail = await use_cases_second.get_session_detail("sess-recovery", recent_limit=10)
    _require(detail.recovery is not None, "recovery snapshot missing from persisted session detail")
    _require(detail.recovery.state == "interrupted", "persisted detail recovery state mismatch")
    _require(
        detail.recovery.last_activity == "shell ok | pytest -q | 32 passed",
        "persisted recovery should retain last activity summary",
    )
    _require(detail.recovery.last_user_message == "inspect tests", "persisted recovery should retain last user message")
    _require(
        len(list(detail.recovery.pending_approvals or [])) == 1,
        "persisted recovery should retain lost pending approvals",
    )

    activated = await _activate_runtime_surface(use_cases_second, "sess-recovery", surface="tui")
    _require(activated.active_surface == "tui", "interrupted session surface activation after restart failed")
    detail_after_takeover = await use_cases_second.get_session_detail("sess-recovery", recent_limit=10)
    _require(detail_after_takeover.recovery is not None, "recovery snapshot missing after takeover")
    _require(
        detail_after_takeover.recovery.state == "interrupted",
        "takeover should not discard interrupted recovery before the next turn",
    )
    second = await use_cases_second.run_chat(
        MainAgentChatRequest(
            message="continue after interruption",
            workspace_dir=str(workspace),
            session_id="sess-recovery",
            surface="tui",
        )
    )
    _require(second.reply == "hooked:continue after interruption", "interrupted recovery continuation reply mismatch")
    managed_session = await use_cases_second._session_service._runtime_manager.get_or_create_session(
        "sess-recovery",
        workspace,
    )
    captured_turn_context = getattr(managed_session.runtime.agent, "captured_turn_contexts", [])[-1]
    recovery_metadata = {}
    if isinstance(captured_turn_context, dict):
        metadata = captured_turn_context.get("metadata")
        if isinstance(metadata, dict):
            recovery_metadata = dict(metadata.get("recovery") or {})
    _require(recovery_metadata.get("state") == "interrupted", "recovery metadata should be passed into the next turn")
    _require(recovery_metadata.get("pending_approvals"), "lost approvals should be included in recovery metadata")

    detail_after = await use_cases_second.get_session_detail("sess-recovery", recent_limit=10)
    _require(detail_after.recovery is not None, "recovery snapshot missing after interrupted recovery continue")
    _require(detail_after.recovery.state == "handoff", "recovered session should show handoff state after TUI takeover")
    _require(
        detail_after.recent_messages[-1].content == "hooked:continue after interruption",
        "recovered session continuation transcript mismatch",
    )

    return WalkthroughResult(
        name="restart-recovery-snapshot",
        ok=True,
        note="persisted interrupted shared sessions expose recovery context after restart and can still be taken over and continued",
        excerpts={
            "detail_after_restart": _clip(_format_detail(detail)),
            "detail_after_takeover": _clip(_format_detail(detail_after_takeover)),
            "turn_context_recovery": _clip(str(recovery_metadata)),
            "detail_after_continue": _clip(_format_detail(detail_after)),
        },
    )


async def _run_all(root: Path) -> list[WalkthroughResult]:
    return [
        await _check_shared_activity_and_takeover(root / "shared-activity"),
        await _check_shared_control_and_cancel(root / "shared-control"),
        await _check_shared_model_selection(root / "shared-model-selection"),
        await _check_import_export_roundtrip(root / "import-export"),
        await _check_restart_recovery_snapshot(root / "restart-recovery"),
        await _check_restart_persistence(root / "restart-persistence"),
    ]


def _render_report(*, captured_at: datetime, results: list[WalkthroughResult]) -> str:
    overall_ok = all(item.ok for item in results)
    lines = [
        f"# Shared Session Gateway Walkthrough - {captured_at.strftime('%Y-%m-%d %H:%M:%S %Z')}",
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
    parser = argparse.ArgumentParser(description="Run scripted shared-session gateway walkthrough.")
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
        else output_dir / f"shared_session_gateway_walkthrough_{captured_at.strftime('%Y%m%dT%H%M%SZ')}.md"
    )

    try:
        with tempfile.TemporaryDirectory(
            prefix="mini-agent-shared-session-walkthrough-",
            ignore_cleanup_errors=True,
        ) as temp_dir:
            results = asyncio.run(_run_all(Path(temp_dir)))
    except Exception as exc:
        results = [
            WalkthroughResult(
                name="shared-session-gateway-walkthrough",
                ok=False,
                note=str(exc),
            )
        ]

    report_path.write_text(
        _render_report(captured_at=captured_at, results=results),
        encoding="utf-8",
    )
    overall_ok = all(item.ok for item in results)
    print(f"[shared-session-walkthrough] report={report_path}")
    print(f"[shared-session-walkthrough] overall={'PASS' if overall_ok else 'FAIL'}")
    return 0 if overall_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
