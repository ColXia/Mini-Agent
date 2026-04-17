from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

from mini_agent.application.interaction_request_adapter import ApplicationInteractionBinding
from mini_agent.application.session_service import SessionApplicationService
from mini_agent.config import AgentConfig, Config, LLMConfig, ToolsConfig
from mini_agent.interfaces import (
    MainAgentSessionApprovalRequest,
    MainAgentSessionApprovalResponse,
    MainAgentSessionCancelRequest,
    MainAgentSessionCreateRequest,
    MainAgentSessionForkRequest,
    MainAgentSessionMemoryRequest,
    MainAgentSessionMemoryResponse,
    MainAgentSessionModelSelectionRequest,
    MainAgentSessionModelSelectionResponse,
    MainAgentSessionMutationResponse,
    MainAgentSessionRenameRequest,
    MainAgentSessionRuntimePolicyRequest,
    MainAgentSessionRuntimePolicyResponse,
    MainAgentSessionShareRequest,
    MainAgentSessionSkillRequest,
    MainAgentSessionSkillResponse,
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


def test_session_service_cancel_and_approval_use_injected_run_control_service() -> None:
    class _RunControlStub:
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
                active_surface="qq",
            )

    class _RuntimeStub:
        def validate_workspace(self, workspace_dir: Path) -> None:
            _ = workspace_dir

    async def _run() -> None:
        run_control = _RunControlStub()
        service = SessionApplicationService(runtime_manager=_RuntimeStub(), run_control_service=run_control)

        cancel = await service.cancel_session(
            "sess-1",
            MainAgentSessionCancelRequest(
                reason="stop",
                surface=" qq ",
                channel_type=" qqbot ",
                conversation_id=" group:demo ",
                sender_id=" user-1 ",
            ),
        )
        approved = await service.respond_to_approval(
            "sess-1",
            MainAgentSessionApprovalRequest(
                approved=True,
                token="approval-1",
                surface="tui",
            ),
        )
        denied = await service.respond_to_approval(
            "sess-1",
            MainAgentSessionApprovalRequest(
                approved=False,
                token="approval-2",
                surface="desktop",
            ),
        )

        assert cancel.status == "cancel_requested"
        assert approved.decision == "approved"
        assert denied.decision == "denied"
        assert run_control.calls == [
            (
                "cancel_session_run",
                "sess-1",
                {
                    "reason": "stop",
                    "source": "qq",
                    "surface": "qq",
                    "channel_type": "qq",
                    "conversation_id": "group:demo",
                    "sender_id": "user-1",
                },
            ),
            (
                "approve_session_wait",
                "sess-1",
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
                "sess-1",
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


def test_session_service_default_run_control_falls_back_to_runtime_session_operations() -> None:
    class _RuntimeStub:
        def __init__(self) -> None:
            self.calls: list[tuple[str, object]] = []

        def validate_workspace(self, workspace_dir: Path) -> None:
            _ = workspace_dir

        async def cancel_session_turn(
            self,
            session_id: str,
            *,
            reason: str | None = None,
            surface: str | None = None,
            channel_type: str | None = None,
            conversation_id: str | None = None,
            sender_id: str | None = None,
        ):
            self.calls.append(
                ("cancel_session_turn", session_id, reason, surface, channel_type, conversation_id, sender_id)
            )
            return MainAgentSessionMutationResponse(
                status="cancel_requested",
                session_id=session_id,
                active_surface=surface,
            )

        async def resolve_pending_approval(
            self,
            session_id: str,
            *,
            approved: bool,
            token: str | None = None,
            surface: str | None = None,
            channel_type: str | None = None,
            conversation_id: str | None = None,
            sender_id: str | None = None,
        ):
            self.calls.append(
                (
                    "resolve_pending_approval",
                    session_id,
                    approved,
                    token,
                    surface,
                    channel_type,
                    conversation_id,
                    sender_id,
                )
            )
            return MainAgentSessionApprovalResponse(
                status="resolved",
                session_id=session_id,
                token=token,
                tool_name="shell",
                decision="approved" if approved else "denied",
                active_surface=surface,
            )

        async def get_session_detail(self, session_id: str, *, recent_limit: int = 1):
            self.calls.append(("get_session_detail", session_id, recent_limit))
            return {"session_id": session_id}

    async def _run() -> None:
        runtime = _RuntimeStub()
        service = SessionApplicationService(runtime_manager=runtime)

        cancel = await service.cancel_session(
            "sess-2",
            MainAgentSessionCancelRequest(
                reason="stop now",
                surface="desktop",
                channel_type="desktop",
            ),
        )
        approval = await service.respond_to_approval(
            "sess-2",
            MainAgentSessionApprovalRequest(
                approved=True,
                token="approval-9",
                surface="desktop",
            ),
        )

        assert cancel.status == "cancel_requested"
        assert approval.decision == "approved"
        assert runtime.calls == [
            ("cancel_session_turn", "sess-2", "stop now", "desktop", "desktop", None, None),
            ("resolve_pending_approval", "sess-2", True, "approval-9", "desktop", None, None, None),
        ]

    asyncio.run(_run())


def test_session_service_update_model_selection_uses_injected_model_service() -> None:
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

    class _RuntimeStub:
        def validate_workspace(self, workspace_dir: Path) -> None:
            _ = workspace_dir

    async def _run() -> None:
        model_service = _ModelServiceStub()
        service = SessionApplicationService(runtime_manager=_RuntimeStub(), model_service=model_service)

        response = await service.update_session_model_selection(
            "sess-model-1",
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
                "sess-model-1",
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


def test_session_service_default_model_service_falls_back_to_runtime_session_model_selection() -> None:
    class _RuntimeStub:
        def __init__(self) -> None:
            self.calls: list[tuple[str, object]] = []

        def validate_workspace(self, workspace_dir: Path) -> None:
            _ = workspace_dir

        async def update_session_model_selection(
            self,
            session_id: str,
            *,
            provider_source: str | None = None,
            provider_id: str | None = None,
            model_id: str | None = None,
            surface: str | None = None,
            channel_type: str | None = None,
            conversation_id: str | None = None,
            sender_id: str | None = None,
        ):
            self.calls.append(
                (
                    "update_session_model_selection",
                    session_id,
                    provider_source,
                    provider_id,
                    model_id,
                    surface,
                    channel_type,
                    conversation_id,
                    sender_id,
                )
            )
            return MainAgentSessionModelSelectionResponse(
                status="selected",
                session_id=session_id,
                active_surface=surface,
                applied=True,
                queued=False,
                selected_model_source=provider_source,
                selected_provider_id=provider_id,
                selected_model_id=model_id,
            )

    async def _run() -> None:
        runtime = _RuntimeStub()
        service = SessionApplicationService(runtime_manager=runtime)

        response = await service.update_session_model_selection(
            "sess-model-2",
            MainAgentSessionModelSelectionRequest(
                provider_source="preset",
                provider_id="openai",
                model_id="gpt-5.4",
                surface="desktop",
            ),
        )

        assert response.selected_model_id == "gpt-5.4"
        assert runtime.calls == [
            (
                "update_session_model_selection",
                "sess-model-2",
                "preset",
                "openai",
                "gpt-5.4",
                "desktop",
                None,
                None,
                None,
            )
        ]

    asyncio.run(_run())


def test_session_service_update_runtime_policy_uses_injected_agent_service() -> None:
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

    class _RuntimeStub:
        def validate_workspace(self, workspace_dir: Path) -> None:
            _ = workspace_dir

    async def _run() -> None:
        agent_service = _AgentServiceStub()
        service = SessionApplicationService(runtime_manager=_RuntimeStub(), agent_service=agent_service)

        response = await service.update_session_runtime_policy(
            "sess-policy-1",
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
        assert response.access_level == "full-access"
        assert agent_service.calls == [
            (
                "update_session_runtime_policy",
                "sess-policy-1",
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


def test_session_service_default_agent_service_falls_back_to_runtime_policy_update() -> None:
    class _RuntimeStub:
        def __init__(self) -> None:
            self.calls: list[tuple[str, object]] = []

        def validate_workspace(self, workspace_dir: Path) -> None:
            _ = workspace_dir

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
        ):
            self.calls.append(
                (
                    "update_session_runtime_policy",
                    session_id,
                    approval_profile,
                    access_level,
                    surface,
                    channel_type,
                    conversation_id,
                    sender_id,
                )
            )
            return MainAgentSessionRuntimePolicyResponse(
                status="updated",
                session_id=session_id,
                active_surface=surface,
                applied=True,
                approval_profile=str(approval_profile or ""),
                access_level=str(access_level or ""),
                summary="runtime build / default",
                details="Runtime policy updated.",
                status_text="Runtime set to build / default.",
                sandbox_diagnostics={"sandbox_mode": "workspace"},
            )

    async def _run() -> None:
        runtime = _RuntimeStub()
        service = SessionApplicationService(runtime_manager=runtime)

        response = await service.update_session_runtime_policy(
            "sess-policy-2",
            MainAgentSessionRuntimePolicyRequest(
                approval_profile="build",
                access_level="default",
                surface="desktop",
            ),
        )

        assert response.status == "updated"
        assert response.approval_profile == "build"
        assert runtime.calls == [
            (
                "update_session_runtime_policy",
                "sess-policy-2",
                "build",
                "default",
                "desktop",
                None,
                None,
                None,
            )
        ]

    asyncio.run(_run())


def test_session_service_manage_memory_uses_injected_agent_service() -> None:
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
                result={"summary": "runtime memory ok"},
            )

    class _RuntimeStub:
        def validate_workspace(self, workspace_dir: Path) -> None:
            _ = workspace_dir

    async def _run() -> None:
        agent_service = _AgentServiceStub()
        service = SessionApplicationService(runtime_manager=_RuntimeStub(), agent_service=agent_service)

        response = await service.manage_session_memory(
            "sess-memory-1",
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
        assert response.result["summary"] == "runtime memory ok"
        assert agent_service.calls == [
            (
                "manage_session_memory",
                "sess-memory-1",
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


def test_session_service_default_agent_service_falls_back_to_runtime_memory_management() -> None:
    class _RuntimeStub:
        def __init__(self) -> None:
            self.calls: list[tuple[str, object]] = []

        def validate_workspace(self, workspace_dir: Path) -> None:
            _ = workspace_dir

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
        ):
            self.calls.append(
                (
                    "manage_session_memory",
                    session_id,
                    action,
                    engram_id,
                    content,
                    query,
                    day,
                    export_format,
                    detail_mode,
                    surface,
                    channel_type,
                    conversation_id,
                    sender_id,
                )
            )
            return MainAgentSessionMemoryResponse(
                status="ok",
                session_id=session_id,
                action=action,
                active_surface=surface,
                memory_diagnostics={},
                result={"summary": "fallback memory ok"},
            )

    async def _run() -> None:
        runtime = _RuntimeStub()
        service = SessionApplicationService(runtime_manager=runtime)

        response = await service.manage_session_memory(
            "sess-memory-2",
            MainAgentSessionMemoryRequest(
                action="show",
                detail_mode="full",
                surface="desktop",
            ),
        )

        assert response.result["summary"] == "fallback memory ok"
        assert runtime.calls == [
            (
                "manage_session_memory",
                "sess-memory-2",
                "show",
                None,
                None,
                None,
                None,
                None,
                "full",
                "desktop",
                None,
                None,
                None,
            )
        ]

    asyncio.run(_run())


def test_session_service_manage_skills_uses_injected_agent_service() -> None:
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

    class _RuntimeStub:
        def validate_workspace(self, workspace_dir: Path) -> None:
            _ = workspace_dir

    async def _run() -> None:
        agent_service = _AgentServiceStub()
        service = SessionApplicationService(runtime_manager=_RuntimeStub(), agent_service=agent_service)

        response = await service.manage_session_skills(
            "sess-skill-1",
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
                "sess-skill-1",
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


def test_session_service_default_agent_service_falls_back_to_runtime_skill_management() -> None:
    class _RuntimeStub:
        def __init__(self) -> None:
            self.calls: list[tuple[str, object]] = []

        def validate_workspace(self, workspace_dir: Path) -> None:
            _ = workspace_dir

        async def manage_session_skills(
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
        ):
            self.calls.append(
                (
                    "manage_session_skills",
                    session_id,
                    action,
                    skill_name,
                    path,
                    query,
                    mode,
                    surface,
                    channel_type,
                    conversation_id,
                    sender_id,
                )
            )
            return MainAgentSessionSkillResponse(
                status="ok",
                session_id=session_id,
                action=action,
                active_surface=surface,
                result={"summary": "fallback skills ok"},
            )

    async def _run() -> None:
        runtime = _RuntimeStub()
        service = SessionApplicationService(runtime_manager=runtime)

        response = await service.manage_session_skills(
            "sess-skill-2",
            MainAgentSessionSkillRequest(
                action="list",
                query="helper",
                surface="desktop",
            ),
        )

        assert response.result["summary"] == "fallback skills ok"
        assert runtime.calls == [
            (
                "manage_session_skills",
                "sess-skill-2",
                "list",
                None,
                None,
                "helper",
                None,
                "desktop",
                None,
                None,
                None,
            )
        ]

    asyncio.run(_run())
