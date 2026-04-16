"""Scripted channel-ingress -> gateway walkthrough for readiness validation.

Exercises the QQ-like channel ingress mainline without requiring a real login:
- channel ingress creates and reuses a gateway-managed shared session
- channel metadata survives into session detail and recent messages
- activity transcript remains visible for channel-origin turns
- TUI can take over the same ingress-created session and continue work
"""

# ruff: noqa: E402

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

from mini_agent.agent_core.engine import TurnExecutionResult, TurnStopReason
from mini_agent.application import ChannelIngressUseCases, ChannelNovelActionHandler, MainAgentSurfaceService, SessionApplicationService
from mini_agent.config import AgentConfig, Config, LLMConfig, ToolsConfig
from mini_agent.interfaces import ChannelMessageRequest, MainAgentChatRequest
from mini_agent.runtime.main_agent_runtime_manager import MainAgentRuntimeManager
from mini_agent.session import ConversationBindingService, ConversationBindingStore


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
    async def run_turn(
        self,
        *,
        cancel_event: asyncio.Event | None = None,
        hooks: Any = None,
        turn_context: Any = None,
        start_new_run: bool = True,
    ) -> TurnExecutionResult:
        _ = cancel_event
        _ = turn_context
        _ = start_new_run
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


class _UnusedNovelUseCases:
    async def get_config(self, project_dir: str | None = None) -> dict[str, object]:
        _ = project_dir
        raise AssertionError("novel actions are outside this walkthrough scope")


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
    summary_lines = [
        f"session={getattr(detail, 'session_id', '')}",
        f"origin={getattr(detail, 'origin_surface', '')} active={getattr(detail, 'active_surface', '')}",
        (
            f"channel={getattr(detail, 'channel_type', '')} "
            f"conversation={getattr(detail, 'conversation_id', '')} "
            f"sender={getattr(detail, 'sender_id', '')}"
        ),
        f"reply_enabled={getattr(detail, 'reply_enabled', False)} messages={getattr(detail, 'message_count', 0)}",
    ]
    recent_messages = list(getattr(detail, "recent_messages", []) or [])
    if recent_messages:
        summary_lines.append("recent:")
        for item in recent_messages[-6:]:
            role = str(getattr(item, "role", "") or "")
            surface = str(getattr(item, "surface", "") or "")
            content = str(getattr(item, "content", "") or "").strip()
            summary_lines.append(f"- {role}@{surface}: {content}")
    return "\n".join(summary_lines)


def _format_messages(messages: list[Any]) -> str:
    lines = []
    for item in messages:
        role = str(getattr(item, "role", "") or "")
        surface = str(getattr(item, "surface", "") or "")
        content = str(getattr(item, "content", "") or "").strip()
        lines.append(f"- {role}@{surface}: {content}")
    return "\n".join(lines)


