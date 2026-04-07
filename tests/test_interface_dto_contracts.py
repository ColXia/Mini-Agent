"""Contract tests for interface-layer DTO stability."""

from __future__ import annotations

from mini_agent.interfaces import (
    ApiEnvelope,
    ChannelMessageRequest,
    ChannelMessageResponse,
    MainAgentChatRequest,
    MainAgentChatResponse,
    NovelCoverRequest,
    NovelSetupRequest,
)


def _required_fields(model: type) -> set[str]:
    schema = model.model_json_schema()
    return set(schema.get("required", []))


def _property_fields(model: type) -> set[str]:
    schema = model.model_json_schema()
    return set((schema.get("properties") or {}).keys())


def test_main_agent_chat_request_contract() -> None:
    assert _required_fields(MainAgentChatRequest) == {"message"}
    assert _property_fields(MainAgentChatRequest) == {"message", "session_id", "workspace_dir", "dry_run"}


def test_main_agent_chat_response_contract() -> None:
    assert _required_fields(MainAgentChatResponse) == {
        "session_id",
        "reply",
        "message_count",
        "workspace_dir",
        "updated_at",
    }
    assert "token_usage" in _property_fields(MainAgentChatResponse)


def test_channel_message_request_contract() -> None:
    assert _required_fields(ChannelMessageRequest) == {"channel_type", "conversation_id", "message"}
    assert _property_fields(ChannelMessageRequest) == {
        "channel_type",
        "conversation_id",
        "sender_id",
        "message",
        "workspace_dir",
        "session_id",
        "metadata",
        "dry_run",
    }


def test_channel_message_response_contract() -> None:
    assert _required_fields(ChannelMessageResponse) == {
        "session_id",
        "reply",
        "message_count",
        "workspace_dir",
        "updated_at",
    }
    assert "token_usage" in _property_fields(ChannelMessageResponse)


def test_novel_setup_and_cover_contract() -> None:
    assert _required_fields(NovelSetupRequest) == {"topic", "genre"}
    assert _property_fields(NovelSetupRequest) == {
        "topic",
        "genre",
        "num_chapters",
        "words_per_chapter",
        "project_dir",
        "dry_run",
        "api_host",
    }
    assert _required_fields(NovelCoverRequest) == {"prompt"}
    assert "style_type" in _property_fields(NovelCoverRequest)
    assert "style_weight" in _property_fields(NovelCoverRequest)


def test_api_envelope_contract() -> None:
    envelope = ApiEnvelope[dict](ok=True, data={"status": "ok"}, error=None)
    payload = envelope.model_dump()
    assert set(payload.keys()) == {"ok", "data", "error"}
