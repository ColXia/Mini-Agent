"""Tests for TUI state and command interactions."""

from __future__ import annotations

import asyncio
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from prompt_toolkit.completion import CompleteEvent
from prompt_toolkit.completion import Completion
from prompt_toolkit.document import Document
from prompt_toolkit.layout import FloatContainer, HSplit, VSplit, Window
from prompt_toolkit.layout.containers import ConditionalContainer
from prompt_toolkit.layout.margins import ScrollbarMargin
from prompt_toolkit.layout.menus import CompletionsMenu
from prompt_toolkit.keys import Keys

from mini_agent.agent import TurnStopReason
from mini_agent.code_agent import InMemoryLoopMessageBus
from mini_agent.config import AgentConfig, Config, LLMConfig, ToolsConfig
from mini_agent.runtime.session_interrupt_handler import RuntimeSessionInterruptHandler
from mini_agent.schema import LLMResponse, Message
from mini_agent.tui.app import MiniAgentTuiApp
from mini_agent.tools.base import Tool, ToolResult


class DummyRegistry:
    def __init__(self) -> None:
        self.providers: list[dict[str, Any]] = [
            {
                "source": "preset",
                "provider_id": "openai",
                "provider_name": "OpenAI",
                "default_model_id": "gpt-5.4",
                "models": [
                    {
                        "model_id": "gpt-5.4",
                        "display_name": "GPT-5.4",
                        "is_default": True,
                        "context_window": 1_050_000,
                    },
                    {
                        "model_id": "gpt-5.3",
                        "display_name": "GPT-5.3",
                        "is_default": False,
                        "context_window": 400_000,
                    },
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
                        "context_window": 200_000,
                    }
                ],
            },
        ]

    def list_registry(self) -> list[dict[str, Any]]:
        return deepcopy(self.providers)

    def select_model(self, *, source: str, provider_id: str, model_id: str) -> dict[str, Any]:
        _ = source
        for provider in self.providers:
            if provider.get("provider_id") != provider_id:
                continue
            provider["default_model_id"] = model_id
            reordered: list[dict[str, Any]] = []
            for model in provider.get("models", []):
                if isinstance(model, dict):
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

    def clear_learned_token_limit(
        self,
        *,
        source: str,
        provider_id: str,
        model_id: str | None = None,
    ) -> dict[str, Any]:
        removed_models: list[str] = []
        for provider in self.providers:
            if provider.get("source") != source or provider.get("provider_id") != provider_id:
                continue
            for model in provider.get("models", []):
                if not isinstance(model, dict):
                    continue
                if model_id and model.get("model_id") != model_id:
                    continue
                if "learned_token_limit" in model:
                    removed_models.append(str(model.get("model_id")))
                    model.pop("learned_token_limit", None)
            return {
                "provider": deepcopy(provider),
                "removed_models": removed_models,
                "removed_count": len(removed_models),
            }
        raise ValueError(f"Provider not found: {provider_id}")


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


def _new_app(
    tmp_path: Path,
    *,
    state_path: Path,
    registry: DummyRegistry | None = None,
    gateway_client: Any | None = None,
) -> MiniAgentTuiApp:
    return MiniAgentTuiApp(
        workspace=tmp_path,
        registry=registry or DummyRegistry(),
        gateway_client=gateway_client or FakeGatewayClient(profile="local"),
        state_path=state_path,
        build_ui=False,
    )


def _write_skill(skill_dir: Path, *, name: str, description: str, body: str) -> None:
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        (
            "---\n"
            f"name: {name}\n"
            f"description: {description}\n"
            "---\n"
            f"{body}\n"
        ),
        encoding="utf-8",
    )


class FakeTurnAgent:
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
        cancel_event: asyncio.Event | None = None,
        hooks: Any = None,
        turn_context: Any = None,
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


class ApprovalSequenceLLM:
    def __init__(self, responses: list[LLMResponse]) -> None:
        self._responses = responses
        self.calls = 0

    async def generate(self, messages, tools=None):  # noqa: ANN001,ARG002
        response_index = min(self.calls, len(self._responses) - 1)
        self.calls += 1
        return self._responses[response_index]


class ApprovalEchoTool(Tool):
    def __init__(self) -> None:
        self.calls: list[str] = []

    @property
    def name(self) -> str:
        return "echo"

    @property
    def description(self) -> str:
        return "Echo helper tool."

    @property
    def parameters(self) -> dict[str, Any]:
        return {"type": "object", "properties": {"text": {"type": "string"}}}

    async def execute(self, text: str) -> ToolResult:
        self.calls.append(text)
        return ToolResult(success=True, content=f"echo:{text}")


def _fake_kernel_builder():
    async def _builder(*, workspace_dir, options):
        _ = workspace_dir
        model_id = options.requested_model or "gpt-test"
        provider_source = options.requested_provider_source or "preset"
        provider_id = options.requested_provider_id or "openai"
        runtime_provider_id = (
            f"preset-{provider_id}" if provider_source == "preset" else provider_id
        )
        return SimpleNamespace(
            llm=SimpleNamespace(model=model_id),
            runtime_route=SimpleNamespace(provider_id=runtime_provider_id, model=model_id),
            messages=[Message(role="system", content="sys")],
        )

    return _builder


def test_tui_runtime_state_restore_keeps_current_session_and_ui_flags(tmp_path: Path) -> None:
    state_path = tmp_path / ".mini-agent" / "tui_sessions.json"
    gateway = FakeGatewayClient(profile="local")
    app = _new_app(tmp_path, state_path=state_path, gateway_client=gateway)

    asyncio.run(app._run_command("session rename Alpha"))
    asyncio.run(app._run_command("session new"))
    asyncio.run(app._run_command("session rename Beta"))
    app.current_session.view.activity_details_expanded = True
    app.current_session.view.command_details_expanded = True
    app._persist_session_state()

    restored = _new_app(tmp_path, state_path=state_path, gateway_client=gateway)

    assert restored.current_session.session_id == "session-2"
    assert restored.current_session.title == "Beta"
    assert restored.current_session.view.activity_details_expanded is True
    assert restored.current_session.view.command_details_expanded is True
    assert any(session.session_id == "session-1" and session.title == "Alpha" for session in restored.sessions)


def test_tui_session_grouped_state_requires_explicit_nested_access(tmp_path: Path) -> None:
    state_path = tmp_path / ".mini-agent" / "tui_sessions.json"
    app = _new_app(tmp_path, state_path=state_path)

    session = app.current_session
    session.operator.pending_skill_reload = True
    session.runtime.pending_resume_task_id = "task-42"
    session.view.chat_scroll_line = 7
    session.view.chat_follow_output = False

    session.operator.pending_skill_reload_reason = "workspace changed"
    session.runtime.active_task_id = "task-live"
    session.view.command_details_expanded = True

    assert session.operator.pending_skill_reload_reason == "workspace changed"
    assert session.runtime.active_task_id == "task-live"
    assert session.view.command_details_expanded is True
    assert session.view.chat_scroll_line == 7
    assert session.view.chat_follow_output is False
    assert session.runtime.pending_resume_task_id == "task-42"

    with pytest.raises(AttributeError):
        _ = session.pending_skill_reload


def test_tui_runtime_skill_install_routes_through_gateway_feedback(tmp_path: Path) -> None:
    state_path = tmp_path / ".mini-agent" / "tui_sessions.json"
    gateway = FakeGatewayClient(profile="local")
    app = _new_app(tmp_path, state_path=state_path, gateway_client=gateway)

    asyncio.run(app._run_command("skill install C:/skills/repo-helper"))

    assert gateway.skill_calls[-1] == {
        "session_id": "session-1",
        "action": "install",
        "skill_name": None,
        "path": "C:/skills/repo-helper",
        "query": None,
        "mode": None,
        "surface": "tui",
        "channel_type": None,
        "conversation_id": None,
        "sender_id": None,
    }
    assert app.current_session.view.messages[-1].metadata["command"] == "skill install C:/skills/repo-helper"
    assert app.current_session.view.messages[-1].metadata["summary"] == "installed repo-helper"
    assert "Installed Skill:" in app.current_session.view.messages[-1].content
    assert app.status == "Workspace skill installed."


def test_tui_runtime_session_share_and_unshare_toggle_shared_state(tmp_path: Path) -> None:
    state_path = tmp_path / ".mini-agent" / "tui_sessions.json"
    gateway = FakeGatewayClient(profile="local")
    app = _new_app(tmp_path, state_path=state_path, gateway_client=gateway)

    asyncio.run(app._run_command("session share"))

    assert gateway.get_session_detail_sync("session-1")["shared"] is True
    assert "share | shared" in app._render_sessions()
    assert app.status == "Shared Session 1 to remote surfaces."

    asyncio.run(app._run_command("session unshare"))

    assert gateway.get_session_detail_sync("session-1")["shared"] is False
    assert "share | local only" in app._render_sessions()
    assert app.status == "Unshared Session 1."


def test_tui_runtime_model_filter_and_unknown_command_suggestion(tmp_path: Path) -> None:
    state_path = tmp_path / ".mini-agent" / "tui_sessions.json"
    app = _new_app(tmp_path, state_path=state_path)

    baseline = app._render_models()
    assert "gpt-5.4" in baseline
    assert "Anthropic [P]" in baseline

    asyncio.run(app._run_command("model filter sonnet"))

    filtered = app._render_models()
    assert "Anthropic [P]" in filtered
    assert "claude-3-7-sonnet" in filtered
    assert "OpenAI [P] | default" not in filtered

    asyncio.run(app._run_command("sesion list"))

    assert "Did you mean: session?" in app.current_session.view.messages[-1].content


def test_tui_runtime_session_numeric_command_switches_current_session(tmp_path: Path) -> None:
    state_path = tmp_path / ".mini-agent" / "tui_sessions.json"
    gateway = FakeGatewayClient(profile="local")
    app = _new_app(tmp_path, state_path=state_path, gateway_client=gateway)

    asyncio.run(app._run_command("session rename Alpha"))
    asyncio.run(app._run_command("session new"))
    asyncio.run(app._run_command("session rename Beta"))

    assert app.current_session.title == "Beta"

    asyncio.run(app._run_command("session 2"))

    assert app.current_session.session_id == "session-1"
    assert app.current_session.title == "Alpha"
    assert app.status == "Switched to Alpha."


def test_tui_handle_prompt_prefers_local_runtime_when_agent_is_attached(tmp_path: Path) -> None:
    state_path = tmp_path / ".mini-agent" / "tui_sessions.json"
    gateway = FakeGatewayClient(profile="local")
    app = _new_app(tmp_path, state_path=state_path, gateway_client=gateway)
    agent = FakeTurnAgent(final_message="local turn complete")
    app.current_session.runtime.agent = agent

    async def _scenario() -> None:
        turn = asyncio.create_task(app._handle_prompt("run locally"))
        await agent.started.wait()
        await agent.ready_for_cancel.wait()
        agent.release.set()
        await turn

    asyncio.run(_scenario())

    assert gateway.chat_calls == []
    assert app.current_session.view.messages[-1].role == "assistant"
    assert app.current_session.view.messages[-1].content == "local turn complete"
    assert app.current_session.view.tasks[-1].status == "completed"


def test_tui_cancel_prefers_local_runtime_when_agent_is_attached(tmp_path: Path) -> None:
    state_path = tmp_path / ".mini-agent" / "tui_sessions.json"
    gateway = FakeGatewayClient(profile="local")
    app = _new_app(tmp_path, state_path=state_path, gateway_client=gateway)
    agent = FakeTurnAgent(final_message="should not complete")
    app.current_session.runtime.agent = agent

    async def _scenario() -> None:
        turn = asyncio.create_task(app._handle_prompt("cancel locally"))
        await agent.started.wait()
        await agent.ready_for_cancel.wait()
        cancelled = await app._request_cancel_current_turn_async(emit_system_when_idle=True)
        assert cancelled is True
        assert agent.cancel_event is not None and agent.cancel_event.is_set()
        agent.release.set()
        await turn

    asyncio.run(_scenario())

    assert gateway.cancel_calls == []
    assert app.current_session.view.tasks[-1].status == "cancelled"
    assert "Task cancelled by user." in app.current_session.view.messages[-1].content
    assert app.current_session.projection.running_state == ""
    assert app.current_session.runtime.active_task_id is None


def test_tui_skill_list_discovers_workspace_local_skills_without_agent_boot(tmp_path: Path, monkeypatch) -> None:
    state_path = tmp_path / ".mini-agent" / "tui_sessions.json"
    builtin_dir = tmp_path / "builtin-skills"
    workspace_dir = tmp_path / ".mini-agent" / "skills"
    _write_skill(
        builtin_dir / "doc-coauthoring",
        name="doc-coauthoring",
        description="Draft structured docs with the user.",
        body="Use this skill for documentation.",
    )
    _write_skill(
        workspace_dir / "repo-helper",
        name="repo-helper",
        description="Workspace-local repo guidance.",
        body="Use this skill for the current workspace.",
    )

    config = Config(
        llm=LLMConfig(
            api_key="sk-test",
            api_base="https://api.example.com/v1",
            model="model-default",
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
            enable_skills=True,
            enable_mcp=False,
            skills_dir=str(builtin_dir),
        ),
    )
    monkeypatch.setattr("mini_agent.commands.skill_support.Config.load", lambda allow_interactive_setup=False: config)

    app = _new_app(tmp_path, state_path=state_path)

    asyncio.run(app._run_command("skill list"))

    last_message = app.current_session.view.messages[-1]
    assert last_message.metadata["kind"] == "command"
    assert last_message.metadata["command"] == "skill list"
    assert "repo-helper [workspace] active" in last_message.content
    assert "doc-coauthoring [builtin] active" in last_message.content
    assert app.status == "Skill catalog shown."


def test_tui_skill_change_notice_prompts_for_refresh_and_clears_after_refresh(
    tmp_path: Path,
    monkeypatch,
) -> None:
    state_path = tmp_path / ".mini-agent" / "tui_sessions.json"
    builtin_dir = tmp_path / "builtin-skills"
    workspace_dir = tmp_path / ".mini-agent" / "skills"
    _write_skill(
        builtin_dir / "doc-coauthoring",
        name="doc-coauthoring",
        description="Draft structured docs with the user.",
        body="Use this skill for documentation.",
    )
    _write_skill(
        workspace_dir / "repo-helper",
        name="repo-helper",
        description="Workspace-local repo guidance.",
        body="Use this skill for the current workspace.",
    )

    config = Config(
        llm=LLMConfig(
            api_key="sk-test",
            api_base="https://api.example.com/v1",
            model="model-default",
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
            enable_skills=True,
            enable_mcp=False,
            skills_dir=str(builtin_dir),
        ),
    )
    monkeypatch.setattr("mini_agent.commands.skill_support.Config.load", lambda allow_interactive_setup=False: config)

    app = _new_app(tmp_path, state_path=state_path)
    app.current_session.runtime.agent = SimpleNamespace(
        llm=SimpleNamespace(model="gpt-5.4"),
        runtime_route=SimpleNamespace(provider_id="preset-openai", model="gpt-5.4"),
        messages=[Message(role="system", content="sys")],
        tools={},
        prepared_context_diagnostics={},
    )

    async def _fake_build_agent_kernel(*, workspace_dir, options):
        _ = workspace_dir
        return SimpleNamespace(
            llm=SimpleNamespace(model=options.requested_model or "gpt-5.4"),
            runtime_route=SimpleNamespace(
                provider_id="preset-openai",
                model=options.requested_model or "gpt-5.4",
            ),
            messages=[Message(role="system", content="sys")],
            tools={},
            prepared_context_diagnostics={},
        )

    monkeypatch.setattr("mini_agent.tui.app.build_agent_kernel", _fake_build_agent_kernel)

    _write_skill(
        workspace_dir / "new-helper",
        name="new-helper",
        description="A newly added skill.",
        body="Use this new skill after refresh.",
    )

    app._check_skill_catalog_change(force=True)

    assert app._skill_catalog_change_notice == "changed; run /skill refresh"
    assert app.status == "Skill catalog changed. Run /skill refresh to reload skills."

    asyncio.run(app._run_command("skill refresh"))

    assert app._skill_catalog_change_notice == ""
    assert app.current_session.view.messages[-1].metadata["command"] == "skill refresh"


