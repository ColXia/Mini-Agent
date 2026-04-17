from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

from mini_agent.application.interaction_request_adapter import ApplicationInteractionBinding
from mini_agent.application.session_service import SessionApplicationService
from mini_agent.config import AgentConfig, Config, LLMConfig, ToolsConfig
from mini_agent.interfaces import (
    MainAgentSessionCreateRequest,
    MainAgentSessionForkRequest,
    MainAgentSessionMemoryRequest,
    MainAgentSessionRenameRequest,
    MainAgentSessionRuntimePolicyRequest,
    MainAgentSessionShareRequest,
)
from mini_agent.runtime.main_agent_runtime_manager import MainAgentRuntimeManager


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


class _DummyAgent:
    def __init__(self) -> None:
        self.messages: list[object] = []
        self.api_total_tokens = 0
        self.token_limit = 80000
        self.last_prepared_turn_context = {}
        self.prepared_context_diagnostics = {}

    def add_user_message(self, content: str) -> None:
        self.messages.append(SimpleNamespace(role="user", content=content))


class _FakeManagedSession:
    def __init__(self, *, session_id: str, workspace_dir: Path) -> None:
        self.session_id = session_id
        self.workspace_dir = workspace_dir
        self.agent = _DummyAgent()
        self.active_surface = "tui"
        self.origin_surface = "tui"
        self.channel_type = None
        self.conversation_id = None
        self.sender_id = None
        self.context_policy = {}
        self.cancel_event = None
        self.busy = False
        self.running_state = ""
        self.pending_approvals: list[dict[str, object]] = []
        self.updated_at = None
        self._touches = 0

    @property
    def token_usage(self) -> int:
        return int(self.agent.api_total_tokens)

    @property
    def message_count(self) -> int:
        return len(self.agent.messages)

    def touch(self) -> None:
        self._touches += 1


class _FakeTurnScope:
    async def enter(self, session, **kwargs):  # noqa: ANN001, ANN003
        session.busy = True
        session.running_state = str(kwargs.get("running_detail", "") or "")
        return {"scope": "fake"}

    async def exit(self, session) -> None:  # noqa: ANN001
        session.busy = False
        session.running_state = ""

    def touch(self, session) -> None:  # noqa: ANN001
        session.touch()

    def restore_prepared_context_state(self, session) -> None:  # noqa: ANN001
        _ = session

    def capture_prepared_context_state(self, session) -> None:  # noqa: ANN001
        _ = session

    def clear_recovery_context(self, session) -> None:  # noqa: ANN001
        _ = session

    def record_message(self, session, **kwargs) -> None:  # noqa: ANN001, ANN003
        session.agent.messages.append(
            SimpleNamespace(
                role=kwargs.get("role"),
                content=kwargs.get("content"),
            )
        )

    def record_activity(self, session, **kwargs):  # noqa: ANN001, ANN003
        _ = session
        return {"label": kwargs.get("label"), "detail": kwargs.get("detail")}

    def record_pending_approval(self, session, **kwargs):  # noqa: ANN001, ANN003
        payload = dict(kwargs.get("payload", {}) or {})
        session.pending_approvals.append(payload)
        return payload

    def clear_pending_approval(self, session, *, token=None) -> None:  # noqa: ANN001, ANN201
        if token is None:
            session.pending_approvals.clear()
            return
        session.pending_approvals = [
            item for item in session.pending_approvals if str(item.get("token", "")) != str(token)
        ]


class _FakeRuntimePort:
    def __init__(self, session: _FakeManagedSession) -> None:
        self._session = session
        self.turn_scope_handler = _FakeTurnScope()
        self.runtime_policy_ready_calls: list[dict[str, object | None]] = []

    def validate_workspace(self, workspace_dir: Path) -> None:
        assert workspace_dir == self._session.workspace_dir

    async def get_or_create_session(self, session_id, workspace_dir: Path, **kwargs):  # noqa: ANN001, ANN003
        assert session_id is None
        assert workspace_dir == self._session.workspace_dir
        self._session.active_surface = str(kwargs.get("surface") or "tui")
        self._session.origin_surface = self._session.active_surface
        self._session.channel_type = kwargs.get("channel_type")
        self._session.conversation_id = kwargs.get("conversation_id")
        self._session.sender_id = kwargs.get("sender_id")
        return self._session

    async def ensure_session_runtime_policy_ready_for_turn(self, session, **kwargs):  # noqa: ANN001, ANN003
        assert session is self._session
        self.runtime_policy_ready_calls.append(
            {
                "surface": kwargs.get("surface"),
                "channel_type": kwargs.get("channel_type"),
                "conversation_id": kwargs.get("conversation_id"),
                "sender_id": kwargs.get("sender_id"),
            }
        )
        return None