def _new_gateway_use_cases(
    *,
    storage_dir: Path,
    build_agent,
) -> MainAgentSurfaceService:
    runtime = MainAgentRuntimeManager(
        ttl_seconds=3600,
        build_agent=build_agent,
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


def _new_channel_use_cases(gateway_use_cases: MainAgentSurfaceService, *, root: Path) -> ChannelIngressUseCases:
    return ChannelIngressUseCases(
        run_main_agent_chat=gateway_use_cases.run_chat,
        novel_action_handler=ChannelNovelActionHandler(
            novel_use_cases=_UnusedNovelUseCases(),
            resolve_workspace_dir=_resolve_workspace_dir,
            to_utc_iso=_to_utc_iso,
        ),
        conversation_binding=ConversationBindingService(
            binding_store=ConversationBindingStore(root / "conversation-bindings.json"),
        ),
    )


async def _check_channel_reuse_and_continue_contract(root: Path) -> WalkthroughResult:
    workspace = root / "workspace"
    storage_dir = root / "runtime-store"

    async def _build_agent(_workspace: Path):
        return _DummyAgent(prefix="qq")

    gateway_use_cases = _new_gateway_use_cases(storage_dir=storage_dir, build_agent=_build_agent)
    channel_use_cases = _new_channel_use_cases(gateway_use_cases, root=root)

    first = await channel_use_cases.handle_message(
        ChannelMessageRequest(
            channel_type="qq",
            conversation_id="group:alpha",
            sender_id="user-1",
            message="hello from qq",
            workspace_dir=str(workspace),
        )
    )
    _require(first.reply == "qq:hello from qq", "first ingress reply mismatch")

    second = await channel_use_cases.handle_message(
        ChannelMessageRequest(
            channel_type="qq",
            conversation_id="group:alpha",
            sender_id="user-1",
            message="continue from qq",
            workspace_dir=str(workspace),
        )
    )
    _require(second.session_id == first.session_id, "channel ingress should reuse stored session id")
    _require(second.reply == "qq:continue from qq", "second ingress reply mismatch")

    sessions = await gateway_use_cases.list_sessions()
    _require([item.session_id for item in sessions] == [first.session_id], "shared session list mismatch")

    detail = await gateway_use_cases.get_session_detail(first.session_id, recent_limit=10)
    _require(detail.origin_surface == "qq", "channel-origin session should preserve qq origin")
    _require(detail.active_surface == "qq", "channel-origin session should stay on qq before takeover")
    _require(detail.reply_enabled is True, "channel-origin session should stay reply-enabled")
    _require(detail.channel_type == "qq", "channel type mismatch")
    _require(detail.conversation_id == "group:alpha", "conversation id mismatch")
    _require(detail.sender_id == "user-1", "sender id mismatch")
    _require(
        [item.content for item in detail.recent_messages] == [
            "hello from qq",
            "qq:hello from qq",
            "continue from qq",
            "qq:continue from qq",
        ],
        "shared transcript content mismatch for channel reuse",
    )
    _require(
        [item.surface for item in detail.recent_messages] == ["qq", "qq", "qq", "qq"],
        "channel transcript surface mismatch",
    )

    latest = await gateway_use_cases.get_session_messages(first.session_id, limit=4)
    _require(
        [item.content for item in latest] == [
            "hello from qq",
            "qq:hello from qq",
            "continue from qq",
            "qq:continue from qq",
        ],
        "recent messages should stay available for /continue-style consumers",
    )

    return WalkthroughResult(
        name="channel-reuse-and-continue",
        ok=True,
        note="channel ingress reused the same shared session and kept recent transcript readable for remote continue flows",
        excerpts={
            "detail": _clip(_format_detail(detail)),
            "recent_messages": _clip(_format_messages(latest)),
        },
    )


async def _check_channel_activity_and_takeover(root: Path) -> WalkthroughResult:
    workspace = root / "workspace"
    storage_dir = root / "runtime-store"

    async def _build_agent(_workspace: Path):
        return _HookedAgent(prefix="hooked")

    gateway_use_cases = _new_gateway_use_cases(storage_dir=storage_dir, build_agent=_build_agent)
    channel_use_cases = _new_channel_use_cases(gateway_use_cases, root=root)

    first = await channel_use_cases.handle_message(
        ChannelMessageRequest(
            channel_type="qq",
            conversation_id="group:activity",
            sender_id="user-2",
            message="inspect tests",
            workspace_dir=str(workspace),
        )
    )
    _require(first.reply == "hooked:inspect tests", "channel activity reply mismatch")

    detail_before = await gateway_use_cases.get_session_detail(first.session_id, recent_limit=10)
    _require(
        [item.role for item in detail_before.recent_messages] == ["user", "tool", "assistant"],
        "channel activity transcript mismatch",
    )
    activity_entry = detail_before.recent_messages[1]
    metadata = activity_entry.metadata or {}
    _require(metadata.get("kind") == "activity", "activity metadata missing on channel-origin turn")
    labels = [item.get("label") for item in metadata.get("activity_items", [])]
    _require(labels == ["thinking", "shell"], "channel-origin activity labels mismatch")

    activated = await _activate_runtime_surface(gateway_use_cases, first.session_id, surface="tui")
    _require(activated.active_surface == "tui", "tui surface activation should switch active surface")

    second = await gateway_use_cases.run_chat(
        MainAgentChatRequest(
            message="continue in tui",
            workspace_dir=str(workspace),
            session_id=first.session_id,
            surface="tui",
        )
    )
    _require(second.reply == "hooked:continue in tui", "tui continuation reply mismatch")

    detail_after = await gateway_use_cases.get_session_detail(first.session_id, recent_limit=10)
    _require(detail_after.origin_surface == "qq", "origin surface should remain qq")
    _require(detail_after.active_surface == "tui", "active surface should become tui")
    _require(detail_after.reply_enabled is False, "tui takeover should disable automatic qq reply ownership")
    _require(
        [item.role for item in detail_after.recent_messages[-3:]] == ["user", "tool", "assistant"],
        "post-takeover transcript tail mismatch",
    )
    _require(
        [item.surface for item in detail_after.recent_messages[-3:]] == ["tui", "tui", "tui"],
        "post-takeover transcript surfaces mismatch",
    )
    _require(
        detail_after.recent_messages[-1].content == "hooked:continue in tui",
        "tui continuation assistant reply missing from shared transcript",
    )

    return WalkthroughResult(
        name="channel-activity-and-takeover",
        ok=True,
        note="channel-origin sessions kept activity visibility and still handed off cleanly to TUI on the same shared session",
        excerpts={
            "detail_before_takeover": _clip(_format_detail(detail_before)),
            "detail_after_takeover": _clip(_format_detail(detail_after)),
        },
    )


async def _run_all(root: Path) -> list[WalkthroughResult]:
    return [
        await _check_channel_reuse_and_continue_contract(root / "channel-reuse"),
        await _check_channel_activity_and_takeover(root / "channel-takeover"),
    ]


def _render_report(*, captured_at: datetime, results: list[WalkthroughResult]) -> str:
    overall_ok = all(item.ok for item in results)
    lines = [
        f"# Channel Ingress Gateway Walkthrough - {captured_at.strftime('%Y-%m-%d %H:%M:%S %Z')}",
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
    parser = argparse.ArgumentParser(description="Run scripted channel-ingress gateway walkthrough.")
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
        else output_dir / f"channel_ingress_gateway_walkthrough_{captured_at.strftime('%Y%m%dT%H%M%SZ')}.md"
    )

    try:
        with tempfile.TemporaryDirectory(
            prefix="mini-agent-channel-ingress-walkthrough-",
            ignore_cleanup_errors=True,
        ) as temp_dir:
            results = asyncio.run(_run_all(Path(temp_dir)))
    except Exception as exc:
        results = [
            WalkthroughResult(
                name="channel-ingress-gateway-walkthrough",
                ok=False,
                note=str(exc),
            )
        ]

    report_path.write_text(
        _render_report(captured_at=captured_at, results=results),
        encoding="utf-8",
    )
    overall_ok = all(item.ok for item in results)
    print(f"[channel-ingress-walkthrough] report={report_path}")
    print(f"[channel-ingress-walkthrough] overall={'PASS' if overall_ok else 'FAIL'}")
    return 0 if overall_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