class FakeGatewayClient:
    def __init__(self, *, profile: str = "qq") -> None:
        self.chat_calls: list[dict[str, Any]] = []
        self.cancel_calls: list[dict[str, Any]] = []
        self.control_calls: list[dict[str, Any]] = []
        self.memory_calls: list[dict[str, Any]] = []
        self.skill_calls: list[dict[str, Any]] = []
        self.model_calls: list[dict[str, Any]] = []
        self.policy_calls: list[dict[str, Any]] = []
        self.approval_calls: list[dict[str, Any]] = []
        self.derived_create_calls: list[dict[str, Any]] = []
        self.delete_calls: list[str] = []
        self._profile = str(profile or "qq").strip().lower() or "qq"
        self._session_counter = 1
        self._detail = self._build_initial_detail(self._profile)
        self._sessions: dict[str, dict[str, Any]] = {
            str(self._detail["session_id"]): self._detail,
        }
        self._skill_entries = [
            {
                "name": "doc-coauthoring",
                "source": "builtin",
                "description": "Draft structured docs with the user.",
            },
            {
                "name": "repo-helper",
                "source": "workspace",
                "description": "Workspace-local repo guidance.",
            },
        ]
        self._skill_policy_mode = "all"
        self._skill_allowlist: set[str] = set()
        self._skill_denylist: set[str] = set()

    def _build_initial_detail(self, profile: str) -> dict[str, Any]:
        if profile == "local":
            return {
                "session_id": "session-1",
                "workspace_dir": "D:/file/Mini-Agent",
                "created_at": "2026-04-08T10:00:00+00:00",
                "updated_at": "2026-04-08T10:00:01+00:00",
                "title": "Session 1",
                "message_count": 0,
                "origin_surface": "tui",
                "active_surface": "tui",
                "reply_enabled": False,
                "busy": False,
                "running_state": None,
                "shared": False,
                "channel_type": None,
                "conversation_id": None,
                "sender_id": None,
                "token_usage": 0,
                "token_limit": 80000,
                "knowledge_base_enabled": True,
                "selected_model_source": "preset",
                "selected_provider_id": "openai",
                "selected_model_id": "gpt-5.4",
                "pending_model_source": None,
                "pending_provider_id": None,
                "pending_model_id": None,
                "pending_approvals": [],
                "context_policy": {
                    "include_sources": [],
                    "exclude_sources": [],
                    "max_items": 4,
                    "max_total_chars": 2400,
                    "max_items_per_source": 1,
                    "active": False,
                },
                "last_prepared_context": {},
                "prepared_context_diagnostics": {},
                "memory_diagnostics": {
                    "global_profile_fact_count": 1,
                    "consolidated": {"needs_refresh": False},
                    "runtime_task_memory": {"session_count": 1, "shared_count": 0},
                },
                "sandbox_diagnostics": {
                    "approval_profile": "build",
                    "access_level": "default",
                    "sandbox_mode": "workspace",
                },
                "recent_messages": [],
            }
        return {
            "session_id": "remote-qq-1",
            "workspace_dir": "D:/file/Mini-Agent",
            "created_at": "2026-04-08T10:00:00+00:00",
            "updated_at": "2026-04-08T10:00:01+00:00",
            "title": None,
            "message_count": 2,
            "origin_surface": "qq",
            "active_surface": "qq",
            "reply_enabled": True,
            "busy": False,
            "running_state": None,
            "shared": True,
            "channel_type": "qq",
            "conversation_id": "group:demo",
            "sender_id": "user-1",
            "token_usage": 1200,
            "token_limit": 80000,
            "knowledge_base_enabled": True,
            "selected_model_source": "preset",
            "selected_provider_id": "openai",
            "selected_model_id": "gpt-5.4",
            "pending_model_source": None,
            "pending_provider_id": None,
            "pending_model_id": None,
            "pending_approvals": [],
            "context_policy": {
                "include_sources": [],
                "exclude_sources": [],
                "max_items": 4,
                "max_total_chars": 2400,
                "max_items_per_source": 1,
                "active": False,
            },
            "last_prepared_context": {},
            "prepared_context_diagnostics": {},
            "memory_diagnostics": {
                "global_profile_fact_count": 1,
                "consolidated": {"needs_refresh": False},
                "runtime_task_memory": {"session_count": 1, "shared_count": 0},
            },
            "sandbox_diagnostics": {
                "approval_profile": "build",
                "access_level": "default",
                "sandbox_mode": "workspace",
            },
            "recent_messages": [
                {
                    "index": 1,
                    "role": "user",
                    "content": "hello from qq",
                    "surface": "qq",
                    "created_at": "2026-04-08T10:00:00+00:00",
                    "channel_type": "qq",
                    "conversation_id": "group:demo",
                    "sender_id": "user-1",
                },
                {
                    "index": 2,
                    "role": "assistant",
                    "content": "mock:hello from qq",
                    "surface": "qq",
                    "created_at": "2026-04-08T10:00:01+00:00",
                    "channel_type": "qq",
                    "conversation_id": "group:demo",
                    "sender_id": "user-1",
                },
            ],
        }

    def _session(self, session_id: str) -> dict[str, Any]:
        resolved = self._sessions.get(str(session_id))
        assert resolved is not None, f"Unknown session: {session_id}"
        return resolved

    def _summary(self, detail: dict[str, Any]) -> dict[str, Any]:
        payload = deepcopy(detail)
        payload.pop("recent_messages", None)
        return payload

    def list_sessions_sync(self, *, workspace_dir: str | None = None, shared_only: bool = False) -> list[dict[str, Any]]:
        _ = workspace_dir
        items = [self._summary(item) for item in self._sessions.values()]
        if shared_only:
            items = [item for item in items if bool(item.get("shared"))]
        return items

    async def list_sessions(
        self,
        *,
        workspace_dir: str | None = None,
        shared_only: bool = False,
    ) -> list[dict[str, Any]]:
        return self.list_sessions_sync(workspace_dir=workspace_dir, shared_only=shared_only)

    def get_session_detail_sync(self, session_id: str, *, recent_limit: int = 80) -> dict[str, Any]:
        _ = recent_limit
        return deepcopy(self._session(session_id))

    async def get_session_detail(self, session_id: str, *, recent_limit: int = 80) -> dict[str, Any]:
        return self.get_session_detail_sync(session_id, recent_limit=recent_limit)

    def create_session_sync(
        self,
        *,
        workspace_dir: str,
        title: str | None = None,
        surface: str = "tui",
        shared: bool = False,
    ) -> dict[str, Any]:
        self._session_counter += 1
        session_id = f"session-{self._session_counter}"
        now = "2026-04-08T10:00:01+00:00"
        detail = {
            **deepcopy(self._build_initial_detail("local")),
            "session_id": session_id,
            "workspace_dir": workspace_dir,
            "title": title or f"Session {self._session_counter}",
            "origin_surface": surface,
            "active_surface": surface,
            "shared": bool(shared),
            "updated_at": now,
            "created_at": now,
        }
        self._sessions[session_id] = detail
        return deepcopy(detail)

    async def create_session(
        self,
        *,
        workspace_dir: str,
        title: str | None = None,
        surface: str = "tui",
        shared: bool = False,
    ) -> dict[str, Any]:
        return self.create_session_sync(
            workspace_dir=workspace_dir,
            title=title,
            surface=surface,
            shared=shared,
        )

    async def create_derived_session(
        self,
        parent_session_id: str,
        *,
        title: str | None = None,
        surface: str | None = None,
        channel_type: str | None = None,
        conversation_id: str | None = None,
        sender_id: str | None = None,
    ) -> dict[str, Any]:
        parent = deepcopy(self._session(parent_session_id))
        self._session_counter += 1
        session_id = f"session-{self._session_counter}"
        now = "2026-04-08T10:00:01+00:00"
        origin_surface = str(surface or "").strip() or str(parent.get("origin_surface") or "tui")
        active_surface = str(surface or "").strip() or str(parent.get("active_surface") or origin_surface)
        detail = {
            **parent,
            "session_id": session_id,
            "title": title or "Task",
            "origin_surface": origin_surface,
            "active_surface": active_surface,
            "channel_type": channel_type,
            "conversation_id": conversation_id,
            "sender_id": sender_id,
            "reply_enabled": False,
            "busy": False,
            "running_state": "",
            "shared": False,
            "message_count": 0,
            "recent_messages": [],
            "pending_approvals": [],
            "updated_at": now,
            "created_at": now,
        }
        self.derived_create_calls.append(
            {
                "parent_session_id": parent_session_id,
                "title": title,
                "surface": surface,
                "channel_type": channel_type,
                "conversation_id": conversation_id,
                "sender_id": sender_id,
            }
        )
        self._sessions[session_id] = detail
        return deepcopy(detail)

    async def rename_session(self, session_id: str, *, title: str) -> dict[str, Any]:
        detail = self._session(session_id)
        detail["title"] = title
        return {
            "status": "renamed",
            "session_id": session_id,
            "active_surface": detail["active_surface"],
            "title": title,
            "shared": bool(detail.get("shared")),
        }

    async def set_session_shared(self, session_id: str, *, shared: bool) -> dict[str, Any]:
        detail = self._session(session_id)
        detail["shared"] = bool(shared)
        return {
            "status": "shared" if shared else "unshared",
            "session_id": session_id,
            "active_surface": detail["active_surface"],
            "title": detail.get("title"),
            "shared": bool(shared),
        }

    def _skill_key(self, value: str) -> str:
        return str(value or "").strip().lower()

    def _skill_is_active(self, name: str) -> bool:
        key = self._skill_key(name)
        if key in self._skill_denylist:
            return False
        if self._skill_policy_mode == "allowlist":
            return key in self._skill_allowlist
        return True

    def _skill_status(self, name: str) -> str:
        key = self._skill_key(name)
        if key in self._skill_denylist:
            return "inactive (disabled)"
        if self._skill_policy_mode == "allowlist" and key not in self._skill_allowlist:
            return "inactive (not allowlisted)"
        return "active"

    def _skill_counts(self) -> dict[str, Any]:
        return {
            "total": len(self._skill_entries),
            "ready": len(self._skill_entries),
            "blocked": 0,
            "workspace": sum(1 for entry in self._skill_entries if entry["source"] == "workspace"),
            "active": sum(1 for entry in self._skill_entries if self._skill_is_active(entry["name"])),
            "mode": self._skill_policy_mode,
        }

    def _skill_catalog_details(self) -> str:
        counts = self._skill_counts()
        lines = [
            "Skills:",
            (
                f"- total {counts['total']} | ready {counts['ready']} | blocked {counts['blocked']} | "
                f"workspace {counts['workspace']} | active {counts['active']} | mode {counts['mode']}"
            ),
        ]
        for entry in self._skill_entries:
            lines.append(
                f"- {entry['name']} [{entry['source']}] {self._skill_status(entry['name'])}"
            )
            lines.append(f"  {entry['description']}")
        return "\n".join(lines)

    def _skill_policy_details(self) -> str:
        counts = self._skill_counts()
        active_names = [
            entry["name"]
            for entry in self._skill_entries
            if self._skill_is_active(entry["name"])
        ]
        lines = [
            "Workspace Skill Policy:",
            f"- mode {self._skill_policy_mode}",
            f"- active {counts['active']} / ready {counts['ready']}",
        ]
        if self._skill_allowlist:
            lines.append(f"- allowlist {', '.join(sorted(self._skill_allowlist))}")
        if self._skill_denylist:
            lines.append(f"- denylist {', '.join(sorted(self._skill_denylist))}")
        if active_names:
            lines.append(f"- active skills: {', '.join(active_names)}")
        else:
            lines.append("- active skills: (none)")
        return "\n".join(lines)

    def _append_skill_command_message(
        self,
        *,
        command: str,
        summary: str,
        content: str,
        detail: dict[str, Any] | None = None,
    ) -> None:
        session_detail = detail or self._detail
        next_index = len(session_detail["recent_messages"]) + 1
        session_detail["message_count"] += 1
        session_detail["updated_at"] = "2026-04-08T10:00:06+00:00"
        session_detail["recent_messages"].append(
            {
                "index": next_index,
                "role": "system",
                "content": content,
                "surface": session_detail["active_surface"],
                "created_at": "2026-04-08T10:00:06+00:00",
                "channel_type": session_detail["channel_type"],
                "conversation_id": session_detail["conversation_id"],
                "sender_id": session_detail["sender_id"],
                "metadata": {
                    "kind": "command",
                    "command": command,
                    "summary": summary,
                    "level": "info",
                    "threads_visible": False,
                },
            }
        )

    async def get_session_messages(self, session_id: str, *, limit: int = 10) -> list[dict[str, Any]]:
        detail = self._session(session_id)
        return deepcopy(detail["recent_messages"][-limit:])

    async def update_session_model(
        self,
        session_id: str,
        *,
        provider_source: str,
        provider_id: str,
        model_id: str,
        surface: str | None = None,
        channel_type: str | None = None,
        conversation_id: str | None = None,
        sender_id: str | None = None,
    ) -> dict[str, Any]:
        detail = self._session(session_id)
        self.model_calls.append(
            {
                "session_id": session_id,
                "provider_source": provider_source,
                "provider_id": provider_id,
                "model_id": model_id,
                "surface": surface,
                "channel_type": channel_type,
                "conversation_id": conversation_id,
                "sender_id": sender_id,
            }
        )
        if detail["busy"]:
            detail["pending_model_source"] = provider_source
            detail["pending_provider_id"] = provider_id
            detail["pending_model_id"] = model_id
            return {
                "status": "queued",
                "session_id": session_id,
                "active_surface": detail["active_surface"],
                "applied": False,
                "queued": True,
                "selected_model_source": detail["selected_model_source"],
                "selected_provider_id": detail["selected_provider_id"],
                "selected_model_id": detail["selected_model_id"],
                "pending_model_source": provider_source,
                "pending_provider_id": provider_id,
                "pending_model_id": model_id,
            }
        detail["selected_model_source"] = provider_source
        detail["selected_provider_id"] = provider_id
        detail["selected_model_id"] = model_id
        detail["pending_model_source"] = None
        detail["pending_provider_id"] = None
        detail["pending_model_id"] = None
        return {
            "status": "selected",
            "session_id": session_id,
            "active_surface": detail["active_surface"],
            "applied": True,
            "queued": False,
            "selected_model_source": provider_source,
            "selected_provider_id": provider_id,
            "selected_model_id": model_id,
            "pending_model_source": None,
            "pending_provider_id": None,
            "pending_model_id": None,
        }

    async def update_session_runtime_policy(
        self,
        session_id: str,
        *,
        approval_profile: str | None = None,
        access_level: str | None = None,
        surface: str | None = None,
        channel_type: str | None = None,
        conversation_id: str | None = None,
        sender_id: str | None = None,
    ) -> dict[str, Any]:
        detail = self._session(session_id)
        if detail["busy"] and not detail["pending_approvals"]:
            raise RuntimeError(
                "Session is busy. Runtime mode can only change while idle or waiting on approval."
            )
        resolved_profile = str(approval_profile or "").strip() or str(
            detail.get("sandbox_diagnostics", {}).get("approval_profile") or "build"
        )
        resolved_access = str(access_level or "").strip() or str(
            detail.get("sandbox_diagnostics", {}).get("access_level") or "default"
        )
        self.policy_calls.append(
            {
                "session_id": session_id,
                "approval_profile": approval_profile,
                "access_level": access_level,
                "surface": surface,
                "channel_type": channel_type,
                "conversation_id": conversation_id,
                "sender_id": sender_id,
            }
        )
        detail["active_surface"] = surface or detail["active_surface"]
        detail["sandbox_diagnostics"] = {
            **dict(detail.get("sandbox_diagnostics") or {}),
            "approval_profile": resolved_profile,
            "access_level": resolved_access,
            "sandbox_mode": "unrestricted" if resolved_access == "full-access" else "workspace",
        }
        return {
            "status": "updated",
            "session_id": session_id,
            "active_surface": detail["active_surface"],
            "applied": True,
            "approval_profile": resolved_profile,
            "access_level": resolved_access,
            "sandbox_diagnostics": deepcopy(detail["sandbox_diagnostics"]),
        }

    async def run_chat(
        self,
        *,
        session_id: str,
        message: str,
        workspace_dir: str,
        surface: str = "tui",
    ) -> dict[str, Any]:
        detail = self._session(session_id)
        if detail["pending_model_id"]:
            detail["selected_model_source"] = detail["pending_model_source"]
            detail["selected_provider_id"] = detail["pending_provider_id"]
            detail["selected_model_id"] = detail["pending_model_id"]
            detail["pending_model_source"] = None
            detail["pending_provider_id"] = None
            detail["pending_model_id"] = None
        self.chat_calls.append(
            {
                "session_id": session_id,
                "message": message,
                "workspace_dir": workspace_dir,
                "surface": surface,
            }
        )
        detail["active_surface"] = surface
        detail["reply_enabled"] = False
        detail["message_count"] += 2
        detail["token_usage"] = 1536
        detail["updated_at"] = "2026-04-08T10:00:03+00:00"
        base_index = len(detail["recent_messages"])
        detail["recent_messages"].extend(
            [
                {
                    "index": base_index + 1,
                    "role": "user",
                    "content": message,
                    "surface": surface,
                    "created_at": "2026-04-08T10:00:02+00:00",
                },
                {
                    "index": base_index + 2,
                    "role": "assistant",
                    "content": f"remote:{message}",
                    "surface": surface,
                    "created_at": "2026-04-08T10:00:03+00:00",
                },
            ]
        )
        return {
            "session_id": session_id,
            "reply": f"remote:{message}",
            "message_count": detail["message_count"],
            "token_usage": detail["token_usage"],
            "workspace_dir": workspace_dir,
            "updated_at": detail["updated_at"],
        }

    async def stream_chat_events(
        self,
        *,
        session_id: str,
        message: str,
        workspace_dir: str,
        surface: str = "tui",
    ):
        detail = self._session(session_id)
        if detail["pending_model_id"]:
            detail["selected_model_source"] = detail["pending_model_source"]
            detail["selected_provider_id"] = detail["pending_provider_id"]
            detail["selected_model_id"] = detail["pending_model_id"]
            detail["pending_model_source"] = None
            detail["pending_provider_id"] = None
            detail["pending_model_id"] = None
        self.chat_calls.append(
            {
                "session_id": session_id,
                "message": message,
                "workspace_dir": workspace_dir,
                "surface": surface,
                "mode": "stream",
            }
        )
        detail["active_surface"] = surface
        detail["reply_enabled"] = False
        detail["message_count"] += 3
        detail["token_usage"] = 2048
        detail["updated_at"] = "2026-04-08T10:00:03+00:00"
        base_index = len(detail["recent_messages"])
        detail["recent_messages"].extend(
            [
                {
                    "index": base_index + 1,
                    "role": "user",
                    "content": message,
                    "surface": surface,
                    "created_at": "2026-04-08T10:00:02+00:00",
                },
                {
                    "index": base_index + 2,
                    "role": "tool",
                    "content": "",
                    "surface": surface,
                    "created_at": "2026-04-08T10:00:02+00:00",
                    "metadata": {
                        "kind": "activity",
                        "activity_items": [
                            {
                                "id": "activity-1",
                                "label": "thinking",
                                "detail": "planning",
                                "preview": "",
                                "output_text": "",
                                "output_summary": "",
                                "state": "",
                            },
                            {
                                "id": "call-bash",
                                "label": "shell",
                                "detail": "ok",
                                "preview": "pytest -q tests/test_tui_app.py",
                                "output_text": "32 passed",
                                "output_summary": "32 passed",
                                "state": "ok",
                            },
                        ],
                    },
                },
                {
                    "index": base_index + 3,
                    "role": "assistant",
                    "content": f"remote:{message}",
                    "surface": surface,
                    "created_at": "2026-04-08T10:00:03+00:00",
                },
            ]
        )
        yield ("status", {"stage": "running"})
        yield (
            "activity",
            {
                "id": "activity-1",
                "activity_id": "activity-1",
                "label": "thinking",
                "detail": "planning",
                "preview": "",
                "output_text": "",
                "state": "",
                "running_state": "step 1: planned 1 tool call(s)",
            },
        )
        yield (
            "activity",
            {
                "id": "call-bash",
                "activity_id": "call-bash",
                "label": "shell",
                "detail": "running",
                "preview": "pytest -q tests/test_tui_app.py",
                "output_text": "",
                "state": "running",
                "running_state": "step 1: running bash",
            },
        )
        yield (
            "activity",
            {
                "id": "call-bash",
                "activity_id": "call-bash",
                "label": "shell",
                "detail": "ok",
                "preview": "pytest -q tests/test_tui_app.py",
                "output_text": "32 passed",
                "state": "ok",
                "running_state": "step 1: bash ok",
            },
        )
        reply = f"remote:{message}"
        yield ("delta", {"assistant_id": "assistant-1", "chunk": "remote:"})
        yield ("delta", {"assistant_id": "assistant-1", "chunk": message})
        yield (
            "done",
            {
                "session_id": session_id,
                "reply": reply,
                "stop_reason": "end_turn",
                "message_count": detail["message_count"],
                "token_usage": detail["token_usage"],
                "workspace_dir": workspace_dir,
                "updated_at": detail["updated_at"],
            },
        )

    async def reset_session(self, session_id: str) -> dict[str, Any]:
        detail = self._session(session_id)
        detail["message_count"] = 0
        detail["recent_messages"] = []
        return {"status": "reset", "session_id": session_id}

    async def cancel_session(
        self,
        session_id: str,
        *,
        reason: str | None = None,
        surface: str | None = None,
        channel_type: str | None = None,
        conversation_id: str | None = None,
        sender_id: str | None = None,
    ) -> dict[str, Any]:
        detail = self._session(session_id)
        if not bool(detail.get("busy")):
            raise RuntimeError("Gateway HTTP 409: Session has no running turn to cancel.")
        self.cancel_calls.append(
            {
                "session_id": session_id,
                "reason": reason,
                "surface": surface,
                "channel_type": channel_type,
                "conversation_id": conversation_id,
                "sender_id": sender_id,
            }
        )
        next_index = len(detail["recent_messages"]) + 1
        detail["running_state"] = "cancellation requested"
        detail["updated_at"] = "2026-04-08T10:00:02+00:00"
        detail["message_count"] += 1
        detail["recent_messages"].append(
            {
                "index": next_index,
                "role": "system",
                "content": "Action: cancel\nState: cancellation requested\nReason: user_cancel",
                "surface": surface or detail["active_surface"],
                "created_at": "2026-04-08T10:00:02+00:00",
                "channel_type": channel_type,
                "conversation_id": conversation_id,
                "sender_id": sender_id,
                "metadata": {
                    "kind": "command",
                    "command": "cancel",
                    "summary": "cancellation requested",
                    "level": "info",
                },
            }
        )
        return {
            "status": "cancel_requested",
            "session_id": session_id,
            "active_surface": detail["active_surface"],
        }

    async def respond_to_approval(
        self,
        session_id: str,
        *,
        approved: bool,
        token: str | None = None,
        surface: str | None = None,
        channel_type: str | None = None,
        conversation_id: str | None = None,
        sender_id: str | None = None,
    ) -> dict[str, Any]:
        detail = self._session(session_id)
        self.approval_calls.append(
            {
                "session_id": session_id,
                "approved": approved,
                "token": token,
                "surface": surface,
                "channel_type": channel_type,
                "conversation_id": conversation_id,
                "sender_id": sender_id,
            }
        )
        def _text(value: Any) -> str:
            return str(value or "").strip()

        pending = [
            item
            for item in detail.get("pending_approvals", [])
            if _text(item.get("token"))
        ]
        if not pending:
            recovery = detail.get("recovery") if isinstance(detail.get("recovery"), dict) else {}
            recovery_pending = recovery.get("pending_approvals") if isinstance(recovery, dict) else None
            if isinstance(recovery_pending, list) and recovery_pending:
                raise RuntimeError(
                    f"Gateway HTTP 409: {RuntimeSessionInterruptHandler.restart_pending_approval_detail()}"
                )
            raise RuntimeError("Gateway HTTP 409: Session has no pending approval.")
        resolved_token = _text(token)
        if resolved_token:
            target = next((item for item in pending if _text(item.get("token")) == resolved_token), None)
            if target is None:
                raise RuntimeError(f"Gateway HTTP 404: Pending approval not found: {resolved_token}")
        elif len(pending) == 1:
            target = pending[0]
            resolved_token = _text(target.get("token"))
        else:
            raise RuntimeError("Gateway HTTP 409: Multiple approvals pending. Specify a token.")

        detail["pending_approvals"] = [
            item for item in pending if _text(item.get("token")) != resolved_token
        ]
        next_index = len(detail["recent_messages"]) + 1
        detail["recent_messages"].append(
            {
                "index": next_index,
                "role": "system",
                "content": (
                    f"Action: {'approve' if approved else 'deny'}\n"
                    f"Token: {resolved_token}\n"
                    f"Tool: {_text(target.get('tool_name')) or 'tool'}"
                ),
                "surface": surface or "tui",
                "created_at": "2026-04-08T10:00:04+00:00",
                "channel_type": channel_type,
                "conversation_id": conversation_id,
                "sender_id": sender_id,
                "metadata": {
                    "kind": "command",
                    "command": "approve" if approved else "deny",
                    "summary": f"{'approved' if approved else 'denied'} {_text(target.get('tool_name')) or 'tool'}",
                    "level": "info",
                },
            }
        )
        return {
            "status": "resolved",
            "session_id": session_id,
            "token": resolved_token,
            "tool_name": _text(target.get("tool_name")) or "tool",
            "decision": "approved" if approved else "denied",
            "active_surface": detail["active_surface"],
        }

    async def control_session(
        self,
        session_id: str,
        *,
        action: str,
        reason: str | None = None,
        surface: str | None = None,
        channel_type: str | None = None,
        conversation_id: str | None = None,
        sender_id: str | None = None,
    ) -> dict[str, Any]:
        detail = self._session(session_id)
        self.control_calls.append(
            {
                "session_id": session_id,
                "action": action,
                "reason": reason,
                "surface": surface,
                "channel_type": channel_type,
                "conversation_id": conversation_id,
                "sender_id": sender_id,
            }
        )
        if detail.get("busy") and action not in {"mcp_status", "mcp_list"}:
            raise RuntimeError("Gateway HTTP 409: Session is busy. Wait for the current turn to finish.")
        next_index = len(detail["recent_messages"]) + 1
        if action == "mcp_status":
            summary = "1 active server(s) | 2 tool(s)"
            content = "MCP Status:\n- active 1\n- tools 2"
            response = {
                "status": "controlled",
                "session_id": session_id,
                "action": "mcp_status",
                "applied": False,
                "active_surface": detail["active_surface"],
                "knowledge_base_enabled": detail["knowledge_base_enabled"],
                "stats": {
                    "summary": summary,
                    "details": content,
                    "configured_total": 2,
                    "discoverable_total": 2,
                    "disabled_total": 0,
                    "active_total": 1,
                    "tool_total": 2,
                },
            }
            command_name = "mcp status"
            level = "info"
            threads_visible = False
        elif action == "mcp_list":
            summary = "2 configured server(s) | 1 active"
            content = "MCP Status:\n- active 1\n- tools 2\n\nMCP Servers:\n- alpha [stdio] active | trusted"
            response = {
                "status": "controlled",
                "session_id": session_id,
                "action": "mcp_list",
                "applied": False,
                "active_surface": detail["active_surface"],
                "knowledge_base_enabled": detail["knowledge_base_enabled"],
                "stats": {
                    "summary": summary,
                    "details": content,
                    "configured_total": 2,
                    "discoverable_total": 2,
                    "disabled_total": 0,
                    "active_total": 1,
                    "tool_total": 2,
                },
            }
            command_name = "mcp list"
            level = "info"
            threads_visible = False
        elif action == "mcp_reload":
            summary = "reloaded MCP | 2 active server(s) | 5 tool(s)"
            content = "MCP Status:\n- active 2\n- tools 5\n\nMCP Servers:\n- alpha [stdio] active | trusted"
            response = {
                "status": "controlled",
                "session_id": session_id,
                "action": "mcp_reload",
                "applied": True,
                "active_surface": detail["active_surface"],
                "knowledge_base_enabled": detail["knowledge_base_enabled"],
                "stats": {
                    "summary": summary,
                    "details": content,
                    "configured_total": 3,
                    "discoverable_total": 3,
                    "disabled_total": 0,
                    "active_total": 2,
                    "tool_total": 5,
                },
            }
            command_name = "mcp reload"
            level = "info"
            threads_visible = False
        elif action == "kb_on":
            detail["knowledge_base_enabled"] = True
            summary = "knowledge base enabled"
            content = "Action: kb_on\nKnowledge Base: enabled"
            response = {
                "status": "controlled",
                "session_id": session_id,
                "action": "kb_on",
                "applied": True,
                "active_surface": detail["active_surface"],
                "reason": reason,
                "knowledge_base_enabled": True,
            }
            command_name = action
            level = "info"
            threads_visible = None
        elif action == "kb_off":
            detail["knowledge_base_enabled"] = False
            summary = "knowledge base disabled"
            content = "Action: kb_off\nKnowledge Base: disabled"
            response = {
                "status": "controlled",
                "session_id": session_id,
                "action": "kb_off",
                "applied": True,
                "active_surface": detail["active_surface"],
                "reason": reason,
                "knowledge_base_enabled": False,
            }
            command_name = action
            level = "info"
            threads_visible = None
        elif action == "compact":
            summary = "context compacted"
            content = "Action: compact\nMessages: 12 -> 6\nTokens: 480 -> 220"
            response = {
                "status": "controlled",
                "session_id": session_id,
                "action": "compact",
                "applied": True,
                "active_surface": detail["active_surface"],
                "reason": reason,
                "message_count_before": 12,
                "message_count_after": 6,
                "token_count_before": 480,
                "token_count_after": 220,
                "knowledge_base_enabled": detail["knowledge_base_enabled"],
                "stats": {
                    "masked_messages": 1,
                    "snipped_messages": 2,
                    "merged_messages": 0,
                },
            }
            command_name = action
            level = "info"
            threads_visible = None
        else:
            summary = "older memories dropped"
            content = "Action: drop_memories\nMessages: 12 -> 5\nTokens: 480 -> 180"
            response = {
                "status": "controlled",
                "session_id": session_id,
                "action": "drop_memories",
                "applied": True,
                "active_surface": detail["active_surface"],
                "reason": reason,
                "message_count_before": 12,
                "message_count_after": 5,
                "token_count_before": 480,
                "token_count_after": 180,
                "knowledge_base_enabled": detail["knowledge_base_enabled"],
                "stats": {
                    "masked_messages": 0,
                    "snipped_messages": 3,
                    "merged_messages": 1,
                },
            }
            command_name = action
            level = "info"
            threads_visible = None
        detail["message_count"] += 1
        detail["updated_at"] = "2026-04-08T10:00:02+00:00"
        detail["recent_messages"].append(
            {
                "index": next_index,
                "role": "system",
                "content": content,
                "surface": surface or detail["active_surface"],
                "created_at": "2026-04-08T10:00:02+00:00",
                "channel_type": channel_type,
                "conversation_id": conversation_id,
                "sender_id": sender_id,
                "metadata": {
                    "kind": "command",
                    "command": command_name,
                    "summary": summary,
                    "level": level,
                    **({"threads_visible": threads_visible} if threads_visible is not None else {}),
                },
            }
        )
        return response

    async def update_session_context(
        self,
        session_id: str,
        *,
        action: str,
        sources: list[str] | None = None,
        max_items: int | None = None,
        max_total_chars: int | None = None,
        max_items_per_source: int | None = None,
        surface: str | None = None,
        channel_type: str | None = None,
        conversation_id: str | None = None,
        sender_id: str | None = None,
    ) -> dict[str, Any]:
        detail = self._session(session_id)
        self.control_calls.append(
            {
                "session_id": session_id,
                "action": f"context:{action}",
                "sources": deepcopy(list(sources or [])),
                "max_items": max_items,
                "max_total_chars": max_total_chars,
                "max_items_per_source": max_items_per_source,
                "surface": surface,
                "channel_type": channel_type,
                "conversation_id": conversation_id,
                "sender_id": sender_id,
            }
        )
        current = deepcopy(self._detail.get("context_policy") or {})
        current.setdefault("include_sources", [])
        current.setdefault("exclude_sources", [])
        current.setdefault("max_items", 4)
        current.setdefault("max_total_chars", 2400)
        current.setdefault("max_items_per_source", 1)
        if action == "include":
            current["include_sources"] = [str(item).strip().lower() for item in list(sources or []) if str(item).strip()]
            current["exclude_sources"] = [
                item for item in list(current.get("exclude_sources") or []) if item not in current["include_sources"]
            ]
        elif action == "exclude":
            current["exclude_sources"] = [str(item).strip().lower() for item in list(sources or []) if str(item).strip()]
            current["include_sources"] = [
                item for item in list(current.get("include_sources") or []) if item not in current["exclude_sources"]
            ]
        elif action == "budget":
            current["max_items"] = max_items
            if max_total_chars is not None:
                current["max_total_chars"] = max_total_chars
            if max_items_per_source is not None:
                current["max_items_per_source"] = max_items_per_source
        elif action == "reset":
            current = {
                "include_sources": [],
                "exclude_sources": [],
                "max_items": 4,
                "max_total_chars": 2400,
                "max_items_per_source": 1,
                "active": False,
            }
        current["active"] = bool(
            current.get("include_sources")
            or current.get("exclude_sources")
            or int(current.get("max_items") or 0) != 4
            or int(current.get("max_total_chars") or 0) != 2400
            or int(current.get("max_items_per_source") or 0) != 1
        )
        detail["context_policy"] = current
        next_index = len(detail["recent_messages"]) + 1
        detail["recent_messages"].append(
            {
                "index": next_index,
                "role": "system",
                "content": f"Policy: {current}",
                "surface": surface or detail["active_surface"],
                "created_at": "2026-04-08T10:00:05+00:00",
                "channel_type": channel_type,
                "conversation_id": conversation_id,
                "sender_id": sender_id,
                "metadata": {
                    "kind": "command",
                    "command": f"context {action}",
                    "summary": "context policy updated",
                    "level": "info",
                    "threads_visible": False,
                },
            }
        )
        return {
            "status": "updated",
            "session_id": session_id,
            "action": action,
            "active_surface": detail["active_surface"],
            "context_policy": deepcopy(current),
        }

    async def manage_session_memory(
        self,
        session_id: str,
        *,
        action: str,
        engram_id: str | None = None,
        content: str | None = None,
        query: str | None = None,
        day: str | None = None,
        export_format: str | None = None,
        detail_mode: str | None = None,
        surface: str | None = None,
        channel_type: str | None = None,
        conversation_id: str | None = None,
        sender_id: str | None = None,
    ) -> dict[str, Any]:
        detail = self._session(session_id)
        self.memory_calls.append(
            {
                "session_id": session_id,
                "action": action,
                "engram_id": engram_id,
                "content": content,
                "query": query,
                "day": day,
                "export_format": export_format,
                "detail_mode": detail_mode,
                "surface": surface,
                "channel_type": channel_type,
                "conversation_id": conversation_id,
                "sender_id": sender_id,
            }
        )
        summary = "cons fresh | rtm 1+0 | profile 1"
        details = "Memory Diagnostics\nSummary: cons fresh | rtm 1+0 | profile 1"
        command_name = f"memory {action.replace('_', ' ')}"
        result_extra: dict[str, Any] = {}
        if action == "runtime":
            details = "Runtime Task Memory\nSession entries: 1\nShared entries: 0"
            command_name = "memory runtime"
        elif action == "list":
            details = "Session Runtime Memory\nSession entries: 1\nShared entries: 0"
            command_name = "memory list"
        elif action == "overview":
            details = (
                "Memory Overview\nWorkspace: D:/file/Mini-Agent\nMemory root: D:/file/Mini-Agent\n"
                "Long-term file: D:/file/Mini-Agent/MEMORY.md\nDaily dir: D:/file/Mini-Agent/memory\n\n"
                f"Session Context\n- session id: {session_id}\n- workspace anchor: D:/file/Mini-Agent\n"
                f"- session namespace: session:{session_id} | shared namespace: workspace:shared\n\n"
                "Runtime Task Memory\n- session entries: 1 | shared entries: 0\n\n"
                "Durable Memory\n- global profile facts: 1 | workspace notes: 1 | daily files: 1\n\n"
                "Consolidated Memory\n- state: fresh | items: 2 | pending sessions: 0"
            )
            command_name = "memory overview"
        elif action == "export":
            details = (
                "Memory Export\nWorkspace: D:/file/Mini-Agent\nMemory root: D:/file/Mini-Agent\n"
                "Long-term file: D:/file/Mini-Agent/MEMORY.md\nDaily dir: D:/file/Mini-Agent/memory\n"
                f"Format: {export_format or 'jsonl'}\nItem count: 1\n\nContent\n"
                + (
                    "{\"timestamp\": \"2026-04-10T00:00:00+00:00\", \"category\": \"operator_note\", \"content\": \"remembered workspace note\", \"path\": \"MEMORY.md\"}"
                    if (export_format or "jsonl") == "jsonl"
                    else "## MEMORY.md\n- [2026-04-10T00:00:00+00:00] [operator_note] remembered workspace note"
                )
            )
            command_name = "memory export"
        elif action == "session_show":
            details = (
                f"Session Runtime Memory\nEngram: {engram_id or 'session-1'}\n"
                "Layer: working\nImportance: 0.5\nUpdated: 2026-04-09T00:00:00+00:00\n"
                "Content: remembered session detail"
            )
            result_extra["engram_id"] = engram_id or "session-1"
            command_name = "memory show"
        elif action == "consolidated_show":
            details = (
                "Consolidated Memory\nMemory file: D:/file/Mini-Agent/MEMORY.md\n"
                "State: fresh | reason: fresh\nItem count: 2\n\nItems\n"
                "- 1. restart recovery should preserve approval hints\n"
                "- 2. routing guardrails remain workspace scoped"
            )
            command_name = "memory consolidated"
        elif action == "consolidated_search":
            details = (
                f"Consolidated Memory Search\nQuery: {query or 'routing'}\nMemory file: D:/file/Mini-Agent/MEMORY.md\n"
                "State: fresh | reason: fresh\nReturned: 1 / 2 item(s)\n\nHits\n"
                "- 1. (score=9.500 | drift=aligned) routing guardrails remain workspace scoped"
            )
            command_name = "memory consolidated search"
        elif action == "profile":
            details = (
                "Global Profile Memory\nUser file: global/USER.md\nFact count: 1\n\n"
                "Facts\n- 1. User prefers Chinese replies during debugging"
            )
            command_name = "memory profile"
        elif action == "notes":
            details = (
                "Workspace Durable Notes\nWorkspace: D:/file/Mini-Agent\nMemory root: D:/file/Mini-Agent\n"
                "Long-term file: D:/file/Mini-Agent/MEMORY.md\nDaily dir: D:/file/Mini-Agent/memory\n"
                "Recent notes: 1\n\nRecent Workspace Notes\n"
                "- 1. [2026-04-10T00:00:00+00:00] [operator_note] [MEMORY.md] remembered workspace note"
            )
            command_name = "memory notes"
        elif action == "daily":
            details = (
                f"Workspace Daily Memory\nWorkspace: D:/file/Mini-Agent\nDay: {day or '2026-04-10'}\n"
                f"Path: D:/file/Mini-Agent/memory/{day or '2026-04-10'}.md\nNote count: 1\n\n"
                "Daily Notes\n- 1. [2026-04-10T00:00:00+00:00] [operator_note] remembered daily note"
            )
            command_name = "memory daily"
        elif action == "shared_list":
            details = "Workspace-Shared Runtime Memory\nShared namespace: workspace:shared\nShared entries: 1"
            command_name = "memory shared list"
        elif action == "shared_show":
            details = (
                f"Workspace-Shared Runtime Memory\nEngram: {engram_id or 'shared-1'}\n"
                "Layer: working\nImportance: 0.5\nUpdated: 2026-04-09T00:00:00+00:00\n"
                "Content: remembered shared detail"
            )
            result_extra["engram_id"] = engram_id or "shared-1"
            command_name = "memory shared show"
        elif action == "shared_clear":
            details = (
                "Workspace-Shared Runtime Memory\nAction: shared_clear\nCleared: yes\n\n"
                "Memory Diagnostics\nSummary: cons fresh | rtm 1+0 | profile 1"
            )
            summary = "workspace-shared runtime memory cleared"
            command_name = "memory shared clear"
        elif action == "refresh":
            details = "Memory Diagnostics\nSummary: cons fresh | rtm 1+0 | profile 1\nWorkspace: D:/file/Mini-Agent"
            summary = "memory refreshed"
            command_name = "memory refresh"
        elif action == "promote_note":
            summary = "runtime memory promoted to workspace note"
            details = (
                f"Action: promote_note\nEngram: {engram_id}\nTarget: workspace_note\n"
                "Content: remembered detail"
            )
            command_name = "memory promote note"
            result_extra["engram_id"] = engram_id or "session-1"
        elif action == "promote_profile":
            summary = "runtime memory promoted to global profile"
            details = (
                f"Action: promote_profile\nEngram: {engram_id}\nTarget: global_profile\n"
                "Content: remembered profile detail"
            )
            command_name = "memory promote profile"
            result_extra["engram_id"] = engram_id or "session-1"
        elif action == "promote_shared":
            summary = "runtime memory promoted to workspace-shared memory"
            details = (
                f"Action: promote_shared\nEngram: {engram_id}\nTarget: workspace_shared\n"
                "Content: remembered shared detail"
            )
            command_name = "memory promote shared"
            result_extra["engram_id"] = engram_id or "session-1"
        elif action == "save_note":
            summary = "operator note saved to workspace memory"
            details = (
                "Action: save_note\nTarget: workspace_note\nCategory: kb_confirmed\n"
                f"Content: {content or 'remembered detail'}"
            )
            command_name = "memory save note"
            result_extra["saved"] = {
                "target": "workspace_note",
                "category": "kb_confirmed",
                "content": content or "remembered detail",
            }
        elif action == "save_profile":
            summary = "operator profile fact saved"
            details = (
                "Action: save_profile\nTarget: global_profile\nCategory: preference\n"
                f"Content: {content or 'remembered detail'}"
            )
            command_name = "memory save profile"
            result_extra["saved"] = {
                "target": "global_profile",
                "category": "preference",
                "content": content or "remembered detail",
                "saved": True,
            }
        if action in {
            "shared_clear",
            "refresh",
            "promote_note",
            "promote_profile",
            "promote_shared",
            "save_note",
            "save_profile",
        }:
            next_index = len(detail["recent_messages"]) + 1
            detail["message_count"] += 1
            detail["updated_at"] = "2026-04-08T10:00:03+00:00"
            detail["recent_messages"].append(
                {
                    "index": next_index,
                    "role": "system",
                    "content": details,
                    "surface": surface or detail["active_surface"],
                    "created_at": "2026-04-08T10:00:03+00:00",
                    "channel_type": channel_type,
                    "conversation_id": conversation_id,
                    "sender_id": sender_id,
                    "metadata": {
                        "kind": "command",
                        "command": command_name,
                        "summary": summary,
                        "level": "info",
                        "threads_visible": False,
                        **(
                            {"engram_id": result_extra["engram_id"]}
                            if isinstance(result_extra.get("engram_id"), str) and result_extra.get("engram_id")
                            else {}
                        ),
                    },
                }
            )
        return {
            "status": "ok",
            "session_id": session_id,
            "action": action,
            "active_surface": detail["active_surface"],
            "memory_diagnostics": deepcopy(detail.get("memory_diagnostics", {})),
            "result": {
                "summary": summary,
                "details": details,
                **result_extra,
            },
        }

    async def manage_session_skill(
        self,
        session_id: str,
        *,
        action: str,
        skill_name: str | None = None,
        path: str | None = None,
        query: str | None = None,
        mode: str | None = None,
        surface: str | None = None,
        channel_type: str | None = None,
        conversation_id: str | None = None,
        sender_id: str | None = None,
    ) -> dict[str, Any]:
        detail = self._session(session_id)
        self.skill_calls.append(
            {
                "session_id": session_id,
                "action": action,
                "skill_name": skill_name,
                "path": path,
                "query": query,
                "mode": mode,
                "surface": surface,
                "channel_type": channel_type,
                "conversation_id": conversation_id,
                "sender_id": sender_id,
            }
        )
        if action == "list":
            return {
                "status": "ok",
                "session_id": session_id,
                "action": action,
                "active_surface": detail["active_surface"],
                "result": {
                    "summary": (
                        f"{self._skill_counts()['total']} skill(s) | {self._skill_counts()['active']} active | "
                        f"{self._skill_counts()['ready']} ready | {self._skill_counts()['blocked']} blocked | mode {self._skill_policy_mode}"
                    ),
                    "details": self._skill_catalog_details(),
                },
            }
        if action == "active":
            return {
                "status": "ok",
                "session_id": session_id,
                "action": action,
                "active_surface": detail["active_surface"],
                "result": {
                    "summary": f"{self._skill_counts()['active']} active skill(s) | mode {self._skill_policy_mode}",
                    "details": self._skill_policy_details(),
                    "counts": deepcopy(self._skill_counts()),
                    "policy": {
                        "mode": self._skill_policy_mode,
                        "allowlist": sorted(self._skill_allowlist),
                        "denylist": sorted(self._skill_denylist),
                    },
                },
            }
        if action == "install":
            installed_name = "repo-helper"
            return {
                "status": "ok",
                "session_id": session_id,
                "action": action,
                "active_surface": detail["active_surface"],
                "result": {
                    "summary": f"installed {installed_name}",
                    "details": (
                        "Installed Skill:\n"
                        f"- name {installed_name}\n"
                        f"- source directory\n"
                        f"- path {path or 'C:/skills/repo-helper'}\n"
                        "- activated yes"
                    ),
                },
            }
        if action == "show":
            active = self._skill_is_active(skill_name or "")
            found = (skill_name or "").strip().lower() != "missing-skill"
            return {
                "status": "ok" if found else "not_found",
                "session_id": session_id,
                "action": action,
                "active_surface": detail["active_surface"],
                "result": {
                    "summary": f"showing {skill_name}" if found else "skill not found",
                    "details": (
                        f"Skill: {skill_name}\nSource: workspace\nStatus: {'active' if active else 'inactive'}\nSkill Key: {str(skill_name or '').upper()}\n\n"
                        "Description:\nWorkspace-local repo guidance.\n\nInstructions:\nUse this skill for the current workspace."
                        if found
                        else f"Skill not found: {skill_name}\nAvailable skills: doc-coauthoring, repo-helper"
                    ),
                    "skill_name": skill_name,
                    "found": found,
                },
            }
        if action == "search":
            details_lines = [f'Skill matches for "{query}":']
            for entry in self._skill_entries:
                if (query or "").strip() and self._skill_key(query) not in self._skill_key(entry["name"]):
                    continue
                details_lines.append(
                    f"- {entry['name']} [{entry['source']}] {self._skill_status(entry['name'])}"
                )
                details_lines.append(f"  {entry['description']}")
            return {
                "status": "ok",
                "session_id": session_id,
                "action": action,
                "active_surface": detail["active_surface"],
                "result": {
                    "summary": "1 match(es)" if (query or "").strip() else "no matches",
                    "details": "\n".join(details_lines),
                    "query": query,
                    "match_count": 1 if (query or "").strip() else 0,
                },
            }
        if action == "mode":
            self._skill_policy_mode = "allowlist" if self._skill_key(mode) == "allowlist" else "all"
            summary = f"skill mode set to {self._skill_policy_mode}"
            details = self._skill_policy_details()
            self._append_skill_command_message(
                command=f"skill mode {self._skill_policy_mode}",
                summary=summary,
                content=details,
                detail=detail,
            )
            return {
                "status": "ok",
                "session_id": session_id,
                "action": action,
                "active_surface": detail["active_surface"],
                "result": {
                    "summary": summary,
                    "details": details,
                    "counts": deepcopy(self._skill_counts()),
                    "policy": {
                        "mode": self._skill_policy_mode,
                        "allowlist": sorted(self._skill_allowlist),
                        "denylist": sorted(self._skill_denylist),
                    },
                },
            }
        if action == "enable":
            if skill_name:
                self._skill_allowlist.add(self._skill_key(skill_name))
                self._skill_denylist.discard(self._skill_key(skill_name))
            summary = f"enabled {skill_name} in workspace policy"
            details = self._skill_policy_details()
            self._append_skill_command_message(
                command=f"skill enable {skill_name}",
                summary=summary,
                content=details,
                detail=detail,
            )
            return {
                "status": "ok",
                "session_id": session_id,
                "action": action,
                "active_surface": detail["active_surface"],
                "result": {
                    "summary": summary,
                    "details": details,
                    "counts": deepcopy(self._skill_counts()),
                    "policy": {
                        "mode": self._skill_policy_mode,
                        "allowlist": sorted(self._skill_allowlist),
                        "denylist": sorted(self._skill_denylist),
                    },
                },
            }
        if action == "disable":
            if skill_name:
                self._skill_denylist.add(self._skill_key(skill_name))
                self._skill_allowlist.discard(self._skill_key(skill_name))
            summary = f"disabled {skill_name} in workspace policy"
            details = self._skill_policy_details()
            self._append_skill_command_message(
                command=f"skill disable {skill_name}",
                summary=summary,
                content=details,
                detail=detail,
            )
            return {
                "status": "ok",
                "session_id": session_id,
                "action": action,
                "active_surface": detail["active_surface"],
                "result": {
                    "summary": summary,
                    "details": details,
                    "counts": deepcopy(self._skill_counts()),
                    "policy": {
                        "mode": self._skill_policy_mode,
                        "allowlist": sorted(self._skill_allowlist),
                        "denylist": sorted(self._skill_denylist),
                    },
                },
            }
        if action == "reset":
            self._skill_policy_mode = "all"
            self._skill_allowlist.clear()
            self._skill_denylist.clear()
            summary = "workspace skill policy reset"
            details = self._skill_policy_details()
            self._append_skill_command_message(
                command="skill reset",
                summary=summary,
                content=details,
                detail=detail,
            )
            return {
                "status": "ok",
                "session_id": session_id,
                "action": action,
                "active_surface": detail["active_surface"],
                "result": {
                    "summary": summary,
                    "details": details,
                    "counts": deepcopy(self._skill_counts()),
                    "policy": {
                        "mode": self._skill_policy_mode,
                        "allowlist": sorted(self._skill_allowlist),
                        "denylist": sorted(self._skill_denylist),
                    },
                },
            }
        details = self._skill_catalog_details()
        summary = (
            f"{self._skill_counts()['total']} skill(s) refreshed | {self._skill_counts()['active']} active | "
            f"{self._skill_counts()['ready']} ready | {self._skill_counts()['blocked']} blocked"
        )
        self._append_skill_command_message(
            command="skill refresh",
            summary=summary,
            content=details,
            detail=detail,
        )
        return {
            "status": "ok",
            "session_id": session_id,
            "action": action,
            "active_surface": detail["active_surface"],
            "result": {
                "summary": summary,
                "details": details,
                "counts": deepcopy(self._skill_counts()),
            },
        }

    async def delete_session(self, session_id: str) -> dict[str, Any]:
        self.delete_calls.append(session_id)
        detail = self._sessions.pop(session_id, None)
        if detail is None:
            raise RuntimeError(f"Gateway HTTP 404: Session not found: {session_id}")
        detail["deleted"] = True
        return {"status": "deleted", "session_id": session_id}