def test_session_service_prepare_chat_turn_scopes_runtime_lifecycle(tmp_path: Path) -> None:
    async def _run() -> None:
        async def _build_agent(_workspace: Path):
            return _DummyAgent()

        workspace = tmp_path / "workspace"
        workspace.mkdir(parents=True, exist_ok=True)
        runtime = _runtime_manager(
            ttl_seconds=3600,
            build_agent=_build_agent,
            storage_dir=tmp_path / "store",
        )
        service = SessionApplicationService(runtime_manager=runtime)

        turn = await service.prepare_chat_turn(
            workspace_dir=workspace,
            message="hello from gateway",
            surface="qq",
            channel_type="qq",
            conversation_id="group:demo",
            sender_id="user-1",
            running_detail="qq request running",
        )

        async with turn:
            assert turn.busy is True
            assert turn.channel_type == "qq"
            turn.record_message(
                role="assistant",
                content="ack",
                surface="qq",
                channel_type="qq",
                conversation_id="group:demo",
                sender_id="user-1",
            )

        detail = await service.get_session_detail(turn.session_id, recent_limit=10)

        assert detail.busy is False
        assert [item.role for item in detail.recent_messages] == ["user", "assistant"]
        assert detail.recent_messages[0].content == "hello from gateway"
        assert detail.recent_messages[1].content == "ack"

    asyncio.run(_run())


def test_session_service_prepare_chat_turn_prefers_remote_channel_when_surface_missing(tmp_path: Path) -> None:
    async def _run() -> None:
        async def _build_agent(_workspace: Path):
            return _DummyAgent()

        workspace = tmp_path / "workspace-remote-binding"
        workspace.mkdir(parents=True, exist_ok=True)
        runtime = _runtime_manager(
            ttl_seconds=3600,
            build_agent=_build_agent,
            storage_dir=tmp_path / "store-remote-binding",
        )
        service = SessionApplicationService(runtime_manager=runtime)

        turn = await service.prepare_chat_turn(
            workspace_dir=workspace,
            message="hello from remote alias",
            channel_type="qqbot",
            conversation_id="group:demo",
            sender_id="user-1",
            running_detail="remote request running",
        )

        async with turn:
            assert turn.origin_surface == "qq"
            assert turn.active_surface == "qq"
            assert turn.channel_type == "qq"
            turn.record_message(
                role="assistant",
                content="ack from remote alias",
                surface=None,
                channel_type="qqbot",
                conversation_id="group:demo",
                sender_id="user-1",
            )

        detail = await service.get_session_detail(turn.session_id, recent_limit=10)

        assert detail.origin_surface == "qq"
        assert detail.active_surface == "qq"
        assert detail.reply_enabled is True
        assert [item.surface for item in detail.recent_messages] == ["qq", "qq"]
        assert [item.channel_type for item in detail.recent_messages] == ["qq", "qq"]
        assert [item.conversation_id for item in detail.recent_messages] == ["group:demo", "group:demo"]

    asyncio.run(_run())


def test_session_service_mutation_wrappers_shape_session_responses(tmp_path: Path) -> None:
    async def _run() -> None:
        async def _build_agent(_workspace: Path):
            return _DummyAgent()

        workspace = tmp_path / "workspace"
        workspace.mkdir(parents=True, exist_ok=True)
        runtime = _runtime_manager(
            ttl_seconds=3600,
            build_agent=_build_agent,
            storage_dir=tmp_path / "store-mutations",
        )
        service = SessionApplicationService(runtime_manager=runtime)

        detail = await service.create_session(
            MainAgentSessionCreateRequest(
                title="Session 1",
                surface="tui",
                shared=False,
            ),
            workspace_dir=workspace,
        )
        renamed = await service.rename_session(
            detail.session_id,
            MainAgentSessionRenameRequest(title="nyonyo"),
        )
        shared = await service.set_session_shared(
            detail.session_id,
            MainAgentSessionShareRequest(shared=True),
        )
        listed = await service.list_sessions(workspace_dir=workspace)

        assert renamed.status == "renamed"
        assert renamed.title == "nyonyo"
        assert shared.status == "shared"
        assert shared.shared is True
        assert listed[0].title == "nyonyo"
        assert listed[0].shared is True

    asyncio.run(_run())


