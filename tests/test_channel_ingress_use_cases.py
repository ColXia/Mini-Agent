from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path

from mini_agent.application import (
    ChannelIngressUseCases,
    RemoteConversationBindingService,
)
from mini_agent.interfaces import ChannelMessageRequest, MainAgentChatRequest, MainAgentChatResponse
from mini_agent.session import ConversationBindingStore


class _UnusedNovelUseCases:
    async def get_config(self, project_dir: str | None = None) -> dict[str, object]:
        _ = project_dir
        raise AssertionError("novel actions are outside this test scope")


def _resolve_workspace_dir(workspace_dir: str | None) -> Path:
    return Path(workspace_dir or ".").resolve()


def _to_utc_iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def test_channel_ingress_reuses_central_binding_without_explicit_session_id(tmp_path: Path) -> None:
    async def _run() -> None:
        requests: list[MainAgentChatRequest] = []
        next_session_id = "sess-001"

        async def _run_main_agent_chat(request: MainAgentChatRequest) -> MainAgentChatResponse:
            requests.append(request)
            return MainAgentChatResponse(
                session_id=next_session_id,
                reply=f"echo:{request.message}",
                message_count=len(requests),
                token_usage=7,
                workspace_dir=str(_resolve_workspace_dir(request.workspace_dir)),
                updated_at=_to_utc_iso(datetime.now(timezone.utc)),
            )

        binding_store = ConversationBindingStore(tmp_path / "conversation-bindings.json")
        use_cases = ChannelIngressUseCases(
            run_main_agent_chat=_run_main_agent_chat,
            novel_use_cases=_UnusedNovelUseCases(),
            resolve_workspace_dir=_resolve_workspace_dir,
            to_utc_iso=_to_utc_iso,
            remote_binding_service=RemoteConversationBindingService(binding_store=binding_store),
        )

        first = await use_cases.handle_message(
            ChannelMessageRequest(
                channel_type="qq",
                conversation_id="group:alpha",
                sender_id="user-1",
                message="hello",
                workspace_dir=str(tmp_path / "workspace"),
            )
        )
        assert first.session_id == "sess-001"
        assert requests[0].session_id is None

        second = await use_cases.handle_message(
            ChannelMessageRequest(
                channel_type="qq",
                conversation_id="group:alpha",
                sender_id="user-1",
                message="continue",
                workspace_dir=str(tmp_path / "workspace"),
            )
        )
        assert second.session_id == "sess-001"
        assert requests[1].session_id == "sess-001"

    asyncio.run(_run())


def test_channel_ingress_dry_run_does_not_persist_remote_binding(tmp_path: Path) -> None:
    async def _run() -> None:
        requests: list[MainAgentChatRequest] = []

        async def _run_main_agent_chat(request: MainAgentChatRequest) -> MainAgentChatResponse:
            requests.append(request)
            return MainAgentChatResponse(
                session_id="dry-run-session",
                reply=f"echo:{request.message}",
                message_count=len(requests),
                token_usage=0,
                workspace_dir=str(_resolve_workspace_dir(request.workspace_dir)),
                updated_at=_to_utc_iso(datetime.now(timezone.utc)),
            )

        binding_store = ConversationBindingStore(tmp_path / "conversation-bindings.json")
        use_cases = ChannelIngressUseCases(
            run_main_agent_chat=_run_main_agent_chat,
            novel_use_cases=_UnusedNovelUseCases(),
            resolve_workspace_dir=_resolve_workspace_dir,
            to_utc_iso=_to_utc_iso,
            remote_binding_service=RemoteConversationBindingService(binding_store=binding_store),
        )

        await use_cases.handle_message(
            ChannelMessageRequest(
                channel_type="qq",
                conversation_id="group:dry-run",
                sender_id="user-1",
                message="dry run",
                workspace_dir=str(tmp_path / "workspace"),
                dry_run=True,
            )
        )
        assert requests[0].session_id is None
        assert binding_store.get_session_id("qq|group:dry-run") is None

    asyncio.run(_run())


def test_channel_ingress_normalizes_remote_alias_before_binding_lookup(tmp_path: Path) -> None:
    async def _run() -> None:
        requests: list[MainAgentChatRequest] = []

        async def _run_main_agent_chat(request: MainAgentChatRequest) -> MainAgentChatResponse:
            requests.append(request)
            return MainAgentChatResponse(
                session_id="sess-alias",
                reply=f"echo:{request.message}",
                message_count=len(requests),
                token_usage=3,
                workspace_dir=str(_resolve_workspace_dir(request.workspace_dir)),
                updated_at=_to_utc_iso(datetime.now(timezone.utc)),
            )

        binding_store = ConversationBindingStore(tmp_path / "conversation-bindings-alias.json")
        use_cases = ChannelIngressUseCases(
            run_main_agent_chat=_run_main_agent_chat,
            novel_use_cases=_UnusedNovelUseCases(),
            resolve_workspace_dir=_resolve_workspace_dir,
            to_utc_iso=_to_utc_iso,
            remote_binding_service=RemoteConversationBindingService(binding_store=binding_store),
        )

        await use_cases.handle_message(
            ChannelMessageRequest(
                channel_type="qqbot",
                conversation_id="group:alias",
                sender_id="user-1",
                message="hello alias",
                workspace_dir=str(tmp_path / "workspace"),
            )
        )
        await use_cases.handle_message(
            ChannelMessageRequest(
                channel_type="qq",
                conversation_id="group:alias",
                sender_id="user-1",
                message="continue alias",
                workspace_dir=str(tmp_path / "workspace"),
            )
        )

        assert len(requests) == 2
        assert requests[0].session_id is None
        assert requests[1].session_id == "sess-alias"

    asyncio.run(_run())