def test_tui_session_rename_and_delete_commands(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr("mini_agent.memory.memoria_runtime.Path.home", classmethod(lambda cls: tmp_path))

    state_path = tmp_path / ".mini-agent" / "tui_sessions.json"
    app = _new_app(tmp_path, state_path=state_path)

    asyncio.run(app._run_command("session rename Focus"))
    assert app.current_session.title == "Focus"
    first_id = app.current_session.session_id

    asyncio.run(app._run_command("session new"))
    second_id = app.current_session.session_id
    assert second_id != first_id

    asyncio.run(app._run_command(f"session delete {first_id}"))
    assert len(app.sessions) == 1
    assert app.current_session.session_id == second_id

    asyncio.run(app._run_command(f"session delete {second_id}"))
    assert len(app.sessions) == 1
    assert app.current_session.session_id != second_id
    assert app.current_session.title.startswith("Session")


def test_tui_fork_command_creates_child_session_and_runs_prompt(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr("mini_agent.memory.memoria_runtime.Path.home", classmethod(lambda cls: tmp_path))

    state_path = tmp_path / ".mini-agent" / "tui_sessions.json"
    gateway = FakeGatewayClient(profile="remote")
    app = _new_app(tmp_path, state_path=state_path, gateway_client=gateway)

    parent_id = app.current_session.session_id

    asyncio.run(app._run_command("fork Investigate the startup regression"))

    assert app.current_session.session_id != parent_id
    assert app.current_session.title.startswith("Task:")
    assert gateway.derived_create_calls[-1]["parent_session_id"] == parent_id
    assert gateway.chat_calls[-1]["session_id"] == app.current_session.session_id
    assert gateway.chat_calls[-1]["message"] == "Investigate the startup regression"


def test_tui_task_new_command_creates_child_session_without_prompt(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr("mini_agent.memory.memoria_runtime.Path.home", classmethod(lambda cls: tmp_path))

    state_path = tmp_path / ".mini-agent" / "tui_sessions.json"
    gateway = FakeGatewayClient(profile="remote")
    app = _new_app(tmp_path, state_path=state_path, gateway_client=gateway)

    parent_id = app.current_session.session_id

    asyncio.run(app._run_command("task new"))

    assert app.current_session.session_id != parent_id
    assert gateway.derived_create_calls[-1]["parent_session_id"] == parent_id
    assert gateway.chat_calls == []


def test_tui_remote_context_command_routes_through_gateway_and_syncs_state(tmp_path: Path) -> None:
    state_path = tmp_path / ".mini-agent" / "tui_sessions.json"
    gateway = FakeGatewayClient()
    gateway._detail["prepared_context_diagnostics"] = {
        "turn_count": 2,
        "turns_with_context": 1,
        "turns_without_context": 1,
        "total_items": 1,
    }
    gateway._detail["last_prepared_context"] = {
        "item_count": 1,
        "sources": ["knowledge_base"],
        "items": [
            {
                "source": "knowledge_base",
                "title": "Relevant knowledge base context",
                "content": "Hybrid retrieval combines BM25 and RRF.",
            }
        ],
    }
    app = _new_app(tmp_path, state_path=state_path, gateway_client=gateway)

    asyncio.run(app._sync_remote_sessions_once(focus_current=True))
    remote_index = app._find_session_index("remote-qq-1")
    assert remote_index is not None
    app.session_index = remote_index

    asyncio.run(app._run_command("context include knowledge_base workspace_memory"))
    assert gateway.control_calls[-1] == {
        "session_id": "remote-qq-1",
        "action": "context:include",
        "sources": ["knowledge_base", "workspace_memory"],
        "max_items": None,
        "max_total_chars": None,
        "max_items_per_source": None,
        "surface": "tui",
        "channel_type": "qq",
        "conversation_id": "group:demo",
        "sender_id": "user-1",
    }
    assert app.current_session.projection.context_policy["include_sources"] == ["knowledge_base", "workspace_memory"]
    status_text = app._render_status_panel()
    assert "command" in status_text
    assert "context include" in status_text
    assert app.current_session.projection.supplemental.remote_last_command_summary.startswith("context include | ")
    assert "knowledge_base" in app.current_session.projection.supplemental.remote_last_command_summary
    assert "workspace_memory" in app.current_session.projection.supplemental.remote_last_command_summary

    asyncio.run(app._run_command("context show brief"))
    assert "knowledge_base" in app.current_session.view.messages[-1].content

    asyncio.run(app._run_command("context stats"))
    assert "Context diagnostics:" in app.current_session.view.messages[-1].content


def test_tui_remote_context_budget_routes_structured_request_through_gateway(tmp_path: Path) -> None:
    state_path = tmp_path / ".mini-agent" / "tui_sessions.json"
    gateway = FakeGatewayClient()
    app = _new_app(tmp_path, state_path=state_path, gateway_client=gateway)

    asyncio.run(app._sync_remote_sessions_once(focus_current=True))
    remote_index = app._find_session_index("remote-qq-1")
    assert remote_index is not None
    app.session_index = remote_index

    asyncio.run(app._run_command("context budget 6 3600 2"))

    assert gateway.control_calls[-1] == {
        "session_id": "remote-qq-1",
        "action": "context:budget",
        "sources": [],
        "max_items": 6,
        "max_total_chars": 3600,
        "max_items_per_source": 2,
        "surface": "tui",
        "channel_type": "qq",
        "conversation_id": "group:demo",
        "sender_id": "user-1",
    }
    assert app.current_session.projection.context_policy["max_items"] == 6
    assert app.current_session.projection.context_policy["max_total_chars"] == 3600
    assert app.current_session.projection.context_policy["max_items_per_source"] == 2


def test_tui_remote_tagged_local_runtime_routes_context_commands_locally(monkeypatch, tmp_path: Path) -> None:
    state_path = tmp_path / ".mini-agent" / "tui_sessions.json"
    gateway = FakeGatewayClient(profile="local")
    app = _new_app(tmp_path, state_path=state_path, gateway_client=gateway)
    app.current_session.runtime.agent = SimpleNamespace(last_memory_automation={}, last_runtime_task_memory={})
    app.current_session.projection.prepared_context_diagnostics = {
        "turn_count": 1,
        "turns_with_context": 1,
        "turns_without_context": 0,
        "total_items": 1,
    }

    async def _unexpected_sync(self, session, *, recent_limit: int = 80):  # noqa: ANN001
        _ = (self, session, recent_limit)
        raise AssertionError("gateway sync should not run when local runtime state is attached")

    monkeypatch.setattr(MiniAgentTuiApp, "_sync_remote_session_detail", _unexpected_sync)

    asyncio.run(app._run_command("context include knowledge_base workspace_memory"))
    assert gateway.control_calls == []
    assert app.current_session.projection.context_policy["include_sources"] == ["knowledge_base", "workspace_memory"]

    asyncio.run(app._run_command("context stats"))
    assert "Context diagnostics:" in app.current_session.view.messages[-1].content


def test_tui_remote_session_detail_sync_skips_local_runtime_state(monkeypatch, tmp_path: Path) -> None:
    state_path = tmp_path / ".mini-agent" / "tui_sessions.json"
    gateway = FakeGatewayClient(profile="local")
    app = _new_app(tmp_path, state_path=state_path, gateway_client=gateway)
    app.current_session.runtime.loop_bus = InMemoryLoopMessageBus()
    app.current_session.view.messages = [
        SimpleNamespace(role="assistant", content="keep local detail", timestamp="10:00:00"),
    ]

    async def _unexpected_get_session_detail(*args: Any, **kwargs: Any) -> dict[str, Any]:
        _ = (args, kwargs)
        raise AssertionError("gateway detail fetch should not run for local runtime sessions")

    monkeypatch.setattr(app.gateway_client, "get_session_detail", _unexpected_get_session_detail)

    asyncio.run(app._sync_remote_session_detail(app.current_session))

    assert app.current_session.view.messages[-1].content == "keep local detail"


def test_tui_remote_sync_once_preserves_local_runtime_messages(monkeypatch, tmp_path: Path) -> None:
    state_path = tmp_path / ".mini-agent" / "tui_sessions.json"
    gateway = FakeGatewayClient(profile="local")
    app = _new_app(tmp_path, state_path=state_path, gateway_client=gateway)
    app.current_session.runtime.loop_bus = InMemoryLoopMessageBus()
    app.current_session.view.messages = [
        SimpleNamespace(role="assistant", content="keep local transcript", timestamp="10:00:00"),
    ]

    async def _unexpected_get_session_detail(*args: Any, **kwargs: Any) -> dict[str, Any]:
        _ = (args, kwargs)
        raise AssertionError("gateway detail fetch should not run for local runtime sessions")

    async def _unexpected_get_session_messages(*args: Any, **kwargs: Any) -> list[dict[str, Any]]:
        _ = (args, kwargs)
        raise AssertionError("gateway message fetch should not run for local runtime sessions")

    monkeypatch.setattr(app.gateway_client, "get_session_detail", _unexpected_get_session_detail)
    monkeypatch.setattr(app.gateway_client, "get_session_messages", _unexpected_get_session_messages)

    asyncio.run(app._sync_remote_sessions_once())

    assert app.current_session.view.messages[-1].content == "keep local transcript"


def test_tui_local_memory_consolidated_show_and_search_commands(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("MINI_AGENT_GLOBAL_MEMORY_ROOT", str((tmp_path / "global").resolve()))
    monkeypatch.setattr("mini_agent.memory.memoria_runtime.Path.home", classmethod(lambda cls: tmp_path))

    state_path = tmp_path / ".mini-agent" / "tui_sessions.json"
    app = _new_app(tmp_path, state_path=state_path)
    _write_consolidated_memory(
        tmp_path / "MEMORY.md",
        items=[
            "restart recovery should preserve approval hints",
            "routing guardrails remain workspace scoped",
        ],
        last_updated_utc="2026-04-10T00:00:00+00:00",
    )

    asyncio.run(app._run_command("memory consolidated"))
    assert "Consolidated Memory" in app.current_session.view.messages[-1].content
    assert "restart recovery should preserve approval hints" in app.current_session.view.messages[-1].content

    asyncio.run(app._run_command("memory consolidated search routing"))
    assert "Consolidated Memory Search" in app.current_session.view.messages[-1].content
    assert "routing guardrails remain workspace scoped" in app.current_session.view.messages[-1].content


def test_tui_remote_tagged_local_runtime_routes_memory_commands_locally(monkeypatch, tmp_path: Path) -> None:
    state_path = tmp_path / ".mini-agent" / "tui_sessions.json"
    gateway = FakeGatewayClient(profile="local")
    app = _new_app(tmp_path, state_path=state_path, gateway_client=gateway)
    app.current_session.runtime.agent = SimpleNamespace(last_memory_automation={}, last_runtime_task_memory={})
    local_calls: list[dict[str, Any]] = []

    def _fake_local_memory_action(self, session, **kwargs):  # noqa: ANN001
        _ = (self, session)
        local_calls.append(dict(kwargs))
        return {
            "summary": "local memory",
            "details": "Local memory diagnostics",
        }

    async def _unexpected_remote_memory_action(self, session, **kwargs):  # noqa: ANN001
        _ = (self, session, kwargs)
        raise AssertionError("gateway memory route should not run when local runtime state is attached")

    monkeypatch.setattr(MiniAgentTuiApp, "_run_local_memory_action", _fake_local_memory_action)
    monkeypatch.setattr(MiniAgentTuiApp, "_run_remote_memory_action", _unexpected_remote_memory_action)

    asyncio.run(app._run_command("memory status"))
    assert local_calls[-1]["action"] == "status"
    assert local_calls[-1]["detail_mode"] == "brief"
    assert gateway.memory_calls == []

    app.current_session.projection.busy = True
    before_calls = len(local_calls)
    asyncio.run(app._run_command("memory refresh"))
    assert len(local_calls) == before_calls
    assert "busy" in app.status.lower()


def test_tui_remote_memory_command_routes_through_gateway(tmp_path: Path) -> None:
    state_path = tmp_path / ".mini-agent" / "tui_sessions.json"
    gateway = FakeGatewayClient()
    app = _new_app(tmp_path, state_path=state_path, gateway_client=gateway)

    asyncio.run(app._sync_remote_sessions_once(focus_current=True))
    remote_index = app._find_session_index("remote-qq-1")
    assert remote_index is not None
    app.session_index = remote_index

    asyncio.run(app._run_command("memory show brief"))

    assert gateway.memory_calls[-1]["action"] == "show"
    assert gateway.memory_calls[-1]["detail_mode"] == "brief"
    assert "Memory Diagnostics" in app.current_session.view.messages[-1].content
    status_text = app._render_status_panel()
    assert "command" in status_text
    assert "memory show" in status_text
    assert app.current_session.projection.supplemental.remote_last_command_summary == (
        "memory show | cons fresh | rtm 1+0 | profile 1"
    )


def test_tui_remote_tagged_local_runtime_uses_local_sandbox_diagnostics(monkeypatch, tmp_path: Path) -> None:
    state_path = tmp_path / ".mini-agent" / "tui_sessions.json"
    app = _new_app(tmp_path, state_path=state_path, gateway_client=FakeGatewayClient(profile="local"))
    app.current_session.runtime.agent = SimpleNamespace()

    def _fake_collect_sandbox_diagnostics(*, agent):  # noqa: ANN001
        _ = agent
        return {
            "approval_profile": "plan",
            "access_level": "full-access",
            "sandbox_mode": "unrestricted",
        }

    monkeypatch.setattr("mini_agent.tui.app.collect_sandbox_diagnostics", _fake_collect_sandbox_diagnostics)

    asyncio.run(app._run_command("sandbox status"))

    assert app.current_session.projection.sandbox_diagnostics["approval_profile"] == "plan"
    assert app.current_session.projection.sandbox_diagnostics["access_level"] == "full-access"
    assert app.current_session.projection.sandbox_diagnostics["sandbox_mode"] == "unrestricted"


def test_tui_remote_memory_overview_and_export_route_through_gateway(tmp_path: Path) -> None:
    state_path = tmp_path / ".mini-agent" / "tui_sessions.json"
    gateway = FakeGatewayClient()
    app = _new_app(tmp_path, state_path=state_path, gateway_client=gateway)

    asyncio.run(app._sync_remote_sessions_once(focus_current=True))
    remote_index = app._find_session_index("remote-qq-1")
    assert remote_index is not None
    app.session_index = remote_index

    asyncio.run(app._run_command("memory overview"))
    assert gateway.memory_calls[-1]["action"] == "overview"
    assert "Memory Overview" in app.current_session.view.messages[-1].content
    assert "Session Context" in app.current_session.view.messages[-1].content

    asyncio.run(app._run_command("memory export markdown"))
    assert gateway.memory_calls[-1]["action"] == "export"
    assert gateway.memory_calls[-1]["export_format"] == "markdown"
    assert "Memory Export" in app.current_session.view.messages[-1].content


def test_tui_remote_durable_memory_commands_route_through_gateway(tmp_path: Path) -> None:
    state_path = tmp_path / ".mini-agent" / "tui_sessions.json"
    gateway = FakeGatewayClient()
    app = _new_app(tmp_path, state_path=state_path, gateway_client=gateway)

    asyncio.run(app._sync_remote_sessions_once(focus_current=True))
    remote_index = app._find_session_index("remote-qq-1")
    assert remote_index is not None
    app.session_index = remote_index

    asyncio.run(app._run_command("memory profile Chinese replies"))
    assert gateway.memory_calls[-1]["action"] == "profile"
    assert gateway.memory_calls[-1]["query"] == "Chinese replies"
    assert "Global Profile Memory" in app.current_session.view.messages[-1].content

    asyncio.run(app._run_command("memory notes routing"))
    assert gateway.memory_calls[-1]["action"] == "notes"
    assert gateway.memory_calls[-1]["query"] == "routing"
    assert "Workspace Durable Notes" in app.current_session.view.messages[-1].content

    asyncio.run(app._run_command("memory daily 2026-04-10"))
    assert gateway.memory_calls[-1]["action"] == "daily"
    assert gateway.memory_calls[-1]["day"] == "2026-04-10"
    assert "Workspace Daily Memory" in app.current_session.view.messages[-1].content


def test_tui_remote_consolidated_commands_route_through_gateway(tmp_path: Path) -> None:
    state_path = tmp_path / ".mini-agent" / "tui_sessions.json"
    gateway = FakeGatewayClient()
    app = _new_app(tmp_path, state_path=state_path, gateway_client=gateway)

    asyncio.run(app._sync_remote_sessions_once(focus_current=True))
    remote_index = app._find_session_index("remote-qq-1")
    assert remote_index is not None
    app.session_index = remote_index

    asyncio.run(app._run_command("memory consolidated"))
    assert gateway.memory_calls[-1]["action"] == "consolidated_show"
    assert "Consolidated Memory" in app.current_session.view.messages[-1].content

    asyncio.run(app._run_command("memory consolidated search routing"))
    assert gateway.memory_calls[-1]["action"] == "consolidated_search"
    assert gateway.memory_calls[-1]["query"] == "routing"
    assert "Consolidated Memory Search" in app.current_session.view.messages[-1].content


def test_tui_remote_memory_show_latest_routes_through_gateway(tmp_path: Path) -> None:
    state_path = tmp_path / ".mini-agent" / "tui_sessions.json"
    gateway = FakeGatewayClient()
    app = _new_app(tmp_path, state_path=state_path, gateway_client=gateway)

    asyncio.run(app._sync_remote_sessions_once(focus_current=True))
    remote_index = app._find_session_index("remote-qq-1")
    assert remote_index is not None
    app.session_index = remote_index

    asyncio.run(app._run_command("memory show latest"))

    assert gateway.memory_calls[-1]["action"] == "session_show"
    assert gateway.memory_calls[-1]["engram_id"] == "latest"
    assert "Session Runtime Memory" in app.current_session.view.messages[-1].content
    assert "remembered session detail" in app.current_session.view.messages[-1].content


def test_tui_remote_memory_list_routes_through_gateway(tmp_path: Path) -> None:
    state_path = tmp_path / ".mini-agent" / "tui_sessions.json"
    gateway = FakeGatewayClient()
    app = _new_app(tmp_path, state_path=state_path, gateway_client=gateway)

    asyncio.run(app._sync_remote_sessions_once(focus_current=True))
    remote_index = app._find_session_index("remote-qq-1")
    assert remote_index is not None
    app.session_index = remote_index

    asyncio.run(app._run_command("memory list"))

    assert gateway.memory_calls[-1]["action"] == "list"
    assert gateway.memory_calls[-1]["detail_mode"] == "full"


def test_tui_remote_memory_shared_commands_route_through_gateway(tmp_path: Path) -> None:
    state_path = tmp_path / ".mini-agent" / "tui_sessions.json"
    gateway = FakeGatewayClient()
    app = _new_app(tmp_path, state_path=state_path, gateway_client=gateway)

    asyncio.run(app._sync_remote_sessions_once(focus_current=True))
    remote_index = app._find_session_index("remote-qq-1")
    assert remote_index is not None
    app.session_index = remote_index

    asyncio.run(app._run_command("memory shared list"))
    assert gateway.memory_calls[-1]["action"] == "shared_list"
    assert "Workspace-Shared Runtime Memory" in app.current_session.view.messages[-1].content

    asyncio.run(app._run_command("memory shared clear"))
    assert gateway.memory_calls[-1]["action"] == "shared_clear"
    assert gateway.memory_calls[-1]["detail_mode"] == "full"


def test_tui_remote_memory_mutation_commands_route_through_gateway(tmp_path: Path) -> None:
    state_path = tmp_path / ".mini-agent" / "tui_sessions.json"
    gateway = FakeGatewayClient()
    app = _new_app(tmp_path, state_path=state_path, gateway_client=gateway)

    asyncio.run(app._sync_remote_sessions_once(focus_current=True))
    remote_index = app._find_session_index("remote-qq-1")
    assert remote_index is not None
    app.session_index = remote_index

    asyncio.run(app._run_command("memory promote note latest"))
    assert gateway.memory_calls[-1]["action"] == "promote_note"
    assert gateway.memory_calls[-1]["engram_id"] == "latest"
    assert app.current_session.view.messages[-1].metadata["command"] == "memory promote note"
    assert app.current_session.view.messages[-1].metadata["engram_id"] == "latest"
    assert "Action: promote_note" in app.current_session.view.messages[-1].content
    assert app.current_session.projection.supplemental.remote_last_command_summary == (
        "memory promote note | runtime memory promoted to workspace note"
    )

    asyncio.run(app._run_command("memory promote profile latest"))
    assert gateway.memory_calls[-1]["action"] == "promote_profile"
    assert gateway.memory_calls[-1]["engram_id"] == "latest"
    assert app.current_session.view.messages[-1].metadata["command"] == "memory promote profile"
    assert app.current_session.view.messages[-1].metadata["engram_id"] == "latest"
    assert "Target: global_profile" in app.current_session.view.messages[-1].content

    asyncio.run(app._run_command("memory save note remember routing guardrails"))
    assert gateway.memory_calls[-1]["action"] == "save_note"
    assert gateway.memory_calls[-1]["content"] == "remember routing guardrails"
    assert app.current_session.view.messages[-1].metadata["command"] == "memory save note"
    assert "Action: save_note" in app.current_session.view.messages[-1].content

    asyncio.run(app._run_command("memory save profile user prefers concise updates"))
    assert gateway.memory_calls[-1]["action"] == "save_profile"
    assert gateway.memory_calls[-1]["content"] == "user prefers concise updates"
    assert app.current_session.view.messages[-1].metadata["command"] == "memory save profile"
    assert "Action: save_profile" in app.current_session.view.messages[-1].content
    assert app.current_session.projection.supplemental.remote_last_command_summary == (
        "memory save profile | operator profile fact saved"
    )


def test_tui_remote_skill_commands_route_through_gateway(tmp_path: Path) -> None:
    state_path = tmp_path / ".mini-agent" / "tui_sessions.json"
    gateway = FakeGatewayClient()
    app = _new_app(tmp_path, state_path=state_path, gateway_client=gateway)

    asyncio.run(app._sync_remote_sessions_once(focus_current=True))
    remote_index = app._find_session_index("remote-qq-1")
    assert remote_index is not None
    app.session_index = remote_index

    asyncio.run(app._run_command("skill list"))
    assert gateway.skill_calls[-1]["action"] == "list"
    assert "repo-helper [workspace] active" in app.current_session.view.messages[-1].content

    asyncio.run(app._run_command("skill show repo-helper"))
    assert gateway.skill_calls[-1]["action"] == "show"
    assert gateway.skill_calls[-1]["skill_name"] == "repo-helper"
    assert "Skill: repo-helper" in app.current_session.view.messages[-1].content

    asyncio.run(app._run_command("skill search repo"))
    assert gateway.skill_calls[-1]["action"] == "search"
    assert gateway.skill_calls[-1]["query"] == "repo"
    assert 'Skill matches for "repo"' in app.current_session.view.messages[-1].content


def test_tui_remote_skill_refresh_routes_through_gateway_and_updates_status(tmp_path: Path) -> None:
    state_path = tmp_path / ".mini-agent" / "tui_sessions.json"
    gateway = FakeGatewayClient()
    app = _new_app(tmp_path, state_path=state_path, gateway_client=gateway)

    asyncio.run(app._sync_remote_sessions_once(focus_current=True))
    remote_index = app._find_session_index("remote-qq-1")
    assert remote_index is not None
    app.session_index = remote_index

    asyncio.run(app._run_command("skill refresh"))

    assert gateway.skill_calls[-1]["action"] == "refresh"
    assert app.status == f"Skill catalog refreshed for {app.current_session.title}."
    assert app.current_session.view.messages[-1].metadata["command"] == "skill refresh"
    assert "repo-helper [workspace] active" in app.current_session.view.messages[-1].content
    threads_text = app._render_sessions()
    assert "cmd" in threads_text
    assert "skill refresh | 2" in threads_text
    assert "skill(s) refreshed" in threads_text
    status_text = app._render_status_panel()
    assert "command" in status_text
    assert "skill refresh | 2" in status_text
    assert "skill(s) refreshed" in status_text


def test_tui_remote_skill_uninstall_and_rollback_trigger_remote_sync(
    tmp_path: Path,
    monkeypatch,
) -> None:
    state_path = tmp_path / ".mini-agent" / "tui_sessions.json"
    gateway = FakeGatewayClient()

    async def _manage_session_skill(session_id: str, **kwargs: Any) -> dict[str, Any]:
        gateway.skill_calls.append({"session_id": session_id, **kwargs})
        action = str(kwargs.get("action") or "")
        skill_name = str(kwargs.get("skill_name") or "")
        return {
            "status": "ok",
            "session_id": session_id,
            "action": action,
            "active_surface": "qq",
            "result": {
                "summary": f"{action}ed {skill_name}",
                "details": f"Action: {action}\nSkill: {skill_name}",
            },
        }

    monkeypatch.setattr(gateway, "manage_session_skill", _manage_session_skill)
    app = _new_app(tmp_path, state_path=state_path, gateway_client=gateway)

    sync_calls: list[tuple[str, int]] = []

    async def _sync_remote_session_detail(session, recent_limit: int = 80):
        sync_calls.append((session.session_id, recent_limit))

    refresh_calls: list[str] = []
    monkeypatch.setattr(app, "_sync_remote_session_detail", _sync_remote_session_detail)
    monkeypatch.setattr(
        app,
        "_refresh_skill_catalog_signature_baseline",
        lambda: refresh_calls.append("refreshed"),
    )

    asyncio.run(app._sync_remote_sessions_once(focus_current=True))
    remote_index = app._find_session_index("remote-qq-1")
    assert remote_index is not None
    app.session_index = remote_index

    asyncio.run(app._run_command("skill uninstall repo-helper"))
    asyncio.run(app._run_command("skill rollback repo-helper"))

    assert [call["action"] for call in gateway.skill_calls[-2:]] == ["uninstall", "rollback"]
    assert sync_calls == [("remote-qq-1", 80), ("remote-qq-1", 80)]
    assert refresh_calls == ["refreshed", "refreshed"]


def test_tui_remote_skill_show_missing_routes_through_gateway(tmp_path: Path) -> None:
    state_path = tmp_path / ".mini-agent" / "tui_sessions.json"
    gateway = FakeGatewayClient()
    app = _new_app(tmp_path, state_path=state_path, gateway_client=gateway)

    asyncio.run(app._sync_remote_sessions_once(focus_current=True))
    remote_index = app._find_session_index("remote-qq-1")
    assert remote_index is not None
    app.session_index = remote_index

    asyncio.run(app._run_command("skill show missing-skill"))

    assert gateway.skill_calls[-1]["action"] == "show"
    assert gateway.skill_calls[-1]["skill_name"] == "missing-skill"
    assert app.status == "Skill not found."
    assert "Skill not found: missing-skill" in app.current_session.view.messages[-1].content
    assert app.current_session.projection.supplemental.remote_last_command_summary == "skill show | skill not found"


def test_tui_remote_skill_policy_commands_route_through_gateway(tmp_path: Path) -> None:
    state_path = tmp_path / ".mini-agent" / "tui_sessions.json"
    gateway = FakeGatewayClient()
    app = _new_app(tmp_path, state_path=state_path, gateway_client=gateway)

    asyncio.run(app._sync_remote_sessions_once(focus_current=True))
    remote_index = app._find_session_index("remote-qq-1")
    assert remote_index is not None
    app.session_index = remote_index

    asyncio.run(app._run_command("skill active"))
    assert gateway.skill_calls[-1]["action"] == "active"
    assert "Workspace Skill Policy:" in app.current_session.view.messages[-1].content
    assert app.current_session.projection.supplemental.remote_last_command_summary == "skill active | 2 active skill(s) | mode all"

    asyncio.run(app._run_command("skill mode allowlist"))
    assert gateway.skill_calls[-1]["action"] == "mode"
    assert gateway.skill_calls[-1]["mode"] == "allowlist"
    assert app.current_session.view.messages[-1].metadata["command"] == "skill mode allowlist"
    assert "- mode allowlist" in app.current_session.view.messages[-1].content
    assert app.current_session.projection.supplemental.remote_last_command_summary == (
        "skill mode allowlist | skill mode set to allowlist"
    )

    asyncio.run(app._run_command("skill enable doc-coauthoring"))
    assert gateway.skill_calls[-1]["action"] == "enable"
    assert gateway.skill_calls[-1]["skill_name"] == "doc-coauthoring"
    assert app.current_session.view.messages[-1].metadata["command"] == "skill enable doc-coauthoring"
    assert "active skills: doc-coauthoring" in app.current_session.view.messages[-1].content
    assert app.current_session.projection.supplemental.remote_last_command_summary == (
        "skill enable doc-coauthoring | enabled doc-coauthoring in workspace policy"
    )

    asyncio.run(app._run_command("skill disable repo-helper"))
    assert gateway.skill_calls[-1]["action"] == "disable"
    assert gateway.skill_calls[-1]["skill_name"] == "repo-helper"
    assert app.current_session.view.messages[-1].metadata["command"] == "skill disable repo-helper"
    assert "denylist repo-helper" in app.current_session.view.messages[-1].content
    assert app.current_session.projection.supplemental.remote_last_command_summary == (
        "skill disable repo-helper | disabled repo-helper in workspace policy"
    )

    asyncio.run(app._run_command("skill reset"))
    assert gateway.skill_calls[-1]["action"] == "reset"
    assert app.current_session.view.messages[-1].metadata["command"] == "skill reset"
    assert "- mode all" in app.current_session.view.messages[-1].content
    assert "active skills: doc-coauthoring, repo-helper" in app.current_session.view.messages[-1].content
    assert app.current_session.projection.supplemental.remote_last_command_summary == "skill reset | workspace skill policy reset"


def test_tui_remote_skill_list_handles_disabled_status(tmp_path: Path, monkeypatch) -> None:
    state_path = tmp_path / ".mini-agent" / "tui_sessions.json"
    gateway = FakeGatewayClient()

    async def _disabled_manage_session_skill(session_id: str, **kwargs: Any) -> dict[str, Any]:
        _ = (session_id, kwargs)
        gateway.skill_calls.append({"session_id": session_id, **kwargs})
        return {
            "status": "disabled",
            "session_id": "remote-qq-1",
            "action": "list",
            "active_surface": "qq",
            "result": {
                "summary": "skill support disabled",
                "details": "Skill support is disabled in the active configuration.",
            },
        }

    monkeypatch.setattr(gateway, "manage_session_skill", _disabled_manage_session_skill)
    app = _new_app(tmp_path, state_path=state_path, gateway_client=gateway)

    asyncio.run(app._sync_remote_sessions_once(focus_current=True))
    remote_index = app._find_session_index("remote-qq-1")
    assert remote_index is not None
    app.session_index = remote_index

    asyncio.run(app._run_command("skill list"))

    assert gateway.skill_calls[-1]["action"] == "list"
    assert app.status == "Skill support is disabled."
    assert "Skill support is disabled in the active configuration." in app.current_session.view.messages[-1].content
    assert app.current_session.projection.supplemental.remote_last_command_summary == "skill list | skill support disabled"


def test_tui_remote_skill_list_handles_unavailable_status(tmp_path: Path, monkeypatch) -> None:
    state_path = tmp_path / ".mini-agent" / "tui_sessions.json"
    gateway = FakeGatewayClient()

    async def _unavailable_manage_session_skill(session_id: str, **kwargs: Any) -> dict[str, Any]:
        _ = (session_id, kwargs)
        gateway.skill_calls.append({"session_id": session_id, **kwargs})
        return {
            "status": "unavailable",
            "session_id": "remote-qq-1",
            "action": "list",
            "active_surface": "qq",
            "result": {
                "summary": "skill catalog unavailable",
                "details": "Skill catalog unavailable: boom",
            },
        }

    monkeypatch.setattr(gateway, "manage_session_skill", _unavailable_manage_session_skill)
    app = _new_app(tmp_path, state_path=state_path, gateway_client=gateway)

    asyncio.run(app._sync_remote_sessions_once(focus_current=True))
    remote_index = app._find_session_index("remote-qq-1")
    assert remote_index is not None
    app.session_index = remote_index

    asyncio.run(app._run_command("skill list"))

    assert gateway.skill_calls[-1]["action"] == "list"
    assert app.status == "Skill catalog unavailable."
    assert "Skill catalog unavailable: boom" in app.current_session.view.messages[-1].content
    assert app.current_session.projection.supplemental.remote_last_command_summary == "skill list | skill catalog unavailable"


def test_tui_remote_skill_mode_handles_disabled_status_consistently(tmp_path: Path, monkeypatch) -> None:
    state_path = tmp_path / ".mini-agent" / "tui_sessions.json"
    gateway = FakeGatewayClient()

    async def _disabled_manage_session_skill(session_id: str, **kwargs: Any) -> dict[str, Any]:
        _ = session_id
        gateway.skill_calls.append({"session_id": session_id, **kwargs})
        return {
            "status": "disabled",
            "session_id": "remote-qq-1",
            "action": "mode",
            "active_surface": "qq",
            "result": {
                "summary": "skill support disabled",
                "details": "Skill support is disabled in the active configuration.",
            },
        }

    monkeypatch.setattr(gateway, "manage_session_skill", _disabled_manage_session_skill)
    app = _new_app(tmp_path, state_path=state_path, gateway_client=gateway)

    asyncio.run(app._sync_remote_sessions_once(focus_current=True))
    remote_index = app._find_session_index("remote-qq-1")
    assert remote_index is not None
    app.session_index = remote_index

    asyncio.run(app._run_command("skill mode allowlist"))

    assert gateway.skill_calls[-1]["action"] == "mode"
    assert gateway.skill_calls[-1]["mode"] == "allowlist"
    assert app.status == "Skill support is disabled."
    assert "Skill support is disabled in the active configuration." in app.current_session.view.messages[-1].content


def test_tui_remote_skill_mode_handles_unavailable_status_consistently(tmp_path: Path, monkeypatch) -> None:
    state_path = tmp_path / ".mini-agent" / "tui_sessions.json"
    gateway = FakeGatewayClient()

    async def _unavailable_manage_session_skill(session_id: str, **kwargs: Any) -> dict[str, Any]:
        _ = session_id
        gateway.skill_calls.append({"session_id": session_id, **kwargs})
        return {
            "status": "unavailable",
            "session_id": "remote-qq-1",
            "action": "mode",
            "active_surface": "qq",
            "result": {
                "summary": "skill catalog unavailable",
                "details": "Skill catalog unavailable: boom",
            },
        }

    monkeypatch.setattr(gateway, "manage_session_skill", _unavailable_manage_session_skill)
    app = _new_app(tmp_path, state_path=state_path, gateway_client=gateway)

    asyncio.run(app._sync_remote_sessions_once(focus_current=True))
    remote_index = app._find_session_index("remote-qq-1")
    assert remote_index is not None
    app.session_index = remote_index

    asyncio.run(app._run_command("skill mode allowlist"))

    assert gateway.skill_calls[-1]["action"] == "mode"
    assert gateway.skill_calls[-1]["mode"] == "allowlist"
    assert app.status == "Skill catalog unavailable."
    assert "Skill catalog unavailable: boom" in app.current_session.view.messages[-1].content


def test_tui_remote_skill_unknown_action_shows_consistent_operator_message(tmp_path: Path) -> None:
    state_path = tmp_path / ".mini-agent" / "tui_sessions.json"
    gateway = FakeGatewayClient()
    app = _new_app(tmp_path, state_path=state_path, gateway_client=gateway)

    asyncio.run(app._sync_remote_sessions_once(focus_current=True))
    remote_index = app._find_session_index("remote-qq-1")
    assert remote_index is not None
    app.session_index = remote_index

    asyncio.run(app._run_command("skill frob"))

    assert gateway.skill_calls == []
    assert app.status == "Unknown skill action."
    assert "Unknown skill action: frob." in app.current_session.view.messages[-1].content


def test_tui_local_skill_unknown_action_shows_consistent_operator_message(tmp_path: Path, monkeypatch) -> None:
    state_path = tmp_path / ".mini-agent" / "tui_sessions.json"
    builtin_dir = tmp_path / "builtin-skills"
    _write_skill(
        builtin_dir / "doc-coauthoring",
        name="doc-coauthoring",
        description="Draft structured docs with the user.",
        body="Use this skill for documentation.",
    )
    config = Config(
        llm=LLMConfig(
            api_key="sk-test",
            api_base="https://api.example.com/v1",
            model="model-default",
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
            enable_skills=True,
            enable_mcp=False,
            skills_dir=str(builtin_dir),
        ),
    )
    monkeypatch.setattr("mini_agent.commands.skill_support.Config.load", lambda allow_interactive_setup=False: config)
    app = _new_app(tmp_path, state_path=state_path)

    asyncio.run(app._run_command("skill frob"))

    assert app.status == "Unknown skill action."
    assert "Unknown skill action: frob." in app.current_session.view.messages[-1].content


def test_tui_models_assign_color_bands_for_selected_and_adjacent_items(tmp_path: Path) -> None:
    state_path = tmp_path / ".mini-agent" / "tui_sessions.json"
    app = _new_app(tmp_path, state_path=state_path)

    asyncio.run(app._run_command("model next"))
    rendered_lines = app._render_models().splitlines()
    line_styles = list(app._models_line_styles)
    pairs = [(line.strip(), style) for line, style in zip(rendered_lines, line_styles) if line.strip()]

    assert any(line.startswith("> OpenAI [P] | default") and style == "current:provider" for line, style in pairs)
    assert any(line == "gpt-5.4" and style == "current:provider-detail" for line, style in pairs)
    assert any(line.startswith("Anthropic [P] | default") and style == "near:provider" for line, style in pairs)
    assert any(line == "claude-3-7-sonnet" and style == "near:provider-detail" for line, style in pairs)
    assert any(line.startswith(">  GPT-5.3 [gpt-5.3]") and style == "current:model" for line, style in pairs)
    assert any(line.startswith("* GPT-5.4 [gpt-5.4]") and style == "near:model" for line, style in pairs)


def test_tui_models_panel_windows_providers_and_candidates_around_cursor(tmp_path: Path) -> None:
    state_path = tmp_path / ".mini-agent" / "tui_sessions.json"
    registry = DummyRegistry()
    registry.providers.extend(
        [
            {
                "source": "preset",
                "provider_id": "provider-2",
                "provider_name": "Provider 2",
                "default_model_id": "model-2a",
                "models": [{"model_id": "model-2a", "display_name": "Model 2A", "is_default": True}],
            },
            {
                "source": "preset",
                "provider_id": "provider-3",
                "provider_name": "Provider 3",
                "default_model_id": "model-3a",
                "models": [{"model_id": "model-3a", "display_name": "Model 3A", "is_default": True}],
            },
            {
                "source": "preset",
                "provider_id": "provider-4",
                "provider_name": "Provider 4",
                "default_model_id": "model-4d",
                "models": [
                    {"model_id": "model-4a", "display_name": "Model 4A", "is_default": False},
                    {"model_id": "model-4b", "display_name": "Model 4B", "is_default": False},
                    {"model_id": "model-4c", "display_name": "Model 4C", "is_default": False},
                    {"model_id": "model-4d", "display_name": "Model 4D", "is_default": True},
                    {"model_id": "model-4e", "display_name": "Model 4E", "is_default": False},
                    {"model_id": "model-4f", "display_name": "Model 4F", "is_default": False},
                    {"model_id": "model-4g", "display_name": "Model 4G", "is_default": False},
                ],
            },
            {
                "source": "preset",
                "provider_id": "provider-5",
                "provider_name": "Provider 5",
                "default_model_id": "model-5a",
                "models": [{"model_id": "model-5a", "display_name": "Model 5A", "is_default": True}],
            },
            {
                "source": "preset",
                "provider_id": "provider-6",
                "provider_name": "Provider 6",
                "default_model_id": "model-6a",
                "models": [{"model_id": "model-6a", "display_name": "Model 6A", "is_default": True}],
            },
        ]
    )
    app = _new_app(tmp_path, state_path=state_path, registry=registry)

    assert app._set_model_cursor_by_identity(("preset", "provider-4", "model-4d")) is True
    rendered = app._render_models()

    assert "Providers" in rendered
    assert "Provider 4 [P] | default" in rendered
    assert "Provider 5 [P] | default" in rendered
    assert "OpenAI [P]" not in rendered
    assert "Anthropic [P]" not in rendered
    assert rendered.count("  ...") >= 2
    assert "Models (Provider 4)" in rendered
    assert "  >* Model 4D [model-4d]" in rendered
    assert "Model 4A [model-4a]" not in rendered
    assert "Model 4G [model-4g]" not in rendered


def test_tui_model_use_updates_focus_to_selected_model(monkeypatch, tmp_path: Path) -> None:
    state_path = tmp_path / ".mini-agent" / "tui_sessions.json"
    app = _new_app(tmp_path, state_path=state_path)
    monkeypatch.setattr("mini_agent.tui.app.build_agent_kernel", _fake_kernel_builder())

    asyncio.run(app._run_command("model use openai gpt-5.3"))

    selected = app._selected_provider_and_model()
    assert selected is not None
    provider, model = selected
    assert provider["provider_id"] == "openai"
    assert model["model_id"] == "gpt-5.3"


def test_tui_model_limit_show_uses_selected_model(tmp_path: Path) -> None:
    state_path = tmp_path / ".mini-agent" / "tui_sessions.json"
    registry = DummyRegistry()
    registry.providers[0]["models"][0]["learned_token_limit"] = 128_000
    app = _new_app(tmp_path, state_path=state_path, registry=registry)

    asyncio.run(app._run_command("model limit show"))

    last_message = app.current_session.view.messages[-1]
    assert "learned  | 128,000" in str(last_message.content)
    assert "context  | 1,050,000" in str(last_message.content)
    assert "effective| 128,000 (learned_token_limit)" in str(last_message.content)


def test_tui_layout_uses_main_column_with_right_sidebar(tmp_path: Path) -> None:
    state_path = tmp_path / ".mini-agent" / "tui_sessions.json"
    app = _new_app(tmp_path, state_path=state_path)

    layout = app._build_layout()

    assert isinstance(layout.content, HSplit)
    assert len(layout.content.children) == 3
    assert layout.content.height.weight == 1
    body = layout.content.children[1]
    assert isinstance(body, VSplit)
    assert len(body.children) == 2
    assert isinstance(body.children[0], HSplit)
    assert isinstance(body.children[1], HSplit)
    assert body.height.weight == 1
    assert body.children[0].height.weight == 1
    assert body.children[1].height.weight == 1


def test_tui_layout_includes_completion_menu_float(tmp_path: Path) -> None:
    state_path = tmp_path / ".mini-agent" / "tui_sessions.json"
    app = _new_app(tmp_path, state_path=state_path)

    layout = app._build_layout()

    assert isinstance(layout, FloatContainer)
    assert len(layout.floats) >= 2
    completion_float = next(
        (
            item
            for item in layout.floats
            if item.xcursor
            and item.ycursor
            and isinstance(item.content, ConditionalContainer)
            and isinstance(item.content.content, CompletionsMenu)
        ),
        None,
    )
    assert completion_float is not None


def test_tui_footer_surfaces_model_navigation_hint(tmp_path: Path) -> None:
    state_path = tmp_path / ".mini-agent" / "tui_sessions.json"
    app = _new_app(tmp_path, state_path=state_path)

    footer = "".join(fragment for _style, fragment in app._render_footer())

    assert "Ctrl+Left/Right model" in footer


def test_tui_header_stays_static_without_activity_indicator(tmp_path: Path, monkeypatch) -> None:
    state_path = tmp_path / ".mini-agent" / "tui_sessions.json"
    app = _new_app(tmp_path, state_path=state_path)

    monkeypatch.setattr("mini_agent.tui.app.time.monotonic", lambda: 0.0)
    header = "".join(fragment for _style, fragment in app._render_header())

    assert "Mini-Agent" in header
    assert "| Session 1 |" in header
    assert "threads=1" in header
    assert "ctx" not in header
    assert "[.........." not in header
    assert "idle" not in header


def test_tui_status_panel_omits_global_activity_bar(tmp_path: Path, monkeypatch) -> None:
    state_path = tmp_path / ".mini-agent" / "tui_sessions.json"
    app = _new_app(tmp_path, state_path=state_path)
    app.current_session.projection.busy = True
    app.current_session.projection.running_state = "step 1: running search"

    monkeypatch.setattr("mini_agent.tui.app.time.monotonic", lambda: 0.16)
    header = "".join(fragment for _style, fragment in app._render_header())
    status_text = app._render_status_panel()

    assert "[.........." not in header
    assert "working" not in header
    assert "agent | [" not in status_text
    assert "state    | busy" in status_text


def test_tui_prompt_title_shows_activity_indicator(tmp_path: Path, monkeypatch) -> None:
    state_path = tmp_path / ".mini-agent" / "tui_sessions.json"
    app = _new_app(tmp_path, state_path=state_path)
    app.current_session.projection.busy = True
    app.current_session.projection.running_state = "step 1: running search"

    monkeypatch.setattr("mini_agent.tui.app.time.monotonic", lambda: 0.16)
    title = "".join(fragment for _style, fragment in app._render_prompt_title())

    assert "Prompt" in title
    assert "working" in title
    assert ">" in title or "<" in title


def test_tui_prompt_title_uses_active_bracket_style_when_busy(tmp_path: Path, monkeypatch) -> None:
    state_path = tmp_path / ".mini-agent" / "tui_sessions.json"
    app = _new_app(tmp_path, state_path=state_path)
    app.current_session.projection.busy = True
    app.current_session.projection.running_state = "step 1: running search"

    monkeypatch.setattr("mini_agent.tui.app.time.monotonic", lambda: 0.16)
    fragments = app._render_prompt_title()
    bracket_styles = [style for style, text in fragments if text in {"[", "]"}]

    assert "class:header.activity.bracket.active" in bracket_styles


def test_tui_threads_activity_bar_uses_prompt_activity_styles(tmp_path: Path, monkeypatch) -> None:
    state_path = tmp_path / ".mini-agent" / "tui_sessions.json"
    app = _new_app(tmp_path, state_path=state_path)
    app.current_session.projection.busy = True
    app.current_session.projection.running_state = "step 1: running search"

    monkeypatch.setattr("mini_agent.tui.app.time.monotonic", lambda: 0.16)
    app._before_render(app.application)
    state_line_index = next(
        index
        for index, line in enumerate(app.sessions_panel.buffer.document.text.splitlines())
        if "state | working [" in line
    )

    fragments = app.sessions_panel.window.content.lexer.lex_document(app.sessions_panel.buffer.document)(state_line_index)
    styles = [style for style, _text in fragments]

    assert "class:header.activity.bracket.active" in styles
    assert any(style in {"class:header.activity.head", "class:header.activity.tail", "class:header.activity.trail"} for style in styles)


def test_tui_thread_title_fragments_style_live_focus_and_remote_tags(tmp_path: Path) -> None:
    state_path = tmp_path / ".mini-agent" / "tui_sessions.json"
    app = _new_app(tmp_path, state_path=state_path, gateway_client=FakeGatewayClient())

    asyncio.run(app._sync_remote_sessions_once())
    app.session_index = app._find_session_index("remote-qq-1") or 0
    app._before_render(app.application)

    title_line_index = next(
        index
        for index, line in enumerate(app.sessions_panel.buffer.document.text.splitlines())
        if "[QQ]" in line and "[live]" in line and "[focus]" in line
    )
    fragments = app.sessions_panel.window.content.lexer.lex_document(app.sessions_panel.buffer.document)(title_line_index)
    styles = [style for style, _text in fragments]

    assert "class:sidebar.thread.current.tag.source" in styles
    assert "class:sidebar.thread.current.tag.live" in styles
    assert "class:sidebar.thread.current.tag.focus" in styles


def test_tui_chat_render_separates_user_and_assistant_blocks(tmp_path: Path) -> None:
    state_path = tmp_path / ".mini-agent" / "tui_sessions.json"
    app = _new_app(tmp_path, state_path=state_path)

    app.current_session.view.messages = [
        SimpleNamespace(role="user", content="hello there", timestamp="10:00:00"),
        SimpleNamespace(role="assistant", content="hi back", timestamp="10:00:01"),
    ]

    rendered = app._render_chat()

    assert "YOU  10:00:00\n| hello there" in rendered
    assert "\n\nMINI-AGENT  10:00:01\n| hi back" in rendered


def test_tui_chat_panel_uses_message_window_with_wrapping(tmp_path: Path) -> None:
    state_path = tmp_path / ".mini-agent" / "tui_sessions.json"
    app = _new_app(tmp_path, state_path=state_path)

    assert isinstance(app.chat_panel, Window)
    assert bool(app.chat_panel.wrap_lines()) is True
    assert any(isinstance(margin, ScrollbarMargin) for margin in app.chat_panel.right_margins)


def test_tui_chat_render_normalizes_multiline_content_for_terminal_display(tmp_path: Path) -> None:
    state_path = tmp_path / ".mini-agent" / "tui_sessions.json"
    app = _new_app(tmp_path, state_path=state_path)

    app.current_session.view.messages = [
        SimpleNamespace(role="user", content="hello\r\nworld\t!", timestamp="10:00:00"),
    ]

    rendered = app._render_chat()

    assert "YOU  10:00:00" in rendered
    assert "| hello" in rendered
    assert "| world   !" in rendered


def test_tui_chat_render_preserves_assistant_paragraphs(tmp_path: Path) -> None:
    state_path = tmp_path / ".mini-agent" / "tui_sessions.json"
    app = _new_app(tmp_path, state_path=state_path)

    app.current_session.view.messages = [
        SimpleNamespace(
            role="assistant",
            content="First paragraph.\n\n- Current state\n- Next action\n\nWrap up.",
            timestamp="10:00:01",
        ),
    ]

    rendered = app._render_chat()

    assert "MINI-AGENT  10:00:01" in rendered
    assert "| First paragraph." in rendered
    assert "| " in rendered
    assert "| - Current state" in rendered
    assert "| - Next action" in rendered
    assert "| Wrap up." in rendered


def test_tui_chat_render_assigns_assistant_hierarchy_styles(tmp_path: Path) -> None:
    state_path = tmp_path / ".mini-agent" / "tui_sessions.json"
    app = _new_app(tmp_path, state_path=state_path)

    app.current_session.view.messages = [
        SimpleNamespace(
            role="assistant",
            content="# Title\n- Bullet\n> Quote\n```py\nprint('ok')\n```",
            timestamp="10:00:01",
        ),
    ]

    lines = app._build_chat_render_lines()
    line_by_text = {line.text: line for line in lines if line.text}

    assert line_by_text["# Title"].style == "class:chat.body.assistant.heading"
    assert line_by_text["- Bullet"].style == "class:chat.body.assistant.list"
    assert line_by_text["> Quote"].style == "class:chat.body.assistant.quote"
    assert line_by_text["+ code: py"].style == "class:chat.body.assistant.code.border"
    assert line_by_text["print('ok')"].style == "class:chat.body.assistant.code"
    assert line_by_text["print('ok')"].prefix == "|   "
    assert line_by_text["+ end code"].style == "class:chat.body.assistant.code.border"

def test_tui_input_box_supports_multiline_composer(tmp_path: Path) -> None:
    state_path = tmp_path / ".mini-agent" / "tui_sessions.json"
    app = _new_app(tmp_path, state_path=state_path)

    assert bool(app.input_box.buffer.multiline()) is True
    assert bool(app.input_box.window.wrap_lines()) is True


def test_tui_panels_share_a_common_surface_background_style(tmp_path: Path) -> None:
    state_path = tmp_path / ".mini-agent" / "tui_sessions.json"
    app = _new_app(tmp_path, state_path=state_path)

    assert "class:panel.surface" in app.status_panel.window.style
    assert "class:panel.surface" in app.sessions_panel.window.style
    assert "class:panel.surface" in app.models_panel.window.style
    assert "class:panel.surface" in app.input_box.window.style
    assert "class:panel.surface" in app.command_box.window.style
    assert "class:panel.surface" in app.command_help.window.style
    assert app.chat_panel.style == "class:chat.panel"


def test_tui_only_chat_panel_uses_deep_blue_background() -> None:
    dark_rules = dict(MiniAgentTuiApp._style_for_mode("dark").style_rules)
    light_rules = dict(MiniAgentTuiApp._style_for_mode("light").style_rules)

    assert dark_rules["chat.panel"] == "fg:#dbeafe bg:#0b1220"
    assert dark_rules["panel.surface"] == "fg:#dbeafe"
    assert light_rules["chat.panel"] == "fg:#dbeafe bg:#0b1220"
    assert light_rules["panel.surface"] == "fg:#1f2937"


def test_tui_session_switch_has_reliable_fallback_shortcuts(tmp_path: Path) -> None:
    state_path = tmp_path / ".mini-agent" / "tui_sessions.json"
    app = _new_app(tmp_path, state_path=state_path)

    key_sequences = {tuple(binding.keys) for binding in app.bindings.bindings}
    binding_map = {tuple(binding.keys): binding for binding in app.bindings.bindings}

    assert (Keys.ControlM,) in key_sequences
    assert (Keys.ControlPageUp,) in key_sequences
    assert (Keys.ControlPageDown,) in key_sequences
    assert (Keys.Up,) in key_sequences
    assert (Keys.Down,) in key_sequences
    assert (Keys.PageUp,) in key_sequences
    assert (Keys.PageDown,) in key_sequences
    assert (Keys.ControlHome,) in key_sequences
    assert (Keys.ControlEnd,) in key_sequences
    assert (Keys.F4,) in key_sequences
    assert (Keys.F5,) in key_sequences
    assert (Keys.Escape, Keys.Up) in key_sequences
    assert (Keys.Escape, Keys.Down) in key_sequences
    assert (Keys.Escape, Keys.ControlM) in key_sequences
    assert binding_map[(Keys.PageUp,)].eager() is True
    assert binding_map[(Keys.PageUp,)].is_global() is True
    assert binding_map[(Keys.PageDown,)].eager() is True
    assert binding_map[(Keys.PageDown,)].is_global() is True
    assert binding_map[(Keys.Up,)].eager() is True
    assert binding_map[(Keys.Up,)].is_global() is True
    assert binding_map[(Keys.Down,)].eager() is True
    assert binding_map[(Keys.Down,)].is_global() is True


def test_tui_running_feedback_from_turn_hooks(tmp_path: Path) -> None:
    state_path = tmp_path / ".mini-agent" / "tui_sessions.json"
    app = _new_app(tmp_path, state_path=state_path)
    fake_agent = FakeTurnAgent(final_message="done")
    app.current_session.runtime.agent = fake_agent

    async def _scenario() -> None:
        turn_task = asyncio.create_task(app._run_chat_turn("hello"))
        await fake_agent.started.wait()
        await fake_agent.ready_for_cancel.wait()
        await asyncio.sleep(0)
        assert app.current_session.projection.busy is True
        assert "step 1" in app.current_session.projection.running_state.lower()
        assert "step 1" in app.status.lower()
        running_chat = app._render_chat()
        assert "ACTIVITY" in running_chat
        assert "thinking" in running_chat
        assert "search" in running_chat
        fake_agent.release.set()
        await turn_task

    asyncio.run(_scenario())

    assert app.current_session.projection.busy is False
    assert app.current_session.projection.running_state == ""
    assert app.current_session.view.messages[-1].role == "assistant"
    assert app.current_session.view.messages[-1].content == "done"
    rendered = app._render_chat()
    assert "ACTIVITY" in rendered
    assert "thinking" in rendered
    assert "planning" in rendered
    assert "ready" in rendered
    assert "MINI-AGENT" in rendered


def test_tui_run_turn_preserves_assistant_multiline_reply(tmp_path: Path) -> None:
    state_path = tmp_path / ".mini-agent" / "tui_sessions.json"
    app = _new_app(tmp_path, state_path=state_path)
    fake_agent = FakeTurnAgent(
        final_message="First paragraph.\n\n- Check config\n- Fix issue\n\nDone.",
    )
    app.current_session.runtime.agent = fake_agent

    async def _scenario() -> None:
        turn_task = asyncio.create_task(app._run_chat_turn("hello"))
        await fake_agent.started.wait()
        await fake_agent.ready_for_cancel.wait()
        fake_agent.release.set()
        await turn_task

    asyncio.run(_scenario())

    rendered = app._render_chat()
    assert "| First paragraph." in rendered
    assert "| - Check config" in rendered
    assert "| - Fix issue" in rendered
    assert "| Done." in rendered

def test_tui_activity_block_shows_shell_command_preview(tmp_path: Path) -> None:
    state_path = tmp_path / ".mini-agent" / "tui_sessions.json"
    app = _new_app(tmp_path, state_path=state_path)
    fake_agent = FakeTurnAgent(
        final_message="done",
        tool_name="bash",
        tool_arguments={"command": "git status --short"},
        tool_result=SimpleNamespace(
            success=True,
            stdout="M README.md\n?? notes.txt",
            stderr="",
            exit_code=0,
            bash_id=None,
            content="M README.md\n?? notes.txt",
        ),
    )
    app.current_session.runtime.agent = fake_agent

    async def _scenario() -> None:
        turn_task = asyncio.create_task(app._run_chat_turn("inspect repo"))
        await fake_agent.started.wait()
        await fake_agent.ready_for_cancel.wait()
        await asyncio.sleep(0)
        chat = app._render_chat()
        assert "shell" in chat
        assert "git status --short" in chat
        assert "step 1:" not in chat
        assert "|     M README.md" not in chat
        fake_agent.release.set()
        await turn_task

    asyncio.run(_scenario())

    final_chat = app._render_chat()
    assert "shell      ok | git status --short | M README.md (+1 more line(s))" in final_chat
    assert "cmd: git status --short" not in final_chat


def test_tui_activity_expand_command_reveals_shell_output(tmp_path: Path) -> None:
    state_path = tmp_path / ".mini-agent" / "tui_sessions.json"
    app = _new_app(tmp_path, state_path=state_path)
    fake_agent = FakeTurnAgent(
        final_message="done",
        tool_name="bash",
        tool_arguments={"command": "git status --short"},
        tool_result=SimpleNamespace(
            success=True,
            stdout="M README.md\n?? notes.txt",
            stderr="",
            exit_code=0,
            bash_id=None,
            content="M README.md\n?? notes.txt",
        ),
    )
    app.current_session.runtime.agent = fake_agent

    async def _scenario() -> None:
        turn_task = asyncio.create_task(app._run_chat_turn("inspect repo"))
        await fake_agent.started.wait()
        await fake_agent.ready_for_cancel.wait()
        fake_agent.release.set()
        await turn_task

    asyncio.run(_scenario())

    compact = app._render_chat()
    assert "shell      ok | git status --short | M README.md (+1 more line(s))" in compact
    assert "|     M README.md" not in compact

    asyncio.run(app._run_command("activity expand"))

    expanded = app._render_chat()
    assert "output:" in expanded
    assert "cmd: git status --short" in expanded
    assert "|     M README.md" in expanded
    assert "|     ?? notes.txt" in expanded
    assert "activity | expanded" in app._render_status_panel()

    asyncio.run(app._run_command("activity collapse"))

    collapsed = app._render_chat()
    assert "shell      ok | git status --short | M README.md (+1 more line(s))" in collapsed
    assert "|     M README.md" not in collapsed


def test_tui_remote_model_use_routes_through_gateway_and_updates_hint(tmp_path: Path) -> None:
    state_path = tmp_path / ".mini-agent" / "tui_sessions.json"
    gateway = FakeGatewayClient()
    app = _new_app(tmp_path, state_path=state_path, gateway_client=gateway)

    asyncio.run(app._sync_remote_sessions_once())
    app.session_index = app._find_session_index("remote-qq-1") or 0

    asyncio.run(app._run_command("model use openai gpt-5.3"))

    assert gateway.model_calls == [
        {
            "session_id": "remote-qq-1",
            "provider_source": "preset",
            "provider_id": "openai",
            "model_id": "gpt-5.3",
            "surface": "tui",
            "channel_type": "qq",
            "conversation_id": "group:demo",
            "sender_id": "user-1",
        }
    ]
    assert app.current_session.projection.selected_model_source == "preset"
    assert app.current_session.projection.selected_provider_id == "openai"
    assert app.current_session.projection.selected_model_id == "gpt-5.3"
    assert app._current_model_hint() == "openai/gpt-5.3"
    assert app.status == "Applied openai/gpt-5.3 to QQ group:demo."
    status_text = app._render_status_panel()
    assert "command" in status_text
    assert "model use | applied" in status_text
    assert app.current_session.projection.supplemental.remote_last_command_summary == "model use | applied openai/gpt-5.3"


def test_tui_remote_tagged_local_runtime_routes_model_use_locally(monkeypatch, tmp_path: Path) -> None:
    state_path = tmp_path / ".mini-agent" / "tui_sessions.json"
    gateway = FakeGatewayClient(profile="local")
    app = _new_app(tmp_path, state_path=state_path, gateway_client=gateway)
    app.current_session.runtime.agent = SimpleNamespace(
        llm=SimpleNamespace(model="gpt-5.4"),
        runtime_route=SimpleNamespace(provider_id="preset-openai", model="gpt-5.4"),
        messages=[Message(role="system", content="sys")],
    )
    monkeypatch.setattr("mini_agent.tui.app.build_agent_kernel", _fake_kernel_builder())

    asyncio.run(app._run_command("model use openai gpt-5.3"))

    assert gateway.model_calls == []
    assert app.current_session.projection.selected_provider_id == "openai"
    assert app.current_session.projection.selected_model_id == "gpt-5.3"
    assert app._current_model_hint() == "openai/gpt-5.3"


def test_tui_command_palette_accepts_leading_slash(tmp_path: Path) -> None:
    state_path = tmp_path / ".mini-agent" / "tui_sessions.json"
    app = _new_app(tmp_path, state_path=state_path)
    captured: dict[str, str] = {}

    async def _fake_run_command(command: str) -> None:
        captured["command"] = command

    app._run_command = _fake_run_command  # type: ignore[method-assign]
    app._schedule = lambda coro: asyncio.run(coro)  # type: ignore[method-assign]

    buffer = SimpleNamespace(text="/help", document=None)
    app._on_command_submit(buffer)

    assert captured["command"] == "help"


def test_tui_remote_model_use_queues_while_remote_session_busy(tmp_path: Path) -> None:
    state_path = tmp_path / ".mini-agent" / "tui_sessions.json"
    gateway = FakeGatewayClient()
    gateway._detail["busy"] = True
    gateway._detail["running_state"] = "qq request running"
    app = _new_app(tmp_path, state_path=state_path, gateway_client=gateway)

    asyncio.run(app._sync_remote_sessions_once())
    app.session_index = app._find_session_index("remote-qq-1") or 0

    asyncio.run(app._run_command("model use openai gpt-5.3"))

    assert app.current_session.projection.selected_model_id == "gpt-5.4"
    assert app.current_session.operator.pending_model_id == "gpt-5.3"
    assert app._current_model_hint() == "openai/gpt-5.4 -> openai/gpt-5.3 queued"
    status_text = app._render_status_panel()
    assert "command" in status_text
    assert "model use | queued" in status_text
    assert app.current_session.projection.supplemental.remote_last_command_summary == "model use | queued openai/gpt-5.3"


def test_tui_remote_compact_command_routes_through_gateway_and_syncs_transcript(tmp_path: Path) -> None:
    state_path = tmp_path / ".mini-agent" / "tui_sessions.json"
    gateway = FakeGatewayClient()
    app = _new_app(tmp_path, state_path=state_path, gateway_client=gateway)

    asyncio.run(app._sync_remote_sessions_once())
    remote_index = app._find_session_index("remote-qq-1")
    assert remote_index is not None
    app.session_index = remote_index

    asyncio.run(app._run_command("compact trim history"))

    assert gateway.control_calls == [
        {
            "session_id": "remote-qq-1",
            "action": "compact",
            "reason": "trim history",
            "surface": "tui",
            "channel_type": "qq",
            "conversation_id": "group:demo",
            "sender_id": "user-1",
        }
    ]
    assert app.current_session.projection.active_surface == "qq"
    assert app.current_session.projection.reply_enabled is True
    assert app.current_session.view.messages[-1].metadata["kind"] == "command"
    assert app.current_session.view.messages[-1].metadata["summary"] == "context compacted"
    assert app.current_session.view.messages[-1].metadata["surface"] == "tui"
    assert "Messages: 12 -> 6" in app.current_session.view.messages[-1].content
    assert "Compacted shared session" in app.status


def test_tui_remote_compact_busy_relies_on_gateway_conflict(tmp_path: Path) -> None:
    state_path = tmp_path / ".mini-agent" / "tui_sessions.json"
    gateway = FakeGatewayClient()
    gateway._detail["busy"] = True
    app = _new_app(tmp_path, state_path=state_path, gateway_client=gateway)

    asyncio.run(app._sync_remote_sessions_once())
    remote_index = app._find_session_index("remote-qq-1")
    assert remote_index is not None
    app.session_index = remote_index

    asyncio.run(app._run_command("compact trim history"))

    assert gateway.control_calls == [
        {
            "session_id": "remote-qq-1",
            "action": "compact",
            "reason": "trim history",
            "surface": "tui",
            "channel_type": "qq",
            "conversation_id": "group:demo",
            "sender_id": "user-1",
        }
    ]
    assert app.current_session.view.messages[-1].metadata["summary"] == "session busy"
    assert "Session is busy. Wait for the current turn to finish." in app.current_session.view.messages[-1].content
    assert app.status == "Session is busy. Wait for the current turn to finish."


def test_tui_local_kb_command_updates_session_state(tmp_path: Path) -> None:
    state_path = tmp_path / ".mini-agent" / "tui_sessions.json"
    app = _new_app(tmp_path, state_path=state_path)

    asyncio.run(app._run_command("kb off"))

    assert app.current_session.projection.knowledge_base_enabled is False
    assert app.current_session.projection.knowledge_base_enabled is False
    assert app.current_session.view.messages[-1].metadata["summary"] == "knowledge base disabled"
    assert "Knowledge base disabled" in app.status

    asyncio.run(app._run_command("kb status"))

    assert app.current_session.view.messages[-1].metadata["summary"] == "knowledge base disabled"


def test_tui_remote_tagged_local_runtime_routes_kb_and_approval_locally(monkeypatch, tmp_path: Path) -> None:
    state_path = tmp_path / ".mini-agent" / "tui_sessions.json"
    gateway = FakeGatewayClient(profile="local")
    app = _new_app(tmp_path, state_path=state_path, gateway_client=gateway)

    class _FakeKbAgent:
        def __init__(self) -> None:
            self.tools: dict[str, Any] = {"knowledge_base_query": object()}

        def set_knowledge_base_enabled(self, enabled: bool) -> bool:
            self.tools = {"knowledge_base_query": object()} if enabled else {}
            return enabled

    class _FakeLoop:
        def __init__(self) -> None:
            self.calls: list[dict[str, Any]] = []

        async def submit_exec_approval(self, *, approved: bool, token: str) -> None:
            self.calls.append({"approved": approved, "token": token})

    loop = _FakeLoop()
    app.current_session.runtime.agent = _FakeKbAgent()
    app.current_session.runtime.submission_loop = loop
    app.current_session.projection.pending_approvals = [
        {
            "token": "approval-local-1",
            "tool_name": "shell",
            "kind": "exec",
        }
    ]

    asyncio.run(app._run_command("kb off"))
    assert gateway.control_calls == []
    assert app.current_session.projection.knowledge_base_enabled is False

    asyncio.run(app._run_command("approve"))
    assert gateway.approval_calls == []
    assert loop.calls == [{"approved": True, "token": "approval-local-1"}]
    assert app.current_session.projection.pending_approvals == []


def test_tui_remote_kb_command_routes_through_gateway_and_syncs_state(tmp_path: Path) -> None:
    state_path = tmp_path / ".mini-agent" / "tui_sessions.json"
    gateway = FakeGatewayClient()
    app = _new_app(tmp_path, state_path=state_path, gateway_client=gateway)

    asyncio.run(app._sync_remote_sessions_once())
    remote_index = app._find_session_index("remote-qq-1")
    assert remote_index is not None
    app.session_index = remote_index

    asyncio.run(app._run_command("kb off"))

    assert gateway.control_calls[-1] == {
        "session_id": "remote-qq-1",
        "action": "kb_off",
        "reason": None,
        "surface": "tui",
        "channel_type": "qq",
        "conversation_id": "group:demo",
        "sender_id": "user-1",
    }
    assert app.current_session.projection.knowledge_base_enabled is False
    assert app.current_session.view.messages[-1].metadata["summary"] == "knowledge base disabled"
    assert "Knowledge base disabled" in app.status


def test_tui_remote_mcp_status_routes_through_gateway(tmp_path: Path) -> None:
    state_path = tmp_path / ".mini-agent" / "tui_sessions.json"
    gateway = FakeGatewayClient()
    app = _new_app(tmp_path, state_path=state_path, gateway_client=gateway)

    asyncio.run(app._sync_remote_sessions_once())
    remote_index = app._find_session_index("remote-qq-1")
    assert remote_index is not None
    app.session_index = remote_index

    asyncio.run(app._run_command("mcp status"))

    last_message = app.current_session.view.messages[-1]
    assert gateway.control_calls[-1] == {
        "session_id": "remote-qq-1",
        "action": "mcp_status",
        "reason": None,
        "surface": "tui",
        "channel_type": "qq",
        "conversation_id": "group:demo",
        "sender_id": "user-1",
    }
    assert last_message.metadata["command"] == "mcp status"
    assert last_message.metadata["summary"] == "1 active server(s) | 2 tool(s)"
    assert "MCP Status:" in last_message.content
    assert app.status == "Shared MCP status shown."


def test_tui_remote_mcp_reload_routes_through_gateway(tmp_path: Path) -> None:
    state_path = tmp_path / ".mini-agent" / "tui_sessions.json"
    gateway = FakeGatewayClient()
    app = _new_app(tmp_path, state_path=state_path, gateway_client=gateway)

    asyncio.run(app._sync_remote_sessions_once())
    remote_index = app._find_session_index("remote-qq-1")
    assert remote_index is not None
    app.session_index = remote_index

    asyncio.run(app._run_command("mcp reload"))

    last_message = app.current_session.view.messages[-1]
    assert gateway.control_calls[-1] == {
        "session_id": "remote-qq-1",
        "action": "mcp_reload",
        "reason": None,
        "surface": "tui",
        "channel_type": "qq",
        "conversation_id": "group:demo",
        "sender_id": "user-1",
    }
    assert last_message.metadata["command"] == "mcp reload"
    assert last_message.metadata["summary"] == "reloaded MCP | 2 active server(s) | 5 tool(s)"
    assert "MCP Status:" in last_message.content
    assert "MCP Servers:" in last_message.content
    assert app.status == "Shared MCP bindings reloaded."


def test_tui_remote_mcp_reload_busy_relies_on_gateway_conflict(tmp_path: Path) -> None:
    state_path = tmp_path / ".mini-agent" / "tui_sessions.json"
    gateway = FakeGatewayClient()
    gateway._detail["busy"] = True
    app = _new_app(tmp_path, state_path=state_path, gateway_client=gateway)

    asyncio.run(app._sync_remote_sessions_once())
    remote_index = app._find_session_index("remote-qq-1")
    assert remote_index is not None
    app.session_index = remote_index

    asyncio.run(app._run_command("mcp reload"))

    assert gateway.control_calls[-1] == {
        "session_id": "remote-qq-1",
        "action": "mcp_reload",
        "reason": None,
        "surface": "tui",
        "channel_type": "qq",
        "conversation_id": "group:demo",
        "sender_id": "user-1",
    }
    assert app.current_session.view.messages[-1].metadata["summary"] == "session busy"
    assert "Session is busy. Wait for the current turn to finish." in app.current_session.view.messages[-1].content
    assert app.status == "Session is busy. Wait for the current turn to finish."


def test_tui_remote_cancel_command_routes_through_gateway(tmp_path: Path) -> None:
    state_path = tmp_path / ".mini-agent" / "tui_sessions.json"
    gateway = FakeGatewayClient()
    gateway._detail["busy"] = True
    gateway._detail["running_state"] = "qq request running"
    app = _new_app(tmp_path, state_path=state_path, gateway_client=gateway)

    asyncio.run(app._sync_remote_sessions_once())
    remote_index = app._find_session_index("remote-qq-1")
    assert remote_index is not None
    app.session_index = remote_index

    asyncio.run(app._run_command("cancel"))

    assert gateway.cancel_calls == [
        {
            "session_id": "remote-qq-1",
            "reason": "user_cancel",
            "surface": "tui",
            "channel_type": None,
            "conversation_id": None,
            "sender_id": None,
        }
    ]
    assert app.current_session.projection.running_state == "cancellation requested"
    assert app.current_session.projection.running_state == "cancellation requested"
    assert app.current_session.view.messages[-1].metadata["command"] == "cancel"
    assert app.current_session.view.messages[-1].metadata["summary"] == "cancellation requested"
    assert "Cancelling turn" in app.status


def test_tui_remote_session_prompt_uses_gateway_shared_session(tmp_path: Path) -> None:
    state_path = tmp_path / ".mini-agent" / "tui_sessions.json"
    gateway = FakeGatewayClient()
    app = _new_app(tmp_path, state_path=state_path, gateway_client=gateway)

    asyncio.run(app._sync_remote_sessions_once())
    app.session_index = app._find_session_index("remote-qq-1") or 0

    asyncio.run(app._handle_prompt("continue from tui"))

    assert gateway.chat_calls[-1]["session_id"] == "remote-qq-1"
    assert gateway.chat_calls[-1]["surface"] == "tui"
    assert app.current_session.view.messages[-1].content == "remote:continue from tui"
    assert app.current_session.projection.active_surface == "tui"
    assert app.current_session.projection.reply_enabled is False
    assert app.current_session.view.tasks[-1].status == "completed"


def test_tui_remote_session_prompt_renders_streamed_activity_blocks(tmp_path: Path) -> None:
    state_path = tmp_path / ".mini-agent" / "tui_sessions.json"
    gateway = FakeGatewayClient()
    app = _new_app(tmp_path, state_path=state_path, gateway_client=gateway)

    asyncio.run(app._sync_remote_sessions_once())
    app.session_index = app._find_session_index("remote-qq-1") or 0

    asyncio.run(app._handle_prompt("stream remote activity"))

    rendered = app._render_chat()
    assert "thinking   planning" in rendered
    assert "shell      ok" in rendered
    assert "pytest -q tests/test_tui_app.py" in rendered
    assert "remote:stream remote activity" in rendered


def test_tui_remote_session_prompt_consumes_delta_reply_stream(tmp_path: Path, monkeypatch) -> None:
    state_path = tmp_path / ".mini-agent" / "tui_sessions.json"
    gateway = FakeGatewayClient()
    app = _new_app(tmp_path, state_path=state_path, gateway_client=gateway)

    async def _no_sync(self, session, *, recent_limit: int = 80):  # noqa: ANN001
        _ = (self, session, recent_limit)
        return None

    monkeypatch.setattr(MiniAgentTuiApp, "_sync_remote_session_detail", _no_sync)

    asyncio.run(app._sync_remote_sessions_once())
    app.session_index = app._find_session_index("remote-qq-1") or 0

    asyncio.run(app._handle_prompt("stream reply only"))

    assert app.current_session.view.messages[-1].role == "assistant"
    assert app.current_session.view.messages[-1].content == "remote:stream reply only"
    assert app.current_session.view.messages[-1].metadata.get("streaming") is False


def test_tui_activity_render_assigns_tool_type_styles(tmp_path: Path) -> None:
    state_path = tmp_path / ".mini-agent" / "tui_sessions.json"
    app = _new_app(tmp_path, state_path=state_path)
    app.current_session.view.messages = [
        SimpleNamespace(
            role="tool",
            content="",
            timestamp="10:00:01",
            metadata={
                "kind": "activity",
                "activity_items": [
                    {"id": "1", "label": "thinking", "detail": "planning", "preview": "", "output_text": "", "output_summary": "", "state": ""},
                    {"id": "2", "label": "shell", "detail": "ok", "preview": "git status", "output_text": "", "output_summary": "", "state": "ok"},
                    {"id": "3", "label": "read-file", "detail": "ok", "preview": "README.md", "output_text": "", "output_summary": "", "state": "ok"},
                    {"id": "4", "label": "search", "detail": "running", "preview": "TODO", "output_text": "", "output_summary": "", "state": "running"},
                ],
            },
        ),
    ]

    lines = app._build_chat_render_lines()
    line_by_text = {line.text: line for line in lines if line.text}

    assert line_by_text["thinking   planning"].style == "class:chat.body.tool.thinking.old"
    assert line_by_text["thinking   planning"].prefix == "| . "
    assert line_by_text["shell      ok | git status"].style == "class:chat.body.tool.shell.old"
    assert line_by_text["shell      ok | git status"].prefix == "| . "
    assert line_by_text["read-file  ok | README.md"].style == "class:chat.body.tool.read.old"
    assert line_by_text["read-file  ok | README.md"].prefix == "| . "
    assert line_by_text["search     running"].style == "class:chat.body.tool.search"
    assert line_by_text["search     running"].prefix == "| > "


def test_tui_usage_prefers_model_context_window_over_reported_token_limit(tmp_path: Path) -> None:
    state_path = tmp_path / ".mini-agent" / "tui_sessions.json"
    app = _new_app(tmp_path, state_path=state_path)
    app.current_session.projection.selected_model_source = "preset"
    app.current_session.projection.selected_provider_id = "openai"
    app.current_session.projection.selected_model_id = "gpt-5.4"
    app.current_session.runtime.agent = SimpleNamespace(
        api_total_tokens=16000,
        token_limit=80000,
        messages=[
            Message(role="system", content="system"),
            Message(role="user", content="hello"),
            Message(role="assistant", content="world"),
        ],
    )

    usage = app._session_usage_stats(app.current_session)
    header = "".join(fragment for _style, fragment in app._render_header())
    status_text = app._render_status_panel()

    assert usage["limit"] == 1_050_000
    assert usage["limit_source"] == "model_context_window"
    assert "2%" in header
    assert "16.0k/1.1m" not in header
    assert "16,000 / 1,050,000" in status_text


def test_tui_prompt_input_slash_completer_suggests_command_candidates(tmp_path: Path) -> None:
    state_path = tmp_path / ".mini-agent" / "tui_sessions.json"
    app = _new_app(tmp_path, state_path=state_path)

    completer = app.input_box.completer
    assert completer is not None

    completions = list(
        completer.get_completions(
            Document("/m", cursor_position=2),
            CompleteEvent(completion_requested=False),
        )
    )
    completion_texts = {completion.text for completion in completions}

    assert "/model" in completion_texts
    assert any(text.startswith("/memory") for text in completion_texts)


def test_tui_accept_completion_uses_first_candidate_when_none_selected(tmp_path: Path) -> None:
    state_path = tmp_path / ".mini-agent" / "tui_sessions.json"
    app = _new_app(tmp_path, state_path=state_path)
    applied: list[Completion] = []
    suppressed_during_apply: list[bool] = []
    state = SimpleNamespace(
        current_completion=None,
        completions=[Completion("session", start_position=-5)],
    )
    buffer = SimpleNamespace(
        complete_state=state,
        document=Document("/sess", cursor_position=5),
        apply_completion=lambda completion: (
            suppressed_during_apply.append(not app._completion_allowed(buffer, slash_only=True)),
            applied.append(completion),
        ),
        cancel_completion=lambda: setattr(buffer, "complete_state", None),
    )

    accepted = app._accept_completion(buffer)

    assert accepted is True
    assert applied
    assert applied[0].text == "session"
    assert buffer.complete_state is None
    assert suppressed_during_apply == [True]


def test_tui_chat_render_cache_reuses_built_lines_until_session_changes(tmp_path: Path, monkeypatch) -> None:
    state_path = tmp_path / ".mini-agent" / "tui_sessions.json"
    app = _new_app(tmp_path, state_path=state_path)
    app._append_message("assistant", "cached reply")
    build_calls = 0
    original = MiniAgentTuiApp._build_chat_render_lines

    def _counted(self):  # noqa: ANN001
        nonlocal build_calls
        build_calls += 1
        return original(self)

    monkeypatch.setattr(MiniAgentTuiApp, "_build_chat_render_lines", _counted)

    fragments = app._render_chat_fragments()
    prefix = app._chat_line_prefix(1, 0)
    cursor = app._chat_cursor_position()

    assert fragments
    assert prefix != ""
    assert cursor.y >= 0
    assert build_calls == 1

    app._append_message("assistant", "new reply")
    app._render_chat_fragments()

    assert build_calls == 2


def test_tui_stream_assistant_reply_updates_message_incrementally(tmp_path: Path, monkeypatch) -> None:
    state_path = tmp_path / ".mini-agent" / "tui_sessions.json"
    app = _new_app(tmp_path, state_path=state_path)
    snapshots: list[str] = []
    content = "Streaming reply for tui with multiple visible chunks"
    app._last_stream_render_at = -1.0

    def _capture_render() -> None:
        if app.current_session.view.messages:
            snapshots.append(app.current_session.view.messages[-1].content)

    app._render_all = _capture_render  # type: ignore[method-assign]
    monkeypatch.setattr("mini_agent.tui.app.time.monotonic", lambda: 0.0)

    asyncio.run(app._stream_assistant_reply(app.current_session, content))

    assert app.current_session.view.messages[-1].role == "assistant"
    assert app.current_session.view.messages[-1].content == content
    assert app.current_session.view.messages[-1].metadata.get("streaming") is False
    assert len(snapshots) >= 2
    assert len(snapshots) <= 3
    assert snapshots[0] != snapshots[-1]
    assert snapshots[-1] == content


def test_tui_run_chat_turn_uses_streaming_reply_helper(tmp_path: Path, monkeypatch) -> None:
    state_path = tmp_path / ".mini-agent" / "tui_sessions.json"
    app = _new_app(tmp_path, state_path=state_path)
    streamed: list[str] = []

    class _FakeLoop:
        async def start(self) -> None:
            return None

        async def submit_user_input(
            self,
            _prompt: str,
            *,
            policy_overrides=None,
            metadata=None,
            start_new_run: bool = True,
        ) -> str:
            _ = (policy_overrides, metadata, start_new_run)
            return "sub-stream"

    async def _fake_wait_for_submission_payload(
        self,
        *,
        session,
        submission_id: str,
        event_start_index: int,
    ) -> dict[str, Any]:
        _ = (self, session, submission_id, event_start_index)
        return {
            "state": "completed",
            "stop_reason": "end_turn",
            "message": "stream me",
            "error": "",
            "prepared_context": {},
        }

    async def _fake_stream_assistant_reply(
        self,
        session,
        content: str,
        *,
        message_index: int | None = None,
    ) -> int:
        _ = message_index
        streamed.append(content)
        return self._append_session_message(session, "assistant", content, metadata={"streaming": False}, persist=False)

    app.current_session.runtime.agent = SimpleNamespace(
        llm=SimpleNamespace(model="gpt-test"),
        messages=[{"role": "system", "content": "sys"}],
        max_steps=3,
        max_tool_calls_per_step=None,
    )
    app.current_session.runtime.submission_loop = _FakeLoop()
    app.current_session.runtime.loop_bus = InMemoryLoopMessageBus()

    monkeypatch.setattr(
        MiniAgentTuiApp,
        "_wait_for_submission_payload",
        _fake_wait_for_submission_payload,
    )
    monkeypatch.setattr(
        MiniAgentTuiApp,
        "_stream_assistant_reply",
        _fake_stream_assistant_reply,
    )

    asyncio.run(app._run_chat_turn("stream locally"))

    assert streamed == ["stream me"]
    assert app.current_session.view.messages[-1].content == "stream me"


def test_tui_usage_prefers_learned_token_limit_over_context_window(tmp_path: Path) -> None:
    state_path = tmp_path / ".mini-agent" / "tui_sessions.json"
    registry = DummyRegistry()
    registry.providers[0]["models"][0]["learned_token_limit"] = 128_000
    app = _new_app(tmp_path, state_path=state_path, registry=registry)
    app.current_session.projection.selected_model_source = "preset"
    app.current_session.projection.selected_provider_id = "openai"
    app.current_session.projection.selected_model_id = "gpt-5.4"
    app.current_session.runtime.agent = SimpleNamespace(
        api_total_tokens=16000,
        token_limit=80000,
        messages=[
            Message(role="system", content="system"),
            Message(role="user", content="hello"),
            Message(role="assistant", content="world"),
        ],
    )

    usage = app._session_usage_stats(app.current_session)

    assert usage["limit"] == 128_000
    assert usage["limit_source"] == "learned_token_limit"


def test_tui_remote_interrupted_session_shows_recovery_summary(tmp_path: Path) -> None:
    state_path = tmp_path / ".mini-agent" / "tui_sessions.json"
    gateway = FakeGatewayClient()
    gateway._detail["recovery"] = {
        "state": "interrupted",
        "summary": "interrupted after restart: qq request running",
        "last_activity": "shell ok | pytest -q | 32 passed",
        "last_user_message": "inspect tests",
        "last_assistant_message": None,
        "pending_approvals": [
            {
                "token": "approval-1",
                "tool_name": "shell",
            }
        ],
    }
    app = _new_app(tmp_path, state_path=state_path, gateway_client=gateway)

    asyncio.run(app._sync_remote_sessions_once())
    app.session_index = app._find_session_index("remote-qq-1") or 0

    threads_text = app._render_sessions()
    status_text = app._render_status_panel()

    assert "state | recovery pending" in threads_text
    assert "state    | interrupted" in status_text
    assert "task     | interrupted after" in status_text
    assert "recover  | interrupted after" in status_text
    assert "activity | shell ok | pytest" in status_text
    assert app._pending_approval_summary(app.current_session) == "restart lost | shell"


def test_tui_status_panel_separates_source_and_execution_for_local_runtime(tmp_path: Path) -> None:
    state_path = tmp_path / ".mini-agent" / "tui_sessions.json"
    app = _new_app(tmp_path, state_path=state_path, gateway_client=FakeGatewayClient(profile="local"))
    app.current_session.runtime.agent = SimpleNamespace()

    status_text = app._render_status_panel()

    assert "scope    | private [tui]" in status_text
    assert "route    | tui / own / local" in status_text
    assert "share    | local only" in status_text
    assert "Channel" not in status_text


def test_tui_status_panel_separates_source_and_execution_for_gateway_session(tmp_path: Path) -> None:
    state_path = tmp_path / ".mini-agent" / "tui_sessions.json"
    gateway = FakeGatewayClient()
    app = _new_app(tmp_path, state_path=state_path, gateway_client=gateway)

    asyncio.run(app._sync_remote_sessions_once())
    app.session_index = app._find_session_index("remote-qq-1") or 0

    status_text = app._render_status_panel()

    assert "scope    | shared [qq]" in status_text
    assert app._session_route_summary(app.current_session) == "qq / reply / gateway"
    assert "Channel" in status_text
    assert "peer     | qq/group:demo" in status_text


def test_tui_chat_history_scroll_updates_status_and_follow_mode(tmp_path: Path) -> None:
    state_path = tmp_path / ".mini-agent" / "tui_sessions.json"
    app = _new_app(tmp_path, state_path=state_path)
    app.current_session.view.messages = [
        SimpleNamespace(role="user", content=f"line {index}", timestamp=f"10:00:{index:02d}")
        for index in range(12)
    ]

    app._scroll_chat_home()

    assert app.current_session.view.chat_follow_output is False
    assert app.current_session.view.chat_scroll_line == 0
    assert "chat     | history" in app._render_status_panel()

    app._scroll_chat_end()

    assert app.current_session.view.chat_follow_output is True
    assert "chat     | live" in app._render_status_panel()


def test_tui_page_scroll_moves_in_fifteen_line_steps(tmp_path: Path) -> None:
    state_path = tmp_path / ".mini-agent" / "tui_sessions.json"
    app = _new_app(tmp_path, state_path=state_path)
    app.current_session.view.messages = [
        SimpleNamespace(role="user", content=f"line {index}", timestamp=f"10:00:{index:02d}")
        for index in range(30)
    ]

    app._scroll_chat_page(1)
    assert app.current_session.view.chat_scroll_line == 15
    assert app.current_session.view.chat_follow_output is False

    app._scroll_chat_page(1)
    assert app.current_session.view.chat_scroll_line == 30

    app._scroll_chat_page(-1)
    assert app.current_session.view.chat_scroll_line == 15


def test_tui_single_line_scroll_moves_one_line_at_a_time(tmp_path: Path) -> None:
    state_path = tmp_path / ".mini-agent" / "tui_sessions.json"
    app = _new_app(tmp_path, state_path=state_path)
    app.current_session.view.messages = [
        SimpleNamespace(role="user", content=f"line {index}", timestamp=f"10:00:{index:02d}")
        for index in range(30)
    ]

    app._scroll_chat_lines(1)
    assert app.current_session.view.chat_scroll_line == 1
    assert app.current_session.view.chat_follow_output is False

    app._scroll_chat_lines(1)
    assert app.current_session.view.chat_scroll_line == 2

    app._scroll_chat_lines(-1)
    assert app.current_session.view.chat_scroll_line == 1


def test_tui_single_line_down_uses_session_scroll_state_when_viewport_is_stale(tmp_path: Path) -> None:
    state_path = tmp_path / ".mini-agent" / "tui_sessions.json"
    app = _new_app(tmp_path, state_path=state_path)
    app.current_session.view.messages = [
        SimpleNamespace(role="user", content=f"line {index}", timestamp=f"10:00:{index:02d}")
        for index in range(30)
    ]
    app.current_session.view.chat_scroll_line = 4
    app.current_session.view.chat_follow_output = False
    app.chat_panel.vertical_scroll = 0

    app._scroll_chat_lines(1)

    assert app.current_session.view.chat_scroll_line == 5
    assert app.chat_panel.vertical_scroll == 5
    assert app.current_session.view.chat_follow_output is False


def test_tui_remote_sync_keeps_history_mode_for_current_session(tmp_path: Path) -> None:
    state_path = tmp_path / ".mini-agent" / "tui_sessions.json"
    gateway = FakeGatewayClient()
    gateway._detail["message_count"] = 20
    gateway._detail["recent_messages"] = [
        {
            "index": index + 1,
            "role": "user" if index % 2 == 0 else "assistant",
            "content": f"remote line {index}",
            "surface": "qq",
            "created_at": f"2026-04-08T10:00:{index:02d}+00:00",
            "channel_type": "qq",
            "conversation_id": "group:demo",
            "sender_id": "user-1",
        }
        for index in range(20)
    ]
    app = _new_app(tmp_path, state_path=state_path, gateway_client=gateway)

    asyncio.run(app._sync_remote_sessions_once())
    remote_index = app._find_session_index("remote-qq-1")
    assert remote_index is not None
    app.session_index = remote_index
    app.chat_panel.vertical_scroll = 4
    app.current_session.view.chat_scroll_line = 4
    app.current_session.view.chat_follow_output = False

    gateway._detail["message_count"] = 22
    gateway._detail["recent_messages"].extend(
        [
            {
                "index": 21,
                "role": "user",
                "content": "new qq message",
                "surface": "qq",
                "created_at": "2026-04-08T10:00:20+00:00",
                "channel_type": "qq",
                "conversation_id": "group:demo",
                "sender_id": "user-1",
            },
            {
                "index": 22,
                "role": "assistant",
                "content": "new qq reply",
                "surface": "qq",
                "created_at": "2026-04-08T10:00:21+00:00",
                "channel_type": "qq",
                "conversation_id": "group:demo",
                "sender_id": "user-1",
            },
        ]
    )

    asyncio.run(app._sync_remote_sessions_once())

    assert app.current_session.view.chat_follow_output is False
    assert app.current_session.view.chat_scroll_line == 4
    assert app.current_session.view.messages[-1].content == "new qq reply"


def test_tui_appending_message_keeps_history_mode_for_current_session(tmp_path: Path) -> None:
    state_path = tmp_path / ".mini-agent" / "tui_sessions.json"
    app = _new_app(tmp_path, state_path=state_path)
    app.current_session.view.messages = [
        SimpleNamespace(role="user", content=f"line {index}", timestamp=f"10:00:{index:02d}")
        for index in range(20)
    ]
    app.chat_panel.vertical_scroll = 3
    app.current_session.view.chat_scroll_line = 3
    app.current_session.view.chat_follow_output = False

    app._append_message("assistant", "new line", persist=False)

    assert app.current_session.view.chat_follow_output is False
    assert app.current_session.view.chat_scroll_line == 3


def test_tui_submit_input_buffer_clears_prompt_immediately(tmp_path: Path) -> None:
    state_path = tmp_path / ".mini-agent" / "tui_sessions.json"
    app = _new_app(tmp_path, state_path=state_path)
    scheduled: list[Any] = []

    async def _fake_handle_prompt(_text: str) -> None:
        return None

    app._handle_prompt = _fake_handle_prompt  # type: ignore[method-assign]
    app._schedule = lambda coro: scheduled.append(coro)  # type: ignore[method-assign]
    app.input_box.buffer.document = Document("ship it")

    app._submit_input_buffer()

    assert app.input_box.buffer.text == ""
    assert len(scheduled) == 1
    asyncio.run(scheduled[0])


def test_tui_ensure_agent_does_not_append_internal_init_message(monkeypatch, tmp_path: Path) -> None:
    state_path = tmp_path / ".mini-agent" / "tui_sessions.json"
    app = _new_app(tmp_path, state_path=state_path)
    baseline_count = len(app.current_session.view.messages)

    fake_agent = SimpleNamespace(llm=SimpleNamespace(model="gpt-test"))

    async def _fake_build_agent_kernel(*, workspace_dir, options):
        assert options.console_output is False
        assert options.allow_interactive_setup is False
        assert options.suppress_background_output is True
        return fake_agent

    monkeypatch.setattr("mini_agent.tui.app.build_agent_kernel", _fake_build_agent_kernel)

    resolved = asyncio.run(app._ensure_agent(app.current_session))

    assert resolved is fake_agent
    assert len(app.current_session.view.messages) == baseline_count
    assert app.status == "Agent ready on gpt-test."


def test_tui_cancel_feedback_when_idle(tmp_path: Path) -> None:
    state_path = tmp_path / ".mini-agent" / "tui_sessions.json"
    app = _new_app(tmp_path, state_path=state_path)

    before_count = len(app.current_session.view.messages)
    assert app._request_cancel_current_turn(emit_system_when_idle=False) is False
    assert app.status == "No running turn to cancel."
    assert len(app.current_session.view.messages) == before_count

    assert app._request_cancel_current_turn(emit_system_when_idle=True) is False
    assert app.status == "No running turn to cancel."
    assert len(app.current_session.view.messages) == before_count + 1
    assert app.current_session.view.messages[-1].content == "No running turn to cancel."
    assert app.current_session.view.messages[-1].metadata["kind"] == "command"


def test_tui_tasks_list_tracks_completed_turn(tmp_path: Path) -> None:
    state_path = tmp_path / ".mini-agent" / "tui_sessions.json"
    app = _new_app(tmp_path, state_path=state_path)
    fake_agent = FakeTurnAgent(final_message="done")
    app.current_session.runtime.agent = fake_agent

    async def _scenario() -> None:
        turn_task = asyncio.create_task(app._run_chat_turn("build core"))
        await fake_agent.started.wait()
        await fake_agent.ready_for_cancel.wait()
        fake_agent.release.set()
        await turn_task

    asyncio.run(_scenario())

    assert len(app.current_session.view.tasks) == 1
    task = app.current_session.view.tasks[0]
    assert task.task_id == "task-1"
    assert task.status == "completed"
    assert task.submission_id.startswith("sub_")
    assert task.stop_reason == "end_turn"
    assert app.current_session.runtime.active_task_id is None

    asyncio.run(app._run_command("tasks list"))
    summary = app.current_session.view.messages[-1].content
    assert "Tasks" in summary
    assert "task-1" in summary
    assert "status=completed" in summary


def test_tui_workflow_command_routes_objective(tmp_path: Path, monkeypatch) -> None:
    state_path = tmp_path / ".mini-agent" / "tui_sessions.json"
    app = _new_app(tmp_path, state_path=state_path)
    called: dict[str, str] = {}

    async def _fake_run_workflow(self, objective: str) -> None:  # noqa: ANN001
        called["objective"] = objective

    monkeypatch.setattr(MiniAgentTuiApp, "_run_minimal_workflow", _fake_run_workflow)
    asyncio.run(app._run_command("workflow run ship p22.5"))

    assert called["objective"] == "ship p22.5"


def test_tui_workflow_command_requires_objective(tmp_path: Path) -> None:
    state_path = tmp_path / ".mini-agent" / "tui_sessions.json"
    app = _new_app(tmp_path, state_path=state_path)

    asyncio.run(app._run_command("workflow run"))
    assert app.current_session.view.messages[-1].content == "Usage: /workflow run <objective>"
    assert app.current_session.view.messages[-1].metadata["kind"] == "command"


def test_tui_remote_approve_command_routes_through_gateway(tmp_path: Path) -> None:
    state_path = tmp_path / ".mini-agent" / "tui_sessions.json"
    gateway = FakeGatewayClient()
    gateway._detail["pending_approvals"] = [
        {
            "token": "approval-gateway-1",
            "tool_name": "shell",
            "arguments": {"command": "pytest -q"},
            "kind": "exec",
            "reason": "needs manual approval",
            "step": 1,
        }
    ]
    app = _new_app(tmp_path, state_path=state_path, gateway_client=gateway)
    asyncio.run(app._sync_remote_sessions_once())
    remote_index = app._find_session_index("remote-qq-1")
    assert remote_index is not None
    app.session_index = remote_index
    app.current_session.projection.pending_approvals = app._normalize_pending_approvals_payload(gateway._detail["pending_approvals"])

    asyncio.run(app._run_command("approve"))

    assert gateway.approval_calls == [
        {
            "session_id": "remote-qq-1",
            "approved": True,
            "token": None,
            "surface": "tui",
            "channel_type": "qq",
            "conversation_id": "group:demo",
            "sender_id": "user-1",
        }
    ]
    assert app.current_session.projection.pending_approvals == []
    assert "Approved shell" in app.status


def test_tui_remote_approve_after_restart_loss_suggests_continue(tmp_path: Path) -> None:
    state_path = tmp_path / ".mini-agent" / "tui_sessions.json"
    gateway = FakeGatewayClient()
    gateway._detail["recovery"] = {
        "state": "interrupted",
        "summary": "interrupted after restart: approval pending for shell",
        "last_activity": "shell running | pytest -q",
        "pending_approvals": [{"token": "approval-gateway-1", "tool_name": "shell"}],
    }
    app = _new_app(tmp_path, state_path=state_path, gateway_client=gateway)
    asyncio.run(app._sync_remote_sessions_once())
    remote_index = app._find_session_index("remote-qq-1")
    assert remote_index is not None
    app.session_index = remote_index

    asyncio.run(app._run_command("approve"))

    assert gateway.approval_calls == [
        {
            "session_id": "remote-qq-1",
            "approved": True,
            "token": None,
            "surface": "tui",
            "channel_type": "qq",
            "conversation_id": "group:demo",
            "sender_id": "user-1",
        }
    ]
    assert "continue with recovery context" in app.status


def test_tui_remote_approve_multiple_pending_relies_on_gateway_token_resolution(tmp_path: Path) -> None:
    state_path = tmp_path / ".mini-agent" / "tui_sessions.json"
    gateway = FakeGatewayClient()
    gateway._detail["pending_approvals"] = [
        {
            "token": "approval-gateway-1",
            "tool_name": "shell",
            "arguments": {"command": "pytest -q"},
            "kind": "exec",
            "reason": "needs manual approval",
            "step": 1,
        },
        {
            "token": "approval-gateway-2",
            "tool_name": "shell",
            "arguments": {"command": "ruff check"},
            "kind": "exec",
            "reason": "needs manual approval",
            "step": 2,
        },
    ]
    app = _new_app(tmp_path, state_path=state_path, gateway_client=gateway)
    asyncio.run(app._sync_remote_sessions_once())
    remote_index = app._find_session_index("remote-qq-1")
    assert remote_index is not None
    app.session_index = remote_index
    app.current_session.projection.pending_approvals = app._normalize_pending_approvals_payload(
        gateway._detail["pending_approvals"]
    )

    asyncio.run(app._run_command("approve"))

    assert gateway.approval_calls == [
        {
            "session_id": "remote-qq-1",
            "approved": True,
            "token": None,
            "surface": "tui",
            "channel_type": "qq",
            "conversation_id": "group:demo",
            "sender_id": "user-1",
        }
    ]
    assert app.status == "Specify approval token."
    assert "Multiple approvals pending. Specify a token." in app.current_session.view.messages[-1].content


def test_tui_run_chat_turn_surfaces_prepared_context(tmp_path: Path, monkeypatch) -> None:
    state_path = tmp_path / ".mini-agent" / "tui_sessions.json"
    app = _new_app(tmp_path, state_path=state_path)

    class _FakeLoop:
        async def start(self) -> None:
            return None

        async def submit_user_input(
            self,
            _prompt: str,
            *,
            policy_overrides=None,
            metadata=None,
            start_new_run: bool = True,
        ) -> str:
            _ = (policy_overrides, metadata, start_new_run)
            return "sub-prepared"

    app.current_session.runtime.agent = SimpleNamespace(
        llm=SimpleNamespace(model="gpt-test"),
        messages=[{"role": "system", "content": "sys"}],
        max_steps=3,
        max_tool_calls_per_step=None,
    )
    app.current_session.runtime.submission_loop = _FakeLoop()
    app.current_session.runtime.loop_bus = InMemoryLoopMessageBus()

    async def _fake_wait_for_submission_payload(
        self,
        *,
        session,
        submission_id: str,
        event_start_index: int,
    ) -> dict[str, Any]:
        _ = (self, session, submission_id, event_start_index)
        return {
            "state": "completed",
            "stop_reason": "end_turn",
            "message": "done",
            "error": "",
            "prepared_context": {
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
                "provider_failures": [],
            },
        }

    monkeypatch.setattr(
        MiniAgentTuiApp,
        "_wait_for_submission_payload",
        _fake_wait_for_submission_payload,
    )

    asyncio.run(app._run_chat_turn("show prepared context"))

    context_entries = [
        message
        for message in app.current_session.view.messages
        if isinstance(getattr(message, "metadata", None), dict)
        and message.metadata.get("kind") == "command"
        and message.metadata.get("command") == "context"
    ]
    assert len(context_entries) == 1
    assert context_entries[0].metadata["summary"] == "prepared 1 item(s) from knowledge_base"
    assert context_entries[0].metadata["threads_visible"] is False
    assert "Relevant knowledge base context" in context_entries[0].content
    assert "ranking: basis knowledge_base_rrf | raw 0.0294 | item-relevance 0.881" in context_entries[0].content
    assert "selection: provider-weight 1.000 | priority 100 | final-selection 1.881" in context_entries[0].content
    assert app.current_session.projection.last_prepared_context["item_count"] == 1
    status_panel = app._render_status_panel()
    assert "ctx" in status_panel
    assert "knowledge_base" in status_panel
    assert app._prepared_context_summary(app.current_session) == "1 item(s) from knowledge_base"


def test_tui_run_chat_turn_includes_context_policy_metadata(tmp_path: Path, monkeypatch) -> None:
    state_path = tmp_path / ".mini-agent" / "tui_sessions.json"
    app = _new_app(tmp_path, state_path=state_path)
    captured: dict[str, Any] = {}

    class _FakeLoop:
        async def start(self) -> None:
            return None

        async def submit_user_input(
            self,
            _prompt: str,
            *,
            policy_overrides=None,
            metadata=None,
            start_new_run: bool = True,
        ) -> str:
            captured["policy_overrides"] = policy_overrides
            captured["metadata"] = metadata
            captured["start_new_run"] = start_new_run
            return "sub-context-policy"

    app.current_session.projection.context_policy = {
        "include_sources": ["knowledge_base"],
        "exclude_sources": ["mcp_catalog"],
        "max_items": 2,
    }
    app.current_session.runtime.agent = SimpleNamespace(
        llm=SimpleNamespace(model="gpt-test"),
        messages=[{"role": "system", "content": "sys"}],
        max_steps=3,
        max_tool_calls_per_step=None,
    )
    app.current_session.runtime.submission_loop = _FakeLoop()
    app.current_session.runtime.loop_bus = InMemoryLoopMessageBus()

    async def _fake_wait_for_submission_payload(
        self,
        *,
        session,
        submission_id: str,
        event_start_index: int,
    ) -> dict[str, Any]:
        _ = (self, session, submission_id, event_start_index)
        return {
            "state": "completed",
            "stop_reason": "end_turn",
            "message": "done",
            "error": "",
            "prepared_context": {"item_count": 0, "sources": [], "items": [], "provider_failures": []},
        }

    monkeypatch.setattr(
        MiniAgentTuiApp,
        "_wait_for_submission_payload",
        _fake_wait_for_submission_payload,
    )

    asyncio.run(app._run_chat_turn("respect context policy"))

    assert captured["metadata"]["surface"] == "tui"
    assert captured["metadata"]["prepared_context_policy"]["include_sources"] == ["knowledge_base"]
    assert captured["metadata"]["prepared_context_policy"]["exclude_sources"] == ["mcp_catalog"]
    assert captured["metadata"]["prepared_context_policy"]["max_items"] == 2


def test_tui_runtime_policy_commands_update_local_session(tmp_path: Path) -> None:
    state_path = tmp_path / ".mini-agent" / "tui_sessions.json"
    app = _new_app(tmp_path, state_path=state_path)

    asyncio.run(app._run_command("plan"))
    assert app.current_session.projection.sandbox_diagnostics["approval_profile"] == "plan"

    asyncio.run(app._run_command("fill-access"))
    assert app.current_session.projection.sandbox_diagnostics["access_level"] == "full-access"

    header_text = "".join(text for _style, text in app._render_header())
    assert "mode=plan" in header_text
    assert "access=full-access" in header_text


def test_tui_runtime_policy_commands_route_remote_session_through_gateway(tmp_path: Path) -> None:
    state_path = tmp_path / ".mini-agent" / "tui_sessions.json"
    gateway = FakeGatewayClient()
    app = _new_app(tmp_path, state_path=state_path, gateway_client=gateway)

    asyncio.run(app._sync_remote_sessions_once(focus_current=True))
    remote_index = app._find_session_index("remote-qq-1")
    assert remote_index is not None
    app.session_index = remote_index

    asyncio.run(app._run_command("plan"))
    asyncio.run(app._run_command("full-access"))

    assert gateway.policy_calls[-2]["approval_profile"] == "plan"
    assert gateway.policy_calls[-1]["access_level"] == "full-access"
    assert app.current_session.projection.sandbox_diagnostics["approval_profile"] == "plan"
    assert app.current_session.projection.sandbox_diagnostics["access_level"] == "full-access"


def test_tui_remote_tagged_local_runtime_routes_runtime_policy_locally(tmp_path: Path) -> None:
    state_path = tmp_path / ".mini-agent" / "tui_sessions.json"
    gateway = FakeGatewayClient(profile="local")
    app = _new_app(tmp_path, state_path=state_path, gateway_client=gateway)
    app.current_session.runtime.loop_bus = InMemoryLoopMessageBus()

    asyncio.run(app._run_command("plan"))
    asyncio.run(app._run_command("full-access"))

    assert gateway.policy_calls == []
    assert app.current_session.projection.sandbox_diagnostics["approval_profile"] == "plan"
    assert app.current_session.projection.sandbox_diagnostics["access_level"] == "full-access"


def test_tui_remote_tagged_local_runtime_clear_resets_local_session(monkeypatch, tmp_path: Path) -> None:
    state_path = tmp_path / ".mini-agent" / "tui_sessions.json"
    gateway = FakeGatewayClient(profile="local")
    app = _new_app(tmp_path, state_path=state_path, gateway_client=gateway)
    app.current_session.runtime.loop_bus = InMemoryLoopMessageBus()
    app.current_session.view.messages = [
        SimpleNamespace(role="user", content="hello", timestamp="10:00:00"),
        SimpleNamespace(role="assistant", content="world", timestamp="10:00:01"),
    ]

    async def _unexpected_reset(_session_id: str) -> dict[str, Any]:
        raise AssertionError("gateway reset should not run when local runtime state is attached")

    monkeypatch.setattr(app.gateway_client, "reset_session", _unexpected_reset)

    asyncio.run(app._run_command("clear"))

    assert app.current_session.view.messages == []
    assert app.current_session.projection.token_usage == 0
    assert app.status == "Cleared Session 1."


def test_tui_approval_modal_opens_for_current_pending_request(tmp_path: Path) -> None:
    state_path = tmp_path / ".mini-agent" / "tui_sessions.json"
    app = _new_app(tmp_path, state_path=state_path)
    app.current_session.projection.pending_approvals = [
        {
            "token": "approval-1",
            "tool_name": "shell_command",
            "reason": "needs approval",
            "arguments": {"command": "pytest -q"},
        }
    ]

    app._before_render(app.application)

    assert app._approval_modal_visible() is True
    modal_text = "".join(text for _style, text in app._render_approval_modal_fragments())
    assert "approval-1" in modal_text
    assert "shell_command" in modal_text