def test_session_surface_binding_extracts_request_context() -> None:
    request = MainAgentSessionMemoryRequest(
        action="status",
        surface=" qq ",
        channel_type=" qqbot ",
        conversation_id=" group:demo ",
        sender_id=" user-1 ",
    )

    binding = ApplicationInteractionBinding.from_request(request)

    assert binding.as_kwargs() == {
        "surface": "qq",
        "channel_type": "qq",
        "conversation_id": "group:demo",
        "sender_id": "user-1",
    }


def test_session_service_prepare_chat_turn_accepts_structural_runtime_port(tmp_path: Path) -> None:
    async def _run() -> None:
        workspace = tmp_path / "workspace-port"
        workspace.mkdir(parents=True, exist_ok=True)
        session = _FakeManagedSession(session_id="sess-port", workspace_dir=workspace)
        runtime_port = _FakeRuntimePort(session)
        service = SessionApplicationService(runtime_manager=runtime_port)

        turn = await service.prepare_chat_turn(
            workspace_dir=workspace,
            message="hello seam",
            surface="cli",
            channel_type="terminal",
            conversation_id="local:1",
            sender_id="operator",
            running_detail="cli request running",
        )

        async with turn:
            assert turn.session_id == "sess-port"
            assert turn.active_surface == "cli"
            assert turn.channel_type == "terminal"
            assert turn.busy is True
            turn.record_message(role="assistant", content="ack", surface="cli")

        assert turn.busy is False
        assert [item.role for item in session.agent.messages] == ["assistant"]
        assert [item.content for item in session.agent.messages] == ["ack"]
        assert runtime_port.runtime_policy_ready_calls == [
            {
                "surface": "cli",
                "channel_type": "terminal",
                "conversation_id": "local:1",
                "sender_id": "operator",
            }
        ]

    asyncio.run(_run())


def test_session_service_prepare_chat_turn_normalizes_private_desktop_plan_session(tmp_path: Path) -> None:
    async def _run() -> None:
        async def _build_agent(_workspace: Path):
            return _DummyAgent()

        workspace = tmp_path / "workspace-desktop-autofix"
        workspace.mkdir(parents=True, exist_ok=True)
        runtime = _runtime_manager(
            ttl_seconds=3600,
            build_agent=_build_agent,
            storage_dir=tmp_path / "store-desktop-autofix",
        )
        service = SessionApplicationService(runtime_manager=runtime)

        created = await service.create_session(
            MainAgentSessionCreateRequest(title="Desktop Session", surface="desktop", shared=False),
            workspace_dir=workspace,
        )
        await service.update_session_runtime_policy(
            created.session_id,
            MainAgentSessionRuntimePolicyRequest(
                approval_profile="plan",
                access_level="default",
                surface="desktop",
            ),
        )

        before = await service.get_session_detail(created.session_id, recent_limit=5)
        assert before.sandbox_diagnostics["approval_profile"] == "plan"

        _turn = await service.prepare_chat_turn(
            workspace_dir=workspace,
            session_id=created.session_id,
            message="hello desktop",
            surface="desktop",
            running_detail="desktop request running",
        )

        after = await service.get_session_detail(created.session_id, recent_limit=5)
        assert after.sandbox_diagnostics["approval_profile"] == "build"
        assert after.sandbox_diagnostics["access_level"] == "default"
        assert after.active_surface == "desktop"

    asyncio.run(_run())


def test_session_surface_binding_prefers_remote_channel_over_default_surface() -> None:
    request = MainAgentSessionForkRequest(
        title="remote fork",
        channel_type=" qqbot ",
        conversation_id=" group:demo ",
        sender_id=" user-1 ",
    )

    binding = ApplicationInteractionBinding.from_request(request, default_surface="tui")

    assert binding.as_kwargs() == {
        "surface": "qq",
        "channel_type": "qq",
        "conversation_id": "group:demo",
        "sender_id": "user-1",
    }
