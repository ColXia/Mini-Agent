from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

from mini_agent.application.session_service import SessionApplicationService, SessionSurfaceBinding
from mini_agent.interfaces import (
    MainAgentSessionCreateRequest,
    MainAgentSessionForkRequest,
    MainAgentSessionMemoryRequest,
    MainAgentSessionRenameRequest,
    MainAgentSessionShareRequest,
)
from mini_agent.runtime.main_agent_runtime_manager import MainAgentRuntimeManager


class _DummyAgent:
    def __init__(self) -> None:
        self.messages: list[object] = []
        self.api_total_tokens = 0
        self.token_limit = 80000
        self.last_prepared_turn_context = {}
        self.prepared_context_diagnostics = {}

    def add_user_message(self, content: str) -> None:
        self.messages.append(SimpleNamespace(role="user", content=content))


def test_session_service_prepare_chat_turn_scopes_runtime_lifecycle(tmp_path: Path) -> None:
    async def _run() -> None:
        async def _build_agent(_workspace: Path):
            return _DummyAgent()

        workspace = tmp_path / "workspace"
        workspace.mkdir(parents=True, exist_ok=True)
        runtime = MainAgentRuntimeManager(
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
        runtime = MainAgentRuntimeManager(
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
        runtime = MainAgentRuntimeManager(
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

    binding = SessionSurfaceBinding.from_request(request)

    assert binding.as_kwargs() == {
        "surface": "qq",
        "channel_type": "qq",
        "conversation_id": "group:demo",
        "sender_id": "user-1",
    }


def test_session_surface_binding_prefers_remote_channel_over_default_surface() -> None:
    request = MainAgentSessionForkRequest(
        title="remote fork",
        channel_type=" qqbot ",
        conversation_id=" group:demo ",
        sender_id=" user-1 ",
    )

    binding = SessionSurfaceBinding.from_request(request, default_surface="tui")

    assert binding.as_kwargs() == {
        "surface": "qq",
        "channel_type": "qq",
        "conversation_id": "group:demo",
        "sender_id": "user-1",
    }
