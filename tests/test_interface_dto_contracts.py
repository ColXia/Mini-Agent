"""Contract tests for interface-layer DTO stability."""

from __future__ import annotations

from mini_agent.interfaces import (
    ApiEnvelope,
    ChannelMessageRequest,
    ChannelMessageResponse,
    MainAgentChatRequest,
    MainAgentChatResponse,
    MainAgentDefaultSessionRequest,
    MainAgentRoutingDiagnostics,
    MainAgentSessionContextRequest,
    MainAgentSessionContextResponse,
    MainAgentSessionControlRequest,
    MainAgentSessionControlResponse,
    MainAgentSessionCreateRequest,
    MainAgentSessionDetail,
    MainAgentSessionMessage,
    MainAgentSessionMemoryRequest,
    MainAgentSessionMemoryResponse,
    MainAgentSessionModelSelectionRequest,
    MainAgentSessionModelSelectionResponse,
    MainAgentSessionRuntimePolicyResponse,
    ModelRouteCandidateDiagnostics,
    ModelRouteDiagnostics,
    MainAgentSessionShareRequest,
    MainAgentSessionSkillRequest,
    MainAgentSessionSkillResponse,
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
    assert _property_fields(MainAgentChatRequest) == {
        "message",
        "session_id",
        "session_title_hint",
        "workspace_dir",
        "dry_run",
        "surface",
        "channel_type",
        "conversation_id",
        "sender_id",
    }


def test_main_agent_chat_response_contract() -> None:
    assert _required_fields(MainAgentChatResponse) == {
        "session_id",
        "reply",
        "message_count",
        "workspace_dir",
        "updated_at",
    }
    assert "token_usage" in _property_fields(MainAgentChatResponse)


def test_main_agent_runtime_session_request_contracts() -> None:
    assert _property_fields(MainAgentSessionCreateRequest) == {
        "workspace_dir",
        "title",
        "surface",
        "shared",
    }
    assert _property_fields(MainAgentDefaultSessionRequest) == {
        "workspace_dir",
        "surface",
        "channel_type",
        "conversation_id",
        "sender_id",
    }
    assert _required_fields(MainAgentSessionShareRequest) == {"shared"}
    assert _property_fields(MainAgentSessionShareRequest) == {"shared"}


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


def test_main_agent_session_contracts() -> None:
    assert _required_fields(MainAgentSessionMessage) == {"index", "role", "content", "surface", "created_at"}
    assert "metadata" in _property_fields(MainAgentSessionMessage)
    assert _property_fields(MainAgentSessionDetail) >= {
        "session_id",
        "workspace_dir",
        "created_at",
        "updated_at",
        "message_count",
        "origin_surface",
        "active_surface",
        "reply_enabled",
        "token_usage",
        "token_limit",
        "selected_model_source",
        "selected_provider_id",
        "selected_model_id",
        "pending_model_source",
        "pending_provider_id",
        "pending_model_id",
        "pending_skill_reload",
        "pending_skill_reload_reason",
        "recovery",
        "remote_recovery_text",
        "context_policy",
        "last_prepared_context",
        "prepared_context_diagnostics",
        "sandbox_diagnostics",
        "recent_messages",
    }
    assert _required_fields(MainAgentSessionControlRequest) == {"action"}
    assert _property_fields(MainAgentSessionControlRequest) == {
        "action",
        "reason",
        "surface",
        "channel_type",
        "conversation_id",
        "sender_id",
    }
    assert _required_fields(MainAgentSessionControlResponse) == {
        "status",
        "session_id",
        "action",
    }
    assert _property_fields(MainAgentSessionControlResponse) >= {
        "applied",
        "active_surface",
        "reason",
        "message_count_before",
        "message_count_after",
        "token_count_before",
        "token_count_after",
        "stats",
    }
    assert _required_fields(MainAgentSessionContextRequest) == {"action"}
    assert _property_fields(MainAgentSessionContextRequest) == {
        "action",
        "sources",
        "max_items",
        "max_total_chars",
        "max_items_per_source",
        "surface",
        "channel_type",
        "conversation_id",
        "sender_id",
    }
    assert _required_fields(MainAgentSessionContextResponse) == {
        "status",
        "session_id",
        "action",
    }
    assert _property_fields(MainAgentSessionContextResponse) >= {
        "active_surface",
        "context_policy",
    }
    assert _required_fields(MainAgentSessionMemoryRequest) == {"action"}
    assert _property_fields(MainAgentSessionMemoryRequest) == {
        "action",
        "engram_id",
        "content",
        "query",
        "day",
        "export_format",
        "detail_mode",
        "surface",
        "channel_type",
        "conversation_id",
        "sender_id",
    }
    assert _required_fields(MainAgentSessionMemoryResponse) == {
        "status",
        "session_id",
        "action",
    }
    assert _property_fields(MainAgentSessionMemoryResponse) >= {
        "active_surface",
        "memory_diagnostics",
        "result",
    }
    assert _required_fields(MainAgentSessionSkillRequest) == {"action"}
    assert _property_fields(MainAgentSessionSkillRequest) == {
        "action",
        "skill_name",
        "path",
        "query",
        "mode",
        "surface",
        "channel_type",
        "conversation_id",
        "sender_id",
    }
    assert _required_fields(MainAgentSessionSkillResponse) == {
        "status",
        "session_id",
        "action",
    }
    assert _property_fields(MainAgentSessionSkillResponse) >= {
        "active_surface",
        "result",
    }
    assert _required_fields(MainAgentSessionModelSelectionRequest) == {
        "provider_id",
        "model_id",
    }
    assert _property_fields(MainAgentSessionModelSelectionRequest) == {
        "provider_source",
        "provider_id",
        "model_id",
        "surface",
        "channel_type",
        "conversation_id",
        "sender_id",
    }
    assert _required_fields(MainAgentSessionModelSelectionResponse) == {
        "status",
        "session_id",
    }
    assert _property_fields(MainAgentSessionModelSelectionResponse) >= {
        "active_surface",
        "applied",
        "queued",
        "selected_model_source",
        "selected_provider_id",
        "selected_model_id",
        "pending_model_source",
        "pending_provider_id",
        "pending_model_id",
    }
    assert _required_fields(MainAgentSessionRuntimePolicyResponse) == {
        "status",
        "session_id",
        "approval_profile",
        "access_level",
    }
    assert _property_fields(MainAgentSessionRuntimePolicyResponse) >= {
        "summary",
        "details",
        "status_text",
        "sandbox_diagnostics",
    }


def test_system_diagnostics_contracts() -> None:
    assert _property_fields(MainAgentRoutingDiagnostics) >= {
        "model_route_resolutions",
        "latest_model_route",
    }
    assert _property_fields(ModelRouteDiagnostics) >= {
        "route_intent",
        "selected_provider_id",
        "selected_model",
        "bootstrap_selection_reason",
        "candidate_count",
        "candidates",
    }
    assert _property_fields(ModelRouteCandidateDiagnostics) >= {
        "provider_id",
        "model",
        "mapping_mode",
        "supports_tools",
        "supports_thinking",
    }


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
