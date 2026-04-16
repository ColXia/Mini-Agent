"""Tests for application-layer interaction request adapters."""

from __future__ import annotations

from pathlib import Path

from mini_agent.application.interaction_request_adapter import ApplicationInteractionBinding
from mini_agent.interfaces import ChannelMessageRequest, MainAgentChatRequest, MainAgentSessionApprovalRequest


def test_application_interaction_binding_builds_main_chat_request_from_channel_payload() -> None:
    request = ChannelMessageRequest(
        channel_type="qqbot",
        conversation_id="group:demo",
        sender_id="user-1",
        message="hello",
        workspace_dir=".",
        session_id="sess-1",
        dry_run=True,
    )

    binding = ApplicationInteractionBinding.from_channel_message_request(request)
    chat_request = binding.to_main_agent_chat_request(
        message=request.message,
        session_id=request.session_id,
        workspace_dir=request.workspace_dir,
        dry_run=request.dry_run,
    )

    assert chat_request == MainAgentChatRequest(
        message="hello",
        session_id="sess-1",
        workspace_dir=".",
        dry_run=True,
        surface="qq",
        channel_type="qq",
        conversation_id="group:demo",
        sender_id="user-1",
    )


def test_application_interaction_binding_builds_surface_request_from_main_chat_request() -> None:
    request = MainAgentChatRequest(
        message="inspect repo",
        session_id="sess-tui",
        session_title_hint="Demo",
        workspace_dir=".",
        dry_run=False,
        surface="tui",
        channel_type="qqbot",
        conversation_id="group:ops",
        sender_id="user-2",
    )

    binding = ApplicationInteractionBinding.from_main_agent_chat_request(request)
    surface_request = binding.to_surface_chat_execution_request(
        message=request.message,
        workspace_dir=Path(".").resolve(),
        session_id=request.session_id,
        session_title_hint=request.session_title_hint,
        dry_run=request.dry_run,
        running_detail="tui request running",
    )

    assert surface_request.message == "inspect repo"
    assert surface_request.workspace_dir == Path(".").resolve()
    assert surface_request.session_id == "sess-tui"
    assert surface_request.session_title_hint == "Demo"
    assert surface_request.surface == "tui"
    assert surface_request.channel_type == "qq"
    assert surface_request.conversation_id == "group:ops"
    assert surface_request.sender_id == "user-2"
    assert surface_request.running_detail == "tui request running"


def test_application_interaction_binding_extracts_request_context_and_remote_binding_key() -> None:
    request = MainAgentSessionApprovalRequest(
        approved=True,
        token="approval-1",
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
    assert binding.entrance == "remote"
    assert binding.remote_channel == "qq"
    assert binding.remote_binding_key == "qq|group:demo"

