"""Contract tests for interface-layer DTO stability."""

from __future__ import annotations

from mini_agent.interfaces.agent import (
    MainAgentChatRequest,
    MainAgentChatResponse,
    MainAgentDefaultSessionRequest,
    MainAgentRunApprovalWait,
    MainAgentRunCheckpoint,
    MainAgentRunApprovalRequest,
    MainAgentRunCancelRequest,
    MainAgentRunInterruptRequest,
    MainAgentRunResumeRequest,
    MainAgentRunSummary,
    MainAgentWorkspaceRuntimeSummary,
    MainAgentWorkspaceSummary,
    MainAgentWorkspaceSwitchRequest,
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
    MainAgentSessionShareRequest,
    MainAgentSessionSkillRequest,
    MainAgentSessionSkillResponse,
)
from mini_agent.interfaces.channel import ChannelMessageRequest, ChannelMessageResponse
from mini_agent.interfaces.common import ApiEnvelope
from mini_agent.interfaces.model import (
    MainAgentModelBindingDiagnostics,
    MainAgentModelBindingRecord,
    MainAgentModelBindingRequest,
    MainAgentModelBindingSummary,
    MainAgentModelCandidateListResponse,
    MainAgentModelCandidateProviderSummary,
    MainAgentModelCandidateSummary,
    MainAgentModelCapabilities,
)
from mini_agent.interfaces.ops import StudioProviderListResponse, StudioProviderSummary
from mini_agent.interfaces.surface_payload_adapter import (
    surface_payload_from_dto,
    surface_payload_list_from_dtos,
)
from mini_agent.interfaces.system import (
    MainAgentRuntimeDiagnostics,
    MainAgentRoutingDiagnostics,
    ModelRouteCandidateDiagnostics,
    ModelRouteDiagnostics,
    SystemHealthResponse,
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


def test_main_agent_workspace_contracts() -> None:
    assert _required_fields(MainAgentWorkspaceSummary) == {
        "workspace_id",
        "workspace_dir",
    }
    assert _property_fields(MainAgentWorkspaceSummary) == {
        "workspace_id",
        "workspace_dir",
        "title",
        "default",
        "kind",
        "session_count",
        "default_session_count",
        "shared_session_count",
        "busy_session_count",
        "last_updated_at",
        "active",
        "switched",
    }
    assert _property_fields(MainAgentWorkspaceRuntimeSummary) >= {
        "runtime_policy",
        "runtime",
        "runtime_error",
    }
    assert _required_fields(MainAgentWorkspaceSwitchRequest) == {"workspace_id"}


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
        "workspace_runtime_snapshot",
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


def test_main_agent_run_contracts() -> None:
    assert _required_fields(MainAgentRunApprovalWait) == {
        "wait_id",
        "run_id",
        "session_id",
        "tool_name",
        "tool_arguments_summary",
        "wait_state",
    }
    assert _property_fields(MainAgentRunApprovalWait) >= {
        "workspace_id",
        "approval_token",
        "approval_kind",
        "policy_reason",
        "cache_key",
        "can_escalate",
        "decision_result",
        "created_at",
        "resolved_at",
        "invalidated_reason",
    }
    assert _required_fields(MainAgentRunCheckpoint) == {
        "checkpoint_id",
        "kind",
    }
    assert _property_fields(MainAgentRunCheckpoint) >= {
        "source",
        "created_at",
        "workspace_dir",
        "runtime_mode",
        "access_scope",
        "mutation_count",
    }
    assert _required_fields(MainAgentRunSummary) == {
        "run_id",
        "session_id",
        "status",
        "phase",
    }
    assert _property_fields(MainAgentRunSummary) >= {
        "busy",
        "waiting_on_approval",
        "active_surface",
        "channel_type",
        "conversation_id",
        "sender_id",
        "running_state",
        "control_mode",
        "interrupt_requested",
        "cancel_requested",
        "resumable",
        "active_wait_id",
        "approval_wait",
        "checkpoint",
    }
    assert _property_fields(MainAgentRunResumeRequest) == {
        "resume_token",
        "surface",
        "channel_type",
        "conversation_id",
        "sender_id",
    }
    assert _property_fields(MainAgentRunInterruptRequest) == {
        "reason",
        "surface",
        "channel_type",
        "conversation_id",
        "sender_id",
    }
    assert _property_fields(MainAgentRunCancelRequest) == {
        "reason",
        "surface",
        "channel_type",
        "conversation_id",
        "sender_id",
    }
    assert _required_fields(MainAgentRunApprovalRequest) == {"approved"}
    assert _property_fields(MainAgentRunApprovalRequest) == {
        "approved",
        "token",
        "reason",
        "surface",
        "channel_type",
        "conversation_id",
        "sender_id",
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


def test_main_agent_model_contracts() -> None:
    assert _required_fields(MainAgentModelBindingRequest) == {"provider_id", "model_id"}
    assert _property_fields(MainAgentModelBindingRequest) == {
        "agent_id",
        "provider_source",
        "provider_id",
        "model_id",
    }
    assert _required_fields(MainAgentModelCandidateSummary) == {
        "model_id",
        "display_name",
        "is_default",
    }
    assert _property_fields(MainAgentModelCandidateSummary) >= {
        "is_current_binding",
        "context_window",
        "supports_tools",
        "supports_thinking",
    }
    assert _required_fields(MainAgentModelCandidateProviderSummary) == {
        "source",
        "provider_id",
        "provider_name",
        "api_type",
        "api_base",
    }
    assert _property_fields(MainAgentModelCandidateProviderSummary) >= {
        "models",
        "default_model_id",
        "enabled",
        "priority",
    }
    assert _property_fields(MainAgentModelCandidateListResponse) == {"items"}
    assert _required_fields(MainAgentModelBindingRecord) == {
        "agent_id",
        "provider_source",
        "provider_id",
        "model_id",
        "binding_kind",
    }
    assert _required_fields(MainAgentModelBindingSummary) == {
        "agent_id",
        "binding_kind",
    }
    assert _property_fields(MainAgentModelBindingSummary) >= {
        "provider_source",
        "provider_id",
        "model_id",
        "switch_generation",
        "supports_tools",
        "supports_thinking",
    }
    assert _property_fields(MainAgentModelCapabilities) >= {
        "agent_id",
        "binding_kind",
        "provider_source",
        "provider_id",
        "model_id",
        "supports_tools",
        "supports_thinking",
    }
    assert _required_fields(MainAgentModelBindingDiagnostics) == {
        "current_binding",
    }
    assert _property_fields(MainAgentModelBindingDiagnostics) >= {
        "agent_id",
        "configured_binding",
        "configured_binding_error",
        "latest_route",
    }
def test_api_envelope_contract() -> None:
    envelope = ApiEnvelope[dict](ok=True, data={"status": "ok"}, error=None)
    payload = envelope.model_dump()
    assert set(payload.keys()) == {"ok", "data", "error"}


def test_surface_payload_from_dto_preserves_nested_model_candidate_shape() -> None:
    payload = surface_payload_from_dto(
        MainAgentModelCandidateListResponse(
            items=[
                MainAgentModelCandidateProviderSummary(
                    source="preset",
                    provider_id="openai",
                    provider_name="OpenAI",
                    api_type="openai",
                    api_base="https://api.openai.com/v1",
                    default_model_id="gpt-5.4",
                    models=[
                        MainAgentModelCandidateSummary(
                            model_id="gpt-5.4",
                            display_name="GPT-5.4",
                            is_default=True,
                            is_current_binding=True,
                        )
                    ],
                )
            ]
        )
    )

    assert payload == {
        "items": [
            {
                "source": "preset",
                "provider_id": "openai",
                "provider_name": "OpenAI",
                "api_type": "openai",
                "api_base": "https://api.openai.com/v1",
                "provider_family": None,
                "provider_variant": None,
                "default_model_id": "gpt-5.4",
                "default_model_strategy": None,
                "default_model_confidence": None,
                "models": [
                    {
                        "model_id": "gpt-5.4",
                        "display_name": "GPT-5.4",
                        "is_default": True,
                        "is_current_binding": True,
                        "model_role": None,
                        "context_window": None,
                        "learned_token_limit": None,
                        "token_limit": None,
                        "supports_tools": None,
                        "supports_tools_truth": None,
                        "supports_tools_confidence": None,
                        "supports_tools_source": None,
                        "supports_thinking": None,
                        "supports_thinking_truth": None,
                        "supports_thinking_confidence": None,
                        "supports_thinking_source": None,
                        "discovered_at": None,
                        "discovery_source": None,
                        "discovery_confidence": None,
                    }
                ],
                "enabled": True,
                "priority": 0,
            }
        ]
    }


def test_surface_payload_list_from_dtos_projects_workspace_summaries() -> None:
    payloads = surface_payload_list_from_dtos(
        [
            MainAgentWorkspaceSummary(
                workspace_id="ws-1",
                workspace_dir="D:/file/Mini-Agent",
                title="Default Workspace",
                default=True,
                active=True,
            )
        ]
    )

    assert payloads == [
        {
            "workspace_id": "ws-1",
            "workspace_dir": "D:/file/Mini-Agent",
            "title": "Default Workspace",
            "default": True,
            "kind": None,
            "session_count": 0,
            "default_session_count": 0,
            "shared_session_count": 0,
            "busy_session_count": 0,
            "last_updated_at": None,
            "active": True,
            "switched": False,
        }
    ]


def test_surface_payload_from_dto_preserves_session_detail_recent_messages() -> None:
    payload = surface_payload_from_dto(
        MainAgentSessionDetail(
            session_id="sess-1",
            workspace_dir="D:/file/Mini-Agent",
            created_at="2026-04-18T08:00:00+00:00",
            updated_at="2026-04-18T08:00:01+00:00",
            message_count=1,
            origin_surface="desktop",
            active_surface="desktop",
            reply_enabled=True,
            recent_messages=[
                MainAgentSessionMessage(
                    index=1,
                    role="user",
                    content="hello",
                    surface="desktop",
                    created_at="2026-04-18T08:00:01+00:00",
                )
            ],
        )
    )

    assert payload["session_id"] == "sess-1"
    assert payload["recent_messages"] == [
        {
            "index": 1,
            "role": "user",
            "content": "hello",
            "surface": "desktop",
            "created_at": "2026-04-18T08:00:01+00:00",
            "channel_type": None,
            "conversation_id": None,
            "sender_id": None,
            "metadata": None,
        }
    ]


def test_surface_payload_from_dto_preserves_provider_list_items() -> None:
    payload = surface_payload_from_dto(
        StudioProviderListResponse(
            catalog_path="D:/file/Mini-Agent/providers.json",
            provider_count=1,
            items=[
                StudioProviderSummary(
                    id="ollama-local",
                    name="Ollama Local",
                    api_type="openai",
                    api_base="http://127.0.0.1:11434/v1",
                    api_key_masked="",
                    models=["qwen3.5:9b"],
                    enabled=True,
                    priority=10,
                    timeout=45,
                    headers={},
                    catalog_path="D:/file/Mini-Agent/providers.json",
                    health_status="healthy",
                    breaker_state="closed",
                    selected_count=0,
                    error_rate=0.0,
                    consecutive_failures=0,
                )
            ],
        )
    )

    assert payload["provider_count"] == 1
    assert payload["items"] == [
        {
            "id": "ollama-local",
            "name": "Ollama Local",
            "api_type": "openai",
            "api_base": "http://127.0.0.1:11434/v1",
            "api_key_masked": "",
            "models": ["qwen3.5:9b"],
            "model_display_names": {},
            "enabled": True,
            "priority": 10,
            "timeout": 45,
            "headers": {},
            "catalog_path": "D:/file/Mini-Agent/providers.json",
            "health_status": "healthy",
            "breaker_state": "closed",
            "selected_count": 0,
            "error_rate": 0.0,
            "consecutive_failures": 0,
        }
    ]


def test_surface_payload_from_dto_preserves_system_health_runtime_snapshot() -> None:
    payload = surface_payload_from_dto(
        SystemHealthResponse(
            status="ok",
            now_utc="2026-04-18T08:00:00+00:00",
            workspace_root="D:/file/Mini-Agent",
            runtime=MainAgentRuntimeDiagnostics(
                mode="single_main",
                active_sessions=2,
                max_active_sessions=8,
                available_session_slots=6,
                reserved_team_slots=1,
                workspace_application_required=True,
            ),
        )
    )

    assert payload == {
        "status": "ok",
        "now_utc": "2026-04-18T08:00:00+00:00",
        "workspace_root": "D:/file/Mini-Agent",
        "runtime": {
            "mode": "single_main",
            "active_sessions": 2,
            "max_active_sessions": 8,
            "available_session_slots": 6,
            "reserved_team_slots": 1,
            "workspace_application_required": True,
            "team_saturation_rejections": 0,
            "team_workspace_conflict_rejections": 0,
            "lifecycle_auto_resets": 0,
            "session_reset_mode": "none",
            "session_idle_seconds": 1800,
            "main_workspace_dir": None,
        },
    }
