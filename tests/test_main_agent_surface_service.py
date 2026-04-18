"""Unit tests for main-agent surface application-layer use cases."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from mini_agent.agent_core.engine import ToolApprovalRequest, TurnExecutionResult, TurnStopReason
from mini_agent.agent_core.runtime_bindings import get_agent_runtime_services
from mini_agent.agent_core.session import SessionLifecyclePolicy, SessionLifecycleState, SessionResetMode
from mini_agent.agent_core.skills.policy import WorkspaceSkillPolicyStore
from mini_agent.application import build_main_agent_surface_service, build_runtime_backed_main_agent_surface_service
from mini_agent.application.facades import MainAgentSurfaceService
from mini_agent.config import AgentConfig, Config, LLMConfig, ToolsConfig
from mini_agent.interfaces import (
    MainAgentChatRequest,
    MainAgentWorkspaceSwitchRequest,
    MainAgentModelBindingDiagnostics,
    MainAgentModelBindingRequest,
    MainAgentModelBindingSummary,
    MainAgentModelCandidateListResponse,
    MainAgentModelCapabilities,
    MainAgentSessionApprovalRequest,
    MainAgentSessionApprovalResponse,
    MainAgentSessionCancelRequest,
    MainAgentSessionContextRequest,
    MainAgentSessionContextResponse,
    MainAgentSessionCreateRequest,
    MainAgentSessionDetail,
    MainAgentSessionForkRequest,
    MainAgentSessionMemoryRequest,
    MainAgentSessionMemoryResponse,
    MainAgentSessionModelSelectionRequest,
    MainAgentSessionModelSelectionResponse,
    MainAgentSessionMutationResponse,
    MainAgentSessionRuntimePolicyRequest,
    MainAgentSessionRuntimePolicyResponse,
    MainAgentSessionSummary,
    MainAgentSessionSkillRequest,
    MainAgentSessionSkillResponse,
)
from mini_agent.interfaces import MainAgentSessionControlRequest, MainAgentSessionControlResponse
from mini_agent.memory.memoria_runtime import WorkspaceMemoriaRuntime
from mini_agent.memory.service import MemoryService
from mini_agent.runtime.main_agent_runtime_contracts import (
    MainAgentRuntimeMode,
    MainAgentRuntimePolicy,
)
from mini_agent.runtime.main_agent_runtime_manager import (
    MainAgentRuntimeManager,
)
from mini_agent.runtime.session_model_identity_codec import RuntimeSessionModelIdentityCodec
from mini_agent.runtime.session_agent_runtime_handler import RuntimeSessionAgentRuntimeHandler
from mini_agent.runtime.session_catalog_handler import RuntimeSessionCatalogHandler
from mini_agent.runtime.session_snapshot_handler import RuntimeSessionSnapshotImportCommand
from mini_agent.schema import LLMStreamEvent, LLMStreamEventType
from tests.runtime_contract_fixtures import RuntimeContractAgentStub


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


def _runtime_manager(**kwargs):
    if "load_runtime_config" not in kwargs:
        kwargs["load_runtime_config"] = lambda: _test_runtime_config()
    return MainAgentRuntimeManager(**kwargs)


def _runtime_surface_service(runtime_manager, **kwargs):  # noqa: ANN001
    kwargs.setdefault("resolve_workspace_dir", _resolve_workspace_dir)
    kwargs.setdefault("to_utc_iso", _to_utc_iso)
    kwargs.setdefault("sse_event", _sse_event)
    kwargs.setdefault("format_bootstrap_error", _format_bootstrap_error)
    kwargs.setdefault("stream_chunk_size", 64)
    return build_runtime_backed_main_agent_surface_service(runtime_manager=runtime_manager, **kwargs)


def test_main_agent_surface_service_is_exported_from_application_package() -> None:
    assert MainAgentSurfaceService.__module__ == "mini_agent.application.main_agent_surface_service"


def test_main_agent_surface_service_uses_injected_session_task_service_for_session_listing() -> None:
    class _InjectedSessionTaskService:
        async def list_sessions(self, *, workspace_dir=None, shared_only=False):  # noqa: ANN001, ANN003
            assert workspace_dir == Path(".").resolve()
            assert shared_only is True
            now = datetime.now(timezone.utc).isoformat()
            return [
                MainAgentSessionSummary(
                    session_id="sess-injected",
                    title="Injected Session",
                    workspace_dir=str(Path(".").resolve()),
                    created_at=now,
                    updated_at=now,
                    message_count=0,
                    token_usage=0,
                    token_limit=0,
                    active_surface="tui",
                    origin_surface="tui",
                    shared=True,
                )
            ]

    async def _run() -> None:
        use_cases = MainAgentSurfaceService(
            session_task_service=_InjectedSessionTaskService(),
            resolve_workspace_dir=_resolve_workspace_dir,
            to_utc_iso=_to_utc_iso,
            sse_event=_sse_event,
            format_bootstrap_error=_format_bootstrap_error,
            stream_chunk_size=64,
        )
        sessions = await use_cases.list_sessions(workspace_dir=".", shared_only=True)
        assert [item.session_id for item in sessions] == ["sess-injected"]

    asyncio.run(_run())


def test_main_agent_surface_service_uses_injected_workspace_service_for_workspace_routes() -> None:
    class _InjectedWorkspaceService:
        async def list_workspaces(self):
            return [
                {
                    "workspace_id": "ws-1",
                    "workspace_dir": str(Path(".").resolve()),
                    "title": "Default Workspace",
                    "default": True,
                    "active": True,
                }
            ]

        async def get_workspace(self, workspace_id: str):
            return {
                "workspace_id": workspace_id,
                "workspace_dir": str(Path(".").resolve()),
                "title": "Resolved Workspace",
            }

        async def get_active_workspace(self):
            return {
                "workspace_id": "ws-1",
                "workspace_dir": str(Path(".").resolve()),
                "title": "Default Workspace",
                "default": True,
                "active": True,
            }

        async def switch_workspace(self, workspace_id: str):
            return {
                "workspace_id": workspace_id,
                "workspace_dir": str(Path(".").resolve()),
                "title": "Switched Workspace",
                "active": True,
                "switched": True,
            }

        async def get_workspace_runtime_summary(self, workspace_id: str | None = None):
            return {
                "workspace_id": workspace_id or "ws-1",
                "workspace_dir": str(Path(".").resolve()),
                "title": "Runtime Workspace",
                "runtime_policy": {"mode": "single_main"},
                "runtime": {"mode": "direct"},
            }

    async def _run() -> None:
        use_cases = MainAgentSurfaceService(
            session_task_service=SimpleNamespace(),
            workspace_service=_InjectedWorkspaceService(),
            resolve_workspace_dir=_resolve_workspace_dir,
            to_utc_iso=_to_utc_iso,
            sse_event=_sse_event,
            format_bootstrap_error=_format_bootstrap_error,
            stream_chunk_size=64,
        )
        listed = await use_cases.list_workspaces()
        resolved = await use_cases.get_workspace("ws-lookup")
        active = await use_cases.get_active_workspace()
        switched = await use_cases.switch_workspace(MainAgentWorkspaceSwitchRequest(workspace_id="ws-switch"))
        runtime = await use_cases.get_workspace_runtime_summary(workspace_id="ws-runtime")

        assert [item.workspace_id for item in listed] == ["ws-1"]
        assert resolved.workspace_id == "ws-lookup"
        assert active.active is True
        assert switched.workspace_id == "ws-switch"
        assert switched.switched is True
        assert runtime.workspace_id == "ws-runtime"
        assert runtime.runtime_policy["mode"] == "single_main"
        assert runtime.runtime["mode"] == "direct"

    asyncio.run(_run())


class _DummyAgent(RuntimeContractAgentStub):
    def __init__(self) -> None:
        super().__init__(messages=[SimpleNamespace(role="system", content="system")])

    async def run(self) -> str:
        text = f"mock:{self.messages[-1].content}"
        self.append_assistant_message(text)
        self.api_total_tokens += 7
        return text

    async def run_turn(
        self,
        *,
        cancel_event=None,
        hooks=None,
        turn_context=None,
        start_new_run: bool = True,
    ) -> TurnExecutionResult:
        _ = cancel_event
        _ = hooks
        _ = turn_context
        _ = start_new_run
        text = await self.run()
        return TurnExecutionResult(stop_reason=TurnStopReason.END_TURN, message=text)


class _PrefixAgent(_DummyAgent):
    def __init__(self, *, prefix: str, fail: bool = False) -> None:
        super().__init__()
        self._prefix = prefix
        self._fail = fail

    async def run(self) -> str:
        if self._fail:
            raise RuntimeError(f"{self._prefix}-failure")
        text = f"{self._prefix}:{self.messages[-1].content}"
        self.messages.append(SimpleNamespace(role="assistant", content=text))
        self.api_total_tokens += 5
        return text


class _SelectableAgent(_DummyAgent):
    def __init__(self, *, provider_source: str, provider_id: str, model_id: str) -> None:
        RuntimeContractAgentStub.__init__(
            self,
            model=model_id,
            provider_source=provider_source,
            provider_id=provider_id,
            expose_llm=True,
            messages=[SimpleNamespace(role="system", content="system")],
        )
        self.runtime_policy_engine = SimpleNamespace(
            policy=SimpleNamespace(
                approval_profile="build",
                access_level="default",
                sandbox_mode="workspace",
            )
        )


class _HookedAgent(_DummyAgent):
    async def run_turn(
        self,
        *,
        cancel_event=None,
        hooks=None,
        turn_context=None,
        start_new_run: bool = True,
    ) -> TurnExecutionResult:
        _ = cancel_event
        _ = turn_context
        _ = start_new_run
        reply = f"hooked:{self.messages[-1].content}"
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
        self.append_assistant_message(reply)
        self.api_total_tokens += 11
        return TurnExecutionResult(stop_reason=TurnStopReason.END_TURN, message=reply)


class _StreamingAgent(_DummyAgent):
    async def run_turn(
        self,
        *,
        cancel_event=None,
        hooks=None,
        turn_context=None,
        start_new_run: bool = True,
    ) -> TurnExecutionResult:
        _ = cancel_event
        _ = turn_context
        _ = start_new_run
        reply = f"streamed:{self.messages[-1].content}"
        if hooks and getattr(hooks, "on_llm_event", None):
            await hooks.on_llm_event(1, LLMStreamEvent(type=LLMStreamEventType.MESSAGE_START))
            await hooks.on_llm_event(1, LLMStreamEvent(type=LLMStreamEventType.TEXT_DELTA, delta="streamed:"))
            await hooks.on_llm_event(
                1,
                LLMStreamEvent(
                    type=LLMStreamEventType.TEXT_DELTA,
                    delta=self.messages[-1].content,
                ),
            )
            await hooks.on_llm_event(1, LLMStreamEvent(type=LLMStreamEventType.MESSAGE_STOP, finish_reason="stop"))
        self.messages.append(SimpleNamespace(role="assistant", content=reply))
        self.api_total_tokens += 9
        return TurnExecutionResult(stop_reason=TurnStopReason.END_TURN, message=reply)


class _ControllableAgent(_DummyAgent):
    def __init__(self) -> None:
        super().__init__()
        self.control_calls: list[tuple[str, str | None]] = []
        self._knowledge_base_enabled = True

    def compact_context(self, *, reason: str | None = None) -> dict[str, object]:
        self.control_calls.append(("compact", reason))
        return {
            "applied": True,
            "message_count_before": 5,
            "message_count_after": 3,
            "token_count_before": 220,
            "token_count_after": 120,
            "stats": {
                "masked_messages": 1,
                "snipped_messages": 1,
                "merged_messages": 0,
            },
        }

    def drop_memories(self, *, reason: str | None = None) -> dict[str, object]:
        self.control_calls.append(("drop_memories", reason))
        return {
            "applied": True,
            "message_count_before": 8,
            "message_count_after": 4,
            "token_count_before": 360,
            "token_count_after": 140,
            "stats": {
                "masked_messages": 0,
                "snipped_messages": 2,
                "merged_messages": 1,
            },
        }

    def knowledge_base_enabled(self) -> bool:
        return self._knowledge_base_enabled

    def set_knowledge_base_enabled(self, enabled: bool) -> bool:
        self.control_calls.append((f"kb_{'on' if enabled else 'off'}", None))
        self._knowledge_base_enabled = bool(enabled)
        return self._knowledge_base_enabled


class _BlockingCancelableAgent(_DummyAgent):
    def __init__(self) -> None:
        super().__init__()
        self.started = asyncio.Event()
        self.received_cancel_event: asyncio.Event | None = None

    async def run_turn(
        self,
        *,
        cancel_event=None,
        hooks=None,
        turn_context=None,
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


class _ApprovalBlockingAgent(_DummyAgent):
    def __init__(self) -> None:
        super().__init__()
        self.tool_approval_handler = None
        self.started = asyncio.Event()
        self.tool_name = "shell"

    async def run_turn(
        self,
        *,
        cancel_event=None,
        hooks=None,
        turn_context=None,
        start_new_run: bool = True,
    ) -> TurnExecutionResult:
        _ = cancel_event
        _ = hooks
        _ = turn_context
        _ = start_new_run
        self.started.set()
        handler = self.tool_approval_handler
        if handler is None:
            raise AssertionError("tool_approval_handler should be injected by gateway use case")
        decision = await handler(
            ToolApprovalRequest(
                token="approval_gateway_1",
                step=1,
                tool_name=self.tool_name,
                arguments={"command": "pytest -q"},
                kind="exec",
                reason="needs manual approval",
                cache_key="shell:pytest",
                can_escalate=False,
            )
        )
        if decision is True:
            text = "approved remote run"
        elif decision is False:
            text = "denied remote run"
        else:
            text = "cancelled remote run"
        self.messages.append(SimpleNamespace(role="assistant", content=text))
        return TurnExecutionResult(stop_reason=TurnStopReason.END_TURN, message=text)


class _RecoveryCaptureAgent(_DummyAgent):
    def __init__(self) -> None:
        super().__init__()
        self.captured_turn_contexts: list[dict[str, object] | None] = []

    async def run_turn(
        self,
        *,
        cancel_event=None,
        hooks=None,
        turn_context=None,
        start_new_run: bool = True,
    ) -> TurnExecutionResult:
        _ = (cancel_event, hooks, start_new_run)
        self.captured_turn_contexts.append(turn_context if isinstance(turn_context, dict) else None)
        text = f"recovered:{self.messages[-1].content}"
        self.messages.append(SimpleNamespace(role="assistant", content=text))
        return TurnExecutionResult(stop_reason=TurnStopReason.END_TURN, message=text)


def _resolve_workspace_dir(workspace_dir: str | None) -> Path:
    return Path(workspace_dir or ".").resolve()


def _to_utc_iso(value: datetime) -> str:
    return value.isoformat()


def _sse_event(event: str, data: dict[str, object]) -> str:
    return f"{event}:{data}"


def _format_bootstrap_error(exc: Exception):
    raise RuntimeError(str(exc))


async def _import_runtime_session(
    runtime: MainAgentRuntimeManager,
    *,
    workspace_dir: str | None,
    session_id: str | None = None,
    **kwargs: object,
):
    resolved_workspace = _resolve_workspace_dir(workspace_dir)
    runtime.validate_workspace(resolved_workspace)
    session = await runtime.import_session_snapshot(
        RuntimeSessionSnapshotImportCommand(
            session_id=session_id,
            workspace_dir=resolved_workspace,
            **kwargs,
        )
    )
    transcript = kwargs.get("transcript")
    recent_limit = max(50, len(transcript) if isinstance(transcript, list) else 0)
    return await runtime.get_session_detail(session.session_id, recent_limit=recent_limit)


async def _export_runtime_session(runtime: MainAgentRuntimeManager, session_id: str):
    return await runtime.export_session_snapshot(session_id)


async def _activate_runtime_surface(
    runtime: MainAgentRuntimeManager,
    session_id: str,
    *,
    surface: str,
) -> MainAgentSessionSummary:
    return await runtime.set_active_surface(session_id, surface=surface)


def test_use_case_chat_session_lifecycle(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr("mini_agent.memory.memoria_runtime.Path.home", classmethod(lambda cls: tmp_path))

    async def _run() -> None:
        async def _build_agent(_workspace: Path):
            return _DummyAgent()

        runtime = _runtime_manager(ttl_seconds=3600, build_agent=_build_agent)
        use_cases = _runtime_surface_service(runtime_manager=runtime)

        chat = await use_cases.run_chat(
            MainAgentChatRequest(message="hello", workspace_dir=".", session_id="sess-1", dry_run=False)
        )
        assert chat.session_id == "sess-1"
        assert chat.reply == "mock:hello"
        assert chat.message_count >= 3
        assert chat.token_usage == 7

        sessions = await use_cases.list_sessions()
        assert len(sessions) == 1
        assert sessions[0].session_id == "sess-1"
        assert sessions[0].token_usage == 7
        assert sessions[0].token_limit >= 0

        reset = await use_cases.reset_session("sess-1")
        assert reset.status == "reset"

        deleted = await use_cases.delete_session("sess-1")
        assert deleted.status == "deleted"
        assert (await use_cases.list_sessions()) == []

    asyncio.run(_run())


def test_use_case_tracks_shared_session_metadata_and_recent_messages() -> None:
    async def _run() -> None:
        async def _build_agent(_workspace: Path):
            return _DummyAgent()

        runtime = _runtime_manager(ttl_seconds=3600, build_agent=_build_agent)
        use_cases = _runtime_surface_service(runtime_manager=runtime)

        first = await use_cases.run_chat(
            MainAgentChatRequest(
                message="hello from qq",
                workspace_dir=".",
                session_id="sess-qq",
                surface="qq",
                channel_type="qq",
                conversation_id="group:demo",
                sender_id="user-1",
            )
        )
        assert first.reply == "mock:hello from qq"

        summary = (await use_cases.list_sessions())[0]
        assert summary.origin_surface == "qq"
        assert summary.active_surface == "qq"
        assert summary.reply_enabled is True
        assert summary.channel_type == "qq"
        assert summary.conversation_id == "group:demo"
        assert summary.sender_id == "user-1"

        detail = await use_cases.get_session_detail("sess-qq", recent_limit=10)
        assert [item.role for item in detail.recent_messages] == ["user", "assistant"]
        assert [item.surface for item in detail.recent_messages] == ["qq", "qq"]
        assert detail.recent_messages[0].content == "hello from qq"
        assert detail.recent_messages[1].content == "mock:hello from qq"

        latest = await use_cases.get_session_messages("sess-qq", limit=1)
        assert len(latest) == 1
        assert latest[0].role == "assistant"
        assert latest[0].content == "mock:hello from qq"

        activated = await _activate_runtime_surface(runtime, "sess-qq", surface="tui")
        assert activated.active_surface == "tui"

        second = await use_cases.run_chat(
            MainAgentChatRequest(
                message="continue in tui",
                workspace_dir=".",
                session_id="sess-qq",
                surface="tui",
            )
        )
        assert second.reply == "mock:continue in tui"

        detail_after = await use_cases.get_session_detail("sess-qq", recent_limit=10)
        assert detail_after.origin_surface == "qq"
        assert detail_after.active_surface == "tui"
        assert detail_after.reply_enabled is False
        assert [item.content for item in detail_after.recent_messages[-2:]] == [
            "continue in tui",
            "mock:continue in tui",
        ]
        assert [item.surface for item in detail_after.recent_messages[-2:]] == ["tui", "tui"]

    asyncio.run(_run())


def test_use_case_can_import_local_session_snapshot(tmp_path: Path) -> None:
    async def _run() -> None:
        async def _build_agent(_workspace: Path):
            return _DummyAgent()

        runtime = _runtime_manager(
            ttl_seconds=3600,
            build_agent=_build_agent,
            storage_dir=tmp_path / "import-session-store",
        )
        use_cases = _runtime_surface_service(runtime_manager=runtime)

        detail = await _import_runtime_session(
            runtime,
                workspace_dir=".",
                title="Local Draft",
                origin_surface="tui",
                active_surface="tui",
                token_usage=1234,
                token_limit=80000,
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

        assert detail.title == "Local Draft"
        assert detail.origin_surface == "tui"
        assert detail.active_surface == "tui"
        assert detail.token_usage == 1234
        assert detail.token_limit == 80000
        assert [item.content for item in detail.recent_messages] == ["hello local", "hello shared"]

        sessions = await use_cases.list_sessions()
        assert len(sessions) == 1
        assert sessions[0].title == "Local Draft"
        assert sessions[0].session_id == detail.session_id

    asyncio.run(_run())


def test_use_case_import_session_restores_runtime_task_memory_payload(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr("mini_agent.memory.memoria_runtime.Path.home", classmethod(lambda cls: tmp_path))

    async def _run() -> None:
        async def _build_agent(_workspace: Path):
            return _DummyAgent()

        workspace = (tmp_path / "workspace").resolve()
        workspace.mkdir(parents=True, exist_ok=True)

        source_runtime = WorkspaceMemoriaRuntime(workspace)
        source_runtime.save_session_memory(
            "local-session",
            content="runtime task memory should survive snapshot import into gateway",
        )
        runtime_payload = source_runtime.snapshot_session_namespace_payload("local-session")

        runtime = _runtime_manager(
            ttl_seconds=3600,
            build_agent=_build_agent,
            storage_dir=tmp_path / "import-session-store-rtm",
        )
        use_cases = _runtime_surface_service(runtime_manager=runtime, resolve_workspace_dir=lambda workspace_dir: Path(str(workspace_dir or workspace)).resolve())

        detail = await _import_runtime_session(
            runtime,
                workspace_dir=str(workspace),
                title="Local Draft",
                origin_surface="tui",
                active_surface="tui",
                runtime_task_memory_payload=runtime_payload,
        )

        restored_runtime = WorkspaceMemoriaRuntime(workspace)
        payload = restored_runtime.retrieve_for_turn(
            session_id=detail.session_id,
            query="What should survive snapshot import into gateway?",
        )
        assert any("survive snapshot import into gateway" in item["content"] for item in payload["session_hits"])

    asyncio.run(_run())


def test_use_case_import_session_merges_workspace_shared_runtime_task_memory_payload(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr("mini_agent.memory.memoria_runtime.Path.home", classmethod(lambda cls: tmp_path))

    async def _run() -> None:
        async def _build_agent(_workspace: Path):
            return _DummyAgent()

        workspace = (tmp_path / "workspace").resolve()
        workspace.mkdir(parents=True, exist_ok=True)

        source_runtime = WorkspaceMemoriaRuntime(workspace, state_root=(tmp_path / "source-state").resolve())
        source_runtime.save_workspace_shared_memory(
            content="workspace shared runtime facts should survive snapshot import into gateway",
        )
        shared_payload = source_runtime.snapshot_workspace_shared_namespace_payload()

        target_runtime = WorkspaceMemoriaRuntime(workspace)
        target_runtime.save_workspace_shared_memory(
            content="existing workspace shared runtime facts must remain after import merge",
        )

        runtime = _runtime_manager(
            ttl_seconds=3600,
            build_agent=_build_agent,
            storage_dir=tmp_path / "import-session-store-shared-rtm",
        )
        use_cases = _runtime_surface_service(runtime_manager=runtime, resolve_workspace_dir=lambda workspace_dir: Path(str(workspace_dir or workspace)).resolve())

        detail = await _import_runtime_session(
            runtime,
                workspace_dir=str(workspace),
                title="Local Draft",
                origin_surface="tui",
                active_surface="tui",
                workspace_shared_runtime_memory_payload=shared_payload,
        )

        restored_runtime = WorkspaceMemoriaRuntime(workspace)
        payload = restored_runtime.retrieve_for_turn(
            session_id=detail.session_id,
            query="How should workspace shared runtime facts behave after import merge?",
        )
        assert any("survive snapshot import into gateway" in item["content"] for item in payload["shared_hits"])
        assert any("must remain after import merge" in item["content"] for item in payload["shared_hits"])

    asyncio.run(_run())


def test_use_case_can_export_shared_session_snapshot(tmp_path: Path) -> None:
    async def _run() -> None:
        async def _build_agent(_workspace: Path):
            return _DummyAgent()

        runtime = _runtime_manager(
            ttl_seconds=3600,
            build_agent=_build_agent,
            storage_dir=tmp_path / "export-session-store",
        )
        use_cases = _runtime_surface_service(runtime_manager=runtime)

        detail = await _import_runtime_session(
            runtime,
                workspace_dir=".",
                title="Local Draft",
                origin_surface="tui",
                active_surface="tui",
                token_usage=2048,
                token_limit=80000,
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

        snapshot = await _export_runtime_session(runtime, detail.session_id)
        assert snapshot.title == "Local Draft"
        assert snapshot.origin_surface == "tui"
        assert snapshot.token_usage == 2048
        assert snapshot.token_limit == 80000
        assert [item.content for item in snapshot.transcript] == ["hello local", "hello shared"]
        assert [item["role"] for item in snapshot.agent_messages] == ["system", "user", "assistant"]
        assert snapshot.lineage_parent_session_id is None
        assert snapshot.lineage_root_session_id == detail.session_id
        assert snapshot.lineage_reason == "root"

    asyncio.run(_run())


def test_runtime_manager_import_session_snapshot_can_register_lineage_child(tmp_path: Path) -> None:
    async def _run() -> None:
        async def _build_agent(_workspace: Path):
            return _DummyAgent()

        workspace = Path(".").resolve()
        runtime = _runtime_manager(
            ttl_seconds=3600,
            build_agent=_build_agent,
            storage_dir=tmp_path / "lineage-import-store",
            policy=MainAgentRuntimePolicy(
                mode=MainAgentRuntimeMode.TEAM,
                main_workspace_dir=workspace,
                max_active_sessions=4,
                reserved_team_slots=4,
            ),
        )

        parent = await runtime.get_or_create_session("sess-parent", workspace)
        imported = await runtime.import_session_snapshot(
            RuntimeSessionSnapshotImportCommand(
                session_id="sess-child",
                workspace_dir=workspace,
                title="Imported Child",
                lineage_parent_session_id=parent.session_id,
                lineage_root_session_id=parent.session_id,
                lineage_reason="snapshot_import",
                lineage_metadata={"source": "test"},
                transcript=[
                    {
                        "role": "user",
                        "content": "hello child",
                        "surface": "tui",
                    }
                ],
            )
        )

        assert imported.lineage_state.parent_session_id == "sess-parent"
        assert imported.lineage_state.root_session_id == "sess-parent"
        assert imported.lineage_state.reason == "snapshot_import"
        assert runtime._session_lineage.parent_of("sess-child") is not None
        assert runtime._session_lineage.parent_of("sess-child").session_key == "sess-parent"

        snapshot = await runtime.export_session_snapshot("sess-child")
        assert snapshot.lineage_parent_session_id == "sess-parent"
        assert snapshot.lineage_root_session_id == "sess-parent"
        assert snapshot.lineage_reason == "snapshot_import"
        assert snapshot.lineage_metadata["source"] == "test"

    asyncio.run(_run())


def test_use_case_export_session_includes_runtime_task_memory_payload(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr("mini_agent.memory.memoria_runtime.Path.home", classmethod(lambda cls: tmp_path))

    async def _run() -> None:
        async def _build_agent(_workspace: Path):
            return _DummyAgent()

        workspace = (tmp_path / "workspace").resolve()
        workspace.mkdir(parents=True, exist_ok=True)

        runtime = _runtime_manager(
            ttl_seconds=3600,
            build_agent=_build_agent,
            storage_dir=tmp_path / "export-session-store-rtm",
        )
        use_cases = _runtime_surface_service(runtime_manager=runtime, resolve_workspace_dir=lambda workspace_dir: Path(str(workspace_dir or workspace)).resolve())

        detail = await _import_runtime_session(
            runtime,
                workspace_dir=str(workspace),
                title="Local Draft",
                origin_surface="tui",
                active_surface="tui",
        )

        runtime_memory = WorkspaceMemoriaRuntime(workspace)
        runtime_memory.save_session_memory(
            detail.session_id,
            content="exported shared session snapshots should include runtime task memory payload",
        )

        snapshot = await _export_runtime_session(runtime, detail.session_id)

        assert snapshot.runtime_task_memory_payload["entry_count"] >= 1
        engine_payload = snapshot.runtime_task_memory_payload.get("engine")
        assert isinstance(engine_payload, dict)

    asyncio.run(_run())


def test_use_case_export_session_includes_workspace_shared_runtime_task_memory_payload(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr("mini_agent.memory.memoria_runtime.Path.home", classmethod(lambda cls: tmp_path))

    async def _run() -> None:
        async def _build_agent(_workspace: Path):
            return _DummyAgent()

        workspace = (tmp_path / "workspace").resolve()
        workspace.mkdir(parents=True, exist_ok=True)

        runtime = _runtime_manager(
            ttl_seconds=3600,
            build_agent=_build_agent,
            storage_dir=tmp_path / "export-session-store-shared-rtm",
        )
        use_cases = _runtime_surface_service(runtime_manager=runtime, resolve_workspace_dir=lambda workspace_dir: Path(str(workspace_dir or workspace)).resolve())

        detail = await _import_runtime_session(
            runtime,
                workspace_dir=str(workspace),
                title="Local Draft",
                origin_surface="tui",
                active_surface="tui",
        )

        runtime_memory = WorkspaceMemoriaRuntime(workspace)
        runtime_memory.save_workspace_shared_memory(
            content="exported shared session snapshots should include workspace-shared runtime task memory payload",
        )

        snapshot = await _export_runtime_session(runtime, detail.session_id)

        assert snapshot.workspace_shared_runtime_memory_payload["entry_count"] >= 1
        engine_payload = snapshot.workspace_shared_runtime_memory_payload.get("engine")
        assert isinstance(engine_payload, dict)

    asyncio.run(_run())


def test_runtime_manager_import_session_snapshot_rejects_duplicate_session_id() -> None:
    async def _run() -> None:
        async def _build_agent(_workspace: Path):
            return _DummyAgent()

        runtime = _runtime_manager(
            ttl_seconds=3600,
            build_agent=_build_agent,
            policy=MainAgentRuntimePolicy(
                mode=MainAgentRuntimeMode.TEAM,
                main_workspace_dir=Path(".").resolve(),
                max_active_sessions=4,
                reserved_team_slots=4,
            ),
        )
        workspace = Path(".").resolve()

        await runtime.import_session_snapshot(
            RuntimeSessionSnapshotImportCommand(
                session_id="dup-import",
                workspace_dir=workspace,
                title="Imported Once",
                transcript=[],
            )
        )

        with pytest.raises(HTTPException, match="Session already exists."):
            await runtime.import_session_snapshot(
                RuntimeSessionSnapshotImportCommand(
                    session_id="dup-import",
                    workspace_dir=workspace,
                    title="Imported Twice",
                    transcript=[],
                )
            )

    asyncio.run(_run())


def test_runtime_manager_can_export_snapshot_from_persisted_record(tmp_path: Path) -> None:
    async def _run() -> None:
        async def _build_agent(_workspace: Path):
            return _DummyAgent()

        workspace = Path(".").resolve()
        storage_dir = tmp_path / "persisted-export-store"

        seed_runtime = _runtime_manager(
            ttl_seconds=3600,
            build_agent=_build_agent,
            storage_dir=storage_dir,
            policy=MainAgentRuntimePolicy(
                mode=MainAgentRuntimeMode.TEAM,
                main_workspace_dir=workspace,
                max_active_sessions=4,
                reserved_team_slots=4,
            ),
        )
        imported = await seed_runtime.import_session_snapshot(
            RuntimeSessionSnapshotImportCommand(
                session_id="persisted-export-session",
                workspace_dir=workspace,
                title="Persisted Export",
                origin_surface="qq",
                active_surface="qq",
                transcript=[
                    {
                        "role": "user",
                        "content": "persisted snapshot should still export",
                        "surface": "qq",
                    }
                ],
            )
        )
        assert imported.session_id == "persisted-export-session"

        fresh_runtime = _runtime_manager(
            ttl_seconds=3600,
            build_agent=_build_agent,
            storage_dir=storage_dir,
        )
        snapshot = await fresh_runtime.export_session_snapshot("persisted-export-session")

        assert snapshot.session_id == "persisted-export-session"
        assert snapshot.title == "Persisted Export"
        assert [item.content for item in snapshot.transcript] == ["persisted snapshot should still export"]

    asyncio.run(_run())


def test_runtime_manager_restore_persisted_session_preserves_lineage(tmp_path: Path) -> None:
    async def _run() -> None:
        async def _build_agent(_workspace: Path):
            return _DummyAgent()

        workspace = Path(".").resolve()
        storage_dir = tmp_path / "persisted-lineage-store"

        seed_runtime = _runtime_manager(
            ttl_seconds=3600,
            build_agent=_build_agent,
            storage_dir=storage_dir,
            policy=MainAgentRuntimePolicy(
                mode=MainAgentRuntimeMode.TEAM,
                main_workspace_dir=workspace,
                max_active_sessions=4,
                reserved_team_slots=4,
            ),
        )
        await seed_runtime.get_or_create_session("sess-root", workspace)
        await seed_runtime.import_session_snapshot(
            RuntimeSessionSnapshotImportCommand(
                session_id="sess-child",
                workspace_dir=workspace,
                title="Persisted Child",
                lineage_parent_session_id="sess-root",
                lineage_root_session_id="sess-root",
                lineage_reason="snapshot_import",
                transcript=[
                    {
                        "role": "user",
                        "content": "persisted child",
                        "surface": "tui",
                    }
                ],
            )
        )

        restored_runtime = _runtime_manager(
            ttl_seconds=3600,
            build_agent=_build_agent,
            storage_dir=storage_dir,
        )
        restored = await restored_runtime.get_or_create_session("sess-child", workspace)

        assert restored.lineage_state.parent_session_id == "sess-root"
        assert restored.lineage_state.root_session_id == "sess-root"
        assert restored.lineage_state.reason == "snapshot_import"
        parent = restored_runtime._session_lineage.parent_of("sess-child")
        assert parent is not None
        assert parent.session_key == "sess-root"

        snapshot = await restored_runtime.export_session_snapshot("sess-child")
        assert snapshot.lineage_parent_session_id == "sess-root"
        assert snapshot.lineage_root_session_id == "sess-root"
        assert snapshot.lineage_reason == "snapshot_import"

    asyncio.run(_run())


def test_use_case_can_list_and_refresh_shared_session_skills(tmp_path: Path) -> None:
    builtin_dir = tmp_path / "builtin-skills"
    workspace_dir = tmp_path / "workspace"
    workspace_skill_dir = workspace_dir / ".mini-agent" / "skills"
    builtin_dir.mkdir(parents=True, exist_ok=True)
    workspace_skill_dir.mkdir(parents=True, exist_ok=True)
    (builtin_dir / "doc-coauthoring").mkdir(parents=True, exist_ok=True)
    (builtin_dir / "doc-coauthoring" / "SKILL.md").write_text(
        "---\nname: doc-coauthoring\ndescription: Draft structured docs.\n---\nUse for docs.\n",
        encoding="utf-8",
    )
    (workspace_skill_dir / "repo-helper").mkdir(parents=True, exist_ok=True)
    (workspace_skill_dir / "repo-helper" / "SKILL.md").write_text(
        "---\nname: repo-helper\ndescription: Workspace-local guidance.\n---\nUse for this repo.\n",
        encoding="utf-8",
    )

    config = Config(
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
            enable_skills=True,
            enable_mcp=False,
            skills_dir=str(builtin_dir),
        ),
    )
    async def _run() -> None:
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

        runtime = _runtime_manager(
            ttl_seconds=3600,
            build_agent=_build_agent,
            build_agent_with_selection=_build_agent_with_selection,
            load_runtime_config=lambda: config,
            storage_dir=tmp_path / "skill-selection-store",
        )
        use_cases = _runtime_surface_service(runtime_manager=runtime, resolve_workspace_dir=lambda value: Path(str(value or workspace_dir)).resolve())

        detail = await _import_runtime_session(
            runtime,
                workspace_dir=str(workspace_dir),
                title="Remote Skill Test",
                origin_surface="qq",
                active_surface="qq",
                selected_model_source="preset",
                selected_provider_id="openai",
                selected_model_id="gpt-5.4",
                agent_messages=[
                    {"role": "system", "content": "system"},
                    {"role": "assistant", "content": "ready"},
                ],
                transcript=[
                    {"role": "assistant", "content": "ready", "surface": "qq"},
                ],
        )

        listed = await use_cases.manage_session_skills(
            detail.session_id,
            MainAgentSessionSkillRequest(action="list", surface="qq"),
        )
        assert listed.status == "ok"
        assert "repo-helper [workspace] active" in listed.result["details"]
        assert "doc-coauthoring [builtin] active" in listed.result["details"]

        refreshed = await use_cases.manage_session_skills(
            detail.session_id,
            MainAgentSessionSkillRequest(action="refresh", surface="qq"),
        )
        assert refreshed.status == "ok"
        assert refreshed.result["counts"]["total"] == 2
        assert build_calls[-1] == ("preset", "openai", "gpt-5.4")

        updated = await use_cases.get_session_detail(detail.session_id, recent_limit=10)
        assert updated.recent_messages[-1].metadata["command"] == "skill refresh"
        assert "repo-helper [workspace] active" in updated.recent_messages[-1].content

    asyncio.run(_run())


def test_use_case_can_manage_shared_session_skill_policy(tmp_path: Path) -> None:
    builtin_dir = tmp_path / "builtin-skills"
    workspace_dir = tmp_path / "workspace"
    workspace_skill_dir = workspace_dir / ".mini-agent" / "skills"
    builtin_dir.mkdir(parents=True, exist_ok=True)
    workspace_skill_dir.mkdir(parents=True, exist_ok=True)
    (builtin_dir / "doc-coauthoring").mkdir(parents=True, exist_ok=True)
    (builtin_dir / "doc-coauthoring" / "SKILL.md").write_text(
        "---\nname: doc-coauthoring\ndescription: Draft structured docs.\n---\nUse for docs.\n",
        encoding="utf-8",
    )
    (workspace_skill_dir / "repo-helper").mkdir(parents=True, exist_ok=True)
    (workspace_skill_dir / "repo-helper" / "SKILL.md").write_text(
        "---\nname: repo-helper\ndescription: Workspace-local guidance.\n---\nUse for this repo.\n",
        encoding="utf-8",
    )

    config = Config(
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
            enable_skills=True,
            enable_mcp=False,
            skills_dir=str(builtin_dir),
        ),
    )
    async def _run() -> None:
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

        runtime = _runtime_manager(
            ttl_seconds=3600,
            build_agent=_build_agent,
            build_agent_with_selection=_build_agent_with_selection,
            load_runtime_config=lambda: config,
            storage_dir=tmp_path / "skill-policy-store",
        )
        use_cases = _runtime_surface_service(runtime_manager=runtime, resolve_workspace_dir=lambda value: Path(str(value or workspace_dir)).resolve())

        detail = await _import_runtime_session(
            runtime,
                workspace_dir=str(workspace_dir),
                title="Remote Skill Policy Test",
                origin_surface="qq",
                active_surface="qq",
                selected_model_source="preset",
                selected_provider_id="openai",
                selected_model_id="gpt-5.4",
                agent_messages=[
                    {"role": "system", "content": "system"},
                    {"role": "assistant", "content": "ready"},
                ],
                transcript=[
                    {"role": "assistant", "content": "ready", "surface": "qq"},
                ],
        )

        active_before = await use_cases.manage_session_skills(
            detail.session_id,
            MainAgentSessionSkillRequest(action="active", surface="qq"),
        )
        assert active_before.status == "ok"
        assert active_before.result["counts"]["active"] == 2
        assert active_before.result["policy"]["mode"] == "all"

        mode_updated = await use_cases.manage_session_skills(
            detail.session_id,
            MainAgentSessionSkillRequest(action="mode", mode="allowlist", surface="qq"),
        )
        assert mode_updated.status == "ok"
        assert mode_updated.result["policy"]["mode"] == "allowlist"
        assert build_calls[-1] == ("preset", "openai", "gpt-5.4")

        enabled = await use_cases.manage_session_skills(
            detail.session_id,
            MainAgentSessionSkillRequest(action="enable", skill_name="doc-coauthoring", surface="qq"),
        )
        assert enabled.status == "ok"
        assert enabled.result["counts"]["active"] == 1
        assert "active skills: doc-coauthoring" in enabled.result["details"]

        disabled = await use_cases.manage_session_skills(
            detail.session_id,
            MainAgentSessionSkillRequest(action="disable", skill_name="repo-helper", surface="qq"),
        )
        assert disabled.status == "ok"
        assert "denylist repo-helper" in disabled.result["details"]

        reset = await use_cases.manage_session_skills(
            detail.session_id,
            MainAgentSessionSkillRequest(action="reset", surface="qq"),
        )
        assert reset.status == "ok"
        assert reset.result["policy"]["mode"] == "all"
        assert reset.result["counts"]["active"] == 2

        persisted_policy = WorkspaceSkillPolicyStore(workspace_dir).load()
        assert persisted_policy.mode == "all"
        assert persisted_policy.allowlist == ()
        assert persisted_policy.denylist == ()

    asyncio.run(_run())


def test_use_case_can_install_workspace_skill_for_shared_session(tmp_path: Path) -> None:
    builtin_dir = tmp_path / "builtin-skills"
    workspace_dir = tmp_path / "workspace"
    source_skill_dir = tmp_path / "source-skill"
    builtin_dir.mkdir(parents=True, exist_ok=True)
    source_skill_dir.mkdir(parents=True, exist_ok=True)
    (source_skill_dir / "SKILL.md").write_text(
        "---\nname: repo-helper\ndescription: Workspace-local guidance.\n---\nUse for this repo.\n",
        encoding="utf-8",
    )

    config = Config(
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
            enable_skills=True,
            enable_mcp=False,
            skills_dir=str(builtin_dir),
        ),
    )
    async def _run() -> None:
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

        runtime = _runtime_manager(
            ttl_seconds=3600,
            build_agent=_build_agent,
            build_agent_with_selection=_build_agent_with_selection,
            load_runtime_config=lambda: config,
            storage_dir=tmp_path / "skill-install-store",
        )
        use_cases = _runtime_surface_service(runtime_manager=runtime, resolve_workspace_dir=lambda value: Path(str(value or workspace_dir)).resolve())

        detail = await _import_runtime_session(
            runtime,
                workspace_dir=str(workspace_dir),
                title="Remote Skill Install Test",
                origin_surface="qq",
                active_surface="qq",
                selected_model_source="preset",
                selected_provider_id="openai",
                selected_model_id="gpt-5.4",
                agent_messages=[
                    {"role": "system", "content": "system"},
                    {"role": "assistant", "content": "ready"},
                ],
                transcript=[
                    {"role": "assistant", "content": "ready", "surface": "qq"},
                ],
        )

        response = await use_cases.manage_session_skills(
            detail.session_id,
            MainAgentSessionSkillRequest(
                action="install",
                path=str(source_skill_dir),
                surface="qq",
            ),
        )

        assert response.status == "ok"
        assert response.result["summary"] == "installed repo-helper"
        assert "Installed Skill:" in response.result["details"]
        assert "- ledger " in response.result["details"]
        assert "repo-helper" in response.result["details"]
        assert build_calls[-1] == ("preset", "openai", "gpt-5.4")
        installed_skill_file = workspace_dir / ".mini-agent" / "skills" / "repo-helper" / "SKILL.md"
        assert installed_skill_file.exists()
        persisted_policy = WorkspaceSkillPolicyStore(workspace_dir).load()
        assert "repo-helper" in persisted_policy.allowlist

    asyncio.run(_run())


def test_use_case_can_uninstall_and_rollback_workspace_skill_for_shared_session(tmp_path: Path) -> None:
    builtin_dir = tmp_path / "builtin-skills"
    workspace_dir = tmp_path / "workspace"
    source_skill_dir = tmp_path / "source-skill"
    builtin_dir.mkdir(parents=True, exist_ok=True)
    source_skill_dir.mkdir(parents=True, exist_ok=True)
    (source_skill_dir / "SKILL.md").write_text(
        "---\nname: repo-helper\ndescription: Workspace-local guidance.\n---\nUse for this repo.\n",
        encoding="utf-8",
    )

    config = Config(
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
            enable_skills=True,
            enable_mcp=False,
            skills_dir=str(builtin_dir),
        ),
    )
    async def _run() -> None:
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

        runtime = _runtime_manager(
            ttl_seconds=3600,
            build_agent=_build_agent,
            build_agent_with_selection=_build_agent_with_selection,
            load_runtime_config=lambda: config,
            storage_dir=tmp_path / "skill-uninstall-rollback-store",
        )
        use_cases = _runtime_surface_service(runtime_manager=runtime, resolve_workspace_dir=lambda value: Path(str(value or workspace_dir)).resolve())

        detail = await _import_runtime_session(
            runtime,
                workspace_dir=str(workspace_dir),
                title="Remote Skill Uninstall Test",
                origin_surface="qq",
                active_surface="qq",
                selected_model_source="preset",
                selected_provider_id="openai",
                selected_model_id="gpt-5.4",
                agent_messages=[
                    {"role": "system", "content": "system"},
                    {"role": "assistant", "content": "ready"},
                ],
                transcript=[
                    {"role": "assistant", "content": "ready", "surface": "qq"},
                ],
        )

        await use_cases.manage_session_skills(
            detail.session_id,
            MainAgentSessionSkillRequest(
                action="install",
                path=str(source_skill_dir),
                surface="qq",
            ),
        )

        uninstall = await use_cases.manage_session_skills(
            detail.session_id,
            MainAgentSessionSkillRequest(
                action="uninstall",
                skill_name="repo-helper",
                surface="qq",
            ),
        )
        assert uninstall.status == "ok"
        assert uninstall.result["summary"] == "uninstalled repo-helper"
        assert "Uninstalled Skill:" in uninstall.result["details"]
        assert "repo-helper" in uninstall.result["details"]
        installed_skill_dir = workspace_dir / ".mini-agent" / "skills" / "repo-helper"
        assert installed_skill_dir.exists() is False

        rollback = await use_cases.manage_session_skills(
            detail.session_id,
            MainAgentSessionSkillRequest(
                action="rollback",
                skill_name="repo-helper",
                surface="qq",
            ),
        )
        assert rollback.status == "ok"
        assert rollback.result["summary"] == "rolled back repo-helper"
        assert "Rolled Back Skill:" in rollback.result["details"]
        assert installed_skill_dir.joinpath("SKILL.md").exists()
        assert build_calls[-1] == ("preset", "openai", "gpt-5.4")

    asyncio.run(_run())


def test_use_case_updates_shared_session_skill_policy_while_busy_without_rebuild(tmp_path: Path) -> None:
    builtin_dir = tmp_path / "builtin-skills"
    workspace_dir = tmp_path / "workspace"
    workspace_skill_dir = workspace_dir / ".mini-agent" / "skills"
    builtin_dir.mkdir(parents=True, exist_ok=True)
    workspace_skill_dir.mkdir(parents=True, exist_ok=True)
    (builtin_dir / "doc-coauthoring").mkdir(parents=True, exist_ok=True)
    (builtin_dir / "doc-coauthoring" / "SKILL.md").write_text(
        "---\nname: doc-coauthoring\ndescription: Draft structured docs.\n---\nUse for docs.\n",
        encoding="utf-8",
    )

    config = Config(
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
            enable_skills=True,
            enable_mcp=False,
            skills_dir=str(builtin_dir),
        ),
    )
    async def _run() -> None:
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

        runtime = _runtime_manager(
            ttl_seconds=3600,
            build_agent=_build_agent,
            build_agent_with_selection=_build_agent_with_selection,
            load_runtime_config=lambda: config,
            policy=MainAgentRuntimePolicy(
                mode=MainAgentRuntimeMode.TEAM,
                max_active_sessions=4,
                reserved_team_slots=4,
            ),
            storage_dir=tmp_path / "skill-policy-busy-store",
        )
        use_cases = _runtime_surface_service(runtime_manager=runtime, resolve_workspace_dir=lambda value: Path(str(value or workspace_dir)).resolve())

        detail = await _import_runtime_session(
            runtime,
                workspace_dir=str(workspace_dir),
                title="Remote Busy Skill Policy Test",
                origin_surface="qq",
                active_surface="qq",
                selected_model_source="preset",
                selected_provider_id="openai",
                selected_model_id="gpt-5.4",
                agent_messages=[
                    {"role": "system", "content": "system"},
                    {"role": "assistant", "content": "ready"},
                ],
                transcript=[
                    {"role": "assistant", "content": "ready", "surface": "qq"},
                ],
        )
        sibling = await _import_runtime_session(
            runtime,
                workspace_dir=str(workspace_dir),
                title="Sibling Skill Policy Test",
                origin_surface="qq",
                active_surface="qq",
                selected_model_source="preset",
                selected_provider_id="openai",
                selected_model_id="gpt-5.4",
                agent_messages=[
                    {"role": "system", "content": "system"},
                    {"role": "assistant", "content": "ready"},
                ],
                transcript=[
                    {"role": "assistant", "content": "ready", "surface": "qq"},
                ],
        )

        session = runtime._sessions[detail.session_id]
        session.projection.busy = True
        sibling_session = runtime._sessions[sibling.session_id]
        build_count_before = len(build_calls)

        response = await use_cases.manage_session_skills(
            detail.session_id,
            MainAgentSessionSkillRequest(action="mode", mode="allowlist", surface="qq"),
        )

        assert response.status == "busy"
        assert "apply automatically" in response.result["details"].lower()
        assert response.result["reload_pending"] is True
        assert response.result["reload_queued_current_session"] is True
        assert response.result["reload_queued_other_sessions"] == 1
        assert len(build_calls) == build_count_before
        assert session.projection.pending_skill_reload is True
        assert sibling_session.projection.pending_skill_reload is True
        detail_after = await use_cases.get_session_detail(detail.session_id)
        sibling_after = await use_cases.get_session_detail(sibling.session_id)
        assert detail_after.pending_skill_reload is True
        assert sibling_after.pending_skill_reload is True
        persisted_policy = WorkspaceSkillPolicyStore(workspace_dir).load()
        assert persisted_policy.mode == "allowlist"
        session.projection.busy = False
        reapplied = await runtime.apply_pending_session_skill_reload(session)
        assert reapplied is True
        assert session.projection.pending_skill_reload is False
        assert build_calls[-1] == ("preset", "openai", "gpt-5.4")

    asyncio.run(_run())


def test_use_case_returns_not_found_for_missing_shared_session_skill(tmp_path: Path) -> None:
    builtin_dir = tmp_path / "builtin-skills"
    workspace_dir = tmp_path / "workspace"
    builtin_dir.mkdir(parents=True, exist_ok=True)
    (builtin_dir / "doc-coauthoring").mkdir(parents=True, exist_ok=True)
    (builtin_dir / "doc-coauthoring" / "SKILL.md").write_text(
        "---\nname: doc-coauthoring\ndescription: Draft structured docs.\n---\nUse for docs.\n",
        encoding="utf-8",
    )

    config = Config(
        llm=LLMConfig(api_key="sk-test", api_base="https://api.example.com/v1", model="gpt-5.4", provider="openai"),
        agent=AgentConfig(max_steps=8, max_tool_calls_per_step=2, system_prompt_path="system_prompt.md"),
        tools=ToolsConfig(enable_file_tools=False, enable_bash=False, enable_note=False, enable_skills=True, enable_mcp=False, skills_dir=str(builtin_dir)),
    )
    async def _run() -> None:
        runtime = _runtime_manager(
            ttl_seconds=3600,
            build_agent=lambda _workspace: asyncio.sleep(
                0,
                result=_SelectableAgent(
                    provider_source="preset",
                    provider_id="openai",
                    model_id="gpt-5.4",
                ),
            ),
            load_runtime_config=lambda: config,
        )
        use_cases = _runtime_surface_service(runtime_manager=runtime, resolve_workspace_dir=lambda value: Path(str(value or workspace_dir)).resolve())

        detail = await _import_runtime_session(
            runtime,
                workspace_dir=str(workspace_dir),
                title="Remote Missing Skill Test",
                origin_surface="qq",
                active_surface="qq",
                selected_model_source="preset",
                selected_provider_id="openai",
                selected_model_id="gpt-5.4",
                agent_messages=[{"role": "system", "content": "system"}],
                transcript=[{"role": "assistant", "content": "ready", "surface": "qq"}],
        )

        response = await use_cases.manage_session_skills(
            detail.session_id,
            MainAgentSessionSkillRequest(action="show", skill_name="missing-skill", surface="qq"),
        )
        assert response.status == "not_found"
        assert response.result["found"] is False
        assert "Skill not found: missing-skill" in response.result["details"]

    asyncio.run(_run())


def test_use_case_rejects_invalid_shared_session_skill_mode(tmp_path: Path) -> None:
    builtin_dir = tmp_path / "builtin-skills"
    workspace_dir = tmp_path / "workspace"
    builtin_dir.mkdir(parents=True, exist_ok=True)
    (builtin_dir / "doc-coauthoring").mkdir(parents=True, exist_ok=True)
    (builtin_dir / "doc-coauthoring" / "SKILL.md").write_text(
        "---\nname: doc-coauthoring\ndescription: Draft structured docs.\n---\nUse for docs.\n",
        encoding="utf-8",
    )

    config = Config(
        llm=LLMConfig(api_key="sk-test", api_base="https://api.example.com/v1", model="gpt-5.4", provider="openai"),
        agent=AgentConfig(max_steps=8, max_tool_calls_per_step=2, system_prompt_path="system_prompt.md"),
        tools=ToolsConfig(enable_file_tools=False, enable_bash=False, enable_note=False, enable_skills=True, enable_mcp=False, skills_dir=str(builtin_dir)),
    )
    async def _run() -> None:
        runtime = _runtime_manager(
            ttl_seconds=3600,
            build_agent=lambda _workspace: asyncio.sleep(
                0,
                result=_SelectableAgent(
                    provider_source="preset",
                    provider_id="openai",
                    model_id="gpt-5.4",
                ),
            ),
            load_runtime_config=lambda: config,
        )
        use_cases = _runtime_surface_service(runtime_manager=runtime, resolve_workspace_dir=lambda value: Path(str(value or workspace_dir)).resolve())

        detail = await _import_runtime_session(
            runtime,
                workspace_dir=str(workspace_dir),
                title="Remote Invalid Skill Mode Test",
                origin_surface="qq",
                active_surface="qq",
                selected_model_source="preset",
                selected_provider_id="openai",
                selected_model_id="gpt-5.4",
                agent_messages=[{"role": "system", "content": "system"}],
                transcript=[{"role": "assistant", "content": "ready", "surface": "qq"}],
        )

        with pytest.raises(HTTPException, match="Unsupported skill policy mode: invalid-mode"):
            await use_cases.manage_session_skills(
                detail.session_id,
                MainAgentSessionSkillRequest(action="mode", mode="invalid-mode", surface="qq"),
            )

    asyncio.run(_run())


def test_use_case_reports_shared_session_skill_support_disabled(tmp_path: Path) -> None:
    workspace_dir = tmp_path / "workspace"

    config = Config(
        llm=LLMConfig(api_key="sk-test", api_base="https://api.example.com/v1", model="gpt-5.4", provider="openai"),
        agent=AgentConfig(max_steps=8, max_tool_calls_per_step=2, system_prompt_path="system_prompt.md"),
        tools=ToolsConfig(enable_file_tools=False, enable_bash=False, enable_note=False, enable_skills=False, enable_mcp=False, skills_dir=str(tmp_path / "builtin-skills")),
    )
    async def _run() -> None:
        runtime = _runtime_manager(
            ttl_seconds=3600,
            build_agent=lambda _workspace: asyncio.sleep(
                0,
                result=_SelectableAgent(
                    provider_source="preset",
                    provider_id="openai",
                    model_id="gpt-5.4",
                ),
            ),
            load_runtime_config=lambda: config,
        )
        use_cases = _runtime_surface_service(runtime_manager=runtime, resolve_workspace_dir=lambda value: Path(str(value or workspace_dir)).resolve())

        detail = await _import_runtime_session(
            runtime,
                workspace_dir=str(workspace_dir),
                title="Remote Disabled Skill Test",
                origin_surface="qq",
                active_surface="qq",
                selected_model_source="preset",
                selected_provider_id="openai",
                selected_model_id="gpt-5.4",
                agent_messages=[{"role": "system", "content": "system"}],
                transcript=[{"role": "assistant", "content": "ready", "surface": "qq"}],
        )

        response = await use_cases.manage_session_skills(
            detail.session_id,
            MainAgentSessionSkillRequest(action="list", surface="qq"),
        )
        assert response.status == "disabled"
        assert response.result["summary"] == "skill support disabled"

    asyncio.run(_run())


def test_use_case_reports_shared_session_skill_catalog_unavailable(tmp_path: Path, monkeypatch) -> None:
    workspace_dir = tmp_path / "workspace"

    async def _run() -> None:
        runtime = _runtime_manager(
            ttl_seconds=3600,
            build_agent=lambda _workspace: asyncio.sleep(0, result=_SelectableAgent(provider_source="preset", provider_id="openai", model_id="gpt-5.4")),
        )
        use_cases = _runtime_surface_service(runtime_manager=runtime, resolve_workspace_dir=lambda value: Path(str(value or workspace_dir)).resolve())

        detail = await _import_runtime_session(
            runtime,
                workspace_dir=str(workspace_dir),
                title="Remote Unavailable Skill Test",
                origin_surface="qq",
                active_surface="qq",
                selected_model_source="preset",
                selected_provider_id="openai",
                selected_model_id="gpt-5.4",
                agent_messages=[{"role": "system", "content": "system"}],
                transcript=[{"role": "assistant", "content": "ready", "surface": "qq"}],
        )

        monkeypatch.setattr(
            "mini_agent.agent_core.skills.command_service.resolve_skill_catalog_loader",
            lambda **kwargs: (_ for _ in ()).throw(RuntimeError("loader boom")),
        )
        response = await use_cases.manage_session_skills(
            detail.session_id,
            MainAgentSessionSkillRequest(action="list", surface="qq"),
        )
        assert response.status == "unavailable"
        assert "loader boom" in response.result["details"]

    asyncio.run(_run())


def test_use_case_can_update_shared_session_model_selection(tmp_path: Path) -> None:
    async def _run() -> None:
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

        runtime = _runtime_manager(
            ttl_seconds=3600,
            build_agent=_build_agent,
            build_agent_with_selection=_build_agent_with_selection,
            storage_dir=tmp_path / "model-selection-store",
        )
        use_cases = _runtime_surface_service(runtime_manager=runtime)

        detail = await _import_runtime_session(
            runtime,
                workspace_dir=".",
                title="Remote Model Test",
                origin_surface="qq",
                active_surface="qq",
                selected_model_source="preset",
                selected_provider_id="openai",
                selected_model_id="gpt-5.4",
                agent_messages=[
                    {"role": "system", "content": "system"},
                    {"role": "user", "content": "hello"},
                    {"role": "assistant", "content": "mock:hello"},
                ],
                transcript=[
                    {"role": "user", "content": "hello", "surface": "qq"},
                    {"role": "assistant", "content": "mock:hello", "surface": "qq"},
                ],
        )
        assert detail.selected_model_id == "gpt-5.4"

        response = await use_cases.update_session_model_selection(
            detail.session_id,
            MainAgentSessionModelSelectionRequest(
                provider_source="preset",
                provider_id="openai",
                model_id="gpt-5.3",
                surface="tui",
            ),
        )

        assert response.applied is True
        assert response.queued is False
        assert response.selected_model_source == "preset"
        assert response.selected_provider_id == "openai"
        assert response.selected_model_id == "gpt-5.3"
        assert build_calls[-1] == ("preset", "openai", "gpt-5.3")

        updated = await use_cases.get_session_detail(detail.session_id, recent_limit=10)
        assert updated.selected_model_id == "gpt-5.3"
        assert updated.pending_model_id is None

    asyncio.run(_run())


def test_use_case_can_update_shared_session_model_selection_without_provider_source(
    tmp_path: Path,
    monkeypatch,
) -> None:
    async def _run() -> None:
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

        monkeypatch.setattr(
            "mini_agent.runtime.main_agent_runtime_manager.resolve_session_model_selection_identity",
            lambda *, provider_id, model_id, provider_source=None, catalog_path=None: (
                "custom",
                provider_id,
                model_id,
            ),
        )

        runtime = _runtime_manager(
            ttl_seconds=3600,
            build_agent=_build_agent,
            build_agent_with_selection=_build_agent_with_selection,
            storage_dir=tmp_path / "shared-model-selection-inferred-store",
        )
        use_cases = _runtime_surface_service(runtime_manager=runtime)

        detail = await _import_runtime_session(
            runtime,
            workspace_dir=str(tmp_path / "workspace"),
            title="Remote Model Selection Inferred Source Test",
            origin_surface="qq",
            active_surface="qq",
            selected_model_source="preset",
            selected_provider_id="openai",
            selected_model_id="gpt-5.4",
            agent_messages=[
                {"role": "system", "content": "system"},
                {"role": "user", "content": "hello"},
                {"role": "assistant", "content": "mock:hello"},
            ],
            transcript=[
                {"role": "user", "content": "hello", "surface": "qq"},
                {"role": "assistant", "content": "mock:hello", "surface": "qq"},
            ],
        )

        response = await use_cases.update_session_model_selection(
            detail.session_id,
            MainAgentSessionModelSelectionRequest(
                provider_id="maas",
                model_id="astron-code-latest",
                surface="qq",
            ),
        )

        assert response.applied is True
        assert response.queued is False
        assert response.selected_model_source == "custom"
        assert response.selected_provider_id == "maas"
        assert response.selected_model_id == "astron-code-latest"
        assert build_calls[-1] == ("custom", "maas", "astron-code-latest")

    asyncio.run(_run())


def test_use_case_queued_shared_session_model_applies_on_next_turn(tmp_path: Path) -> None:
    async def _run() -> None:
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

        runtime = _runtime_manager(
            ttl_seconds=3600,
            build_agent=_build_agent,
            build_agent_with_selection=_build_agent_with_selection,
            storage_dir=tmp_path / "queued-model-selection-store",
        )
        use_cases = _runtime_surface_service(runtime_manager=runtime)

        session = await runtime.get_or_create_session("sess-model-queued", Path(".").resolve())
        session.projection.busy = True
        session.projection.running_state = "qq request running"
        RuntimeSessionModelIdentityCodec.set_selected_model_identity(session, ("preset", "openai", "gpt-5.4"))

        queued = await use_cases.update_session_model_selection(
            session.session_id,
            MainAgentSessionModelSelectionRequest(
                provider_source="preset",
                provider_id="openai",
                model_id="gpt-5.3",
                surface="qq",
            ),
        )
        assert queued.applied is False
        assert queued.queued is True
        assert queued.pending_model_id == "gpt-5.3"

        session.projection.busy = False
        session.projection.running_state = ""

        result = await use_cases.run_chat(
            MainAgentChatRequest(
                message="hello after queue",
                workspace_dir=".",
                session_id=session.session_id,
                surface="qq",
            )
        )

        assert result.reply == "mock:hello after queue"
        assert build_calls[-1] == ("preset", "openai", "gpt-5.3")
        detail = await use_cases.get_session_detail(session.session_id, recent_limit=10)
        assert detail.selected_model_id == "gpt-5.3"
        assert detail.pending_model_id is None

    asyncio.run(_run())


def test_use_case_can_update_shared_session_runtime_policy(tmp_path: Path, monkeypatch) -> None:
    async def _run() -> None:
        async def _build_agent(_workspace: Path):
            return _SelectableAgent(provider_source="preset", provider_id="openai", model_id="gpt-5.4")

        runtime = _runtime_manager(
            ttl_seconds=3600,
            build_agent=_build_agent,
            storage_dir=tmp_path / "runtime-policy-store",
        )
        use_cases = _runtime_surface_service(runtime_manager=runtime)

        session = await runtime.get_or_create_session("sess-policy", Path(".").resolve())

        def _fake_reconfigure(
            _handler,
            target_session,
            *,
            approval_profile: str | None,
            access_level: str | None,
        ) -> dict[str, str]:
            policy = getattr(
                get_agent_runtime_services(target_session.runtime.agent).runtime_policy_engine,
                "policy",
                None,
            )
            if policy is not None:
                policy.approval_profile = str(approval_profile or "")
                policy.access_level = str(access_level or "")
                policy.sandbox_mode = "unrestricted" if access_level == "full-access" else "workspace"
            diagnostics = {
                "approval_profile": str(approval_profile or ""),
                "access_level": str(access_level or ""),
                "sandbox_mode": "unrestricted" if access_level == "full-access" else "workspace",
            }
            target_session.projection.sandbox_diagnostics = dict(diagnostics)
            return diagnostics

        monkeypatch.setattr(RuntimeSessionAgentRuntimeHandler, "reconfigure_runtime_policy", _fake_reconfigure)

        response = await use_cases.update_session_runtime_policy(
            session.session_id,
            MainAgentSessionRuntimePolicyRequest(
                approval_profile="plan",
                access_level="full-access",
                surface="tui",
            ),
        )

        assert response.status == "updated"
        assert response.approval_profile == "plan"
        assert response.access_level == "full-access"
        assert response.summary == "runtime plan / full-access"
        assert "Runtime policy updated." in str(response.details)
        assert response.status_text == "Runtime set to plan / full-access."
        assert response.sandbox_diagnostics["sandbox_mode"] == "unrestricted"

        detail = await use_cases.get_session_detail(session.session_id, recent_limit=10)
        assert detail.sandbox_diagnostics["approval_profile"] == "plan"
        assert detail.sandbox_diagnostics["access_level"] == "full-access"
        assert detail.recent_messages[-1].metadata["command"] == "policy"

    asyncio.run(_run())


def test_use_case_rejects_runtime_policy_change_while_busy_without_pending_approval(tmp_path: Path) -> None:
    async def _run() -> None:
        async def _build_agent(_workspace: Path):
            return _SelectableAgent(provider_source="preset", provider_id="openai", model_id="gpt-5.4")

        runtime = _runtime_manager(
            ttl_seconds=3600,
            build_agent=_build_agent,
            storage_dir=tmp_path / "runtime-policy-busy-store",
        )
        use_cases = _runtime_surface_service(runtime_manager=runtime)

        session = await runtime.get_or_create_session("sess-policy-busy", Path(".").resolve())
        session.projection.busy = True
        session.runtime.pending_approvals = []

        with pytest.raises(HTTPException, match="Runtime mode can only change while idle or waiting on approval"):
            await use_cases.update_session_runtime_policy(
                session.session_id,
                MainAgentSessionRuntimePolicyRequest(
                    approval_profile="plan",
                    access_level="default",
                    surface="qq",
                ),
            )

    asyncio.run(_run())


def test_use_case_persisted_interrupted_session_exposes_recovery_snapshot_after_restart(tmp_path: Path) -> None:
    async def _run() -> None:
        async def _build_agent(_workspace: Path):
            return _HookedAgent()

        workspace = Path(".").resolve()
        runtime_first = _runtime_manager(
            ttl_seconds=3600,
            build_agent=_build_agent,
            storage_dir=tmp_path / "recovery-store",
        )
        _use_cases_first = _runtime_surface_service(runtime_manager=runtime_first)

        session = await runtime_first.get_or_create_session("sess-recovery", workspace)
        runtime_first.bind_session_surface(
            session,
            surface="qq",
            channel_type="qq",
            conversation_id="group:recovery",
            sender_id="user-1",
        )
        runtime_first.mark_turn_started(session, surface="qq", detail="qq request running")
        runtime_first.record_message(
            session,
            role="user",
            content="inspect tests",
            surface="qq",
            channel_type="qq",
            conversation_id="group:recovery",
            sender_id="user-1",
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
            sender_id="user-1",
        )

        runtime_second = _runtime_manager(
            ttl_seconds=3600,
            build_agent=_build_agent,
            storage_dir=tmp_path / "recovery-store",
        )
        use_cases_second = _runtime_surface_service(runtime_manager=runtime_second)

        sessions = await use_cases_second.list_sessions()
        assert len(sessions) == 1
        assert sessions[0].busy is False
        assert sessions[0].recovery is not None
        assert sessions[0].recovery.state == "interrupted"
        assert "qq request running" in sessions[0].recovery.summary

        detail = await use_cases_second.get_session_detail("sess-recovery", recent_limit=10)
        assert detail.recovery is not None
        assert detail.recovery.state == "interrupted"
        assert detail.recovery.last_activity == "shell ok | pytest -q | 32 passed"
        assert detail.recovery.last_user_message == "inspect tests"

    asyncio.run(_run())


def test_use_case_restarted_shared_session_keeps_recovery_until_next_turn_consumes_it(tmp_path: Path) -> None:
    async def _run() -> None:
        recovery_agent = _RecoveryCaptureAgent()

        async def _build_agent(_workspace: Path):
            return recovery_agent

        workspace = Path(".").resolve()
        store_dir = tmp_path / "recovery-continue-store"
        runtime_first = _runtime_manager(
            ttl_seconds=3600,
            build_agent=_build_agent,
            storage_dir=store_dir,
        )

        session = await runtime_first.get_or_create_session("sess-recovery-continue", workspace)
        runtime_first.bind_session_surface(
            session,
            surface="qq",
            channel_type="qq",
            conversation_id="group:recovery",
            sender_id="user-1",
        )
        runtime_first.mark_turn_started(session, surface="qq", detail="qq request running")
        runtime_first.record_message(
            session,
            role="user",
            content="inspect tests",
            surface="qq",
            channel_type="qq",
            conversation_id="group:recovery",
            sender_id="user-1",
        )
        runtime_first.record_activity(
            session,
            label="bash",
            detail="running",
            surface="qq",
            preview="pytest -q",
            state="running",
            channel_type="qq",
            conversation_id="group:recovery",
            sender_id="user-1",
        )
        approval_future: asyncio.Future[bool | None] = asyncio.get_running_loop().create_future()
        runtime_first.record_pending_approval(
            session,
            payload={
                "token": "approval-restart-1",
                "tool_name": "shell",
                "arguments": {"command": "pytest -q"},
                "kind": "exec",
                "reason": "needs manual approval",
                "step": 1,
            },
            future=approval_future,
        )

        runtime_second = _runtime_manager(
            ttl_seconds=3600,
            build_agent=_build_agent,
            storage_dir=store_dir,
        )
        use_cases_second = _runtime_surface_service(runtime_manager=runtime_second)

        detail = await use_cases_second.get_session_detail("sess-recovery-continue", recent_limit=10)
        assert detail.recovery is not None
        assert detail.recovery.state == "interrupted"
        assert detail.recovery.pending_approvals[0].token == "approval-restart-1"

        activated = await _activate_runtime_surface(runtime_second, "sess-recovery-continue", surface="tui")
        assert activated.active_surface == "tui"
        detail_after_takeover = await use_cases_second.get_session_detail("sess-recovery-continue", recent_limit=10)
        assert detail_after_takeover.recovery is not None
        assert detail_after_takeover.recovery.state == "interrupted"
        assert "approval pending" in detail_after_takeover.recovery.summary

        resumed = await use_cases_second.run_chat(
            MainAgentChatRequest(
                message="continue previous task",
                workspace_dir=".",
                session_id="sess-recovery-continue",
                surface="tui",
            )
        )
        assert resumed.reply == "recovered:continue previous task"
        captured = recovery_agent.captured_turn_contexts[-1]
        assert isinstance(captured, dict)
        metadata = captured.get("metadata")
        assert isinstance(metadata, dict)
        recovery = metadata.get("recovery")
        assert isinstance(recovery, dict)
        assert recovery.get("state") == "interrupted"
        assert recovery.get("pending_approvals")
        assert recovery.get("continue_hint")

        detail_after_resume = await use_cases_second.get_session_detail("sess-recovery-continue", recent_limit=10)
        assert detail_after_resume.recovery is not None
        assert detail_after_resume.recovery.state == "handoff"
        assert detail_after_resume.recent_messages[-1].content == "recovered:continue previous task"

        second_follow_up = await use_cases_second.run_chat(
            MainAgentChatRequest(
                message="follow up",
                workspace_dir=".",
                session_id="sess-recovery-continue",
                surface="tui",
            )
        )
        assert second_follow_up.reply == "recovered:follow up"
        metadata_second = recovery_agent.captured_turn_contexts[-1].get("metadata")
        assert isinstance(metadata_second, dict)
        assert metadata_second.get("recovery") is None

    asyncio.run(_run())


def test_runtime_record_turn_persists_user_and_assistant_messages(tmp_path: Path) -> None:
    async def _run() -> None:
        async def _build_agent(_workspace: Path):
            return _DummyAgent()

        workspace = tmp_path / "workspace-record-turn"
        workspace.mkdir(parents=True, exist_ok=True)
        runtime = _runtime_manager(
            ttl_seconds=3600,
            build_agent=_build_agent,
            storage_dir=tmp_path / "record-turn-store",
        )

        session = await runtime.get_or_create_session("sess-record-turn", workspace)
        runtime.record_turn(
            session,
            user_message="hello",
            assistant_reply="world",
            surface="tui",
        )

        detail = await runtime.get_session_detail("sess-record-turn", recent_limit=10)

        assert [item.role for item in detail.recent_messages] == ["user", "assistant"]
        assert detail.recent_messages[0].content == "hello"
        assert detail.recent_messages[1].content == "world"

    asyncio.run(_run())


def test_use_case_records_activity_transcript_for_shared_sessions() -> None:
    async def _run() -> None:
        async def _build_agent(_workspace: Path):
            return _HookedAgent()

        runtime = _runtime_manager(
            ttl_seconds=3600,
            build_agent=_build_agent,
            load_runtime_config=lambda: object(),
        )
        use_cases = _runtime_surface_service(runtime_manager=runtime)

        response = await use_cases.run_chat(
            MainAgentChatRequest(
                message="inspect tests",
                workspace_dir=".",
                session_id="sess-activity",
                surface="qq",
                channel_type="qq",
                conversation_id="group:demo",
                sender_id="user-1",
            )
        )

        assert response.reply == "hooked:inspect tests"

        detail = await use_cases.get_session_detail("sess-activity", recent_limit=10)
        assert [item.role for item in detail.recent_messages] == ["user", "tool", "assistant"]
        activity_entry = detail.recent_messages[1]
        assert activity_entry.metadata is not None
        assert activity_entry.metadata["kind"] == "activity"
        labels = [item["label"] for item in activity_entry.metadata["activity_items"]]
        assert labels == ["thinking", "shell"]
        shell_item = activity_entry.metadata["activity_items"][-1]
        assert shell_item["preview"] == "pytest -q"
        assert shell_item["state"] == "ok"
        assert "32 passed" in shell_item["output_text"]

    asyncio.run(_run())


def test_use_case_control_session_compact_keeps_existing_surface_and_records_command() -> None:
    async def _run() -> None:
        agent = _ControllableAgent()

        async def _build_agent(_workspace: Path):
            return agent

        runtime = _runtime_manager(ttl_seconds=3600, build_agent=_build_agent)
        use_cases = _runtime_surface_service(runtime_manager=runtime)

        response = await use_cases.run_chat(
            MainAgentChatRequest(
                message="hello from qq",
                workspace_dir=".",
                session_id="sess-control",
                surface="qq",
                channel_type="qq",
                conversation_id="group:demo",
                sender_id="user-1",
            )
        )
        assert response.reply == "mock:hello from qq"

        control = await use_cases.control_session(
            "sess-control",
            MainAgentSessionControlRequest(
                action="compact",
                reason="keep freshest context",
                surface="tui",
            ),
        )
        assert control.action == "compact"
        assert control.applied is True
        assert control.active_surface == "qq"
        assert agent.control_calls == [("compact", "keep freshest context")]

        detail = await use_cases.get_session_detail("sess-control", recent_limit=10)
        assert detail.active_surface == "qq"
        assert detail.reply_enabled is True
        command_entry = detail.recent_messages[-1]
        assert command_entry.role == "system"
        assert command_entry.surface == "tui"
        assert command_entry.metadata is not None
        assert command_entry.metadata["kind"] == "command"
        assert command_entry.metadata["command"] == "compact"
        assert command_entry.metadata["summary"] == "context compacted"
        assert "Messages: 5 -> 3" in command_entry.content
        assert "Tokens: 220 -> 120" in command_entry.content

    asyncio.run(_run())


def test_use_case_control_session_drop_memories_routes_to_agent_method() -> None:
    async def _run() -> None:
        agent = _ControllableAgent()

        async def _build_agent(_workspace: Path):
            return agent

        runtime = _runtime_manager(ttl_seconds=3600, build_agent=_build_agent)
        use_cases = _runtime_surface_service(runtime_manager=runtime)

        await use_cases.run_chat(
            MainAgentChatRequest(
                message="seed session",
                workspace_dir=".",
                session_id="sess-drop",
                surface="qq",
                channel_type="qq",
                conversation_id="group:drop",
                sender_id="user-2",
            )
        )

        control = await use_cases.control_session(
            "sess-drop",
            MainAgentSessionControlRequest(
                action="drop_memories",
                reason="clear older context",
                surface="qq",
                channel_type="qq",
                conversation_id="group:drop",
                sender_id="user-2",
            ),
        )
        assert control.action == "drop_memories"
        assert control.applied is True
        assert control.message_count_before == 8
        assert control.message_count_after == 4
        assert agent.control_calls == [("drop_memories", "clear older context")]

    asyncio.run(_run())


def test_use_case_control_session_can_toggle_knowledge_base() -> None:
    async def _run() -> None:
        agent = _ControllableAgent()

        async def _build_agent(_workspace: Path):
            return agent

        runtime = _runtime_manager(ttl_seconds=3600, build_agent=_build_agent)
        use_cases = _runtime_surface_service(runtime_manager=runtime)

        await use_cases.run_chat(
            MainAgentChatRequest(
                message="seed kb session",
                workspace_dir=".",
                session_id="sess-kb",
                surface="qq",
            )
        )

        control = await use_cases.control_session(
            "sess-kb",
            MainAgentSessionControlRequest(
                action="kb_off",
                surface="tui",
            ),
        )
        assert control.action == "kb_off"
        assert control.applied is True
        assert control.knowledge_base_enabled is False
        assert agent.control_calls[-1] == ("kb_off", None)

        detail = await use_cases.get_session_detail("sess-kb", recent_limit=10)
        assert detail.knowledge_base_enabled is False
        command_entry = detail.recent_messages[-1]
        assert command_entry.metadata is not None
        assert command_entry.metadata["command"] == "kb_off"
        assert command_entry.metadata["summary"] == "knowledge base disabled"
        assert "Knowledge Base: disabled" in command_entry.content

    asyncio.run(_run())


def test_use_case_control_session_mcp_list_records_operator_snapshot(monkeypatch) -> None:
    async def _run() -> None:
        agent = _DummyAgent()

        async def _build_agent(_workspace: Path):
            return agent

        runtime = _runtime_manager(ttl_seconds=3600, build_agent=_build_agent)
        use_cases = _runtime_surface_service(runtime_manager=runtime)

        await use_cases.run_chat(
            MainAgentChatRequest(
                message="seed mcp session",
                workspace_dir=".",
                session_id="sess-mcp-list",
                surface="qq",
            )
        )

        snapshot = SimpleNamespace(
            configured_total=3,
            discoverable_total=2,
            disabled_total=1,
            active_total=1,
            tool_total=2,
        )
        monkeypatch.setattr(
            "mini_agent.runtime.main_agent_runtime_manager.collect_mcp_operator_snapshot",
            lambda config: snapshot,
        )
        monkeypatch.setattr(
            "mini_agent.runtime.main_agent_runtime_manager.format_mcp_status",
            lambda current: f"MCP Status:\n- active {current.active_total}\n- tools {current.tool_total}",
        )
        monkeypatch.setattr(
            "mini_agent.runtime.main_agent_runtime_manager.format_mcp_server_list",
            lambda current: f"MCP Servers:\n- configured {current.configured_total}",
        )

        control = await use_cases.control_session(
            "sess-mcp-list",
            MainAgentSessionControlRequest(
                action="mcp_list",
                surface="tui",
            ),
        )
        assert control.action == "mcp_list"
        assert control.applied is False
        assert control.stats is not None
        assert control.stats["summary"] == "3 configured server(s) | 1 active"
        assert "MCP Servers:" in control.stats["details"]

        detail = await use_cases.get_session_detail("sess-mcp-list", recent_limit=10)
        command_entry = detail.recent_messages[-1]
        assert command_entry.metadata is not None
        assert command_entry.metadata["command"] == "mcp list"
        assert command_entry.metadata["summary"] == "3 configured server(s) | 1 active"
        assert command_entry.metadata["threads_visible"] is False
        assert "MCP Status:" in command_entry.content
        assert "MCP Servers:" in command_entry.content

    asyncio.run(_run())


def test_use_case_control_session_mcp_reload_rebuilds_session_agent(monkeypatch, tmp_path: Path) -> None:
    async def _run() -> None:
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

        runtime = _runtime_manager(
            ttl_seconds=3600,
            build_agent=_build_agent,
            build_agent_with_selection=_build_agent_with_selection,
            load_runtime_config=lambda: object(),
            storage_dir=tmp_path / "mcp-reload-store",
        )
        use_cases = _runtime_surface_service(runtime_manager=runtime)

        await use_cases.run_chat(
            MainAgentChatRequest(
                message="seed mcp reload session",
                workspace_dir=".",
                session_id="sess-mcp-reload",
                surface="qq",
            )
        )

        snapshot = SimpleNamespace(
            configured_total=3,
            discoverable_total=3,
            disabled_total=0,
            active_total=2,
            tool_total=5,
        )
        calls: dict[str, int] = {"cleanup": 0}
        monkeypatch.setattr(
            "mini_agent.runtime.main_agent_runtime_manager.collect_mcp_operator_snapshot",
            lambda config: snapshot,
        )
        monkeypatch.setattr(
            "mini_agent.runtime.main_agent_runtime_manager.format_mcp_status",
            lambda current: f"status active={current.active_total} tools={current.tool_total}",
        )
        monkeypatch.setattr(
            "mini_agent.runtime.main_agent_runtime_manager.format_mcp_server_list",
            lambda current: f"servers configured={current.configured_total}",
        )

        async def _fake_cleanup() -> None:
            calls["cleanup"] += 1

        monkeypatch.setattr(
            "mini_agent.runtime.main_agent_runtime_manager.cleanup_mcp_connections",
            _fake_cleanup,
        )

        control = await use_cases.control_session(
            "sess-mcp-reload",
            MainAgentSessionControlRequest(
                action="mcp_reload",
                surface="tui",
            ),
        )
        assert control.action == "mcp_reload"
        assert control.applied is True
        assert control.stats is not None
        assert control.stats["summary"] == "reloaded MCP | 2 active server(s) | 5 tool(s)"
        assert "servers configured=3" in control.stats["details"]
        assert calls["cleanup"] == 1
        assert build_calls == [
            (None, None, None),
            ("preset", "openai", "gpt-5.4"),
        ]

        detail = await use_cases.get_session_detail("sess-mcp-reload", recent_limit=10)
        command_entry = detail.recent_messages[-1]
        assert command_entry.metadata is not None
        assert command_entry.metadata["command"] == "mcp reload"
        assert command_entry.metadata["summary"] == "reloaded MCP | 2 active server(s) | 5 tool(s)"
        assert command_entry.metadata["threads_visible"] is False
        assert "status active=2 tools=5" in command_entry.content
        assert "servers configured=3" in command_entry.content

    asyncio.run(_run())


def test_use_case_control_session_rejects_busy_shared_session() -> None:
    async def _run() -> None:
        agent = _ControllableAgent()

        async def _build_agent(_workspace: Path):
            return agent

        runtime = _runtime_manager(ttl_seconds=3600, build_agent=_build_agent)
        use_cases = _runtime_surface_service(runtime_manager=runtime)

        session = await runtime.get_or_create_session("sess-busy-control", Path(".").resolve())
        session.projection.busy = True

        with pytest.raises(Exception) as exc_info:
            await use_cases.control_session(
                "sess-busy-control",
                MainAgentSessionControlRequest(action="compact"),
            )
        assert getattr(exc_info.value, "status_code", None) == 409

    asyncio.run(_run())


def test_use_case_update_session_context_persists_and_applies_on_next_turn() -> None:
    async def _run() -> None:
        agent = _RecoveryCaptureAgent()

        async def _build_agent(_workspace: Path):
            return agent

        runtime = _runtime_manager(ttl_seconds=3600, build_agent=_build_agent)
        use_cases = _runtime_surface_service(runtime_manager=runtime)

        await use_cases.run_chat(
            MainAgentChatRequest(
                message="seed context session",
                workspace_dir=".",
                session_id="sess-context-policy",
                surface="qq",
                channel_type="qq",
                conversation_id="group:context",
                sender_id="user-ctx",
            )
        )

        updated = await use_cases.update_session_context(
            "sess-context-policy",
            MainAgentSessionContextRequest(
                action="include",
                sources=["knowledge_base", "workspace_memory"],
                surface="qq",
                channel_type="qq",
                conversation_id="group:context",
                sender_id="user-ctx",
            ),
        )
        assert updated.status == "updated"
        assert updated.context_policy["include_sources"] == ["knowledge_base", "workspace_memory"]

        detail = await use_cases.get_session_detail("sess-context-policy", recent_limit=10)
        assert detail.context_policy["include_sources"] == ["knowledge_base", "workspace_memory"]
        assert detail.recent_messages[-1].metadata["command"] == "context include"

        await use_cases.run_chat(
            MainAgentChatRequest(
                message="respect shared policy",
                workspace_dir=".",
                session_id="sess-context-policy",
                surface="tui",
            )
        )
        captured = agent.captured_turn_contexts[-1]
        assert isinstance(captured, dict)
        metadata = captured.get("metadata")
        assert isinstance(metadata, dict)
        assert metadata["prepared_context_policy"]["include_sources"] == [
            "knowledge_base",
            "workspace_memory",
        ]

    asyncio.run(_run())


def test_use_case_update_session_context_budget_and_reset() -> None:
    async def _run() -> None:
        async def _build_agent(_workspace: Path):
            return _DummyAgent()

        runtime = _runtime_manager(ttl_seconds=3600, build_agent=_build_agent)
        use_cases = _runtime_surface_service(runtime_manager=runtime)

        await use_cases.run_chat(
            MainAgentChatRequest(
                message="seed context budget session",
                workspace_dir=".",
                session_id="sess-context-budget",
                surface="tui",
            )
        )

        updated = await use_cases.update_session_context(
            "sess-context-budget",
            MainAgentSessionContextRequest(
                action="budget",
                max_items=2,
                max_total_chars=900,
                max_items_per_source=1,
                surface="tui",
            ),
        )
        assert updated.context_policy["max_items"] == 2
        assert updated.context_policy["max_total_chars"] == 900
        assert updated.context_policy["max_items_per_source"] == 1
        assert updated.context_policy["active"] is True

        reset = await use_cases.update_session_context(
            "sess-context-budget",
            MainAgentSessionContextRequest(
                action="reset",
                surface="tui",
            ),
        )
        assert reset.context_policy["include_sources"] == []
        assert reset.context_policy["exclude_sources"] == []
        assert reset.context_policy["max_items"] == 4
        assert reset.context_policy["max_total_chars"] == 2400
        assert reset.context_policy["max_items_per_source"] == 1
        assert reset.context_policy["active"] is False

    asyncio.run(_run())


def test_use_case_rejects_context_update_while_busy() -> None:
    async def _run() -> None:
        async def _build_agent(_workspace: Path):
            return _DummyAgent()

        runtime = _runtime_manager(ttl_seconds=3600, build_agent=_build_agent)
        use_cases = _runtime_surface_service(runtime_manager=runtime)

        session = await runtime.get_or_create_session("sess-context-busy", Path(".").resolve())
        session.projection.busy = True

        with pytest.raises(Exception) as exc_info:
            await use_cases.update_session_context(
                "sess-context-busy",
                MainAgentSessionContextRequest(action="reset"),
            )
        assert getattr(exc_info.value, "status_code", None) == 409

    asyncio.run(_run())


def test_use_case_manage_session_memory_reports_runtime_entries_and_can_promote_note_and_shared(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("MINI_AGENT_GLOBAL_MEMORY_ROOT", str((tmp_path / "global").resolve()))
    monkeypatch.setattr("mini_agent.memory.memoria_runtime.Path.home", classmethod(lambda cls: tmp_path))

    async def _run() -> None:
        async def _build_agent(_workspace: Path):
            return _DummyAgent()

        workspace = tmp_path / "workspace"
        workspace.mkdir(parents=True, exist_ok=True)
        runtime = _runtime_manager(
            ttl_seconds=3600,
            build_agent=_build_agent,
            storage_dir=tmp_path / "memory-session-store",
        )
        use_cases = _runtime_surface_service(runtime_manager=runtime, resolve_workspace_dir=lambda workspace_dir: workspace if workspace_dir else workspace)

        await use_cases.run_chat(
            MainAgentChatRequest(
                message="seed memory session",
                workspace_dir=str(workspace),
                session_id="sess-memory",
                surface="tui",
            )
        )

        runtime_memory = WorkspaceMemoriaRuntime(workspace)
        saved = runtime_memory.save_session_memory(
            "sess-memory",
            content="task: inspect memory plumbing | latest: gateway shared sessions should route reply targets through the active surface",
            metadata={
                "knowledge_base_grounded": True,
                "knowledge_base_query": "reply target routing",
                "knowledge_base_id": "default",
                "knowledge_base_hits": 2,
                "knowledge_base_refs": ["docs/routing.md", "docs/gateway.md"],
                "workspace_shared_candidate": True,
                "workspace_shared_candidate_reason": "",
                "workspace_shared_candidate_text": "gateway shared sessions should route reply targets through the active surface",
            },
        )
        engram_id = str(saved.get("engram_id") or "")
        assert engram_id

        runtime_view = await use_cases.manage_session_memory(
            "sess-memory",
            MainAgentSessionMemoryRequest(action="runtime", detail_mode="full", surface="tui"),
        )
        assert runtime_view.status == "ok"
        assert "Runtime Task Memory" in runtime_view.result["details"]
        assert runtime_view.memory_diagnostics["runtime_task_memory"]["session_count"] >= 1

        list_view = await use_cases.manage_session_memory(
            "sess-memory",
            MainAgentSessionMemoryRequest(action="list", detail_mode="full", surface="tui"),
        )
        assert list_view.status == "ok"
        assert "Session Runtime Memory" in list_view.result["details"]
        assert "1. [" in list_view.result["details"]
        assert "[KB | shared-candidate]" in list_view.result["details"]
        assert "kb: default | hits: 2 | query: reply target routing" in list_view.result["details"]
        assert "refs: docs/routing.md; docs/gateway.md" in list_view.result["details"]

        session_show = await use_cases.manage_session_memory(
            "sess-memory",
            MainAgentSessionMemoryRequest(
                action="session_show",
                engram_id="latest",
                detail_mode="full",
                surface="tui",
            ),
        )
        assert session_show.status == "ok"
        assert str(session_show.result["engram_id"] or "").strip()
        assert "Session Runtime Memory" in session_show.result["details"]
        assert "Knowledge Base: grounded" in session_show.result["details"]
        assert "- query: reply target routing" in session_show.result["details"]
        assert "- refs: docs/routing.md; docs/gateway.md" in session_show.result["details"]

        shared_promoted = await use_cases.manage_session_memory(
            "sess-memory",
            MainAgentSessionMemoryRequest(
                action="promote_shared",
                engram_id="latest",
                detail_mode="brief",
                surface="tui",
            ),
        )
        assert shared_promoted.status == "ok"
        assert shared_promoted.result["promotion"]["target"] == "workspace_shared"
        assert shared_promoted.result["engram_id"] == engram_id
        assert shared_promoted.result["selector"] == "latest"

        shared_list = await use_cases.manage_session_memory(
            "sess-memory",
            MainAgentSessionMemoryRequest(action="shared_list", detail_mode="full", surface="tui"),
        )
        assert shared_list.status == "ok"
        assert "Workspace-Shared Runtime Memory" in shared_list.result["details"]
        assert "Shared entries: 1" in shared_list.result["details"]

        shared_show = await use_cases.manage_session_memory(
            "sess-memory",
            MainAgentSessionMemoryRequest(
                action="shared_show",
                engram_id="latest",
                detail_mode="full",
                surface="tui",
            ),
        )
        assert shared_show.status == "ok"
        assert str(shared_show.result["engram_id"] or "").strip()
        assert "route reply targets through the active surface" in shared_show.result["details"]
        assert "Knowledge Base: grounded" in shared_show.result["details"]
        assert "- query: reply target routing" in shared_show.result["details"]
        assert "- refs: docs/routing.md; docs/gateway.md" in shared_show.result["details"]

        promoted = await use_cases.manage_session_memory(
            "sess-memory",
            MainAgentSessionMemoryRequest(
                action="promote_note",
                engram_id="latest",
                detail_mode="brief",
                surface="tui",
            ),
        )
        assert promoted.status == "ok"
        assert promoted.result["promotion"]["target"] == "workspace_note"
        assert promoted.result["engram_id"] == engram_id
        assert promoted.result["selector"] == "latest"

        detail = await use_cases.get_session_detail("sess-memory", recent_limit=12)
        command_entries = [
            item
            for item in detail.recent_messages
            if item.role == "system"
            and isinstance(item.metadata, dict)
            and item.metadata.get("command") in {"memory promote_shared", "memory promote_note"}
        ]
        assert command_entries
        assert "route reply targets through the active surface" in workspace.joinpath("MEMORY.md").read_text(encoding="utf-8")
        runtime_view_after = await use_cases.manage_session_memory(
            "sess-memory",
            MainAgentSessionMemoryRequest(action="runtime", detail_mode="full", surface="tui"),
        )
        assert runtime_view_after.memory_diagnostics["runtime_task_memory"]["shared_count"] >= 1

        shared_cleared = await use_cases.manage_session_memory(
            "sess-memory",
            MainAgentSessionMemoryRequest(action="shared_clear", detail_mode="full", surface="tui"),
        )
        assert shared_cleared.status == "ok"
        assert shared_cleared.result["cleared"] is True

        runtime_view_cleared = await use_cases.manage_session_memory(
            "sess-memory",
            MainAgentSessionMemoryRequest(action="runtime", detail_mode="full", surface="tui"),
        )
        assert runtime_view_cleared.memory_diagnostics["runtime_task_memory"]["shared_count"] == 0
    asyncio.run(_run())


def test_use_case_manage_session_memory_can_save_distilled_note_and_profile(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("MINI_AGENT_GLOBAL_MEMORY_ROOT", str((tmp_path / "global").resolve()))
    monkeypatch.setattr("mini_agent.memory.memoria_runtime.Path.home", classmethod(lambda cls: tmp_path))

    async def _run() -> None:
        async def _build_agent(_workspace: Path):
            return _DummyAgent()

        workspace = tmp_path / "workspace"
        workspace.mkdir(parents=True, exist_ok=True)
        runtime = _runtime_manager(
            ttl_seconds=3600,
            build_agent=_build_agent,
            storage_dir=tmp_path / "memory-save-store",
        )
        use_cases = _runtime_surface_service(runtime_manager=runtime, resolve_workspace_dir=lambda workspace_dir: workspace if workspace_dir else workspace)

        await use_cases.run_chat(
            MainAgentChatRequest(
                message="seed session for save commands",
                workspace_dir=str(workspace),
                session_id="sess-memory-save",
                surface="tui",
            )
        )

        runtime._sessions["sess-memory-save"].projection.last_prepared_context = {
            "sources": ["knowledge_base"],
            "items": [
                {
                    "source": "knowledge_base",
                    "title": "KB result",
                    "content": "Manual confirmation should store distilled conclusions only.",
                    "metadata": {
                        "query": "manual KB confirmation",
                        "knowledge_base_id": "default",
                        "source_path": "docs/grounding.md",
                    },
                }
            ],
        }

        note_result = await use_cases.manage_session_memory(
            "sess-memory-save",
            MainAgentSessionMemoryRequest(
                action="save_note",
                content="Workspace decision: confirm KB conclusions manually before durable storage",
                detail_mode="brief",
                surface="tui",
            ),
        )
        assert note_result.status == "ok"
        assert note_result.result["saved"]["target"] == "workspace_note"
        assert note_result.result["saved"]["category"] == "kb_confirmed"
        assert note_result.result["saved"]["knowledge_base_grounding"]["grounded"] is True
        assert "docs/grounding.md" in note_result.result["saved"]["knowledge_base_grounding"]["refs"]

        profile_result = await use_cases.manage_session_memory(
            "sess-memory-save",
            MainAgentSessionMemoryRequest(
                action="save_profile",
                content="User prefers Chinese replies during debugging",
                detail_mode="brief",
                surface="tui",
            ),
        )
        assert profile_result.status == "ok"
        assert profile_result.result["saved"]["target"] == "global_profile"

        memory_text = workspace.joinpath("MEMORY.md").read_text(encoding="utf-8")
        assert "kb_confirmed" in memory_text
        assert "confirm KB conclusions manually" in memory_text

        global_profile = (tmp_path / "global" / "USER.md").read_text(encoding="utf-8")
        assert "User prefers Chinese replies during debugging" in global_profile

    asyncio.run(_run())


def test_use_case_manage_session_memory_can_view_durable_profile_notes_and_daily(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("MINI_AGENT_GLOBAL_MEMORY_ROOT", str((tmp_path / "global").resolve()))
    monkeypatch.setattr("mini_agent.memory.memoria_runtime.Path.home", classmethod(lambda cls: tmp_path))

    async def _run() -> None:
        async def _build_agent(_workspace: Path):
            return _DummyAgent()

        workspace = tmp_path / "workspace"
        workspace.mkdir(parents=True, exist_ok=True)
        memory = MemoryService(workspace)
        memory.add_profile_fact(fact="User prefers concise Chinese replies during debugging")
        memory.append_note(
            content="routing decisions should stay in workspace durable notes",
            category="operator_note",
            scope="long_term",
            now=datetime(2026, 4, 10, tzinfo=timezone.utc),
        )
        memory.append_note(
            content="daily durable note for gateway memory daily command",
            category="daily_note",
            scope="daily",
            now=datetime(2026, 4, 10, tzinfo=timezone.utc),
        )

        runtime = _runtime_manager(
            ttl_seconds=3600,
            build_agent=_build_agent,
            storage_dir=tmp_path / "memory-view-store",
        )
        use_cases = _runtime_surface_service(runtime_manager=runtime, resolve_workspace_dir=lambda workspace_dir: workspace if workspace_dir else workspace)

        await use_cases.run_chat(
            MainAgentChatRequest(
                message="seed durable memory session",
                workspace_dir=str(workspace),
                session_id="sess-memory-view",
                surface="tui",
            )
        )

        profile_view = await use_cases.manage_session_memory(
            "sess-memory-view",
            MainAgentSessionMemoryRequest(
                action="profile",
                query="Chinese replies",
                detail_mode="full",
                surface="tui",
            ),
        )
        assert profile_view.status == "ok"
        assert "Global Profile Memory" in profile_view.result["details"]
        assert "User prefers concise Chinese replies during debugging" in profile_view.result["details"]

        notes_view = await use_cases.manage_session_memory(
            "sess-memory-view",
            MainAgentSessionMemoryRequest(
                action="notes",
                query="routing",
                detail_mode="full",
                surface="tui",
            ),
        )
        assert notes_view.status == "ok"
        assert "Workspace Durable Notes" in notes_view.result["details"]
        assert "routing decisions should stay in workspace durable notes" in notes_view.result["details"]

        daily_view = await use_cases.manage_session_memory(
            "sess-memory-view",
            MainAgentSessionMemoryRequest(
                action="daily",
                day="2026-04-10",
                detail_mode="full",
                surface="tui",
            ),
        )
        assert daily_view.status == "ok"
        assert "Workspace Daily Memory" in daily_view.result["details"]
        assert "daily durable note for gateway memory daily command" in daily_view.result["details"]

    asyncio.run(_run())


def test_use_case_manage_session_memory_can_view_consolidated_memory(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("MINI_AGENT_GLOBAL_MEMORY_ROOT", str((tmp_path / "global").resolve()))
    monkeypatch.setattr("mini_agent.memory.memoria_runtime.Path.home", classmethod(lambda cls: tmp_path))

    async def _run() -> None:
        async def _build_agent(_workspace: Path):
            return _DummyAgent()

        workspace = tmp_path / "workspace"
        workspace.mkdir(parents=True, exist_ok=True)
        _write_consolidated_memory(
            workspace / "MEMORY.md",
            items=[
                "restart recovery should preserve approval hints",
                "routing guardrails remain workspace scoped",
            ],
            last_updated_utc="2026-04-10T00:00:00+00:00",
        )

        runtime = _runtime_manager(
            ttl_seconds=3600,
            build_agent=_build_agent,
            storage_dir=tmp_path / "memory-consolidated-store",
        )
        use_cases = _runtime_surface_service(runtime_manager=runtime, resolve_workspace_dir=lambda workspace_dir: workspace if workspace_dir else workspace)

        await use_cases.run_chat(
            MainAgentChatRequest(
                message="seed consolidated memory session",
                workspace_dir=str(workspace),
                session_id="sess-memory-consolidated",
                surface="tui",
            )
        )

        consolidated_view = await use_cases.manage_session_memory(
            "sess-memory-consolidated",
            MainAgentSessionMemoryRequest(
                action="consolidated_show",
                detail_mode="full",
                surface="tui",
            ),
        )
        assert consolidated_view.status == "ok"
        assert "Consolidated Memory" in consolidated_view.result["details"]
        assert "restart recovery should preserve approval hints" in consolidated_view.result["details"]

        consolidated_search = await use_cases.manage_session_memory(
            "sess-memory-consolidated",
            MainAgentSessionMemoryRequest(
                action="consolidated_search",
                query="routing",
                detail_mode="full",
                surface="tui",
            ),
        )
        assert consolidated_search.status == "ok"
        assert "Consolidated Memory Search" in consolidated_search.result["details"]
        assert "routing guardrails remain workspace scoped" in consolidated_search.result["details"]

    asyncio.run(_run())


def test_use_case_manage_session_memory_can_view_memory_overview_and_export(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("MINI_AGENT_GLOBAL_MEMORY_ROOT", str((tmp_path / "global").resolve()))
    monkeypatch.setattr("mini_agent.memory.memoria_runtime.Path.home", classmethod(lambda cls: tmp_path))

    async def _run() -> None:
        async def _build_agent(_workspace: Path):
            return _DummyAgent()

        workspace = tmp_path / "workspace"
        workspace.mkdir(parents=True, exist_ok=True)
        memory = MemoryService(workspace)
        memory.add_profile_fact(fact="User prefers concise Chinese replies during debugging")
        _write_consolidated_memory(
            workspace / "MEMORY.md",
            items=["restart recovery should preserve approval hints"],
            last_updated_utc="2026-04-10T00:00:00+00:00",
        )
        memory.append_note(
            content="remembered workspace note for gateway export",
            category="operator_note",
            scope="long_term",
            now=datetime(2026, 4, 10, tzinfo=timezone.utc),
        )

        runtime = _runtime_manager(
            ttl_seconds=3600,
            build_agent=_build_agent,
            storage_dir=tmp_path / "memory-overview-store",
        )
        use_cases = _runtime_surface_service(runtime_manager=runtime, resolve_workspace_dir=lambda workspace_dir: workspace if workspace_dir else workspace)

        await use_cases.run_chat(
            MainAgentChatRequest(
                message="seed memory overview session",
                workspace_dir=str(workspace),
                session_id="sess-memory-overview",
                surface="tui",
            )
        )

        overview = await use_cases.manage_session_memory(
            "sess-memory-overview",
            MainAgentSessionMemoryRequest(
                action="overview",
                detail_mode="full",
                surface="tui",
            ),
        )
        assert overview.status == "ok"
        assert "Memory Overview" in overview.result["details"]
        assert "Session Context" in overview.result["details"]
        assert "session id: sess-memory-overview" in overview.result["details"]
        assert "Durable Memory" in overview.result["details"]
        assert "Consolidated Memory" in overview.result["details"]

        exported = await use_cases.manage_session_memory(
            "sess-memory-overview",
            MainAgentSessionMemoryRequest(
                action="export",
                export_format="markdown",
                detail_mode="full",
                surface="tui",
            ),
        )
        assert exported.status == "ok"
        assert "Memory Export" in exported.result["details"]
        assert "Format: markdown" in exported.result["details"]
        assert "remembered workspace note for gateway export" in exported.result["details"]

    asyncio.run(_run())


def test_runtime_manager_reset_session_clears_runtime_task_memory_and_runtime_state(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr("mini_agent.memory.memoria_runtime.Path.home", classmethod(lambda cls: tmp_path))

    async def _run() -> None:
        async def _build_agent(_workspace: Path):
            agent = _DummyAgent()
            agent.last_prepared_turn_context = {"item_count": 1}
            agent.prepared_context_diagnostics = {"turn_count": 2}
            agent.last_runtime_task_memory = {"stored": True}
            agent.api_total_tokens = 99
            return agent

        workspace = tmp_path / "workspace"
        workspace.mkdir(parents=True, exist_ok=True)
        runtime = _runtime_manager(
            ttl_seconds=3600,
            build_agent=_build_agent,
            storage_dir=tmp_path / "runtime-reset-store",
        )

        session = await runtime.get_or_create_session("sess-reset", workspace)
        session.runtime.pending_approvals = [{"token": "tok-1", "tool_name": "bash", "arguments": {}}]
        session.projection.last_prepared_context = {"item_count": 1}
        session.projection.prepared_context_diagnostics = {"turn_count": 2}
        session.projection.busy = True
        session.projection.running_state = "running"

        runtime_memory = WorkspaceMemoriaRuntime(workspace)
        runtime_memory.save_session_memory(
            "sess-reset",
            content="stale runtime memory should disappear after reset",
        )

        await runtime.reset_session("sess-reset")

        restored = await runtime.get_or_create_session("sess-reset", workspace)
        assert len(restored.runtime.agent.messages) == 1
        assert restored.runtime.agent.api_total_tokens == 0
        assert restored.runtime.pending_approvals == []
        assert restored.projection.last_prepared_context == {}
        assert restored.projection.prepared_context_diagnostics == {}
        assert restored.projection.busy is False
        assert restored.projection.running_state == ""
        assert "session:sess-reset" not in runtime_memory.stats()["namespaces"]

    asyncio.run(_run())


def test_runtime_manager_delete_session_clears_persisted_runtime_task_memory_for_inactive_session(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr("mini_agent.memory.memoria_runtime.Path.home", classmethod(lambda cls: tmp_path))

    async def _run() -> None:
        async def _build_agent(_workspace: Path):
            return _DummyAgent()

        workspace = tmp_path / "workspace"
        workspace.mkdir(parents=True, exist_ok=True)
        runtime = _runtime_manager(
            ttl_seconds=3600,
            build_agent=_build_agent,
            storage_dir=tmp_path / "runtime-delete-store",
        )

        await runtime.get_or_create_session("sess-delete", workspace)
        runtime_memory = WorkspaceMemoriaRuntime(workspace)
        runtime_memory.save_session_memory(
            "sess-delete",
            content="persisted runtime memory should also be cleared on delete",
        )

        await runtime.clear()
        assert "session:sess-delete" in runtime_memory.stats()["namespaces"]

        await runtime.delete_session("sess-delete")

        assert "session:sess-delete" not in runtime_memory.stats()["namespaces"]

    asyncio.run(_run())


def test_use_case_cancel_session_requests_running_turn_without_waiting_for_turn_lock() -> None:
    async def _run() -> None:
        agent = _BlockingCancelableAgent()

        async def _build_agent(_workspace: Path):
            return agent

        runtime = _runtime_manager(ttl_seconds=3600, build_agent=_build_agent)
        use_cases = _runtime_surface_service(runtime_manager=runtime)

        run_task = asyncio.create_task(
            use_cases.run_chat(
                MainAgentChatRequest(
                    message="long running task",
                    workspace_dir=".",
                    session_id="sess-cancel",
                    surface="qq",
                    channel_type="qq",
                    conversation_id="group:cancel",
                    sender_id="user-cancel",
                )
            )
        )

        await asyncio.wait_for(agent.started.wait(), timeout=1.0)

        cancel = await asyncio.wait_for(
            use_cases.cancel_session(
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

        assert cancel.status == "cancel_requested"
        assert cancel.active_surface == "qq"
        assert agent.received_cancel_event is not None
        assert agent.received_cancel_event.is_set()

        response = await asyncio.wait_for(run_task, timeout=1.0)
        assert response.reply == "Task cancelled by user."

        detail = await use_cases.get_session_detail("sess-cancel", recent_limit=10)
        assert detail.busy is False
        assert detail.active_surface == "qq"
        command_entry = next(
            item
            for item in detail.recent_messages
            if item.role == "system" and isinstance(item.metadata, dict) and item.metadata.get("command") == "cancel"
        )
        assert command_entry.surface == "tui"
        assert "State: cancellation requested" in command_entry.content
        assert detail.recent_messages[-1].content == "Task cancelled by user."

    asyncio.run(_run())


def test_use_case_remote_approval_resolves_pending_shared_session_turn() -> None:
    async def _run() -> None:
        async def _build_agent(_workspace: Path):
            return _ApprovalBlockingAgent()

        runtime = _runtime_manager(ttl_seconds=3600, build_agent=_build_agent)
        use_cases = _runtime_surface_service(runtime_manager=runtime)

        run_task = asyncio.create_task(
            use_cases.run_chat(
                MainAgentChatRequest(
                    message="run approved command",
                    workspace_dir=".",
                    session_id="sess-approval",
                    surface="qq",
                    channel_type="qq",
                    conversation_id="group:approval",
                    sender_id="user-1",
                )
            )
        )

        for _ in range(100):
            try:
                detail = await use_cases.get_session_detail("sess-approval", recent_limit=10)
            except Exception as exc:
                if getattr(exc, "status_code", None) == 404:
                    await asyncio.sleep(0.02)
                    continue
                raise
            if detail.pending_approvals:
                break
            await asyncio.sleep(0.02)

        detail = await use_cases.get_session_detail("sess-approval", recent_limit=10)
        assert detail.pending_approvals
        assert detail.pending_approvals[0].token == "approval_gateway_1"
        assert detail.running_state == "approval required for shell"

        approval = await use_cases.respond_to_approval(
            "sess-approval",
            MainAgentSessionApprovalRequest(
                approved=True,
                token="approval_gateway_1",
                surface="tui",
            ),
        )
        assert approval.decision == "approved"
        assert approval.tool_name == "shell"

        response = await asyncio.wait_for(run_task, timeout=2.0)
        assert response.reply == "approved remote run"

        detail_after = await use_cases.get_session_detail("sess-approval", recent_limit=12)
        assert detail_after.pending_approvals == []
        assert detail_after.recent_messages[-1].role == "assistant"
        assert detail_after.recent_messages[-1].content == "approved remote run"
        command_entries = [
            item
            for item in detail_after.recent_messages
            if item.role == "system" and isinstance(item.metadata, dict) and item.metadata.get("command") == "approve"
        ]
        assert command_entries

    asyncio.run(_run())


def test_surface_service_prefers_injected_session_task_service_for_session_entrypoints() -> None:
    class _FailingSessionService:
        def validate_workspace(self, workspace_dir: Path) -> None:
            raise AssertionError(f"session_service.validate_workspace should not be called: {workspace_dir}")

        async def list_sessions(self, *, workspace_dir=None, shared_only=False):  # noqa: ANN001, ANN003
            raise AssertionError(
                f"session_service.list_sessions should not be called: {workspace_dir}, {shared_only}"
            )

        async def create_session(self, request, *, workspace_dir):  # noqa: ANN001, ANN003
            raise AssertionError(f"session_service.create_session should not be called: {request}, {workspace_dir}")

        async def get_session_detail(self, session_id: str, *, recent_limit: int = 50):
            raise AssertionError(
                f"session_service.get_session_detail should not be called: {session_id}, {recent_limit}"
            )

        async def delete_session(self, session_id: str):
            raise AssertionError(f"session_service.delete_session should not be called: {session_id}")

    class _SessionTaskServiceStub:
        def __init__(self) -> None:
            self.calls: list[tuple[str, object]] = []

        def validate_workspace(self, workspace_dir: Path) -> None:
            self.calls.append(("validate_workspace", workspace_dir))

        async def list_sessions(self, *, workspace_dir=None, shared_only=False):  # noqa: ANN001, ANN003
            self.calls.append(("list_sessions", workspace_dir, shared_only))
            now = datetime.now(timezone.utc).isoformat()
            return [
                MainAgentSessionSummary(
                    session_id="sess-task-1",
                    title="Task Session",
                    workspace_dir=str(workspace_dir),
                    created_at=now,
                    updated_at=now,
                    message_count=0,
                    token_usage=0,
                    token_limit=0,
                    active_surface="desktop",
                    origin_surface="desktop",
                    shared=False,
                )
            ]

        async def create_session(self, request, *, workspace_dir):  # noqa: ANN001, ANN003
            self.calls.append(("create_session", request.title, workspace_dir))
            now = datetime.now(timezone.utc).isoformat()
            return MainAgentSessionDetail(
                session_id="sess-task-1",
                workspace_dir=str(workspace_dir),
                created_at=now,
                updated_at=now,
                title=request.title,
                message_count=0,
                token_usage=0,
                token_limit=0,
                origin_surface="desktop",
                active_surface="desktop",
                shared=False,
                recent_messages=[],
            )

        async def get_session_detail(self, session_id: str, *, recent_limit: int = 50):
            self.calls.append(("get_session_detail", session_id, recent_limit))
            now = datetime.now(timezone.utc).isoformat()
            return MainAgentSessionDetail(
                session_id=session_id,
                workspace_dir=str(Path(".").resolve()),
                created_at=now,
                updated_at=now,
                title="Task Session",
                message_count=0,
                token_usage=0,
                token_limit=0,
                origin_surface="desktop",
                active_surface="desktop",
                shared=False,
                recent_messages=[],
            )

        async def delete_session(self, session_id: str):
            self.calls.append(("delete_session", session_id))
            return MainAgentSessionMutationResponse(status="deleted", session_id=session_id)

    async def _run() -> None:
        session_task_service = _SessionTaskServiceStub()
        use_cases = MainAgentSurfaceService(
            session_task_service=session_task_service,
            resolve_workspace_dir=_resolve_workspace_dir,
            to_utc_iso=_to_utc_iso,
            sse_event=_sse_event,
            format_bootstrap_error=_format_bootstrap_error,
            stream_chunk_size=64,
        )

        listed = await use_cases.list_sessions(workspace_dir=".", shared_only=True)
        created = await use_cases.create_session(
            MainAgentSessionCreateRequest(workspace_dir=".", title="Session 1", surface="desktop", shared=False)
        )
        detail = await use_cases.get_session_detail("sess-task-1", recent_limit=3)
        deleted = await use_cases.delete_session("sess-task-1")

        assert [item.session_id for item in listed] == ["sess-task-1"]
        assert created.session_id == "sess-task-1"
        assert detail.session_id == "sess-task-1"
        assert deleted.status == "deleted"
        assert session_task_service.calls == [
            ("list_sessions", Path(".").resolve(), True),
            ("validate_workspace", Path(".").resolve()),
            ("create_session", "Session 1", Path(".").resolve()),
            ("get_session_detail", "sess-task-1", 3),
            ("delete_session", "sess-task-1"),
        ]

    asyncio.run(_run())


def test_surface_service_can_run_with_explicit_services_without_session_facade() -> None:
    class _SessionTaskServiceStub:
        def __init__(self) -> None:
            self.calls: list[tuple[str, object]] = []

        def validate_workspace(self, workspace_dir: Path) -> None:
            self.calls.append(("validate_workspace", workspace_dir))

        async def list_sessions(self, *, workspace_dir=None, shared_only=False):  # noqa: ANN001, ANN003
            self.calls.append(("list_sessions", workspace_dir, shared_only))
            now = datetime.now(timezone.utc).isoformat()
            return [
                MainAgentSessionSummary(
                    session_id="sess-explicit-1",
                    title="Explicit Session",
                    workspace_dir=str(workspace_dir),
                    created_at=now,
                    updated_at=now,
                    message_count=0,
                    token_usage=0,
                    token_limit=0,
                    active_surface="desktop",
                    origin_surface="desktop",
                    shared=False,
                )
            ]

    class _RunControlServiceStub:
        def __init__(self) -> None:
            self.calls: list[tuple[str, object]] = []

        async def cancel_session_run(self, session_id: str, **kwargs):
            self.calls.append(("cancel_session_run", session_id, kwargs))
            return MainAgentSessionMutationResponse(status="cancel_requested", session_id=session_id)

        async def approve_session_wait(self, session_id: str, **kwargs):
            self.calls.append(("approve_session_wait", session_id, kwargs))
            return MainAgentSessionApprovalResponse(
                status="resolved",
                session_id=session_id,
                token=str(kwargs.get("token") or ""),
                tool_name="shell",
                decision="approved",
            )

        async def deny_session_wait(self, session_id: str, **kwargs):
            self.calls.append(("deny_session_wait", session_id, kwargs))
            return MainAgentSessionApprovalResponse(
                status="resolved",
                session_id=session_id,
                token=str(kwargs.get("token") or ""),
                tool_name="shell",
                decision="denied",
            )

    class _AgentServiceStub:
        def __init__(self) -> None:
            self.calls: list[tuple[str, object]] = []

        async def control_session(self, session_id: str, **kwargs):
            self.calls.append(("control_session", session_id, kwargs))
            return MainAgentSessionControlResponse(
                status="controlled",
                session_id=session_id,
                action=str(kwargs.get("action") or ""),
                applied=True,
                active_surface="desktop",
            )

    class _ModelServiceStub:
        def __init__(self) -> None:
            self.calls: list[tuple[str, object]] = []

        async def update_session_model_selection(self, session_id: str, **kwargs):
            self.calls.append(("update_session_model_selection", session_id, kwargs))
            return MainAgentSessionModelSelectionResponse(
                status="selected",
                session_id=session_id,
                active_surface="desktop",
                applied=True,
                queued=False,
                selected_model_source=str(kwargs.get("provider_source") or ""),
                selected_provider_id=str(kwargs.get("provider_id") or ""),
                selected_model_id=str(kwargs.get("model_id") or ""),
            )

    async def _run() -> None:
        session_task_service = _SessionTaskServiceStub()
        run_control_service = _RunControlServiceStub()
        agent_service = _AgentServiceStub()
        model_service = _ModelServiceStub()
        use_cases = MainAgentSurfaceService(
            session_task_service=session_task_service,
            run_control_service=run_control_service,
            agent_service=agent_service,
            model_service=model_service,
            resolve_workspace_dir=_resolve_workspace_dir,
            to_utc_iso=_to_utc_iso,
            sse_event=_sse_event,
            format_bootstrap_error=_format_bootstrap_error,
            stream_chunk_size=64,
        )

        sessions = await use_cases.list_sessions(workspace_dir=".", shared_only=True)
        cancelled = await use_cases.cancel_session(
            "sess-explicit-1",
            MainAgentSessionCancelRequest(reason="stop", surface="desktop"),
        )
        controlled = await use_cases.control_session(
            "sess-explicit-1",
            MainAgentSessionControlRequest(action="compact", surface="desktop"),
        )
        selected = await use_cases.update_session_model_selection(
            "sess-explicit-1",
            MainAgentSessionModelSelectionRequest(
                provider_source="preset",
                provider_id="openai",
                model_id="gpt-5.4",
                surface="desktop",
            ),
        )
        approved = await use_cases.respond_to_approval(
            "sess-explicit-1",
            MainAgentSessionApprovalRequest(approved=True, token="approval-1", surface="desktop"),
        )

        assert [item.session_id for item in sessions] == ["sess-explicit-1"]
        assert cancelled.status == "cancel_requested"
        assert controlled.action == "compact"
        assert selected.selected_model_id == "gpt-5.4"
        assert approved.decision == "approved"
        assert session_task_service.calls == [
            ("list_sessions", Path(".").resolve(), True),
        ]
        assert run_control_service.calls == [
            (
                "cancel_session_run",
                "sess-explicit-1",
                {
                    "reason": "stop",
                    "source": "desktop",
                    "surface": "desktop",
                    "channel_type": None,
                    "conversation_id": None,
                    "sender_id": None,
                },
            ),
            (
                "approve_session_wait",
                "sess-explicit-1",
                {
                    "token": "approval-1",
                    "source": "desktop",
                    "surface": "desktop",
                    "channel_type": None,
                    "conversation_id": None,
                    "sender_id": None,
                },
            ),
        ]
        assert agent_service.calls == [
            (
                "control_session",
                "sess-explicit-1",
                {
                    "action": "compact",
                    "reason": None,
                    "surface": "desktop",
                    "channel_type": None,
                    "conversation_id": None,
                    "sender_id": None,
                },
            )
        ]
        assert model_service.calls == [
            (
                "update_session_model_selection",
                "sess-explicit-1",
                {
                    "provider_source": "preset",
                    "provider_id": "openai",
                    "model_id": "gpt-5.4",
                    "surface": "desktop",
                    "channel_type": None,
                    "conversation_id": None,
                    "sender_id": None,
                },
            )
        ]

    asyncio.run(_run())


def test_surface_service_prefers_injected_agent_service_for_run_control_entrypoints() -> None:
    class _RunControlServiceStub:
        def __init__(self) -> None:
            self.calls: list[tuple[str, object]] = []

        async def cancel_session_run(self, session_id: str, **kwargs):
            self.calls.append(("cancel_session_run", session_id, kwargs))
            return MainAgentSessionMutationResponse(
                status="cancel_requested",
                session_id=session_id,
                active_surface="qq",
            )

        async def approve_session_wait(self, session_id: str, **kwargs):
            self.calls.append(("approve_session_wait", session_id, kwargs))
            return MainAgentSessionApprovalResponse(
                status="resolved",
                session_id=session_id,
                token="approval-1",
                tool_name="shell",
                decision="approved",
                active_surface="qq",
            )

        async def deny_session_wait(self, session_id: str, **kwargs):
            self.calls.append(("deny_session_wait", session_id, kwargs))
            return MainAgentSessionApprovalResponse(
                status="resolved",
                session_id=session_id,
                token="approval-2",
                tool_name="shell",
                decision="denied",
                active_surface="desktop",
            )

    async def _run() -> None:
        run_control_service = _RunControlServiceStub()
        use_cases = MainAgentSurfaceService(
            session_task_service=SimpleNamespace(),
            run_control_service=run_control_service,
            resolve_workspace_dir=_resolve_workspace_dir,
            to_utc_iso=_to_utc_iso,
            sse_event=_sse_event,
            format_bootstrap_error=_format_bootstrap_error,
            stream_chunk_size=64,
        )

        cancel = await use_cases.cancel_session(
            "sess-agent-service",
            MainAgentSessionCancelRequest(
                reason="stop now",
                surface=" qq ",
                channel_type=" qqbot ",
                conversation_id=" group:demo ",
                sender_id=" user-1 ",
            ),
        )
        approved = await use_cases.respond_to_approval(
            "sess-agent-service",
            MainAgentSessionApprovalRequest(
                approved=True,
                token="approval-1",
                surface="tui",
            ),
        )
        denied = await use_cases.respond_to_approval(
            "sess-agent-service",
            MainAgentSessionApprovalRequest(
                approved=False,
                token="approval-2",
                surface="desktop",
            ),
        )

        assert cancel.status == "cancel_requested"
        assert approved.decision == "approved"
        assert denied.decision == "denied"
        assert run_control_service.calls == [
            (
                "cancel_session_run",
                "sess-agent-service",
                {
                    "reason": "stop now",
                    "source": "qq",
                    "surface": "qq",
                    "channel_type": "qq",
                    "conversation_id": "group:demo",
                    "sender_id": "user-1",
                },
            ),
            (
                "approve_session_wait",
                "sess-agent-service",
                {
                    "token": "approval-1",
                    "source": "tui",
                    "surface": "tui",
                    "channel_type": None,
                    "conversation_id": None,
                    "sender_id": None,
                },
            ),
            (
                "deny_session_wait",
                "sess-agent-service",
                {
                    "token": "approval-2",
                    "source": "desktop",
                    "surface": "desktop",
                    "channel_type": None,
                    "conversation_id": None,
                    "sender_id": None,
                },
            ),
        ]

    asyncio.run(_run())


def test_surface_service_builder_preserves_legacy_session_service_run_control_owner_when_available() -> None:
    class _RunControlServiceStub:
        def __init__(self) -> None:
            self.calls: list[tuple[str, object]] = []

        async def cancel_session_run(self, session_id: str, **kwargs):
            self.calls.append(("cancel_session_run", session_id, kwargs))
            return MainAgentSessionMutationResponse(status="cancel_requested", session_id=session_id)

        async def approve_session_wait(self, session_id: str, **kwargs):
            self.calls.append(("approve_session_wait", session_id, kwargs))
            return MainAgentSessionApprovalResponse(
                status="resolved",
                session_id=session_id,
                token=str(kwargs.get("token") or ""),
                tool_name="shell",
                decision="approved",
            )

        async def deny_session_wait(self, session_id: str, **kwargs):
            self.calls.append(("deny_session_wait", session_id, kwargs))
            return MainAgentSessionApprovalResponse(
                status="resolved",
                session_id=session_id,
                token=str(kwargs.get("token") or ""),
                tool_name="shell",
                decision="denied",
            )

    class _SessionServiceStub:
        def __init__(self) -> None:
            self.session_task_service = SimpleNamespace()
            self.agent_service = object()
            self.model_service = object()
            self.workspace_service = object()
            self.run_control_service = _RunControlServiceStub()

        async def cancel_session(self, session_id: str, request):  # noqa: ANN001
            raise AssertionError(f"legacy session_service.cancel_session should not be called for {session_id}: {request}")

        async def respond_to_approval(self, session_id: str, request):  # noqa: ANN001
            raise AssertionError(
                f"legacy session_service.respond_to_approval should not be called for {session_id}: {request}"
            )

    async def _run() -> None:
        session_service = _SessionServiceStub()
        use_cases = build_main_agent_surface_service(
            session_service=session_service,
            resolve_workspace_dir=_resolve_workspace_dir,
            to_utc_iso=_to_utc_iso,
            sse_event=_sse_event,
            format_bootstrap_error=_format_bootstrap_error,
            stream_chunk_size=64,
        )

        cancel = await use_cases.cancel_session(
            "sess-run-owner",
            MainAgentSessionCancelRequest(reason="stop", surface="desktop"),
        )
        approved = await use_cases.respond_to_approval(
            "sess-run-owner",
            MainAgentSessionApprovalRequest(approved=True, token="approval-1", surface="desktop"),
        )
        denied = await use_cases.respond_to_approval(
            "sess-run-owner",
            MainAgentSessionApprovalRequest(approved=False, token="approval-2", surface="desktop"),
        )

        assert cancel.status == "cancel_requested"
        assert approved.decision == "approved"
        assert denied.decision == "denied"
        assert session_service.run_control_service.calls == [
            (
                "cancel_session_run",
                "sess-run-owner",
                {
                    "reason": "stop",
                    "source": "desktop",
                    "surface": "desktop",
                    "channel_type": None,
                    "conversation_id": None,
                    "sender_id": None,
                },
            ),
            (
                "approve_session_wait",
                "sess-run-owner",
                {
                    "token": "approval-1",
                    "source": "desktop",
                    "surface": "desktop",
                    "channel_type": None,
                    "conversation_id": None,
                    "sender_id": None,
                },
            ),
            (
                "deny_session_wait",
                "sess-run-owner",
                {
                    "token": "approval-2",
                    "source": "desktop",
                    "surface": "desktop",
                    "channel_type": None,
                    "conversation_id": None,
                    "sender_id": None,
                },
            ),
        ]

    asyncio.run(_run())


def test_surface_service_prefers_injected_agent_service_for_control_entrypoint() -> None:
    class _AgentServiceStub:
        def __init__(self) -> None:
            self.calls: list[tuple[str, object]] = []

        async def control_session(self, session_id: str, **kwargs):
            self.calls.append(("control_session", session_id, kwargs))
            return MainAgentSessionControlResponse(
                status="controlled",
                session_id=session_id,
                action=str(kwargs.get("action") or ""),
                applied=True,
                active_surface="qq",
            )

    async def _run() -> None:
        agent_service = _AgentServiceStub()
        use_cases = MainAgentSurfaceService(
            session_task_service=SimpleNamespace(),
            agent_service=agent_service,
            resolve_workspace_dir=_resolve_workspace_dir,
            to_utc_iso=_to_utc_iso,
            sse_event=_sse_event,
            format_bootstrap_error=_format_bootstrap_error,
            stream_chunk_size=64,
        )

        response = await use_cases.control_session(
            "sess-control-service",
            MainAgentSessionControlRequest(
                action=" compact ",
                reason=" trim history ",
                surface=" qq ",
                channel_type=" qqbot ",
                conversation_id=" group:demo ",
                sender_id=" user-1 ",
            ),
        )

        assert response.status == "controlled"
        assert response.action == " compact "
        assert agent_service.calls == [
            (
                "control_session",
                "sess-control-service",
                {
                    "action": " compact ",
                    "reason": " trim history ",
                    "surface": "qq",
                    "channel_type": "qq",
                    "conversation_id": "group:demo",
                    "sender_id": "user-1",
                },
            )
        ]

    asyncio.run(_run())


def test_surface_service_prefers_injected_agent_service_for_context_entrypoint() -> None:
    class _AgentServiceStub:
        def __init__(self) -> None:
            self.calls: list[tuple[str, object]] = []

        async def update_session_context(self, session_id: str, **kwargs):
            self.calls.append(("update_session_context", session_id, kwargs))
            return MainAgentSessionContextResponse(
                status="updated",
                session_id=session_id,
                action=str(kwargs.get("action") or ""),
                active_surface="qq",
                context_policy={"include_sources": kwargs.get("sources") or []},
            )

    async def _run() -> None:
        agent_service = _AgentServiceStub()
        use_cases = MainAgentSurfaceService(
            session_task_service=SimpleNamespace(),
            agent_service=agent_service,
            resolve_workspace_dir=_resolve_workspace_dir,
            to_utc_iso=_to_utc_iso,
            sse_event=_sse_event,
            format_bootstrap_error=_format_bootstrap_error,
            stream_chunk_size=64,
        )

        response = await use_cases.update_session_context(
            "sess-context-service",
            MainAgentSessionContextRequest(
                action=" include ",
                sources=["knowledge_base", "workspace_memory"],
                max_items=4,
                max_total_chars=2400,
                max_items_per_source=1,
                surface=" qq ",
                channel_type=" qqbot ",
                conversation_id=" group:demo ",
                sender_id=" user-1 ",
            ),
        )

        assert response.status == "updated"
        assert response.context_policy["include_sources"] == ["knowledge_base", "workspace_memory"]
        assert agent_service.calls == [
            (
                "update_session_context",
                "sess-context-service",
                {
                    "action": " include ",
                    "sources": ["knowledge_base", "workspace_memory"],
                    "max_items": 4,
                    "max_total_chars": 2400,
                    "max_items_per_source": 1,
                    "surface": "qq",
                    "channel_type": "qq",
                    "conversation_id": "group:demo",
                    "sender_id": "user-1",
                },
            )
        ]

    asyncio.run(_run())


def test_surface_service_prefers_injected_model_service_for_model_selection_entrypoint() -> None:
    class _ModelServiceStub:
        def __init__(self) -> None:
            self.calls: list[tuple[str, object]] = []

        async def update_session_model_selection(self, session_id: str, **kwargs):
            self.calls.append(("update_session_model_selection", session_id, kwargs))
            return MainAgentSessionModelSelectionResponse(
                status="selected",
                session_id=session_id,
                active_surface="qq",
                applied=True,
                queued=False,
                selected_model_source="preset",
                selected_provider_id="openai",
                selected_model_id="gpt-5.3",
            )

    async def _run() -> None:
        model_service = _ModelServiceStub()
        use_cases = MainAgentSurfaceService(
            session_task_service=SimpleNamespace(),
            model_service=model_service,
            resolve_workspace_dir=_resolve_workspace_dir,
            to_utc_iso=_to_utc_iso,
            sse_event=_sse_event,
            format_bootstrap_error=_format_bootstrap_error,
            stream_chunk_size=64,
        )

        response = await use_cases.update_session_model_selection(
            "sess-model-service",
            MainAgentSessionModelSelectionRequest(
                provider_source=" preset ",
                provider_id=" openai ",
                model_id=" gpt-5.3 ",
                surface=" qq ",
                channel_type=" qqbot ",
                conversation_id=" group:demo ",
                sender_id=" user-1 ",
            ),
        )

        assert response.status == "selected"
        assert response.selected_model_id == "gpt-5.3"
        assert model_service.calls == [
            (
                "update_session_model_selection",
                "sess-model-service",
                {
                    "provider_source": " preset ",
                    "provider_id": " openai ",
                    "model_id": " gpt-5.3 ",
                    "surface": "qq",
                    "channel_type": "qq",
                    "conversation_id": "group:demo",
                    "sender_id": "user-1",
                },
            )
        ]

    asyncio.run(_run())


def test_surface_service_prefers_injected_model_service_for_agent_model_entrypoints() -> None:
    class _ModelServiceStub:
        async def list_model_candidates(self):
            return {
                "items": [
                    {
                        "source": "custom",
                        "provider_id": "maas",
                        "provider_name": "MaaS",
                        "api_type": "openai",
                        "api_base": "https://maas.example.com/v1",
                        "models": [
                            {
                                "model_id": "astron-code-latest",
                                "display_name": "astron-code-latest",
                                "is_default": True,
                                "is_current_binding": True,
                            }
                        ],
                    }
                ]
            }

        async def get_current_model_binding(self, agent_id: str | None = None):
            assert agent_id == "main-agent"
            return {
                "agent_id": "main-agent",
                "binding_kind": "explicit",
                "provider_source": "custom",
                "provider_id": "maas",
                "model_id": "astron-code-latest",
                "switch_generation": 2,
            }

        async def set_agent_model_binding(self, **kwargs):
            assert kwargs == {
                "agent_id": "main-agent",
                "provider_source": "custom",
                "provider_id": "maas",
                "model_id": "astron-code-stable",
            }
            return {
                "agent_id": "main-agent",
                "binding_kind": "explicit",
                "provider_source": "custom",
                "provider_id": "maas",
                "model_id": "astron-code-stable",
                "switch_generation": 3,
            }

        async def get_current_model_capabilities(self, agent_id: str | None = None):
            assert agent_id == "main-agent"
            return {
                "agent_id": "main-agent",
                "binding_kind": "explicit",
                "provider_source": "custom",
                "provider_id": "maas",
                "model_id": "astron-code-latest",
                "supports_tools": True,
                "supports_thinking": True,
            }

        async def get_model_binding_diagnostics(self, agent_id: str | None = None):
            assert agent_id == "main-agent"
            return {
                "agent_id": "main-agent",
                "current_binding": {
                    "agent_id": "main-agent",
                    "binding_kind": "explicit",
                    "provider_source": "custom",
                    "provider_id": "maas",
                    "model_id": "astron-code-latest",
                },
                "configured_binding": {
                    "agent_id": "main-agent",
                    "provider_source": "custom",
                    "provider_id": "maas",
                    "model_id": "astron-code-latest",
                    "binding_kind": "explicit",
                    "bound_at": "2026-04-18T12:00:00+00:00",
                    "switch_generation": 2,
                },
                "latest_route": {
                    "selected_provider_id": "maas",
                    "selected_model": "astron-code-latest",
                    "candidate_count": 1,
                    "candidates": [],
                },
            }

    async def _run() -> None:
        use_cases = MainAgentSurfaceService(
            session_task_service=SimpleNamespace(),
            model_service=_ModelServiceStub(),
            resolve_workspace_dir=_resolve_workspace_dir,
            to_utc_iso=_to_utc_iso,
            sse_event=_sse_event,
            format_bootstrap_error=_format_bootstrap_error,
            stream_chunk_size=64,
        )

        candidates = await use_cases.list_model_candidates()
        binding = await use_cases.get_current_model_binding("main-agent")
        updated = await use_cases.set_agent_model_binding(
            MainAgentModelBindingRequest(
                agent_id="main-agent",
                provider_source="custom",
                provider_id="maas",
                model_id="astron-code-stable",
            )
        )
        capabilities = await use_cases.get_current_model_capabilities("main-agent")
        diagnostics = await use_cases.get_model_binding_diagnostics("main-agent")

        assert isinstance(candidates, MainAgentModelCandidateListResponse)
        assert candidates.items[0].models[0].is_current_binding is True
        assert isinstance(binding, MainAgentModelBindingSummary)
        assert binding.model_id == "astron-code-latest"
        assert isinstance(updated, MainAgentModelBindingSummary)
        assert updated.switch_generation == 3
        assert isinstance(capabilities, MainAgentModelCapabilities)
        assert capabilities.supports_tools is True
        assert isinstance(diagnostics, MainAgentModelBindingDiagnostics)
        assert diagnostics.latest_route is not None
        assert diagnostics.latest_route.selected_model == "astron-code-latest"

    asyncio.run(_run())


def test_surface_service_prefers_injected_agent_service_for_runtime_policy_entrypoint() -> None:
    class _AgentServiceStub:
        def __init__(self) -> None:
            self.calls: list[tuple[str, object]] = []

        async def update_session_runtime_policy(self, session_id: str, **kwargs):
            self.calls.append(("update_session_runtime_policy", session_id, kwargs))
            return MainAgentSessionRuntimePolicyResponse(
                status="updated",
                session_id=session_id,
                active_surface="qq",
                applied=True,
                approval_profile="plan",
                access_level="full-access",
                summary="runtime plan / full-access",
                details="Runtime policy updated.",
                status_text="Runtime set to plan / full-access.",
                sandbox_diagnostics={"sandbox_mode": "unrestricted"},
            )

    async def _run() -> None:
        agent_service = _AgentServiceStub()
        use_cases = MainAgentSurfaceService(
            session_task_service=SimpleNamespace(),
            agent_service=agent_service,
            resolve_workspace_dir=_resolve_workspace_dir,
            to_utc_iso=_to_utc_iso,
            sse_event=_sse_event,
            format_bootstrap_error=_format_bootstrap_error,
            stream_chunk_size=64,
        )

        response = await use_cases.update_session_runtime_policy(
            "sess-policy-service",
            MainAgentSessionRuntimePolicyRequest(
                approval_profile="plan",
                access_level="full-access",
                surface=" qq ",
                channel_type=" qqbot ",
                conversation_id=" group:demo ",
                sender_id=" user-1 ",
            ),
        )

        assert response.status == "updated"
        assert response.status_text == "Runtime set to plan / full-access."
        assert agent_service.calls == [
            (
                "update_session_runtime_policy",
                "sess-policy-service",
                {
                    "approval_profile": "plan",
                    "access_level": "full-access",
                    "surface": "qq",
                    "channel_type": "qq",
                    "conversation_id": "group:demo",
                    "sender_id": "user-1",
                },
            )
        ]

    asyncio.run(_run())


def test_surface_service_prefers_injected_agent_service_for_memory_entrypoint() -> None:
    class _AgentServiceStub:
        def __init__(self) -> None:
            self.calls: list[tuple[str, object]] = []

        async def manage_session_memory(self, session_id: str, **kwargs):
            self.calls.append(("manage_session_memory", session_id, kwargs))
            return MainAgentSessionMemoryResponse(
                status="ok",
                session_id=session_id,
                action=str(kwargs.get("action") or ""),
                active_surface="qq",
                memory_diagnostics={"runtime_task_memory": {"session_count": 1}},
                result={"summary": "memory ok"},
            )

    async def _run() -> None:
        agent_service = _AgentServiceStub()
        use_cases = MainAgentSurfaceService(
            session_task_service=SimpleNamespace(),
            agent_service=agent_service,
            resolve_workspace_dir=_resolve_workspace_dir,
            to_utc_iso=_to_utc_iso,
            sse_event=_sse_event,
            format_bootstrap_error=_format_bootstrap_error,
            stream_chunk_size=64,
        )

        response = await use_cases.manage_session_memory(
            "sess-memory-service",
            MainAgentSessionMemoryRequest(
                action=" show ",
                engram_id=" mem-1 ",
                query=" recent note ",
                detail_mode=" brief ",
                surface=" qq ",
                channel_type=" qqbot ",
                conversation_id=" group:demo ",
                sender_id=" user-1 ",
            ),
        )

        assert response.status == "ok"
        assert response.result["summary"] == "memory ok"
        assert agent_service.calls == [
            (
                "manage_session_memory",
                "sess-memory-service",
                {
                    "action": " show ",
                    "engram_id": " mem-1 ",
                    "content": None,
                    "query": " recent note ",
                    "day": None,
                    "export_format": None,
                    "detail_mode": " brief ",
                    "surface": "qq",
                    "channel_type": "qq",
                    "conversation_id": "group:demo",
                    "sender_id": "user-1",
                },
            )
        ]

    asyncio.run(_run())


def test_surface_service_prefers_injected_agent_service_for_skill_entrypoint() -> None:
    class _AgentServiceStub:
        def __init__(self) -> None:
            self.calls: list[tuple[str, object]] = []

        async def manage_session_skills(self, session_id: str, **kwargs):
            self.calls.append(("manage_session_skills", session_id, kwargs))
            return MainAgentSessionSkillResponse(
                status="ok",
                session_id=session_id,
                action=str(kwargs.get("action") or ""),
                active_surface="qq",
                result={"summary": "skills ok"},
            )

    async def _run() -> None:
        agent_service = _AgentServiceStub()
        use_cases = MainAgentSurfaceService(
            session_task_service=SimpleNamespace(),
            agent_service=agent_service,
            resolve_workspace_dir=_resolve_workspace_dir,
            to_utc_iso=_to_utc_iso,
            sse_event=_sse_event,
            format_bootstrap_error=_format_bootstrap_error,
            stream_chunk_size=64,
        )

        response = await use_cases.manage_session_skills(
            "sess-skill-service",
            MainAgentSessionSkillRequest(
                action=" search ",
                skill_name=" helper ",
                path=" C:/skills/helper ",
                query=" foundry ",
                mode=" allowlist ",
                surface=" qq ",
                channel_type=" qqbot ",
                conversation_id=" group:demo ",
                sender_id=" user-1 ",
            ),
        )

        assert response.status == "ok"
        assert response.result["summary"] == "skills ok"
        assert agent_service.calls == [
            (
                "manage_session_skills",
                "sess-skill-service",
                {
                    "action": " search ",
                    "skill_name": " helper ",
                    "path": " C:/skills/helper ",
                    "query": " foundry ",
                    "mode": " allowlist ",
                    "surface": "qq",
                    "channel_type": "qq",
                    "conversation_id": "group:demo",
                    "sender_id": "user-1",
                },
            )
        ]

    asyncio.run(_run())


def test_surface_service_prefers_session_task_service_for_session_compatibility_entrypoints() -> None:
    class _SessionTaskServiceStub:
        def __init__(self) -> None:
            self.calls: list[tuple[str, object]] = []

        async def control_session(self, session_id: str, **kwargs):
            self.calls.append(("control_session", session_id, kwargs))
            return MainAgentSessionControlResponse(
                status="controlled",
                session_id=session_id,
                action=str(kwargs.get("action") or ""),
                applied=True,
                active_surface=str(kwargs.get("surface") or "desktop"),
            )

        async def update_session_context(self, session_id: str, **kwargs):
            self.calls.append(("update_session_context", session_id, kwargs))
            return MainAgentSessionContextResponse(
                status="updated",
                session_id=session_id,
                action=str(kwargs.get("action") or ""),
                active_surface=str(kwargs.get("surface") or "desktop"),
                context_policy={"include_sources": list(kwargs.get("sources") or [])},
            )

        async def manage_session_memory(self, session_id: str, **kwargs):
            self.calls.append(("manage_session_memory", session_id, kwargs))
            return MainAgentSessionMemoryResponse(
                status="ok",
                session_id=session_id,
                action=str(kwargs.get("action") or ""),
                active_surface=str(kwargs.get("surface") or "desktop"),
                memory_diagnostics={},
                result={"summary": "memory ok"},
            )

        async def manage_session_skills(self, session_id: str, **kwargs):
            self.calls.append(("manage_session_skills", session_id, kwargs))
            return MainAgentSessionSkillResponse(
                status="ok",
                session_id=session_id,
                action=str(kwargs.get("action") or ""),
                active_surface=str(kwargs.get("surface") or "desktop"),
                result={"summary": "skills ok"},
            )

        async def update_session_model_selection(self, session_id: str, **kwargs):
            self.calls.append(("update_session_model_selection", session_id, kwargs))
            return MainAgentSessionModelSelectionResponse(
                status="selected",
                session_id=session_id,
                active_surface=str(kwargs.get("surface") or "desktop"),
                applied=True,
                queued=False,
                selected_model_source=str(kwargs.get("provider_source") or ""),
                selected_provider_id=str(kwargs.get("provider_id") or ""),
                selected_model_id=str(kwargs.get("model_id") or ""),
            )

        async def update_session_runtime_policy(self, session_id: str, **kwargs):
            self.calls.append(("update_session_runtime_policy", session_id, kwargs))
            return MainAgentSessionRuntimePolicyResponse(
                status="updated",
                session_id=session_id,
                active_surface=str(kwargs.get("surface") or "desktop"),
                applied=True,
                approval_profile=str(kwargs.get("approval_profile") or ""),
                access_level=str(kwargs.get("access_level") or ""),
                summary="policy updated",
                details="policy updated",
                status_text="policy updated",
                sandbox_diagnostics={"sandbox_mode": "workspace"},
            )

    class _AgentServiceStub:
        async def control_session(self, session_id: str, **kwargs):
            raise AssertionError(f"agent_service.control_session should not be called: {session_id}, {kwargs}")

        async def update_session_context(self, session_id: str, **kwargs):
            raise AssertionError(f"agent_service.update_session_context should not be called: {session_id}, {kwargs}")

        async def manage_session_memory(self, session_id: str, **kwargs):
            raise AssertionError(f"agent_service.manage_session_memory should not be called: {session_id}, {kwargs}")

        async def manage_session_skills(self, session_id: str, **kwargs):
            raise AssertionError(f"agent_service.manage_session_skills should not be called: {session_id}, {kwargs}")

        async def update_session_runtime_policy(self, session_id: str, **kwargs):
            raise AssertionError(
                f"agent_service.update_session_runtime_policy should not be called: {session_id}, {kwargs}"
            )

    class _ModelServiceStub:
        async def update_session_model_selection(self, session_id: str, **kwargs):
            raise AssertionError(
                f"model_service.update_session_model_selection should not be called: {session_id}, {kwargs}"
            )

    async def _run() -> None:
        session_task_service = _SessionTaskServiceStub()
        use_cases = MainAgentSurfaceService(
            session_task_service=session_task_service,
            agent_service=_AgentServiceStub(),
            model_service=_ModelServiceStub(),
            resolve_workspace_dir=_resolve_workspace_dir,
            to_utc_iso=_to_utc_iso,
            sse_event=_sse_event,
            format_bootstrap_error=_format_bootstrap_error,
            stream_chunk_size=64,
        )

        controlled = await use_cases.control_session(
            "sess-pref",
            MainAgentSessionControlRequest(action="compact", reason="trim", surface="desktop"),
        )
        context = await use_cases.update_session_context(
            "sess-pref",
            MainAgentSessionContextRequest(action="include", sources=["workspace_memory"], surface="desktop"),
        )
        memory = await use_cases.manage_session_memory(
            "sess-pref",
            MainAgentSessionMemoryRequest(action="show", query="recent", detail_mode="brief", surface="desktop"),
        )
        skills = await use_cases.manage_session_skills(
            "sess-pref",
            MainAgentSessionSkillRequest(action="search", query="foundry", mode="allowlist", surface="desktop"),
        )
        model = await use_cases.update_session_model_selection(
            "sess-pref",
            MainAgentSessionModelSelectionRequest(
                provider_source="preset",
                provider_id="openai",
                model_id="gpt-5.4",
                surface="desktop",
            ),
        )
        policy = await use_cases.update_session_runtime_policy(
            "sess-pref",
            MainAgentSessionRuntimePolicyRequest(
                approval_profile="plan",
                access_level="default",
                surface="desktop",
            ),
        )

        assert controlled.action == "compact"
        assert context.context_policy["include_sources"] == ["workspace_memory"]
        assert memory.result["summary"] == "memory ok"
        assert skills.result["summary"] == "skills ok"
        assert model.selected_model_id == "gpt-5.4"
        assert policy.approval_profile == "plan"
        assert [name for name, *_ in session_task_service.calls] == [
            "control_session",
            "update_session_context",
            "manage_session_memory",
            "manage_session_skills",
            "update_session_model_selection",
            "update_session_runtime_policy",
        ]

    asyncio.run(_run())


def test_use_case_shared_session_survives_runtime_restart(tmp_path: Path) -> None:
    async def _run() -> None:
        async def _build_agent(_workspace: Path):
            return _DummyAgent()

        storage_dir = tmp_path / "persisted-runtime-store"
        runtime_first = _runtime_manager(
            ttl_seconds=3600,
            build_agent=_build_agent,
            storage_dir=storage_dir,
        )
        use_cases_first = _runtime_surface_service(runtime_manager=runtime_first)

        first = await use_cases_first.run_chat(
            MainAgentChatRequest(
                message="hello from qq",
                workspace_dir=".",
                session_id="sess-persist",
                surface="qq",
                channel_type="qq",
                conversation_id="group:persist",
                sender_id="user-1",
            )
        )
        assert first.session_id == "sess-persist"

        runtime_second = _runtime_manager(
            ttl_seconds=3600,
            build_agent=_build_agent,
            storage_dir=storage_dir,
        )
        use_cases_second = _runtime_surface_service(runtime_manager=runtime_second)

        sessions = await use_cases_second.list_sessions()
        assert [item.session_id for item in sessions] == ["sess-persist"]
        assert sessions[0].origin_surface == "qq"
        assert sessions[0].busy is False

        detail = await use_cases_second.get_session_detail("sess-persist", recent_limit=10)
        assert [item.content for item in detail.recent_messages] == [
            "hello from qq",
            "mock:hello from qq",
        ]

        activated = await _activate_runtime_surface(runtime_second, "sess-persist", surface="tui")
        assert activated.active_surface == "tui"

        second = await use_cases_second.run_chat(
            MainAgentChatRequest(
                message="continue after restart",
                workspace_dir=".",
                session_id="sess-persist",
                surface="tui",
            )
        )
        assert second.session_id == "sess-persist"
        assert second.reply == "mock:continue after restart"

        detail_after = await use_cases_second.get_session_detail("sess-persist", recent_limit=10)
        assert [item.content for item in detail_after.recent_messages[-2:]] == [
            "continue after restart",
            "mock:continue after restart",
        ]
        assert detail_after.active_surface == "tui"

    asyncio.run(_run())


def test_use_case_stream_dry_run_emits_done() -> None:
    async def _run() -> None:
        async def _build_agent(_workspace: Path):
            return _DummyAgent()

        runtime = _runtime_manager(ttl_seconds=3600, build_agent=_build_agent)
        use_cases = _runtime_surface_service(runtime_manager=runtime, stream_chunk_size=16)

        events: list[str] = []
        async for event in use_cases.stream_chat_events(message="ping", dry_run=True):
            events.append(event)
        joined = "\n".join(events)
        assert "session" in joined
        assert "done" in joined

    asyncio.run(_run())


def test_runtime_manager_single_runtime_rejects_second_workspace() -> None:
    async def _run() -> None:
        async def _build_agent(_workspace: Path):
            return _DummyAgent()

        runtime = _runtime_manager(
            ttl_seconds=3600,
            build_agent=_build_agent,
            policy=MainAgentRuntimePolicy(mode=MainAgentRuntimeMode.SINGLE_MAIN),
        )
        first_workspace = Path(".").resolve()
        second_workspace = (first_workspace / "workspace-b").resolve()

        session = await runtime.get_or_create_session("sess-1", first_workspace)
        assert session.session_id == "sess-1"

        with pytest.raises(Exception) as exc_info:
            await runtime.get_or_create_session("sess-2", second_workspace)
        exc = exc_info.value
        assert getattr(exc, "status_code", None) == 409

    asyncio.run(_run())


def test_runtime_manager_single_runtime_falls_back_to_global_default_session() -> None:
    async def _run() -> None:
        async def _build_agent(_workspace: Path):
            return _DummyAgent()

        runtime = _runtime_manager(
            ttl_seconds=3600,
            build_agent=_build_agent,
            policy=MainAgentRuntimePolicy(mode=MainAgentRuntimeMode.SINGLE_MAIN),
        )
        workspace = Path(".").resolve()
        first = await runtime.get_or_create_session("sess-1", workspace)
        second = await runtime.get_or_create_session(None, workspace)
        assert first.session_id == "sess-1"
        assert second.session_id == "default"
        assert second.projection.is_default is True

    asyncio.run(_run())


def test_runtime_manager_assigns_human_readable_session_title_hints() -> None:
    async def _run() -> None:
        async def _build_agent(_workspace: Path):
            return _DummyAgent()

        workspace = Path(".").resolve()
        runtime = _runtime_manager(
            ttl_seconds=3600,
            build_agent=_build_agent,
            policy=MainAgentRuntimePolicy(
                mode=MainAgentRuntimeMode.TEAM,
                main_workspace_dir=workspace,
                max_active_sessions=4,
                reserved_team_slots=4,
            ),
        )

        first = await runtime.get_or_create_session(
            "sess-nyonyo-1",
            workspace,
            surface="qq",
            channel_type="qq",
            conversation_id="group:demo",
            sender_id="user-1",
            session_title_hint="nyonyo",
        )
        second = await runtime.get_or_create_session(
            "sess-nyonyo-2",
            workspace,
            surface="qq",
            channel_type="qq",
            conversation_id="group:demo",
            sender_id="user-1",
            session_title_hint="nyonyo",
        )

        assert first.projection.title == "nyonyo"
        assert second.projection.title == "nyonyo 1"

    asyncio.run(_run())


def test_runtime_manager_list_sessions_dedupes_exact_remote_channel_duplicates() -> None:
    async def _run() -> None:
        async def _build_agent(_workspace: Path):
            return _DummyAgent()

        workspace = Path(".").resolve()
        runtime = _runtime_manager(
            ttl_seconds=3600,
            build_agent=_build_agent,
            policy=MainAgentRuntimePolicy(
                mode=MainAgentRuntimeMode.TEAM,
                main_workspace_dir=workspace,
                max_active_sessions=4,
                reserved_team_slots=4,
            ),
        )

        await runtime.import_session_snapshot(
            RuntimeSessionSnapshotImportCommand(
                session_id="dup-qq-1",
                workspace_dir=workspace,
                title="nyonyo",
                origin_surface="qq",
                active_surface="qq",
                reply_enabled=True,
                channel_type="qq",
                conversation_id="group:demo",
                sender_id="user-1",
                transcript=[],
            )
        )
        await runtime.import_session_snapshot(
            RuntimeSessionSnapshotImportCommand(
                session_id="dup-qq-2",
                workspace_dir=workspace,
                title="nyonyo",
                origin_surface="qq",
                active_surface="qq",
                reply_enabled=True,
                channel_type="qq",
                conversation_id="group:demo",
                sender_id="user-1",
                transcript=[],
            )
        )

        sessions = await runtime.list_sessions()
        assert len(sessions) == 1
        assert sessions[0].session_id in {"dup-qq-1", "dup-qq-2"}
        assert sessions[0].title == "nyonyo"

    asyncio.run(_run())


def test_runtime_manager_single_main_workspace_only_rejects_other_workspace() -> None:
    async def _run() -> None:
        async def _build_agent(_workspace: Path):
            return _DummyAgent()

        main_workspace = Path(".").resolve()
        other_workspace = (main_workspace / "workspace-other").resolve()
        runtime = _runtime_manager(
            ttl_seconds=3600,
            build_agent=_build_agent,
            policy=MainAgentRuntimePolicy(
                mode=MainAgentRuntimeMode.SINGLE_MAIN,
                main_workspace_dir=main_workspace,
                max_active_sessions=1,
            ),
        )

        with pytest.raises(Exception) as exc_info:
            await runtime.get_or_create_session("sess-main", other_workspace)
        exc = exc_info.value
        assert getattr(exc, "status_code", None) == 409
        assert "main workspace" in str(getattr(exc, "detail", "")).lower()

    asyncio.run(_run())


def test_use_case_dry_run_also_enforces_single_main_workspace() -> None:
    async def _run() -> None:
        async def _build_agent(_workspace: Path):
            return _DummyAgent()

        main_workspace = Path(".").resolve()
        runtime = _runtime_manager(
            ttl_seconds=3600,
            build_agent=_build_agent,
            policy=MainAgentRuntimePolicy(
                mode=MainAgentRuntimeMode.SINGLE_MAIN,
                main_workspace_dir=main_workspace,
                max_active_sessions=1,
            ),
        )
        use_cases = _runtime_surface_service(runtime_manager=runtime, stream_chunk_size=32)

        with pytest.raises(Exception) as exc_info:
            await use_cases.run_chat(
                MainAgentChatRequest(
                    message="dry-run-check",
                    dry_run=True,
                    workspace_dir=str((main_workspace / "other-workspace").resolve()),
                )
            )
        exc = exc_info.value
        assert getattr(exc, "status_code", None) == 409

    asyncio.run(_run())


def test_use_case_chat_without_session_id_falls_back_to_default_session(tmp_path: Path) -> None:
    async def _run() -> None:
        async def _build_agent(_workspace: Path):
            return _DummyAgent()

        workspace = Path(".").resolve()
        storage_dir = tmp_path / "latest-shared-session-store"
        seed_runtime = _runtime_manager(
            ttl_seconds=3600,
            build_agent=_build_agent,
            storage_dir=storage_dir,
            policy=MainAgentRuntimePolicy(
                mode=MainAgentRuntimeMode.TEAM,
                main_workspace_dir=workspace,
                max_active_sessions=4,
                reserved_team_slots=4,
            ),
        )
        await seed_runtime.import_session_snapshot(
            RuntimeSessionSnapshotImportCommand(
                session_id="sess-old",
                workspace_dir=workspace,
                title="nyonyo",
                origin_surface="qq",
                active_surface="qq",
                reply_enabled=True,
                channel_type="qq",
                conversation_id="group:demo",
                sender_id="user-1",
                transcript=[
                    {
                        "role": "user",
                        "content": "older task",
                        "surface": "qq",
                    }
                ],
            )
        )
        await seed_runtime.import_session_snapshot(
            RuntimeSessionSnapshotImportCommand(
                session_id="sess-new",
                workspace_dir=workspace,
                title="Session 2",
                origin_surface="tui",
                active_surface="tui",
                reply_enabled=False,
                transcript=[
                    {
                        "role": "user",
                        "content": "newer task",
                        "surface": "tui",
                    }
                ],
            )
        )

        runtime = _runtime_manager(
            ttl_seconds=3600,
            build_agent=_build_agent,
            storage_dir=storage_dir,
            policy=MainAgentRuntimePolicy(mode=MainAgentRuntimeMode.SINGLE_MAIN),
        )
        use_cases = _runtime_surface_service(runtime_manager=runtime)

        chat = await use_cases.run_chat(
            MainAgentChatRequest(
                message="continue from qq",
                workspace_dir=".",
                surface="qq",
                channel_type="qq",
                conversation_id="group:demo",
                sender_id="user-1",
            )
        )

        assert chat.session_id == "default"
        detail = await use_cases.get_session_detail("default", recent_limit=10)
        assert detail.title == "Session 1"
        assert detail.active_surface == "qq"
        assert detail.reply_enabled is True
        assert detail.is_default is True

    asyncio.run(_run())


def test_use_case_chat_default_session_ignores_title_hint(tmp_path: Path) -> None:
    async def _run() -> None:
        async def _build_agent(_workspace: Path):
            return _DummyAgent()

        runtime = _runtime_manager(
            ttl_seconds=3600,
            build_agent=_build_agent,
            storage_dir=tmp_path / "title-hint-store",
        )
        use_cases = _runtime_surface_service(runtime_manager=runtime)

        chat = await use_cases.run_chat(
            MainAgentChatRequest(
                message="hello from qq",
                workspace_dir=".",
                surface="qq",
                channel_type="qq",
                conversation_id="group:demo",
                sender_id="user-1",
                session_title_hint="nyonyo",
            )
        )

        detail = await use_cases.get_session_detail(chat.session_id, recent_limit=10)
        assert detail.title == "Session 1"
        assert detail.channel_type == "qq"
        assert detail.conversation_id == "group:demo"
        assert detail.is_default is True

    asyncio.run(_run())


def test_runtime_manager_list_sessions_hides_untitled_channel_stub_when_shared_tui_session_exists() -> None:
    workspace_dir = str(Path(".").resolve())
    stub = MainAgentSessionSummary(
        session_id="qq-stub",
        workspace_dir=workspace_dir,
        created_at="2026-04-11T10:00:00+00:00",
        updated_at="2026-04-11T10:00:01+00:00",
        title=None,
        message_count=2,
        origin_surface="qq",
        active_surface="qq",
        reply_enabled=True,
        busy=False,
        running_state=None,
        channel_type="qq",
        conversation_id="group:demo",
        sender_id="user-1",
        token_usage=0,
        token_limit=0,
        knowledge_base_enabled=True,
    )
    shared = MainAgentSessionSummary(
        session_id="shared-session-10",
        workspace_dir=workspace_dir,
        created_at="2026-04-11T10:05:00+00:00",
        updated_at="2026-04-11T10:05:01+00:00",
        title="Session 10",
        message_count=8,
        origin_surface="tui",
        active_surface="qq",
        reply_enabled=True,
        busy=False,
        running_state=None,
        channel_type="qq",
        conversation_id="group:demo",
        sender_id="user-1",
        token_usage=0,
        token_limit=0,
        knowledge_base_enabled=True,
    )

    deduped = RuntimeSessionCatalogHandler.dedupe_session_summaries([shared, stub])

    assert [item.session_id for item in deduped] == ["shared-session-10"]


def test_runtime_manager_team_mode_allows_multi_workspace_sessions() -> None:
    async def _run() -> None:
        async def _build_agent(_workspace: Path):
            return _DummyAgent()

        root = Path(".").resolve()
        workspace_a = root
        workspace_b = (root / "workspace-b").resolve()

        runtime = _runtime_manager(
            ttl_seconds=3600,
            build_agent=_build_agent,
            policy=MainAgentRuntimePolicy(
                mode=MainAgentRuntimeMode.TEAM,
                main_workspace_dir=root,
                max_active_sessions=4,
                reserved_team_slots=4,
            ),
        )

        session_a = await runtime.get_or_create_session("sess-a", workspace_a)
        session_b = await runtime.get_or_create_session("sess-b", workspace_b)
        assert session_a.session_id == "sess-a"
        assert session_b.session_id == "sess-b"
        sessions = await runtime.list_sessions()
        assert len(sessions) == 2

    asyncio.run(_run())


def test_runtime_manager_team_mode_without_session_id_uses_global_default_session() -> None:
    async def _run() -> None:
        async def _build_agent(_workspace: Path):
            return _DummyAgent()

        root = Path(".").resolve()
        workspace_a = root
        runtime = _runtime_manager(
            ttl_seconds=3600,
            build_agent=_build_agent,
            policy=MainAgentRuntimePolicy(
                mode=MainAgentRuntimeMode.TEAM,
                main_workspace_dir=root,
                max_active_sessions=4,
                reserved_team_slots=4,
            ),
        )

        first = await runtime.get_or_create_session("sess-a", workspace_a)
        second = await runtime.get_or_create_session(None, workspace_a)
        assert first.session_id == "sess-a"
        assert second.session_id == "default"
        assert second.projection.is_default is True
        sessions = await runtime.list_sessions()
        assert len(sessions) == 2

    asyncio.run(_run())


def test_runtime_manager_team_mode_rejects_when_max_active_sessions_reached() -> None:
    async def _run() -> None:
        async def _build_agent(_workspace: Path):
            return _DummyAgent()

        root = Path(".").resolve()
        workspace_a = root
        workspace_b = (root / "workspace-b").resolve()
        workspace_c = (root / "workspace-c").resolve()
        runtime = _runtime_manager(
            ttl_seconds=3600,
            build_agent=_build_agent,
            policy=MainAgentRuntimePolicy(
                mode=MainAgentRuntimeMode.TEAM,
                main_workspace_dir=root,
                max_active_sessions=2,
                reserved_team_slots=4,
            ),
        )

        await runtime.get_or_create_session("sess-a", workspace_a)
        await runtime.get_or_create_session("sess-b", workspace_b)
        with pytest.raises(Exception) as exc_info:
            await runtime.get_or_create_session("sess-c", workspace_c)
        exc = exc_info.value
        assert getattr(exc, "status_code", None) == 409
        assert "max_active_sessions" in str(getattr(exc, "detail", ""))

    asyncio.run(_run())


def test_runtime_manager_runtime_diagnostics_snapshot_tracks_capacity() -> None:
    async def _run() -> None:
        async def _build_agent(_workspace: Path):
            return _DummyAgent()

        root = Path(".").resolve()
        runtime = _runtime_manager(
            ttl_seconds=3600,
            build_agent=_build_agent,
            policy=MainAgentRuntimePolicy(
                mode=MainAgentRuntimeMode.TEAM,
                main_workspace_dir=root,
                max_active_sessions=3,
                reserved_team_slots=5,
                workspace_application_required=True,
            ),
        )

        empty_diag = await runtime.get_runtime_diagnostics()
        assert empty_diag.mode == "team"
        assert empty_diag.active_sessions == 0
        assert empty_diag.max_active_sessions == 3
        assert empty_diag.available_session_slots == 3
        assert empty_diag.reserved_team_slots == 5
        assert empty_diag.workspace_application_required is True
        assert empty_diag.team_saturation_rejections == 0
        assert empty_diag.team_workspace_conflict_rejections == 0
        assert empty_diag.main_workspace_dir

        await runtime.get_or_create_session("sess-a", root)
        after_diag = await runtime.get_runtime_diagnostics()
        assert after_diag.active_sessions == 1
        assert after_diag.available_session_slots == 2
        assert after_diag.team_saturation_rejections == 0
        assert after_diag.team_workspace_conflict_rejections == 0

    asyncio.run(_run())


def test_use_case_stream_emits_activity_events_for_main_route() -> None:
    async def _run() -> None:
        async def _build_agent(_workspace: Path):
            return _HookedAgent()

        runtime = _runtime_manager(ttl_seconds=3600, build_agent=_build_agent)
        use_cases = _runtime_surface_service(runtime_manager=runtime, stream_chunk_size=16)

        events: list[str] = []
        async for event in use_cases.stream_chat_events(message="stream activity", workspace_dir=".", surface="tui"):
            events.append(event)
        joined = "\n".join(events)

        assert "activity:{" in joined
        assert "'label': 'thinking'" in joined
        assert "'label': 'shell'" in joined
        assert "done:{" in joined
        assert "'stop_reason': 'end_turn'" in joined

    asyncio.run(_run())


def test_use_case_stream_prefers_live_llm_delta_events_without_replay_duplication() -> None:
    async def _run() -> None:
        async def _build_agent(_workspace: Path):
            return _StreamingAgent()

        use_cases = _runtime_surface_service(runtime_manager=_runtime_manager(ttl_seconds=3600, build_agent=_build_agent), sse_event=lambda event, data: f"event: {event}\ndata: {data}\n\n", stream_chunk_size=4)

        chunks: list[str] = []
        async for chunk in use_cases.stream_chat_events(
            message="hello",
            session_id="sess-stream-native",
            workspace_dir=".",
            surface="tui",
        ):
            chunks.append(chunk)

        joined = "".join(chunks)
        assert joined.count("event: delta") == 2
        assert "streamed:hello" in joined
        assert "event: done" in joined

    asyncio.run(_run())


def test_runtime_manager_team_mode_diagnostics_track_conflicts_and_saturation() -> None:
    async def _run() -> None:
        async def _build_agent(_workspace: Path):
            return _DummyAgent()

        root = Path(".").resolve()
        workspace_a = root
        workspace_b = (root / "workspace-b").resolve()
        runtime = _runtime_manager(
            ttl_seconds=3600,
            build_agent=_build_agent,
            policy=MainAgentRuntimePolicy(
                mode=MainAgentRuntimeMode.TEAM,
                main_workspace_dir=root,
                max_active_sessions=1,
                reserved_team_slots=2,
            ),
        )

        await runtime.get_or_create_session("sess-a", workspace_a)

        with pytest.raises(Exception) as conflict_exc:
            await runtime.get_or_create_session("sess-a", workspace_b)
        assert getattr(conflict_exc.value, "status_code", None) == 400

        with pytest.raises(Exception) as saturation_exc:
            await runtime.get_or_create_session("sess-b", workspace_b)
        assert getattr(saturation_exc.value, "status_code", None) == 409

        diagnostics = await runtime.get_runtime_diagnostics()
        assert diagnostics.team_workspace_conflict_rejections == 1
        assert diagnostics.team_saturation_rejections == 1

    asyncio.run(_run())


def test_runtime_manager_session_lifecycle_idle_reset_applied_on_reuse(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr("mini_agent.memory.memoria_runtime.Path.home", classmethod(lambda cls: tmp_path))

    async def _run() -> None:
        async def _build_agent(_workspace: Path):
            return _DummyAgent()

        workspace = Path(".").resolve()
        runtime = _runtime_manager(
            ttl_seconds=3600,
            build_agent=_build_agent,
            policy=MainAgentRuntimePolicy(
                mode=MainAgentRuntimeMode.SINGLE_MAIN,
                session_lifecycle=SessionLifecyclePolicy(
                    mode=SessionResetMode.IDLE,
                    idle_seconds=60,
                ),
            ),
        )

        session = await runtime.get_or_create_session("sess-lifecycle", workspace)
        session.runtime.agent.add_user_message("before-reset")
        session.runtime.agent.messages.append(SimpleNamespace(role="assistant", content="mock:before-reset"))
        stale_state = SessionLifecycleState(
            session_key=session.lifecycle_state.session_key,
            created_utc=session.lifecycle_state.created_utc,
            last_activity_utc=datetime.now(timezone.utc) - timedelta(seconds=120),
            revision=session.lifecycle_state.revision,
        )
        session.lifecycle_state = stale_state

        reused = await runtime.get_or_create_session("sess-lifecycle", workspace)
        assert reused.session_id == "sess-lifecycle"
        assert len(reused.runtime.agent.messages) == 1
        assert str(getattr(reused.runtime.agent.messages[0], "role", "")).lower() == "system"
        assert reused.lifecycle_state.revision == 1

        diag = await runtime.get_runtime_diagnostics()
        assert diag.lifecycle_auto_resets == 1
        assert diag.session_reset_mode == "idle"
        assert diag.session_idle_seconds == 60

    asyncio.run(_run())


def test_use_case_chat_delegation_success_runs_sub_agent() -> None:
    async def _run() -> None:
        build_calls = 0

        async def _build_agent(_workspace: Path):
            nonlocal build_calls
            build_calls += 1
            if build_calls == 1:
                return _PrefixAgent(prefix="parent")
            return _PrefixAgent(prefix="delegated")

        runtime = _runtime_manager(ttl_seconds=3600, build_agent=_build_agent)
        use_cases = _runtime_surface_service(runtime_manager=runtime)

        response = await use_cases.run_chat(
            MainAgentChatRequest(
                message="/delegate run ship p23.3",
                workspace_dir=".",
                session_id="sess-delegate-success",
            )
        )
        assert response.session_id == "sess-delegate-success"
        assert response.reply == "delegated:ship p23.3"
        assert response.delegation is not None
        assert response.delegation["used"] is True
        assert response.delegation["fallback_used"] is False
        child_session_id = response.delegation.get("child_session_id")
        assert isinstance(child_session_id, str) and child_session_id
        event_types = [item.get("event_type") for item in response.delegation.get("events", [])]
        assert event_types == ["delegation.started", "delegation.completed"]
        child_detail = await use_cases.get_session_detail(child_session_id, recent_limit=20)
        assert child_detail.title and child_detail.title.startswith("Task:")
        child_contents = [item.content for item in child_detail.recent_messages]
        assert "ship p23.3" in child_contents
        assert "delegated:ship p23.3" in child_contents
        parent = runtime._session_lineage.parent_of(child_session_id)
        assert parent is not None
        assert parent.session_key == "sess-delegate-success"
        sessions = await use_cases.list_sessions()
        assert len(sessions) == 2

    asyncio.run(_run())


def test_use_case_can_create_explicit_derived_session() -> None:
    async def _run() -> None:
        async def _build_agent(_workspace: Path):
            return _SelectableAgent(provider_source="preset", provider_id="openai", model_id="gpt-5.4")

        runtime = _runtime_manager(ttl_seconds=3600, build_agent=_build_agent)
        use_cases = _runtime_surface_service(runtime_manager=runtime)

        parent_response = await use_cases.run_chat(
            MainAgentChatRequest(
                message="Parent session context",
                workspace_dir=".",
                session_id="sess-explicit-parent",
            )
        )
        child_detail = await use_cases.create_derived_session(
            parent_response.session_id,
            MainAgentSessionForkRequest(title="Task: Focused follow-up", surface="tui"),
        )

        assert child_detail.session_id != parent_response.session_id
        assert child_detail.title == "Task: Focused follow-up"
        assert child_detail.selected_model_source == "preset"
        assert child_detail.selected_provider_id == "openai"
        assert child_detail.selected_model_id == "gpt-5.4"
        assert child_detail.message_count == 0
        parent = runtime._session_lineage.parent_of(child_detail.session_id)
        assert parent is not None
        assert parent.session_key == parent_response.session_id

    asyncio.run(_run())


def test_use_case_chat_delegation_requires_objective() -> None:
    async def _run() -> None:
        async def _build_agent(_workspace: Path):
            return _PrefixAgent(prefix="parent")

        runtime = _runtime_manager(ttl_seconds=3600, build_agent=_build_agent)
        use_cases = _runtime_surface_service(runtime_manager=runtime)

        with pytest.raises(Exception) as exc_info:
            await use_cases.run_chat(
                MainAgentChatRequest(
                    message="/delegate",
                    workspace_dir=".",
                    session_id="sess-delegate-empty",
                )
            )
        assert getattr(exc_info.value, "status_code", None) == 400

    asyncio.run(_run())


def test_use_case_chat_delegation_failure_falls_back_to_main_agent() -> None:
    async def _run() -> None:
        build_calls = 0

        async def _build_agent(_workspace: Path):
            nonlocal build_calls
            build_calls += 1
            if build_calls == 1:
                return _PrefixAgent(prefix="parent")
            return _PrefixAgent(prefix="delegated", fail=True)

        runtime = _runtime_manager(ttl_seconds=3600, build_agent=_build_agent)
        use_cases = _runtime_surface_service(runtime_manager=runtime)

        response = await use_cases.run_chat(
            MainAgentChatRequest(
                message="/delegate run recover task",
                workspace_dir=".",
                session_id="sess-delegate-fallback",
            )
        )
        assert response.reply == "parent:recover task"
        assert response.delegation is not None
        assert response.delegation["used"] is True
        assert response.delegation["fallback_used"] is True
        child_session_id = response.delegation.get("child_session_id")
        assert isinstance(child_session_id, str) and child_session_id
        event_types = [item.get("event_type") for item in response.delegation.get("events", [])]
        assert event_types == ["delegation.started", "delegation.failed", "delegation.completed"]
        child_detail = await use_cases.get_session_detail(child_session_id, recent_limit=20)
        child_contents = [item.content for item in child_detail.recent_messages]
        assert "recover task" in child_contents
        assert any("delegated-failure" in item for item in child_contents)
        parent = runtime._session_lineage.parent_of(child_session_id)
        assert parent is not None
        assert parent.session_key == "sess-delegate-fallback"

    asyncio.run(_run())


def test_use_case_stream_delegation_emits_started_failed_and_completed_events() -> None:
    async def _run() -> None:
        build_calls = 0

        async def _build_agent(_workspace: Path):
            nonlocal build_calls
            build_calls += 1
            if build_calls == 1:
                return _PrefixAgent(prefix="parent")
            return _PrefixAgent(prefix="delegated", fail=True)

        runtime = _runtime_manager(ttl_seconds=3600, build_agent=_build_agent)
        use_cases = _runtime_surface_service(runtime_manager=runtime, sse_event=lambda event, data: f"event: {event}\ndata: {data}\n\n")

        output: list[str] = []
        async for chunk in use_cases.stream_chat_events(
            message="/delegate run stream fallback",
            session_id="sess-delegate-stream",
            workspace_dir=".",
            dry_run=False,
        ):
            output.append(chunk)

        joined = "".join(output)
        assert "event: delegation.started" in joined
        assert "event: delegation.failed" in joined
        assert "event: delegation.completed" in joined
        assert "event: done" in joined
        assert "parent:stream fallback" in joined

    asyncio.run(_run())


def test_use_case_routing_diagnostics_tracks_hits_cache_and_fallback(monkeypatch) -> None:
    monkeypatch.setattr(
        "mini_agent.application.agent_route_execution_handler.get_model_route_diagnostics_state",
        lambda: {
            "resolution_count": 4,
            "latest_snapshot": {
                "resolution_kind": "routed",
                "catalog_source": "provider_catalog",
                "route_intent": "automatic",
                "selected_provider_id": "preset-openai",
                "selected_model": "gpt-5.4",
                "selected_reason": "automatic_provider_default",
                "fallback_reason": None,
                "candidate_count": 1,
                "allowed_candidate_count": 1,
                "blocked_candidate_count": 0,
                "bootstrap_selected_provider": "openai",
                "bootstrap_selection_reason": "bootstrap_priority",
                "bootstrap_selection_policy": "explicit_preference_then_priority",
                "bootstrap_alternatives": [],
                "candidates": [
                    {
                        "selected": True,
                        "provider": "openai",
                        "provider_id": "preset-openai",
                        "model": "gpt-5.4",
                    }
                ],
            },
        },
    )

    async def _run() -> None:
        build_calls = 0

        async def _build_agent(_workspace: Path):
            nonlocal build_calls
            build_calls += 1
            if build_calls == 1:
                return _PrefixAgent(prefix="parent")
            return _PrefixAgent(prefix="delegated")

        runtime = _runtime_manager(ttl_seconds=3600, build_agent=_build_agent)
        use_cases = _runtime_surface_service(runtime_manager=runtime)

        _ = await use_cases.run_chat(
            MainAgentChatRequest(message="regular routing", workspace_dir=".", session_id="sess-routing")
        )
        _ = await use_cases.run_chat(
            MainAgentChatRequest(message="/delegate run one", workspace_dir=".", session_id="sess-routing")
        )
        _ = await use_cases.run_chat(
            MainAgentChatRequest(message="/delegate run two", workspace_dir=".", session_id="sess-routing")
        )

        diagnostics = await use_cases.get_routing_diagnostics()
        assert diagnostics.total_resolutions == 3
        assert diagnostics.cache_hits >= 1
        assert diagnostics.fallback_resolutions >= 1
        assert diagnostics.matched_scope_counts.get("peer", 0) >= 2
        assert diagnostics.matched_scope_counts.get("default", 0) >= 1
        assert diagnostics.matched_agent_counts.get("delegate-agent", 0) >= 2
        assert diagnostics.matched_agent_counts.get("main-agent", 0) >= 1
        assert diagnostics.model_route_resolutions == 4
        assert diagnostics.latest_model_route is not None
        assert diagnostics.latest_model_route.selected_provider_id == "preset-openai"
        assert diagnostics.latest_model_route.selected_model == "gpt-5.4"
        assert diagnostics.latest_model_route.bootstrap_selection_reason == "bootstrap_priority"

    asyncio.run(_run())


def test_use_case_chat_long_session_stability() -> None:
    async def _run() -> None:
        async def _build_agent(_workspace: Path):
            return _DummyAgent()

        runtime = _runtime_manager(ttl_seconds=3600, build_agent=_build_agent)
        use_cases = _runtime_surface_service(runtime_manager=runtime)

        total_turns = 40
        last = None
        for i in range(total_turns):
            last = await use_cases.run_chat(
                MainAgentChatRequest(
                    message=f"long-session-{i}",
                    workspace_dir=".",
                    session_id="sess-long",
                )
            )

        assert last is not None
        assert last.session_id == "sess-long"
        # 1(system) + 2 messages per turn(user+assistant)
        assert last.message_count == 1 + (2 * total_turns)
        assert last.reply == f"mock:long-session-{total_turns - 1}"

    asyncio.run(_run())

