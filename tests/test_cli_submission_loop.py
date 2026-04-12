"""Tests for CLI/headless submission-loop integration."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from mini_agent import cli
from mini_agent import cli_interactive
from mini_agent.agent import Agent
from mini_agent.code_agent import AgentLoopContext, AgentSubmissionLoop, ApprovalEngine, InMemoryLoopMessageBus, PermissionPolicy
from mini_agent.logger import AgentLogger
from mini_agent.memory.service import MemoryService
from mini_agent.schema import FunctionCall, LLMResponse, ToolCall
from mini_agent.tools.base import Tool, ToolResult


class _FakeLoop:
    def __init__(self) -> None:
        self.stop_called = False

    async def stop(self) -> None:
        self.stop_called = True


def _write_consolidated_memory(path: Path, *, items: list[str], last_updated_utc: str) -> None:
    section_lines = [
        "<!-- MINI_AGENT_CONSOLIDATED_MEMORY_BEGIN -->",
        "## Consolidated Memory",
    ]
    section_lines.extend(f"- {item}" for item in items)
    section_lines.append(f"last_updated_utc: {last_updated_utc}")
    section_lines.append("<!-- MINI_AGENT_CONSOLIDATED_MEMORY_END -->")
    path.write_text(
        "# Long-Term Memory\n\n" + "\n".join(section_lines) + "\n",
        encoding="utf-8",
    )


class _FakeControlLoop(_FakeLoop):
    def __init__(self, bus) -> None:  # noqa: ANN001
        super().__init__()
        self.bus = bus
        self.calls: list[tuple[str, str | None]] = []

    async def submit_compact(self, *, reason: str | None = None) -> str:
        self.calls.append(("compact", reason))
        event_id = "evt-compact"
        self.bus.events.append(
            {
                "event_type": "loop.compact",
                "payload": {
                    "event_id": event_id,
                    "reason": reason,
                    "applied": True,
                    "message_count_before": 5,
                    "message_count_after": 3,
                    "token_count_before": 220,
                    "token_count_after": 110,
                    "stats": {"masked_messages": 1, "snipped_messages": 1, "merged_messages": 0},
                },
                "timestamp": "2026-04-09T00:00:00+00:00",
            }
        )
        return event_id

    async def submit_drop_memories(self, *, reason: str | None = None) -> str:
        self.calls.append(("drop_memories", reason))
        event_id = "evt-drop"
        self.bus.events.append(
            {
                "event_type": "loop.drop_memories",
                "payload": {
                    "event_id": event_id,
                    "reason": reason,
                    "applied": True,
                    "message_count_before": 11,
                    "message_count_after": 4,
                    "token_count_before": 510,
                    "token_count_after": 160,
                    "stats": {"masked_messages": 0, "snipped_messages": 2, "merged_messages": 1},
                },
                "timestamp": "2026-04-09T00:00:01+00:00",
            }
        )
        return event_id


class _NoDirectRunAgent:
    def __init__(self, *, model: str = "gpt-test") -> None:
        self.llm_client = SimpleNamespace(model=model)
        self.tools: list[object] = []
        self.messages = [SimpleNamespace(role="system"), SimpleNamespace(role="assistant")]
        self.api_total_tokens = 0
        self._knowledge_base_enabled = True

    def add_user_message(self, _content: str) -> None:  # pragma: no cover - regression guard
        raise AssertionError("legacy add_user_message path should not be called")

    async def run(self) -> str:  # pragma: no cover - regression guard
        raise AssertionError("legacy run path should not be called")

    def knowledge_base_enabled(self) -> bool:
        return self._knowledge_base_enabled

    def set_knowledge_base_enabled(self, enabled: bool) -> bool:
        self._knowledge_base_enabled = bool(enabled)
        return self._knowledge_base_enabled


class _SequenceLLM:
    def __init__(self, responses: list[LLMResponse]):
        self._responses = responses
        self.calls = 0

    async def generate(self, messages, tools=None):  # noqa: ANN001,ARG002
        response_index = min(self.calls, len(self._responses) - 1)
        self.calls += 1
        return self._responses[response_index]


class _EchoTool(Tool):
    @property
    def name(self) -> str:
        return "echo"

    @property
    def description(self) -> str:
        return "Echo helper tool."

    @property
    def parameters(self) -> dict:
        return {"type": "object", "properties": {"text": {"type": "string"}}}

    async def execute(self, text: str) -> ToolResult:
        return ToolResult(success=True, content=f"echo:{text}")


def test_run_headless_prompt_async_uses_submission_loop(monkeypatch, tmp_path: Path) -> None:
    fake_agent = _NoDirectRunAgent(model="gpt-headless")
    fake_loop = _FakeLoop()
    captured: dict[str, object] = {"cleanup": False}

    async def _fake_build_agent(_workspace: Path, approval_profile: str | None = None):
        _ = approval_profile
        return fake_agent

    async def _fake_create_loop(*, agent, session_id: str, hooks=None):
        _ = hooks
        captured["agent"] = agent
        captured["session_id"] = session_id
        return fake_loop, object()

    async def _fake_run_prompt(
        *,
        loop,
        bus,
        agent,
        prompt: str,
        metadata=None,
        start_new_run: bool = True,
        approval_resolver=None,
        event_handler=None,
    ):
        _ = loop
        _ = bus
        _ = approval_resolver
        _ = event_handler
        captured["prompt"] = prompt
        captured["metadata"] = metadata
        captured["start_new_run"] = start_new_run
        captured["agent_in_run"] = agent
        return {
            "state": "completed",
            "stop_reason": "end_turn",
            "message": "headless-ok",
            "error": "",
            "prepared_context": {
                "item_count": 1,
                "sources": ["knowledge_base"],
            },
            "prepared_context_diagnostics": {
                "turn_count": 1,
                "turns_with_context": 1,
                "total_item_count": 1,
            },
        }

    async def _fake_cleanup() -> None:
        captured["cleanup"] = True

    monkeypatch.setattr("mini_agent.cli_interactive.build_agent", _fake_build_agent)
    monkeypatch.setattr("mini_agent.cli_interactive.create_submission_loop_for_agent", _fake_create_loop)
    monkeypatch.setattr("mini_agent.cli_interactive.run_prompt_via_submission_loop", _fake_run_prompt)
    monkeypatch.setattr("mini_agent.tools.mcp_loader.cleanup_mcp_connections", _fake_cleanup)

    reply, model_id, prepared_context, prepared_context_diagnostics = asyncio.run(
        cli._run_headless_prompt_async(
            workspace=tmp_path,
            prompt="hello from test",
            approval_profile=None,
        )
    )

    assert reply == "headless-ok"
    assert model_id == "gpt-headless"
    assert prepared_context["item_count"] == 1
    assert prepared_context_diagnostics["turn_count"] == 1
    assert captured["session_id"] == "headless-session"
    assert captured["prompt"] == "hello from test"
    assert captured["metadata"] == {"surface": "headless", "mode": "single_prompt"}
    assert captured["start_new_run"] is True
    assert captured["agent"] is fake_agent
    assert captured["agent_in_run"] is fake_agent
    assert fake_loop.stop_called is True
    assert captured["cleanup"] is True


def test_run_headless_mode_json_includes_prepared_context_payloads(monkeypatch, tmp_path: Path, capsys) -> None:
    async def _fake_headless_prompt_async(*, workspace: Path, prompt: str, approval_profile: str | None):
        _ = workspace
        _ = prompt
        _ = approval_profile
        return (
            "READY",
            "gpt-live",
            {
                "item_count": 1,
                "sources": ["knowledge_base"],
                "raw_item_count": 2,
            },
            {
                "turn_count": 1,
                "turns_with_context": 1,
                "total_item_count": 1,
            },
        )

    monkeypatch.setattr(cli, "_run_headless_prompt_async", _fake_headless_prompt_async)

    args = SimpleNamespace(
        prompt="Reply with exactly: READY",
        workspace=str(tmp_path),
        approval_profile=None,
        output_format="json",
    )
    cli.run_headless_mode(args)

    payload = json.loads(capsys.readouterr().out.strip())
    assert payload["ok"] is True
    assert payload["model"] == "gpt-live"
    assert payload["prepared_context"]["item_count"] == 1
    assert payload["prepared_context_diagnostics"]["turn_count"] == 1


def test_run_headless_prompt_async_raises_on_error_payload(monkeypatch, tmp_path: Path) -> None:
    fake_agent = _NoDirectRunAgent(model="gpt-headless")
    fake_loop = _FakeLoop()
    captured: dict[str, object] = {"cleanup": False}

    async def _fake_build_agent(_workspace: Path, approval_profile: str | None = None):
        _ = approval_profile
        return fake_agent

    async def _fake_create_loop(*, agent, session_id: str, hooks=None):
        _ = agent
        _ = session_id
        _ = hooks
        return fake_loop, object()

    async def _fake_run_prompt(
        *,
        loop,
        bus,
        agent,
        prompt: str,
        metadata=None,
        start_new_run: bool = True,
        approval_resolver=None,
        event_handler=None,
    ):
        _ = loop
        _ = bus
        _ = agent
        _ = prompt
        _ = metadata
        _ = start_new_run
        _ = approval_resolver
        _ = event_handler
        return {
            "state": "errored",
            "stop_reason": "refusal",
            "message": "refused",
            "error": "turn_refusal",
        }

    async def _fake_cleanup() -> None:
        captured["cleanup"] = True

    monkeypatch.setattr("mini_agent.cli_interactive.build_agent", _fake_build_agent)
    monkeypatch.setattr("mini_agent.cli_interactive.create_submission_loop_for_agent", _fake_create_loop)
    monkeypatch.setattr("mini_agent.cli_interactive.run_prompt_via_submission_loop", _fake_run_prompt)
    monkeypatch.setattr("mini_agent.tools.mcp_loader.cleanup_mcp_connections", _fake_cleanup)

    try:
        asyncio.run(
            cli._run_headless_prompt_async(
                workspace=tmp_path,
                prompt="hello from test",
                approval_profile=None,
            )
        )
    except RuntimeError as exc:
        assert "refused" in str(exc)
    else:  # pragma: no cover - defensive
        raise AssertionError("Expected RuntimeError")

    assert fake_loop.stop_called is True
    assert captured["cleanup"] is True


def test_run_interactive_session_task_mode_uses_submission_loop(monkeypatch, tmp_path: Path) -> None:
    fake_agent = _NoDirectRunAgent(model="gpt-cli")
    fake_loop = _FakeLoop()
    captured: dict[str, object] = {"cleanup": False}

    async def _fake_build_agent(_workspace: Path, approval_profile: str | None = None):
        _ = approval_profile
        return fake_agent

    async def _fake_create_loop(*, agent, session_id: str, hooks=None):
        _ = hooks
        captured["agent"] = agent
        captured["session_id"] = session_id
        return fake_loop, object()

    async def _fake_run_prompt(
        *,
        loop,
        bus,
        agent,
        prompt: str,
        metadata=None,
        start_new_run: bool = True,
        approval_resolver=None,
        event_handler=None,
    ):
        _ = loop
        _ = bus
        _ = approval_resolver
        _ = event_handler
        captured["prompt"] = prompt
        captured["metadata"] = metadata
        captured["start_new_run"] = start_new_run
        captured["agent_in_run"] = agent
        return {
            "state": "completed",
            "stop_reason": "end_turn",
            "message": "ok",
            "error": "",
        }

    async def _fake_cleanup() -> None:
        captured["cleanup"] = True

    monkeypatch.setattr("mini_agent.cli_interactive.Config.load", lambda: object())
    monkeypatch.setattr(
        "mini_agent.ops.doctor.run_startup_self_check",
        lambda config, workspace: (True, []),
    )
    monkeypatch.setattr(
        "mini_agent.ops.doctor.format_doctor_report",
        lambda findings, title: "doctor-ok",
    )
    monkeypatch.setattr("mini_agent.cli_interactive.build_agent", _fake_build_agent)
    monkeypatch.setattr("mini_agent.cli_interactive.create_submission_loop_for_agent", _fake_create_loop)
    monkeypatch.setattr("mini_agent.cli_interactive.run_prompt_via_submission_loop", _fake_run_prompt)
    monkeypatch.setattr("mini_agent.cli_interactive.cleanup_mcp_connections", _fake_cleanup)

    asyncio.run(
        cli_interactive.run_interactive_session(
            workspace=tmp_path,
            task="run one",
            approval_profile=None,
        )
    )

    assert captured["session_id"] == "cli-session"
    assert captured["prompt"] == "run one"
    assert captured["metadata"] == {"surface": "cli", "mode": "single_task"}
    assert captured["start_new_run"] is True
    assert captured["agent"] is fake_agent
    assert captured["agent_in_run"] is fake_agent
    assert fake_loop.stop_called is True
    assert captured["cleanup"] is True


def test_run_interactive_session_task_mode_applies_lifecycle_reset(monkeypatch, tmp_path: Path) -> None:
    fake_agent = _NoDirectRunAgent(model="gpt-cli")
    fake_agent.last_prepared_turn_context = {"item_count": 1}
    fake_agent.prepared_context_diagnostics = {"turn_count": 2}
    fake_loop = _FakeLoop()
    captured: dict[str, object] = {"cleanup": False}
    monkeypatch.setattr("mini_agent.memory.memoria_runtime.Path.home", classmethod(lambda cls: tmp_path))

    class _FakeLifecycleRuntime:
        def __init__(self, *, surface: str, workspace_dir: Path, policy=None, agent_id: str = "main-agent"):  # noqa: ANN001
            _ = policy
            _ = agent_id
            captured["surface"] = surface
            captured["workspace_dir"] = workspace_dir
            self.policy = SimpleNamespace(mode=SimpleNamespace(value="idle"), idle_seconds=60)
            self.auto_reset_count = 0

        def ensure_active(self, session_id: str, *, now_utc=None, on_reset=None):  # noqa: ANN001
            _ = now_utc
            captured["session_id"] = session_id
            if on_reset is not None:
                on_reset()
            self.auto_reset_count += 1
            return SimpleNamespace(reset=True, reason="idle")

        def force_reset(self, session_id: str, *, now_utc=None, on_reset=None):  # noqa: ANN001
            _ = session_id
            _ = now_utc
            if on_reset is not None:
                on_reset()

    async def _fake_build_agent(_workspace: Path, approval_profile: str | None = None):
        _ = approval_profile
        return fake_agent

    async def _fake_create_loop(*, agent, session_id: str, hooks=None):
        _ = hooks
        captured["agent"] = agent
        captured["loop_session_id"] = session_id
        return fake_loop, object()

    async def _fake_run_prompt(
        *,
        loop,
        bus,
        agent,
        prompt: str,
        metadata=None,
        start_new_run: bool = True,
        approval_resolver=None,
        event_handler=None,
    ):
        _ = loop
        _ = bus
        _ = approval_resolver
        _ = event_handler
        captured["prompt"] = prompt
        captured["metadata"] = metadata
        captured["start_new_run"] = start_new_run
        captured["agent_in_run"] = agent
        return {
            "state": "completed",
            "stop_reason": "end_turn",
            "message": "ok",
            "error": "",
        }

    async def _fake_cleanup() -> None:
        captured["cleanup"] = True

    monkeypatch.setattr("mini_agent.cli_interactive.Config.load", lambda: object())
    monkeypatch.setattr(
        "mini_agent.ops.doctor.run_startup_self_check",
        lambda config, workspace: (True, []),
    )
    monkeypatch.setattr(
        "mini_agent.ops.doctor.format_doctor_report",
        lambda findings, title: "doctor-ok",
    )
    monkeypatch.setattr("mini_agent.cli_interactive.SurfaceSessionLifecycleRuntime", _FakeLifecycleRuntime)
    monkeypatch.setattr("mini_agent.cli_interactive.build_agent", _fake_build_agent)
    monkeypatch.setattr("mini_agent.cli_interactive.create_submission_loop_for_agent", _fake_create_loop)
    monkeypatch.setattr("mini_agent.cli_interactive.run_prompt_via_submission_loop", _fake_run_prompt)
    monkeypatch.setattr("mini_agent.cli_interactive.cleanup_mcp_connections", _fake_cleanup)

    asyncio.run(
        cli_interactive.run_interactive_session(
            workspace=tmp_path,
            task="run one",
            approval_profile=None,
        )
    )

    assert captured["surface"] == "cli"
    assert captured["session_id"] == "cli-session"
    assert captured["loop_session_id"] == "cli-session"
    assert len(fake_agent.messages) == 1
    assert fake_agent.last_prepared_turn_context is None
    assert fake_agent.prepared_context_diagnostics == {}
    assert fake_loop.stop_called is True
    assert captured["cleanup"] is True


def test_run_interactive_session_routes_compact_and_drop_memory_commands(monkeypatch, tmp_path: Path) -> None:
    fake_agent = _NoDirectRunAgent(model="gpt-cli")
    bus = InMemoryLoopMessageBus()
    fake_loop = _FakeControlLoop(bus)
    captured: dict[str, object] = {"cleanup": False}

    class _FakePromptSession:
        def __init__(self, *args, **kwargs) -> None:  # noqa: ANN002, ANN003
            _ = (args, kwargs)
            self._inputs = iter(
                [
                    "/compact keep latest tool outputs",
                    "/drop-memories clear older context",
                    "/exit",
                ]
            )

        async def prompt_async(self, *args, **kwargs):  # noqa: ANN002, ANN003
            _ = (args, kwargs)
            return next(self._inputs)

    async def _fake_build_agent(_workspace: Path, approval_profile: str | None = None):
        _ = approval_profile
        return fake_agent

    async def _fake_create_loop(*, agent, session_id: str, hooks=None):
        _ = (agent, session_id, hooks)
        return fake_loop, bus

    async def _fake_cleanup() -> None:
        captured["cleanup"] = True

    monkeypatch.setattr("mini_agent.cli_interactive.Config.load", lambda: object())
    monkeypatch.setattr(
        "mini_agent.ops.doctor.run_startup_self_check",
        lambda config, workspace: (True, []),
    )
    monkeypatch.setattr(
        "mini_agent.ops.doctor.format_doctor_report",
        lambda findings, title: "doctor-ok",
    )
    monkeypatch.setattr("mini_agent.cli_interactive.PromptSession", _FakePromptSession)
    monkeypatch.setattr("mini_agent.cli_interactive.build_agent", _fake_build_agent)
    monkeypatch.setattr("mini_agent.cli_interactive.create_submission_loop_for_agent", _fake_create_loop)
    monkeypatch.setattr("mini_agent.cli_interactive.cleanup_mcp_connections", _fake_cleanup)

    asyncio.run(
        cli_interactive.run_interactive_session(
            workspace=tmp_path,
            approval_profile=None,
        )
    )

    assert fake_loop.calls == [
        ("compact", "keep latest tool outputs"),
        ("drop_memories", "clear older context"),
    ]
    assert fake_loop.stop_called is True
    assert captured["cleanup"] is True


def test_run_interactive_session_routes_kb_commands(monkeypatch, tmp_path: Path, capsys) -> None:
    fake_agent = _NoDirectRunAgent(model="gpt-cli")
    fake_loop = _FakeLoop()
    captured: dict[str, object] = {"cleanup": False}

    class _FakePromptSession:
        def __init__(self, *args, **kwargs) -> None:  # noqa: ANN002, ANN003
            _ = (args, kwargs)
            self._inputs = iter(
                [
                    "/kb status",
                    "/kb off",
                    "/kb on",
                    "/exit",
                ]
            )

        async def prompt_async(self, *args, **kwargs):  # noqa: ANN002, ANN003
            _ = (args, kwargs)
            return next(self._inputs)

    async def _fake_build_agent(_workspace: Path, approval_profile: str | None = None):
        _ = approval_profile
        return fake_agent

    async def _fake_create_loop(*, agent, session_id: str, hooks=None):
        _ = (agent, session_id, hooks)
        return fake_loop, object()

    async def _fake_cleanup() -> None:
        captured["cleanup"] = True

    monkeypatch.setattr("mini_agent.cli_interactive.Config.load", lambda: object())
    monkeypatch.setattr(
        "mini_agent.ops.doctor.run_startup_self_check",
        lambda config, workspace: (True, []),
    )
    monkeypatch.setattr(
        "mini_agent.ops.doctor.format_doctor_report",
        lambda findings, title: "doctor-ok",
    )
    monkeypatch.setattr("mini_agent.cli_interactive.PromptSession", _FakePromptSession)
    monkeypatch.setattr("mini_agent.cli_interactive.build_agent", _fake_build_agent)
    monkeypatch.setattr("mini_agent.cli_interactive.create_submission_loop_for_agent", _fake_create_loop)
    monkeypatch.setattr("mini_agent.cli_interactive.cleanup_mcp_connections", _fake_cleanup)

    asyncio.run(
        cli_interactive.run_interactive_session(
            workspace=tmp_path,
            approval_profile=None,
        )
    )

    output = capsys.readouterr().out
    assert "Knowledge Base:" in output
    assert "Knowledge base disabled for this session" in output
    assert "Knowledge base enabled for this session" in output
    assert fake_agent.knowledge_base_enabled() is True
    assert fake_loop.stop_called is True
    assert captured["cleanup"] is True


def test_run_interactive_session_routes_model_commands(monkeypatch, tmp_path: Path, capsys) -> None:
    fake_agent = _NoDirectRunAgent(model="gpt-5.4")
    fake_agent.runtime_route = SimpleNamespace(model="gpt-5.4", provider_id="preset-openai")
    replacement_agent = _NoDirectRunAgent(model="astron-code-latest")
    replacement_agent.runtime_route = SimpleNamespace(model="astron-code-latest", provider_id="maas")
    loops: list[_FakeLoop] = []
    captured: dict[str, object] = {"cleanup": False}

    class _FakePromptSession:
        def __init__(self, *args, **kwargs) -> None:  # noqa: ANN002, ANN003
            _ = (args, kwargs)
            self._inputs = iter(
                [
                    "/model show",
                    "/model list",
                    "/model use maas astron-code-latest",
                    "/model show",
                    "/exit",
                ]
            )

        async def prompt_async(self, *args, **kwargs):  # noqa: ANN002, ANN003
            _ = (args, kwargs)
            return next(self._inputs)

    async def _fake_build_agent(_workspace: Path, approval_profile: str | None = None):
        _ = approval_profile
        return fake_agent

    async def _fake_build_agent_kernel(*, workspace_dir: Path, options) -> _NoDirectRunAgent:  # noqa: ANN001
        assert workspace_dir == tmp_path
        assert options.requested_provider_source == "custom"
        assert options.requested_provider_id == "maas"
        assert options.requested_model == "astron-code-latest"
        return replacement_agent

    async def _fake_create_loop(*, agent, session_id: str, hooks=None):
        _ = (agent, session_id, hooks)
        loop = _FakeLoop()
        loops.append(loop)
        return loop, object()

    async def _fake_cleanup() -> None:
        captured["cleanup"] = True

    monkeypatch.setattr("mini_agent.cli_interactive.Config.load", lambda: object())
    monkeypatch.setattr(
        "mini_agent.ops.doctor.run_startup_self_check",
        lambda config, workspace: (True, []),
    )
    monkeypatch.setattr(
        "mini_agent.ops.doctor.format_doctor_report",
        lambda findings, title: "doctor-ok",
    )
    monkeypatch.setattr("mini_agent.cli_interactive.PromptSession", _FakePromptSession)
    monkeypatch.setattr("mini_agent.cli_interactive.build_agent", _fake_build_agent)
    monkeypatch.setattr("mini_agent.cli_interactive.build_agent_kernel", _fake_build_agent_kernel)
    monkeypatch.setattr("mini_agent.cli_interactive.create_submission_loop_for_agent", _fake_create_loop)
    monkeypatch.setattr("mini_agent.cli_interactive._cli_model_registry", lambda: [
        {
            "source": "preset",
            "provider_id": "openai",
            "provider_name": "OpenAI",
            "default_model_id": "gpt-5.4",
            "models": [
                {"model_id": "gpt-5.4", "display_name": "GPT-5.4"},
            ],
        },
        {
            "source": "custom",
            "provider_id": "maas",
            "provider_name": "MaaS",
            "default_model_id": "astron-code-latest",
            "models": [
                {"model_id": "astron-code-latest", "display_name": "GLM-5/K2.5"},
            ],
        },
    ])
    monkeypatch.setattr("mini_agent.cli_interactive.cleanup_mcp_connections", _fake_cleanup)

    asyncio.run(
        cli_interactive.run_interactive_session(
            workspace=tmp_path,
            approval_profile=None,
        )
    )

    output = capsys.readouterr().out
    assert "openai/gpt-5.4" in output
    assert "Available models:" in output
    assert "Switched session model to maas/astron-code-latest" in output
    assert "maas/astron-code-latest" in output
    assert len(loops) == 2
    assert loops[0].stop_called is True
    assert loops[1].stop_called is True
    assert captured["cleanup"] is True


def test_run_interactive_session_routes_mcp_commands(monkeypatch, tmp_path: Path, capsys) -> None:
    fake_agent = _NoDirectRunAgent(model="gpt-5.4")
    fake_agent.runtime_route = SimpleNamespace(model="gpt-5.4", provider_id="preset-openai")
    replacement_agent = _NoDirectRunAgent(model="gpt-5.4")
    replacement_agent.runtime_route = SimpleNamespace(model="gpt-5.4", provider_id="preset-openai")
    loops: list[_FakeLoop] = []
    captured: dict[str, object] = {"cleanup_calls": 0}
    snapshots = iter(
        [
            SimpleNamespace(active_total=1, tool_total=2, configured_total=1),
            SimpleNamespace(active_total=1, tool_total=2, configured_total=1),
            SimpleNamespace(active_total=0, tool_total=0, configured_total=1),
            SimpleNamespace(active_total=2, tool_total=4, configured_total=3),
        ]
    )

    class _FakePromptSession:
        def __init__(self, *args, **kwargs) -> None:  # noqa: ANN002, ANN003
            _ = (args, kwargs)
            self._inputs = iter(
                [
                    "/mcp status",
                    "/mcp list",
                    "/mcp reload",
                    "/exit",
                ]
            )

        async def prompt_async(self, *args, **kwargs):  # noqa: ANN002, ANN003
            _ = (args, kwargs)
            return next(self._inputs)

    async def _fake_build_agent(_workspace: Path, approval_profile: str | None = None):
        _ = approval_profile
        return fake_agent

    async def _fake_build_agent_kernel(*, workspace_dir: Path, options) -> _NoDirectRunAgent:  # noqa: ANN001
        assert workspace_dir == tmp_path
        assert options.requested_provider_source == "preset"
        assert options.requested_provider_id == "openai"
        assert options.requested_model == "gpt-5.4"
        return replacement_agent

    async def _fake_create_loop(*, agent, session_id: str, hooks=None):
        _ = (agent, session_id, hooks)
        loop = _FakeLoop()
        loops.append(loop)
        return loop, object()

    async def _fake_cleanup() -> None:
        captured["cleanup_calls"] = int(captured["cleanup_calls"]) + 1

    monkeypatch.setattr("mini_agent.cli_interactive.Config.load", lambda: object())
    monkeypatch.setattr(
        "mini_agent.ops.doctor.run_startup_self_check",
        lambda config, workspace: (True, []),
    )
    monkeypatch.setattr(
        "mini_agent.ops.doctor.format_doctor_report",
        lambda findings, title: "doctor-ok",
    )
    monkeypatch.setattr("mini_agent.cli_interactive.PromptSession", _FakePromptSession)
    monkeypatch.setattr("mini_agent.cli_interactive.build_agent", _fake_build_agent)
    monkeypatch.setattr("mini_agent.cli_interactive.build_agent_kernel", _fake_build_agent_kernel)
    monkeypatch.setattr("mini_agent.cli_interactive.create_submission_loop_for_agent", _fake_create_loop)
    monkeypatch.setattr(
        "mini_agent.cli_interactive.collect_mcp_operator_snapshot",
        lambda config: next(snapshots),
    )
    monkeypatch.setattr(
        "mini_agent.cli_interactive.format_mcp_status",
        lambda snapshot: f"MCP Status: active={snapshot.active_total} tools={snapshot.tool_total}",
    )
    monkeypatch.setattr(
        "mini_agent.cli_interactive.format_mcp_server_list",
        lambda snapshot: f"MCP Servers: configured={snapshot.configured_total}",
    )
    monkeypatch.setattr("mini_agent.cli_interactive.cleanup_mcp_connections", _fake_cleanup)

    asyncio.run(
        cli_interactive.run_interactive_session(
            workspace=tmp_path,
            approval_profile=None,
        )
    )

    output = capsys.readouterr().out
    assert "MCP Status: active=1 tools=2" in output
    assert "MCP Servers: configured=1" in output
    assert "Reloaded MCP bindings; current CLI agent reloaded on openai/gpt-5.4" in output
    assert "MCP Status: active=2 tools=4" in output
    assert "MCP Servers: configured=3" in output
    assert len(loops) == 2
    assert loops[0].stop_called is True
    assert loops[1].stop_called is True
    assert captured["cleanup_calls"] == 2


def test_run_interactive_session_routes_sandbox_status(monkeypatch, tmp_path: Path, capsys) -> None:
    fake_agent = _NoDirectRunAgent(model="gpt-cli")
    fake_agent.sandbox_manager = SimpleNamespace(
        select_initial=lambda: SimpleNamespace(
            backend="windows_restricted_token",
            reason="windows_workspace_sandbox",
            metadata={
                "backend": "windows_restricted_token",
                "sandbox_mode": "workspace",
                "workspace_root": str(tmp_path),
                "network_mode": "allow_all",
                "restricted_token": True,
                "low_integrity": True,
                "mandatory_policy": 3,
                "disable_admin_groups": True,
                "restrict_ui": True,
                "die_on_unhandled_exception": True,
            },
        ),
        network_policy=SimpleNamespace(
            mode=SimpleNamespace(value="allow_all"),
            allow_domains=(),
            block_domains=(),
        ),
    )
    fake_agent.runtime_policy_engine = SimpleNamespace(
        policy=SimpleNamespace(
            approval_profile="build",
            access_level="default",
            sandbox_mode="workspace",
        )
    )
    fake_loop = _FakeLoop()
    captured: dict[str, object] = {"cleanup": False}

    class _FakePromptSession:
        def __init__(self, *args, **kwargs) -> None:  # noqa: ANN002, ANN003
            _ = (args, kwargs)
            self._inputs = iter(
                [
                    "/sandbox status",
                    "/exit",
                ]
            )

        async def prompt_async(self, *args, **kwargs):  # noqa: ANN002, ANN003
            _ = (args, kwargs)
            return next(self._inputs)

    async def _fake_build_agent(_workspace: Path, approval_profile: str | None = None):
        _ = approval_profile
        return fake_agent

    async def _fake_create_loop(*, agent, session_id: str, hooks=None):
        _ = (agent, session_id, hooks)
        return fake_loop, object()

    async def _fake_cleanup() -> None:
        captured["cleanup"] = True

    monkeypatch.setattr("mini_agent.cli_interactive.Config.load", lambda: object())
    monkeypatch.setattr(
        "mini_agent.ops.doctor.run_startup_self_check",
        lambda config, workspace: (True, []),
    )
    monkeypatch.setattr(
        "mini_agent.ops.doctor.format_doctor_report",
        lambda findings, title: "doctor-ok",
    )
    monkeypatch.setattr("mini_agent.cli_interactive.PromptSession", _FakePromptSession)
    monkeypatch.setattr("mini_agent.cli_interactive.build_agent", _fake_build_agent)
    monkeypatch.setattr("mini_agent.cli_interactive.create_submission_loop_for_agent", _fake_create_loop)
    monkeypatch.setattr("mini_agent.cli_interactive.cleanup_mcp_connections", _fake_cleanup)

    asyncio.run(
        cli_interactive.run_interactive_session(
            workspace=tmp_path,
            approval_profile=None,
        )
    )

    output = capsys.readouterr().out
    assert "Sandbox Status" in output
    assert "- backend: windows_restricted_token" in output
    assert "- integrity: low" in output
    assert fake_loop.stop_called is True
    assert captured["cleanup"] is True


def test_run_minimal_workflow_via_submission_loop(monkeypatch) -> None:
    fake_agent = _NoDirectRunAgent(model="gpt-cli")
    fake_loop = object()
    fake_bus = object()
    stage_calls: list[str] = []

    stage_payloads = {
        "research": {"state": "completed", "stop_reason": "end_turn", "message": "research ok", "error": ""},
        "implementation": {
            "state": "completed",
            "stop_reason": "end_turn",
            "message": "implementation ok",
            "error": "",
        },
        "verification": {
            "state": "completed",
            "stop_reason": "end_turn",
            "message": "verification ok",
            "error": "",
        },
    }

    async def _fake_run_prompt(
        *,
        loop,
        bus,
        agent,
        prompt: str,
        metadata=None,
        start_new_run: bool = True,
        approval_resolver=None,
        event_handler=None,
    ):
        _ = loop
        _ = bus
        _ = agent
        _ = prompt
        _ = start_new_run
        _ = approval_resolver
        _ = event_handler
        stage = str((metadata or {}).get("stage", ""))
        stage_calls.append(stage)
        return stage_payloads[stage]

    monkeypatch.setattr("mini_agent.cli_interactive.run_prompt_via_submission_loop", _fake_run_prompt)

    report = asyncio.run(
        cli_interactive.run_minimal_workflow_via_submission_loop(
            agent=fake_agent,
            loop=fake_loop,  # type: ignore[arg-type]
            bus=fake_bus,  # type: ignore[arg-type]
            objective="finish P22.5",
            surface="cli",
        )
    )

    assert stage_calls == ["research", "implementation", "verification"]
    assert "Minimal Workflow Report" in report
    assert "Status: completed" in report
    assert "verification ok" in report


def test_run_prompt_via_submission_loop_resolves_approval_with_callback(tmp_path: Path) -> None:
    async def _scenario() -> None:
        agent = Agent(
            llm_client=_SequenceLLM(
                [
                    LLMResponse(
                        content="tool",
                        thinking=None,
                        tool_calls=[
                            ToolCall(
                                id="tool-1",
                                type="function",
                                function=FunctionCall(name="echo", arguments={"text": "hello"}),
                            )
                        ],
                        finish_reason="tool_calls",
                    ),
                    LLMResponse(content="done", thinking=None, tool_calls=None, finish_reason="stop"),
                ]
            ),
            system_prompt="system",
            tools=[_EchoTool()],
            max_steps=3,
            workspace_dir=str(tmp_path / "workspace"),
            logger=AgentLogger(log_dir=tmp_path / "logs"),
            console_output=False,
            approval_engine=ApprovalEngine(PermissionPolicy.strict_policy()),
        )
        bus = InMemoryLoopMessageBus()
        loop = AgentSubmissionLoop(
            context=AgentLoopContext(message_bus=bus, session_id="cli-approval"),
            agent_factory=lambda _ctx: agent,
        )
        await loop.start()
        try:
            payload = await cli_interactive.run_prompt_via_submission_loop(
                loop=loop,
                bus=bus,
                agent=agent,
                prompt="hello",
                metadata={"surface": "cli", "mode": "interactive"},
                start_new_run=True,
                approval_resolver=lambda approval_payload: approval_payload.get("tool_name") == "echo",
            )
        finally:
            await loop.stop()

        assert payload["state"] == "completed"
        assert payload["stop_reason"] == "end_turn"
        assert payload["message"] == "done"

    asyncio.run(_scenario())


def test_run_prompt_via_submission_loop_auto_denies_without_callback(tmp_path: Path) -> None:
    async def _scenario() -> None:
        agent = Agent(
            llm_client=_SequenceLLM(
                [
                    LLMResponse(
                        content="tool",
                        thinking=None,
                        tool_calls=[
                            ToolCall(
                                id="tool-1",
                                type="function",
                                function=FunctionCall(name="echo", arguments={"text": "hello"}),
                            )
                        ],
                        finish_reason="tool_calls",
                    ),
                    LLMResponse(content="done-after-deny", thinking=None, tool_calls=None, finish_reason="stop"),
                ]
            ),
            system_prompt="system",
            tools=[_EchoTool()],
            max_steps=3,
            workspace_dir=str(tmp_path / "workspace-deny"),
            logger=AgentLogger(log_dir=tmp_path / "logs-deny"),
            console_output=False,
            approval_engine=ApprovalEngine(PermissionPolicy.strict_policy()),
        )
        bus = InMemoryLoopMessageBus()
        loop = AgentSubmissionLoop(
            context=AgentLoopContext(message_bus=bus, session_id="cli-deny"),
            agent_factory=lambda _ctx: agent,
        )
        await loop.start()
        try:
            payload = await cli_interactive.run_prompt_via_submission_loop(
                loop=loop,
                bus=bus,
                agent=agent,
                prompt="hello",
                metadata={"surface": "headless", "mode": "single_prompt"},
                start_new_run=True,
            )
        finally:
            await loop.stop()

        assert payload["state"] == "completed"
        assert payload["stop_reason"] == "end_turn"
        assert payload["message"] == "done-after-deny"
        assert any(event["event_type"] == "loop.approval.requested" for event in bus.events)
        assert any(event["event_type"] == "loop.exec_approval" for event in bus.events)

    asyncio.run(_scenario())


def test_run_prompt_via_submission_loop_collects_activity_report(tmp_path: Path) -> None:
    async def _scenario() -> None:
        agent = Agent(
            llm_client=_SequenceLLM(
                [
                    LLMResponse(
                        content="tool",
                        thinking=None,
                        tool_calls=[
                            ToolCall(
                                id="tool-1",
                                type="function",
                                function=FunctionCall(name="echo", arguments={"text": "hello cli"}),
                            )
                        ],
                        finish_reason="tool_calls",
                    ),
                    LLMResponse(content="done", thinking=None, tool_calls=None, finish_reason="stop"),
                ]
            ),
            system_prompt="system",
            tools=[_EchoTool()],
            max_steps=3,
            workspace_dir=str(tmp_path / "workspace-activity"),
            logger=AgentLogger(log_dir=tmp_path / "logs-activity"),
            console_output=False,
        )
        bus = InMemoryLoopMessageBus()
        loop = AgentSubmissionLoop(
            context=AgentLoopContext(message_bus=bus, session_id="cli-activity"),
            agent_factory=lambda _ctx: agent,
        )
        observed_events: list[tuple[str, dict[str, object]]] = []

        async def _event_handler(event_type: str, payload: dict[str, object]) -> None:
            observed_events.append((event_type, dict(payload)))

        await loop.start()
        try:
            payload = await cli_interactive.run_prompt_via_submission_loop(
                loop=loop,
                bus=bus,
                agent=agent,
                prompt="show activity",
                metadata={"surface": "cli", "mode": "interactive"},
                start_new_run=True,
                event_handler=_event_handler,
            )
        finally:
            await loop.stop()

        assert payload["state"] == "completed"
        assert payload["message"] == "done"
        assert payload["running_state"] == "step 2: preparing final response"
        assert payload["last_tool_activity_summary"] == "echo | ok | hello cli | echo:hello cli"
        assert payload["last_tool_activity"]["preview"] == "hello cli"
        assert any(event_type == "loop.activity" for event_type, _ in observed_events)
        assert any(item["label"] == "echo" and item["state"] == "ok" for item in payload["activity_items"])

    asyncio.run(_scenario())


def test_print_submission_runtime_event_renders_prepared_context(capsys) -> None:
    cli_interactive._print_submission_runtime_event(
        "loop.turn.completed",
        {
            "prepared_context": {
                "item_count": 2,
                "sources": ["workspace_memory", "knowledge_base"],
                "items": [
                    {
                        "source": "workspace_memory",
                        "title": "Relevant workspace memory",
                        "preview": "API keys load from env first, then .env.local.",
                        "metadata": {
                            "ranking_score": 0.71234,
                            "ranking_basis": "workspace_memory_text_match",
                            "ranking_score_raw": 5.75,
                        },
                    },
                    {
                        "source": "knowledge_base",
                        "title": "Relevant knowledge base context",
                        "preview": "Hybrid retrieval combines BM25 and RRF.",
                        "metadata": {
                            "ranking_score": 0.88123,
                            "ranking_basis": "knowledge_base_rrf",
                            "ranking_score_raw": 0.02941,
                        },
                    },
                ],
                "provider_statuses": [
                    {
                        "provider": "workspace_memory",
                        "status": "used",
                        "item_count": 1,
                        "reason": "2 note(s) available",
                    },
                    {
                        "provider": "mcp_catalog",
                        "status": "filtered",
                        "item_count": 0,
                        "reason": "excluded by prepared-context policy",
                    },
                ],
                "policy": {
                    "exclude_sources": ["mcp_catalog"],
                    "max_items": 2,
                    "max_items_per_source": 1,
                    "max_total_chars": 1200,
                },
                "provider_failures": [
                    {
                        "provider": "broken_provider",
                        "error": "RuntimeError: synthetic failure",
                    }
                ],
            }
        },
    )

    output = capsys.readouterr().out
    assert "[context]" in output
    assert "prepared 2 item(s) from workspace_memory, knowledge_base | 1 provider failure(s)" in output
    assert "Policy: exclude=mcp_catalog | budget=2 item(s)/1200 chars/1 per-source" in output
    assert "- mcp_catalog: filtered | excluded by prepared-context policy" in output
    assert "[workspace_memory] Relevant workspace memory -> API keys load from env first, then .env.local." in output
    assert "ranking: basis workspace_memory_text_match | raw 5.7500 | item-relevance 0.712" in output
    assert "selection: provider-weight 0.800 | priority 80 | final-selection 1.512" in output
    assert "ranking: basis knowledge_base_rrf | raw 0.0294 | item-relevance 0.881" in output
    assert "selection: provider-weight 1.000 | priority 100 | final-selection 1.881" in output
    assert "- broken_provider: RuntimeError: synthetic failure" in output


def test_run_interactive_session_context_show_brief_uses_compact_detail_mode(
    monkeypatch,
    tmp_path: Path,
    capsys,
) -> None:
    fake_agent = _NoDirectRunAgent(model="gpt-cli")
    fake_agent.last_prepared_turn_context = {
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
            }
        ],
        "provider_failures": [],
    }
    bus = InMemoryLoopMessageBus()
    fake_loop = _FakeLoop()

    class _FakePromptSession:
        def __init__(self, *args, **kwargs) -> None:  # noqa: ANN002, ANN003
            _ = (args, kwargs)
            self._inputs = iter(
                [
                    "/context show brief",
                    "/exit",
                ]
            )

        async def prompt_async(self, *args, **kwargs):  # noqa: ANN002, ANN003
            _ = (args, kwargs)
            return next(self._inputs)

    async def _fake_build_agent(_workspace: Path, approval_profile: str | None = None):
        _ = approval_profile
        return fake_agent

    async def _fake_create_loop(*, agent, session_id: str, hooks=None):
        _ = (agent, session_id, hooks)
        return fake_loop, bus

    async def _fake_cleanup() -> None:
        return None

    monkeypatch.setattr("mini_agent.cli_interactive.Config.load", lambda: object())
    monkeypatch.setattr(
        "mini_agent.ops.doctor.run_startup_self_check",
        lambda config, workspace: (True, []),
    )
    monkeypatch.setattr(
        "mini_agent.ops.doctor.format_doctor_report",
        lambda findings, title: "doctor-ok",
    )
    monkeypatch.setattr("mini_agent.cli_interactive.PromptSession", _FakePromptSession)
    monkeypatch.setattr("mini_agent.cli_interactive.build_agent", _fake_build_agent)
    monkeypatch.setattr("mini_agent.cli_interactive.create_submission_loop_for_agent", _fake_create_loop)
    monkeypatch.setattr("mini_agent.cli_interactive.cleanup_mcp_connections", _fake_cleanup)

    asyncio.run(
        cli_interactive.run_interactive_session(
            workspace=tmp_path,
            approval_profile=None,
        )
    )

    output = capsys.readouterr().out
    assert "Relevant knowledge base context -> Hybrid retrieval combines BM25 and RRF." in output
    assert "ranking:" not in output
    assert "Providers:" not in output


def test_run_interactive_session_context_stats_renders_diagnostics(
    monkeypatch,
    tmp_path: Path,
    capsys,
) -> None:
    fake_agent = _NoDirectRunAgent(model="gpt-cli")
    fake_agent.prepared_context_diagnostics = {
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
        "last_sources": [],
        "last_item_count": 0,
    }
    bus = InMemoryLoopMessageBus()
    fake_loop = _FakeLoop()

    class _FakePromptSession:
        def __init__(self, *args, **kwargs) -> None:  # noqa: ANN002, ANN003
            _ = (args, kwargs)
            self._inputs = iter(["/context stats", "/exit"])

        async def prompt_async(self, *args, **kwargs):  # noqa: ANN002, ANN003
            _ = (args, kwargs)
            return next(self._inputs)

    async def _fake_build_agent(_workspace: Path, approval_profile: str | None = None):
        _ = approval_profile
        return fake_agent

    async def _fake_create_loop(*, agent, session_id: str, hooks=None):
        _ = (agent, session_id, hooks)
        return fake_loop, bus

    async def _fake_cleanup() -> None:
        return None

    monkeypatch.setattr("mini_agent.cli_interactive.Config.load", lambda: object())
    monkeypatch.setattr(
        "mini_agent.ops.doctor.run_startup_self_check",
        lambda config, workspace: (True, []),
    )
    monkeypatch.setattr(
        "mini_agent.ops.doctor.format_doctor_report",
        lambda findings, title: "doctor-ok",
    )
    monkeypatch.setattr("mini_agent.cli_interactive.PromptSession", _FakePromptSession)
    monkeypatch.setattr("mini_agent.cli_interactive.build_agent", _fake_build_agent)
    monkeypatch.setattr("mini_agent.cli_interactive.create_submission_loop_for_agent", _fake_create_loop)
    monkeypatch.setattr("mini_agent.cli_interactive.cleanup_mcp_connections", _fake_cleanup)

    asyncio.run(
        cli_interactive.run_interactive_session(
            workspace=tmp_path,
            approval_profile=None,
        )
    )

    output = capsys.readouterr().out
    assert "Context diagnostics: 2 turn(s) | 1 with context | 1 item(s) | curated 1 | dropped 1" in output
    assert "- knowledge_base: 1 turn(s) | 1 item(s)" in output
    assert "- knowledge_base: no_match 1, used 1" in output


def test_run_interactive_session_memory_show_brief_renders_memory_diagnostics(
    monkeypatch,
    tmp_path: Path,
    capsys,
) -> None:
    fake_agent = _NoDirectRunAgent(model="gpt-cli")
    monkeypatch.setenv("MINI_AGENT_GLOBAL_MEMORY_ROOT", str((tmp_path / "global").resolve()))
    monkeypatch.setattr("mini_agent.memory.memoria_runtime.Path.home", classmethod(lambda cls: tmp_path))

    class _FakePromptSession:
        def __init__(self, *args, **kwargs) -> None:  # noqa: ANN002, ANN003
            _ = (args, kwargs)
            self._inputs = iter(["/memory show brief", "/exit"])

        async def prompt_async(self, *args, **kwargs):  # noqa: ANN002, ANN003
            _ = (args, kwargs)
            return next(self._inputs)

    async def _fake_build_agent(_workspace: Path, approval_profile: str | None = None):
        _ = approval_profile
        return fake_agent

    async def _fake_create_loop(*, agent, session_id: str, hooks=None):
        _ = (agent, session_id, hooks)
        return _FakeLoop(), InMemoryLoopMessageBus()

    async def _fake_cleanup() -> None:
        return None

    monkeypatch.setattr("mini_agent.cli_interactive.Config.load", lambda: object())
    monkeypatch.setattr(
        "mini_agent.ops.doctor.run_startup_self_check",
        lambda config, workspace: (True, []),
    )
    monkeypatch.setattr(
        "mini_agent.ops.doctor.format_doctor_report",
        lambda findings, title: "doctor-ok",
    )
    monkeypatch.setattr("mini_agent.cli_interactive.PromptSession", _FakePromptSession)
    monkeypatch.setattr("mini_agent.cli_interactive.build_agent", _fake_build_agent)
    monkeypatch.setattr("mini_agent.cli_interactive.create_submission_loop_for_agent", _fake_create_loop)
    monkeypatch.setattr("mini_agent.cli_interactive.cleanup_mcp_connections", _fake_cleanup)

    asyncio.run(
        cli_interactive.run_interactive_session(
            workspace=tmp_path,
            approval_profile=None,
        )
    )

    output = capsys.readouterr().out
    assert "Memory Diagnostics" in output
    assert "Consolidated" in output
    assert "Runtime Task Memory" in output


def test_run_interactive_session_durable_memory_commands(
    monkeypatch,
    tmp_path: Path,
    capsys,
) -> None:
    fake_agent = _NoDirectRunAgent(model="gpt-cli")
    monkeypatch.setenv("MINI_AGENT_GLOBAL_MEMORY_ROOT", str((tmp_path / "global").resolve()))
    monkeypatch.setattr("mini_agent.memory.memoria_runtime.Path.home", classmethod(lambda cls: tmp_path))

    memory = MemoryService(tmp_path)
    memory.add_profile_fact(fact="User prefers concise Chinese replies during debugging")
    memory.append_note(
        content="routing decisions should stay in workspace durable notes",
        category="operator_note",
        scope="long_term",
        now=datetime(2026, 4, 10, tzinfo=timezone.utc),
    )
    memory.append_note(
        content="daily durable note for CLI memory daily command",
        category="daily_note",
        scope="daily",
        now=datetime(2026, 4, 10, tzinfo=timezone.utc),
    )

    class _FakePromptSession:
        def __init__(self, *args, **kwargs) -> None:  # noqa: ANN002, ANN003
            _ = (args, kwargs)
            self._inputs = iter(
                [
                    "/memory profile Chinese replies",
                    "/memory notes routing",
                    "/memory daily 2026-04-10",
                    "/exit",
                ]
            )

        async def prompt_async(self, *args, **kwargs):  # noqa: ANN002, ANN003
            _ = (args, kwargs)
            return next(self._inputs)

    async def _fake_build_agent(_workspace: Path, approval_profile: str | None = None):
        _ = approval_profile
        return fake_agent

    async def _fake_create_loop(*, agent, session_id: str, hooks=None):
        _ = (agent, session_id, hooks)
        return _FakeLoop(), InMemoryLoopMessageBus()

    async def _fake_cleanup() -> None:
        return None

    monkeypatch.setattr("mini_agent.cli_interactive.Config.load", lambda: object())
    monkeypatch.setattr(
        "mini_agent.ops.doctor.run_startup_self_check",
        lambda config, workspace: (True, []),
    )
    monkeypatch.setattr(
        "mini_agent.ops.doctor.format_doctor_report",
        lambda findings, title: "doctor-ok",
    )
    monkeypatch.setattr("mini_agent.cli_interactive.PromptSession", _FakePromptSession)
    monkeypatch.setattr("mini_agent.cli_interactive.build_agent", _fake_build_agent)
    monkeypatch.setattr("mini_agent.cli_interactive.create_submission_loop_for_agent", _fake_create_loop)
    monkeypatch.setattr("mini_agent.cli_interactive.cleanup_mcp_connections", _fake_cleanup)

    asyncio.run(
        cli_interactive.run_interactive_session(
            workspace=tmp_path,
            approval_profile=None,
        )
    )

    output = capsys.readouterr().out
    assert "Global Profile Memory" in output
    assert "User prefers concise Chinese replies during debugging" in output
    assert "Workspace Durable Notes" in output
    assert "routing decisions should stay in workspace durable notes" in output
    assert "Workspace Daily Memory" in output
    assert "daily durable note for CLI memory daily command" in output


def test_run_interactive_session_consolidated_memory_commands(
    monkeypatch,
    tmp_path: Path,
    capsys,
) -> None:
    fake_agent = _NoDirectRunAgent(model="gpt-cli")
    monkeypatch.setenv("MINI_AGENT_GLOBAL_MEMORY_ROOT", str((tmp_path / "global").resolve()))
    monkeypatch.setattr("mini_agent.memory.memoria_runtime.Path.home", classmethod(lambda cls: tmp_path))

    _write_consolidated_memory(
        tmp_path / "MEMORY.md",
        items=[
            "restart recovery should preserve approval hints",
            "routing guardrails remain workspace scoped",
        ],
        last_updated_utc="2026-04-10T00:00:00+00:00",
    )

    class _FakePromptSession:
        def __init__(self, *args, **kwargs) -> None:  # noqa: ANN002, ANN003
            _ = (args, kwargs)
            self._inputs = iter(
                [
                    "/memory consolidated",
                    "/memory consolidated search routing",
                    "/exit",
                ]
            )

        async def prompt_async(self, *args, **kwargs):  # noqa: ANN002, ANN003
            _ = (args, kwargs)
            return next(self._inputs)

    async def _fake_build_agent(_workspace: Path, approval_profile: str | None = None):
        _ = approval_profile
        return fake_agent

    async def _fake_create_loop(*, agent, session_id: str, hooks=None):
        _ = (agent, session_id, hooks)
        return _FakeLoop(), InMemoryLoopMessageBus()

    async def _fake_cleanup() -> None:
        return None

    monkeypatch.setattr("mini_agent.cli_interactive.Config.load", lambda: object())
    monkeypatch.setattr(
        "mini_agent.ops.doctor.run_startup_self_check",
        lambda config, workspace: (True, []),
    )
    monkeypatch.setattr(
        "mini_agent.ops.doctor.format_doctor_report",
        lambda findings, title: "doctor-ok",
    )
    monkeypatch.setattr("mini_agent.cli_interactive.PromptSession", _FakePromptSession)
    monkeypatch.setattr("mini_agent.cli_interactive.build_agent", _fake_build_agent)
    monkeypatch.setattr("mini_agent.cli_interactive.create_submission_loop_for_agent", _fake_create_loop)
    monkeypatch.setattr("mini_agent.cli_interactive.cleanup_mcp_connections", _fake_cleanup)

    asyncio.run(
        cli_interactive.run_interactive_session(
            workspace=tmp_path,
            approval_profile=None,
        )
    )

    output = capsys.readouterr().out
    assert "Consolidated Memory" in output
    assert "restart recovery should preserve approval hints" in output
    assert "Consolidated Memory Search" in output
    assert "routing guardrails remain workspace scoped" in output


def test_run_interactive_session_memory_overview_and_export_commands(
    monkeypatch,
    tmp_path: Path,
    capsys,
) -> None:
    fake_agent = _NoDirectRunAgent(model="gpt-cli")
    monkeypatch.setenv("MINI_AGENT_GLOBAL_MEMORY_ROOT", str((tmp_path / "global").resolve()))
    monkeypatch.setattr("mini_agent.memory.memoria_runtime.Path.home", classmethod(lambda cls: tmp_path))

    memory = MemoryService(tmp_path)
    memory.add_profile_fact(fact="User prefers concise Chinese replies during debugging")
    _write_consolidated_memory(
        tmp_path / "MEMORY.md",
        items=["restart recovery should preserve approval hints"],
        last_updated_utc="2026-04-10T00:00:00+00:00",
    )
    memory.append_note(
        content="remembered workspace note for CLI memory export",
        category="operator_note",
        scope="long_term",
        now=datetime(2026, 4, 10, tzinfo=timezone.utc),
    )

    class _FakePromptSession:
        def __init__(self, *args, **kwargs) -> None:  # noqa: ANN002, ANN003
            _ = (args, kwargs)
            self._inputs = iter(
                [
                    "/memory overview",
                    "/memory export markdown",
                    "/exit",
                ]
            )

        async def prompt_async(self, *args, **kwargs):  # noqa: ANN002, ANN003
            _ = (args, kwargs)
            return next(self._inputs)

    async def _fake_build_agent(_workspace: Path, approval_profile: str | None = None):
        _ = approval_profile
        return fake_agent

    async def _fake_create_loop(*, agent, session_id: str, hooks=None):
        _ = (agent, session_id, hooks)
        return _FakeLoop(), InMemoryLoopMessageBus()

    async def _fake_cleanup() -> None:
        return None

    monkeypatch.setattr("mini_agent.cli_interactive.Config.load", lambda: object())
    monkeypatch.setattr(
        "mini_agent.ops.doctor.run_startup_self_check",
        lambda config, workspace: (True, []),
    )
    monkeypatch.setattr(
        "mini_agent.ops.doctor.format_doctor_report",
        lambda findings, title: "doctor-ok",
    )
    monkeypatch.setattr("mini_agent.cli_interactive.PromptSession", _FakePromptSession)
    monkeypatch.setattr("mini_agent.cli_interactive.build_agent", _fake_build_agent)
    monkeypatch.setattr("mini_agent.cli_interactive.create_submission_loop_for_agent", _fake_create_loop)
    monkeypatch.setattr("mini_agent.cli_interactive.cleanup_mcp_connections", _fake_cleanup)

    asyncio.run(
        cli_interactive.run_interactive_session(
            workspace=tmp_path,
            approval_profile=None,
        )
    )

    output = capsys.readouterr().out
    assert "Memory Overview" in output
    assert "Session Context" in output
    assert "session id: cli-session" in output
    assert "Durable Memory" in output
    assert "Consolidated Memory" in output
    assert "Memory Export" in output
    assert "Format: markdown" in output
    assert "remembered workspace note for CLI memory export" in output


def test_run_interactive_session_clear_clears_runtime_task_memory(
    monkeypatch,
    tmp_path: Path,
    capsys,
) -> None:
    fake_agent = _NoDirectRunAgent(model="gpt-cli")
    fake_agent.api_total_tokens = 77
    fake_agent.last_prepared_turn_context = {"item_count": 1}
    fake_agent.prepared_context_diagnostics = {"turn_count": 2}
    monkeypatch.setattr("mini_agent.memory.memoria_runtime.Path.home", classmethod(lambda cls: tmp_path))

    from mini_agent.memory.memoria_runtime import WorkspaceMemoriaRuntime

    runtime = WorkspaceMemoriaRuntime(tmp_path)
    runtime.save_session_memory(
        "cli-session",
        content="CLI runtime memory should be cleared by /clear",
    )

    class _FakePromptSession:
        def __init__(self, *args, **kwargs) -> None:  # noqa: ANN002, ANN003
            _ = (args, kwargs)
            self._inputs = iter(["/clear", "/exit"])

        async def prompt_async(self, *args, **kwargs):  # noqa: ANN002, ANN003
            _ = (args, kwargs)
            return next(self._inputs)

    async def _fake_build_agent(_workspace: Path, approval_profile: str | None = None):
        _ = approval_profile
        return fake_agent

    async def _fake_create_loop(*, agent, session_id: str, hooks=None):
        _ = (agent, session_id, hooks)
        return _FakeLoop(), InMemoryLoopMessageBus()

    async def _fake_cleanup() -> None:
        return None

    monkeypatch.setattr("mini_agent.cli_interactive.Config.load", lambda: object())
    monkeypatch.setattr(
        "mini_agent.ops.doctor.run_startup_self_check",
        lambda config, workspace: (True, []),
    )
    monkeypatch.setattr(
        "mini_agent.ops.doctor.format_doctor_report",
        lambda findings, title: "doctor-ok",
    )
    monkeypatch.setattr("mini_agent.cli_interactive.PromptSession", _FakePromptSession)
    monkeypatch.setattr("mini_agent.cli_interactive.build_agent", _fake_build_agent)
    monkeypatch.setattr("mini_agent.cli_interactive.create_submission_loop_for_agent", _fake_create_loop)
    monkeypatch.setattr("mini_agent.cli_interactive.cleanup_mcp_connections", _fake_cleanup)

    asyncio.run(
        cli_interactive.run_interactive_session(
            workspace=tmp_path,
            approval_profile=None,
        )
    )

    output = capsys.readouterr().out
    assert "[OK] Cleared" in output
    assert fake_agent.api_total_tokens == 0
    assert fake_agent.prepared_context_diagnostics == {}
    assert "session:cli-session" not in runtime.stats()["namespaces"]


def test_run_interactive_session_memory_promote_and_save_commands(
    monkeypatch,
    tmp_path: Path,
    capsys,
) -> None:
    fake_agent = _NoDirectRunAgent(model="gpt-cli")
    fake_agent.last_prepared_turn_context = {"sources": ["knowledge_base"]}
    monkeypatch.setenv("MINI_AGENT_GLOBAL_MEMORY_ROOT", str((tmp_path / "global").resolve()))
    monkeypatch.setattr("mini_agent.memory.memoria_runtime.Path.home", classmethod(lambda cls: tmp_path))

    from mini_agent.memory.memoria_runtime import WorkspaceMemoriaRuntime

    runtime = WorkspaceMemoriaRuntime(tmp_path)
    runtime.save_session_memory(
        "cli-session",
        content="workspace decision: prefer session-scoped memory promotion during debugging",
        metadata={
            "knowledge_base_grounded": True,
            "knowledge_base_query": "session scoped memory promotion",
            "knowledge_base_id": "default",
            "knowledge_base_hits": 2,
            "knowledge_base_refs": ["docs/runtime-memory.md", "docs/operator-flow.md"],
            "workspace_shared_candidate": True,
            "workspace_shared_candidate_reason": "",
            "workspace_shared_candidate_text": "workspace defaults should keep session-scoped memory explicit during debugging",
        },
    )

    class _FakePromptSession:
        def __init__(self, *args, **kwargs) -> None:  # noqa: ANN002, ANN003
            _ = (args, kwargs)
            self._inputs = iter(
                [
                    "/memory list",
                    "/memory show latest",
                    "/memory promote shared 1",
                    "/memory shared list",
                    "/memory shared show latest",
                    "/memory shared clear",
                    "/memory promote note 1",
                    "/memory save profile User prefers Chinese replies during debugging",
                    "/exit",
                ]
            )

        async def prompt_async(self, *args, **kwargs):  # noqa: ANN002, ANN003
            _ = (args, kwargs)
            return next(self._inputs)

    async def _fake_build_agent(_workspace: Path, approval_profile: str | None = None):
        _ = approval_profile
        return fake_agent

    async def _fake_create_loop(*, agent, session_id: str, hooks=None):
        _ = (agent, session_id, hooks)
        return _FakeLoop(), InMemoryLoopMessageBus()

    async def _fake_cleanup() -> None:
        return None

    monkeypatch.setattr("mini_agent.cli_interactive.Config.load", lambda: object())
    monkeypatch.setattr(
        "mini_agent.ops.doctor.run_startup_self_check",
        lambda config, workspace: (True, []),
    )
    monkeypatch.setattr(
        "mini_agent.ops.doctor.format_doctor_report",
        lambda findings, title: "doctor-ok",
    )
    monkeypatch.setattr("mini_agent.cli_interactive.PromptSession", _FakePromptSession)
    monkeypatch.setattr("mini_agent.cli_interactive.build_agent", _fake_build_agent)
    monkeypatch.setattr("mini_agent.cli_interactive.create_submission_loop_for_agent", _fake_create_loop)
    monkeypatch.setattr("mini_agent.cli_interactive.cleanup_mcp_connections", _fake_cleanup)

    asyncio.run(
        cli_interactive.run_interactive_session(
            workspace=tmp_path,
            approval_profile=None,
        )
    )

    output = capsys.readouterr().out
    assert "Session Runtime Memory" in output
    assert "[KB | shared-candidate]" in output
    assert "kb: default | hits: 2 | query: session scoped memory promotion" in output
    assert "refs: docs/runtime-memory.md; docs/operator-flow.md" in output
    assert "Engram:" in output
    assert "Knowledge Base: grounded" in output
    assert "Target: workspace_shared" in output
    assert "Workspace-Shared Runtime Memory" in output
    assert "Cleared: yes" in output
    assert "Selector: 1" in output
    assert "operator profile fact saved" in output
    assert "User prefers Chinese replies during debugging" in output
