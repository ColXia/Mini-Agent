"""Tests for Agent Studio API v1 contract envelope routes."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from fastapi import HTTPException
from fastapi.testclient import TestClient
from uuid import uuid4

import apps.agent_studio_gateway.main as gateway_main
from apps.agent_studio_gateway.main import app
from mini_agent.application.channel_novel_action_handler import ChannelNovelActionHandler
from mini_agent.application.use_cases import ChannelIngressUseCases
from mini_agent.interfaces import (
    MainAgentChatRequest,
    MainAgentChatResponse,
    MainAgentModelBindingDiagnostics,
    MainAgentModelBindingSummary,
    MainAgentModelCandidateListResponse,
    MainAgentModelCapabilities,
    MainAgentSessionApprovalResponse,
    MainAgentSessionContextResponse,
    MainAgentSessionDetail,
    MainAgentSessionControlResponse,
    MainAgentSessionMemoryResponse,
    MainAgentSessionMessage,
    MainAgentSessionModelSelectionResponse,
    MainAgentSessionMutationResponse,
    MainAgentSessionSkillResponse,
    MainAgentSessionSummary,
)
from mini_agent.session.binding import ConversationBindingStore
from mini_agent.session.conversation_binding_service import ConversationBindingService


def test_gateway_root_reports_removed_browser_surfaces() -> None:
    with TestClient(app) as client:
        response = client.get("/")
        assert response.status_code == 200
        payload = response.json()
        assert payload["service"] == "mini-agent-gateway"
        assert payload["entrances"] == ["cli", "tui", "desktop", "remote"]
        assert payload["removed_surfaces"] == ["webui", "openwebui"]


def test_v1_system_health_envelope() -> None:
    with TestClient(app) as client:
        response = client.get("/api/v1/system/health")
        assert response.status_code == 200
        payload = response.json()
        assert payload["ok"] is True
        assert payload["error"] is None
        assert payload["data"]["status"] == "ok"
        assert payload["data"]["workspace_root"]
        assert payload["data"]["now_utc"]
        runtime = payload["data"]["runtime"]
        assert runtime["mode"] in {"single_main", "team"}
        assert runtime["active_sessions"] >= 0
        assert runtime["max_active_sessions"] >= 1
        assert runtime["available_session_slots"] >= 0
        assert runtime["reserved_team_slots"] >= 1
        assert runtime["team_saturation_rejections"] >= 0
        assert runtime["team_workspace_conflict_rejections"] >= 0
        assert isinstance(runtime["workspace_application_required"], bool)


def test_knowledge_base_health_route_is_exposed() -> None:
    with TestClient(app) as client:
        response = client.get("/api/knowledge-base/health")
        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] == "ok"
        assert payload["service"] == "knowledge-base"


def test_memory_manager_health_route_is_exposed() -> None:
    with TestClient(app) as client:
        response = client.get("/api/memory/health")
        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] == "ok"
        assert payload["service"] == "memory-manager"


def test_memory_manager_summary_route_is_exposed(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("MINI_AGENT_MEMORY_ROOT", str(tmp_path))

    with TestClient(app) as client:
        append = client.post(
            "/api/memory/append",
            json={
                "content": "remember the active memory-core slice",
                "category": "plan",
                "scope": "both",
            },
        )
        assert append.status_code == 200

        response = client.get("/api/memory/summary")
        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] == "ok"
        assert payload["notes_count"] >= 1
        assert "plan" in payload["categories"]


def test_v1_agent_chat_dry_run_envelope() -> None:
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/agent/chat",
            json={
                "message": "ping main agent",
                "dry_run": True,
            },
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["ok"] is True
        assert payload["error"] is None

        data = payload["data"]
        assert data["session_id"] == "dry-run-session"
        assert data["message_count"] == 1
        assert data["token_usage"] == 0
        assert "Received task: ping main agent" in data["reply"]


def test_v1_channel_message_dry_run_envelope() -> None:
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/channel/message",
            json={
                "channel_type": "qq",
                "conversation_id": "group:smoke",
                "sender_id": "user-1",
                "message": "ping channel",
                "dry_run": True,
            },
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["ok"] is True
        assert payload["error"] is None

        data = payload["data"]
        assert data["session_id"] == "dry-run-session"
        assert data["message_count"] == 1
        assert data["token_usage"] == 0
        assert "Received task: ping channel" in data["reply"]


def test_v1_channel_message_novel_action_prefix_dispatch() -> None:
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/channel/message",
            json={
                "channel_type": "qq",
                "conversation_id": "dm:demo",
                "message": "/novel config",
                "workspace_dir": ".",
                "dry_run": True,
            },
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["ok"] is True
        assert payload["error"] is None
        data = payload["data"]
        assert data["session_id"].startswith("novel-action-")
        assert data["token_usage"] == 0
        assert "\"kind\": \"novel_action\"" in data["reply"]
        assert "\"action\": \"config\"" in data["reply"]


def test_v1_channel_message_novel_action_invalid_json_rejected() -> None:
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/channel/message",
            json={
                "channel_type": "qq",
                "conversation_id": "group:demo",
                "message": "/novel config {bad-json}",
                "workspace_dir": ".",
            },
        )
        assert response.status_code == 400
        payload = response.json()
        assert "Invalid novel action JSON params" in payload["detail"]


def test_v1_channel_message_novel_action_metadata_dispatch() -> None:
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/channel/message",
            json={
                "channel_type": "qq",
                "conversation_id": "group:demo2",
                "message": "ignored when metadata carries action",
                "metadata": {
                    "novel_action": {
                        "action": "config",
                        "params": {"project_dir": "channel-novel-meta"},
                    }
                },
            },
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["ok"] is True
        assert "\"action\": \"config\"" in payload["data"]["reply"]
        assert "channel-novel-meta" in payload["data"]["reply"]


def test_v1_channel_message_reuses_central_binding_without_explicit_session_id(tmp_path: Path, monkeypatch) -> None:
    requests: list[MainAgentChatRequest] = []

    async def _run_main_agent_chat(request: MainAgentChatRequest) -> MainAgentChatResponse:
        requests.append(request)
        return MainAgentChatResponse(
            session_id="sess-central",
            reply=f"echo:{request.message}",
            message_count=len(requests),
            token_usage=5,
            workspace_dir=str(tmp_path / "workspace"),
            updated_at=datetime.now(timezone.utc).isoformat(),
        )

    class _UnusedNovelUseCases:
        async def get_config(self, project_dir: str | None = None) -> dict[str, object]:
            _ = project_dir
            raise AssertionError("novel actions are outside this test scope")

    monkeypatch.setattr(
        gateway_main.GATEWAY_COMPOSITION,
        "_channel_ingress_use_cases",
        ChannelIngressUseCases(
            run_main_agent_chat=_run_main_agent_chat,
            novel_action_handler=ChannelNovelActionHandler(
                novel_use_cases=_UnusedNovelUseCases(),
                resolve_workspace_dir=lambda value: Path(value or ".").resolve(),
                to_utc_iso=lambda value: value.astimezone(timezone.utc).isoformat(),
            ),
            conversation_binding=ConversationBindingService(
                binding_store=ConversationBindingStore(tmp_path / "conversation-bindings.json"),
            ),
        ),
    )

    with TestClient(app) as client:
        first = client.post(
            "/api/v1/channel/message",
            json={
                "channel_type": "qq",
                "conversation_id": "group:central",
                "sender_id": "user-1",
                "message": "hello",
                "workspace_dir": str(tmp_path / "workspace"),
            },
        )
        assert first.status_code == 200

        second = client.post(
            "/api/v1/channel/message",
            json={
                "channel_type": "qq",
                "conversation_id": "group:central",
                "sender_id": "user-1",
                "message": "continue",
                "workspace_dir": str(tmp_path / "workspace"),
            },
        )
        assert second.status_code == 200

    assert len(requests) == 2
    assert requests[0].session_id is None
    assert requests[1].session_id == "sess-central"


def test_v1_agent_sessions_envelope_empty() -> None:
    with TestClient(app) as client:
        response = client.get("/api/v1/agent/sessions")
        assert response.status_code == 200
        payload = response.json()
        assert payload["ok"] is True
        assert payload["error"] is None
        assert isinstance(payload["data"], list)


def test_v1_agent_workspace_routes(monkeypatch) -> None:
    class _WorkspaceServiceStub:
        async def list_workspaces(self):
            return [
                {
                    "workspace_id": "ws-default",
                    "workspace_dir": "D:/file/Mini-Agent",
                    "title": "Default Workspace",
                    "default": True,
                    "active": True,
                }
            ]

        async def get_active_workspace(self):
            return {
                "workspace_id": "ws-default",
                "workspace_dir": "D:/file/Mini-Agent",
                "title": "Default Workspace",
                "default": True,
                "active": True,
            }

        async def get_workspace(self, workspace_id: str):
            assert workspace_id == "D:/file/Mini-Agent"
            return {
                "workspace_id": "ws-default",
                "workspace_dir": workspace_id,
                "title": "Resolved Workspace",
                "default": True,
                "active": True,
            }

        async def switch_workspace(self, workspace_id: str):
            assert workspace_id == "D:/file/Mini-Agent"
            return {
                "workspace_id": "ws-default",
                "workspace_dir": workspace_id,
                "title": "Switched Workspace",
                "default": True,
                "active": True,
                "switched": True,
            }

        async def get_workspace_runtime_summary(self, *, workspace_id: str | None = None):
            assert workspace_id == "D:/file/Mini-Agent"
            return {
                "workspace_id": "ws-default",
                "workspace_dir": workspace_id,
                "title": "Runtime Workspace",
                "default": True,
                "active": True,
                "runtime_policy": {"mode": "single_main"},
                "runtime": {"mode": "direct", "scope": "workspace_only"},
            }

    monkeypatch.setattr(gateway_main.GATEWAY_COMPOSITION, "_workspace_service", _WorkspaceServiceStub())

    with TestClient(app) as client:
        list_response = client.get("/api/v1/agent/workspaces")
        assert list_response.status_code == 200
        list_payload = list_response.json()
        assert list_payload["ok"] is True
        assert list_payload["data"][0]["workspace_id"] == "ws-default"
        assert list_payload["data"][0]["active"] is True

        active_response = client.get("/api/v1/agent/workspaces/active")
        assert active_response.status_code == 200
        active_payload = active_response.json()
        assert active_payload["ok"] is True
        assert active_payload["data"]["default"] is True

        resolve_response = client.get(
            "/api/v1/agent/workspaces/resolve",
            params={"workspace_id": "D:/file/Mini-Agent"},
        )
        assert resolve_response.status_code == 200
        resolve_payload = resolve_response.json()
        assert resolve_payload["ok"] is True
        assert resolve_payload["data"]["workspace_dir"] == "D:/file/Mini-Agent"

        switch_response = client.post(
            "/api/v1/agent/workspaces/switch",
            json={"workspace_id": "D:/file/Mini-Agent"},
        )
        assert switch_response.status_code == 200
        switch_payload = switch_response.json()
        assert switch_payload["ok"] is True
        assert switch_payload["data"]["switched"] is True

        runtime_response = client.get(
            "/api/v1/agent/workspaces/runtime",
            params={"workspace_id": "D:/file/Mini-Agent"},
        )
        assert runtime_response.status_code == 200
        runtime_payload = runtime_response.json()
        assert runtime_payload["ok"] is True
        assert runtime_payload["data"]["runtime_policy"]["mode"] == "single_main"
        assert runtime_payload["data"]["runtime"]["scope"] == "workspace_only"


def test_v1_agent_workspace_switch_propagates_conflict(monkeypatch) -> None:
    class _WorkspaceServiceStub:
        async def switch_workspace(self, workspace_id: str):
            raise HTTPException(
                status_code=409,
                detail=f"single-main workspace only: {workspace_id}",
            )

    monkeypatch.setattr(gateway_main.GATEWAY_COMPOSITION, "_workspace_service", _WorkspaceServiceStub())

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/agent/workspaces/switch",
            json={"workspace_id": "D:/file/Mini-Agent/workspace-b"},
        )
        assert response.status_code == 409
        assert "single-main workspace only" in response.json()["detail"]


def test_v1_agent_models_envelope(monkeypatch) -> None:
    class _OpsStub:
        def list_models(self, *, catalog_path=None):
            assert catalog_path is None
            return {
                "items": [
                    {
                        "source": "preset",
                        "provider_id": "openai",
                        "provider_name": "OpenAI",
                        "api_type": "openai",
                        "api_base": "https://api.openai.com/v1",
                        "default_model_id": "gpt-5.4",
                        "models": [
                            {
                                "model_id": "gpt-5.4",
                                "display_name": "GPT-5.4",
                                "is_default": True,
                                "context_window": 1_050_000,
                            }
                        ],
                        "enabled": True,
                        "priority": 0,
                    }
                ]
            }

    monkeypatch.setattr(gateway_main, "GATEWAY_PROVIDER_OPERATIONS_USE_CASES", _OpsStub())

    with TestClient(app) as client:
        response = client.get("/api/v1/agent/models")
        assert response.status_code == 200
        payload = response.json()
        assert payload["ok"] is True
        assert payload["data"]["items"][0]["provider_id"] == "openai"
        assert payload["data"]["items"][0]["models"][0]["model_id"] == "gpt-5.4"
        assert payload["data"]["items"][0]["models"][0]["context_window"] == 1_050_000


def test_v1_agent_model_binding_routes_use_model_service(monkeypatch) -> None:
    class _ModelServiceStub:
        async def list_model_candidates(self):
            return MainAgentModelCandidateListResponse(
                items=[
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
            )

        async def get_current_model_binding(self, agent_id: str | None = None):
            assert agent_id == "main-agent"
            return MainAgentModelBindingSummary(
                agent_id="main-agent",
                binding_kind="explicit",
                provider_source="custom",
                provider_id="maas",
                model_id="astron-code-latest",
                switch_generation=2,
            )

        async def set_agent_model_binding(
            self,
            *,
            agent_id: str | None = None,
            provider_source: str | None = None,
            provider_id: str | None = None,
            model_id: str | None = None,
        ):
            assert agent_id == "main-agent"
            assert provider_source == "custom"
            assert provider_id == "maas"
            assert model_id == "astron-code-stable"
            return MainAgentModelBindingSummary(
                agent_id="main-agent",
                binding_kind="explicit",
                provider_source="custom",
                provider_id="maas",
                model_id="astron-code-stable",
                switch_generation=3,
            )

        async def get_current_model_capabilities(self, agent_id: str | None = None):
            assert agent_id == "main-agent"
            return MainAgentModelCapabilities(
                agent_id="main-agent",
                binding_kind="explicit",
                provider_source="custom",
                provider_id="maas",
                model_id="astron-code-latest",
                supports_tools=True,
                supports_thinking=True,
            )

        async def get_model_binding_diagnostics(self, agent_id: str | None = None):
            assert agent_id == "main-agent"
            return MainAgentModelBindingDiagnostics(
                agent_id="main-agent",
                current_binding=MainAgentModelBindingSummary(
                    agent_id="main-agent",
                    binding_kind="explicit",
                    provider_source="custom",
                    provider_id="maas",
                    model_id="astron-code-latest",
                    switch_generation=2,
                ),
                latest_route={
                    "selected_provider_id": "maas",
                    "selected_model": "astron-code-latest",
                    "candidate_count": 1,
                    "candidates": [],
                },
            )

    monkeypatch.setattr(gateway_main.GATEWAY_COMPOSITION, "_model_service", _ModelServiceStub())

    with TestClient(app) as client:
        candidates = client.get("/api/v1/agent/model/candidates")
        assert candidates.status_code == 200
        candidates_payload = candidates.json()
        assert candidates_payload["ok"] is True
        assert candidates_payload["data"]["items"][0]["models"][0]["is_current_binding"] is True

        binding = client.get("/api/v1/agent/model/binding", params={"agent_id": "main-agent"})
        assert binding.status_code == 200
        binding_payload = binding.json()
        assert binding_payload["ok"] is True
        assert binding_payload["data"]["model_id"] == "astron-code-latest"

        updated = client.put(
            "/api/v1/agent/model/binding",
            json={
                "agent_id": "main-agent",
                "provider_source": "custom",
                "provider_id": "maas",
                "model_id": "astron-code-stable",
            },
        )
        assert updated.status_code == 200
        updated_payload = updated.json()
        assert updated_payload["ok"] is True
        assert updated_payload["data"]["switch_generation"] == 3

        capabilities = client.get("/api/v1/agent/model/capabilities", params={"agent_id": "main-agent"})
        assert capabilities.status_code == 200
        capabilities_payload = capabilities.json()
        assert capabilities_payload["ok"] is True
        assert capabilities_payload["data"]["supports_tools"] is True

        diagnostics = client.get("/api/v1/agent/model/diagnostics", params={"agent_id": "main-agent"})
        assert diagnostics.status_code == 200
        diagnostics_payload = diagnostics.json()
        assert diagnostics_payload["ok"] is True
        assert diagnostics_payload["data"]["latest_route"]["selected_model"] == "astron-code-latest"


def test_v1_agent_session_detail_and_operation_routes(monkeypatch) -> None:
    class _SurfaceServiceStub:
        async def ensure_default_session(self, request):
            assert request.workspace_dir == "D:/file/Mini-Agent"
            assert request.surface == "desktop"
            return MainAgentSessionDetail(
                session_id="default",
                workspace_dir="D:/file/Mini-Agent",
                created_at="2026-04-08T00:00:00+00:00",
                updated_at="2026-04-08T00:01:00+00:00",
                title="Session 1",
                message_count=0,
                origin_surface="desktop",
                active_surface="desktop",
                is_default=True,
                reply_enabled=False,
                context_policy={},
                last_prepared_context={},
                prepared_context_diagnostics={},
                recent_messages=[],
            )

        async def get_session_detail(self, session_id: str, recent_limit: int = 50):
            assert session_id == "sess-qq"
            assert recent_limit == 5
            return MainAgentSessionDetail(
                session_id="sess-qq",
                workspace_dir="D:/file/Mini-Agent",
                created_at="2026-04-08T00:00:00+00:00",
                updated_at="2026-04-08T00:01:00+00:00",
                message_count=4,
                origin_surface="qq",
                active_surface="qq",
                reply_enabled=True,
                channel_type="qq",
                conversation_id="group:demo",
                sender_id="user-1",
                context_policy={"include_sources": [], "exclude_sources": [], "max_items": 2, "max_total_chars": 2400, "max_items_per_source": 1, "active": True},
                last_prepared_context={"item_count": 1, "sources": ["knowledge_base"], "items": []},
                prepared_context_diagnostics={"turn_count": 3},
                memory_diagnostics={
                    "global_profile_fact_count": 2,
                    "consolidated": {"needs_refresh": False},
                    "runtime_task_memory": {"session_count": 1, "shared_count": 0},
                },
                recent_messages=[
                    MainAgentSessionMessage(
                        index=3,
                        role="user",
                        content="hello",
                        surface="qq",
                        created_at="2026-04-08T00:00:30+00:00",
                        channel_type="qq",
                        conversation_id="group:demo",
                        sender_id="user-1",
                    ),
                    MainAgentSessionMessage(
                        index=4,
                        role="assistant",
                        content="mock:hello",
                        surface="qq",
                        created_at="2026-04-08T00:00:31+00:00",
                        channel_type="qq",
                        conversation_id="group:demo",
                        sender_id="user-1",
                    ),
                ],
            )

        async def get_session_messages(self, session_id: str, limit: int = 10):
            assert session_id == "sess-qq"
            assert limit == 2
            return [
                MainAgentSessionMessage(
                    index=3,
                    role="user",
                    content="hello",
                    surface="qq",
                    created_at="2026-04-08T00:00:30+00:00",
                ),
                MainAgentSessionMessage(
                    index=4,
                    role="assistant",
                    content="mock:hello",
                    surface="qq",
                    created_at="2026-04-08T00:00:31+00:00",
                ),
            ]

    class _AgentServiceStub:
        async def cancel_session_run(
            self,
            session_id: str,
            *,
            reason: str | None = None,
            source: str | None = None,
            surface: str | None = None,
            channel_type: str | None = None,
            conversation_id: str | None = None,
            sender_id: str | None = None,
        ):
            assert session_id == "sess-qq"
            assert reason == "stop now"
            assert source == "qq"
            assert surface == "qq"
            assert channel_type == "qq"
            assert conversation_id == "group:demo"
            assert sender_id == "user-1"
            return MainAgentSessionMutationResponse(
                status="cancel_requested",
                session_id="sess-qq",
                active_surface="qq",
            )

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
        ):
            assert session_id == "sess-qq"
            assert action == "compact"
            assert reason == "trim history"
            assert surface == "qq"
            assert channel_type == "qq"
            assert conversation_id == "group:demo"
            assert sender_id == "user-1"
            return MainAgentSessionControlResponse(
                status="controlled",
                session_id="sess-qq",
                action="compact",
                applied=True,
                active_surface="qq",
                reason="trim history",
                message_count_before=12,
                message_count_after=6,
                token_count_before=480,
                token_count_after=210,
                stats={
                    "masked_messages": 1,
                    "snipped_messages": 2,
                    "merged_messages": 0,
                },
            )

        async def update_session_context(
            self,
            session_id: str,
            *,
            action: str,
            sources: list[str] | None = None,
            surface: str | None = None,
            channel_type: str | None = None,
            conversation_id: str | None = None,
            sender_id: str | None = None,
            max_items: int | None = None,
            max_total_chars: int | None = None,
            max_items_per_source: int | None = None,
        ):
            assert session_id == "sess-qq"
            assert action == "include"
            assert sources == ["knowledge_base", "workspace_memory"]
            assert surface == "qq"
            assert channel_type == "qq"
            assert conversation_id == "group:demo"
            assert sender_id == "user-1"
            assert max_items is None
            assert max_total_chars is None
            assert max_items_per_source is None
            return MainAgentSessionContextResponse(
                status="updated",
                session_id="sess-qq",
                action="include",
                active_surface="qq",
                context_policy={
                    "include_sources": ["knowledge_base", "workspace_memory"],
                    "exclude_sources": [],
                    "max_items": 4,
                    "max_total_chars": 2400,
                    "max_items_per_source": 1,
                    "active": True,
                },
            )

        async def manage_session_memory(
            self,
            session_id: str,
            *,
            action: str,
            detail_mode: str | None = None,
            surface: str | None = None,
            channel_type: str | None = None,
            conversation_id: str | None = None,
            sender_id: str | None = None,
            engram_id: str | None = None,
            content: str | None = None,
            query: str | None = None,
            day: str | None = None,
            export_format: str | None = None,
        ):
            assert session_id == "sess-qq"
            assert action == "show"
            assert detail_mode == "brief"
            assert surface == "qq"
            assert channel_type == "qq"
            assert conversation_id == "group:demo"
            assert sender_id == "user-1"
            assert engram_id is None
            assert content is None
            assert query is None
            assert day is None
            assert export_format is None
            return MainAgentSessionMemoryResponse(
                status="ok",
                session_id="sess-qq",
                action="show",
                active_surface="qq",
                memory_diagnostics={
                    "global_profile_fact_count": 2,
                    "consolidated": {"needs_refresh": False},
                    "runtime_task_memory": {"session_count": 1, "shared_count": 0},
                },
                result={
                    "summary": "cons fresh | rtm 1+0 | profile 2",
                    "details": "Memory Diagnostics\nSummary: cons fresh | rtm 1+0 | profile 2",
                },
            )

        async def manage_session_skills(
            self,
            session_id: str,
            *,
            action: str,
            query: str | None = None,
            surface: str | None = None,
            channel_type: str | None = None,
            conversation_id: str | None = None,
            sender_id: str | None = None,
            skill_name: str | None = None,
            path: str | None = None,
            mode: str | None = None,
        ):
            assert session_id == "sess-qq"
            assert action == "search"
            assert query == "foundry"
            assert surface == "qq"
            assert channel_type == "qq"
            assert conversation_id == "group:demo"
            assert sender_id == "user-1"
            assert skill_name is None
            assert path is None
            assert mode is None
            return MainAgentSessionSkillResponse(
                status="ok",
                session_id="sess-qq",
                action="search",
                active_surface="qq",
                result={
                    "summary": "1 match(es)",
                    "details": 'Skill matches for "foundry":\n- foundry-helper [workspace] ready\n  Foundry guidance.',
                    "query": "foundry",
                    "match_count": 1,
                },
            )

        async def approve_session_wait(
            self,
            session_id: str,
            *,
            token: str | None = None,
            source: str | None = None,
            surface: str | None = None,
            channel_type: str | None = None,
            conversation_id: str | None = None,
            sender_id: str | None = None,
            reason: str | None = None,
        ):
            assert session_id == "sess-qq"
            assert token == "approval-1"
            assert source == "qq"
            assert surface == "qq"
            assert channel_type == "qq"
            assert conversation_id == "group:demo"
            assert sender_id == "user-1"
            assert reason is None
            return MainAgentSessionApprovalResponse(
                status="resolved",
                session_id="sess-qq",
                token="approval-1",
                tool_name="shell",
                decision="approved",
                active_surface="qq",
            )

    class _ModelServiceStub:
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
            assert session_id == "sess-qq"
            assert provider_source == "preset"
            assert provider_id == "openai"
            assert model_id == "gpt-5.3"
            assert surface == "qq"
            assert channel_type == "qq"
            assert conversation_id == "group:demo"
            assert sender_id == "user-1"
            return MainAgentSessionModelSelectionResponse(
                status="selected",
                session_id="sess-qq",
                active_surface="qq",
                applied=True,
                queued=False,
                selected_model_source="preset",
                selected_provider_id="openai",
                selected_model_id="gpt-5.3",
            )

    monkeypatch.setattr(gateway_main.GATEWAY_COMPOSITION, "_surface_service", _SurfaceServiceStub())
    monkeypatch.setattr(gateway_main.GATEWAY_COMPOSITION, "_agent_service", _AgentServiceStub())
    monkeypatch.setattr(gateway_main.GATEWAY_COMPOSITION, "_model_service", _ModelServiceStub())

    with TestClient(app) as client:
        detail_response = client.get("/api/v1/agent/sessions/sess-qq", params={"recent_limit": 5})
        assert detail_response.status_code == 200
        detail_payload = detail_response.json()
        assert detail_payload["ok"] is True
        assert detail_payload["data"]["origin_surface"] == "qq"
        assert detail_payload["data"]["active_surface"] == "qq"
        assert detail_payload["data"]["context_policy"]["max_items"] == 2
        assert detail_payload["data"]["last_prepared_context"]["item_count"] == 1
        assert detail_payload["data"]["prepared_context_diagnostics"]["turn_count"] == 3
        assert len(detail_payload["data"]["recent_messages"]) == 2

        default_response = client.post(
            "/api/v1/agent/sessions/default",
            json={"workspace_dir": "D:/file/Mini-Agent", "surface": "desktop"},
        )
        assert default_response.status_code == 200
        default_payload = default_response.json()
        assert default_payload["ok"] is True
        assert default_payload["data"]["session_id"] == "default"
        assert default_payload["data"]["is_default"] is True

        message_response = client.get("/api/v1/agent/sessions/sess-qq/messages", params={"limit": 2})
        assert message_response.status_code == 200
        message_payload = message_response.json()
        assert message_payload["ok"] is True
        assert [item["role"] for item in message_payload["data"]] == ["user", "assistant"]

        cancel_response = client.post(
            "/api/v1/agent/sessions/sess-qq/cancel",
            json={
                "reason": "stop now",
                "surface": "qq",
                "channel_type": "qq",
                "conversation_id": "group:demo",
                "sender_id": "user-1",
            },
        )
        assert cancel_response.status_code == 200
        cancel_payload = cancel_response.json()
        assert cancel_payload["ok"] is True
        assert cancel_payload["data"]["status"] == "cancel_requested"
        assert cancel_payload["data"]["active_surface"] == "qq"

        control_response = client.post(
            "/api/v1/agent/sessions/sess-qq/control",
            json={
                "action": "compact",
                "reason": "trim history",
                "surface": "qq",
                "channel_type": "qq",
                "conversation_id": "group:demo",
                "sender_id": "user-1",
            },
        )
        assert control_response.status_code == 200
        control_payload = control_response.json()
        assert control_payload["ok"] is True
        assert control_payload["data"]["status"] == "controlled"
        assert control_payload["data"]["action"] == "compact"
        assert control_payload["data"]["message_count_before"] == 12
        assert control_payload["data"]["message_count_after"] == 6

        context_response = client.post(
            "/api/v1/agent/sessions/sess-qq/context",
            json={
                "action": "include",
                "sources": ["knowledge_base", "workspace_memory"],
                "surface": "qq",
                "channel_type": "qq",
                "conversation_id": "group:demo",
                "sender_id": "user-1",
            },
        )
        assert context_response.status_code == 200
        context_payload = context_response.json()
        assert context_payload["ok"] is True
        assert context_payload["data"]["status"] == "updated"
        assert context_payload["data"]["action"] == "include"
        assert context_payload["data"]["context_policy"]["include_sources"] == [
            "knowledge_base",
            "workspace_memory",
        ]

        memory_response = client.post(
            "/api/v1/agent/sessions/sess-qq/memory",
            json={
                "action": "show",
                "detail_mode": "brief",
                "surface": "qq",
                "channel_type": "qq",
                "conversation_id": "group:demo",
                "sender_id": "user-1",
            },
        )
        assert memory_response.status_code == 200
        memory_payload = memory_response.json()
        assert memory_payload["ok"] is True
        assert memory_payload["data"]["status"] == "ok"
        assert memory_payload["data"]["action"] == "show"
        assert memory_payload["data"]["result"]["summary"] == "cons fresh | rtm 1+0 | profile 2"
        assert "Memory Diagnostics" in memory_payload["data"]["result"]["details"]

        skill_response = client.post(
            "/api/v1/agent/sessions/sess-qq/skill",
            json={
                "action": "search",
                "query": "foundry",
                "surface": "qq",
                "channel_type": "qq",
                "conversation_id": "group:demo",
                "sender_id": "user-1",
            },
        )
        assert skill_response.status_code == 200
        skill_payload = skill_response.json()
        assert skill_payload["ok"] is True
        assert skill_payload["data"]["status"] == "ok"
        assert skill_payload["data"]["action"] == "search"
        assert skill_payload["data"]["result"]["match_count"] == 1
        assert "foundry-helper" in skill_payload["data"]["result"]["details"]

        model_response = client.post(
            "/api/v1/agent/sessions/sess-qq/model",
            json={
                "provider_source": "preset",
                "provider_id": "openai",
                "model_id": "gpt-5.3",
                "surface": "qq",
                "channel_type": "qq",
                "conversation_id": "group:demo",
                "sender_id": "user-1",
            },
        )
        assert model_response.status_code == 200
        model_payload = model_response.json()
        assert model_payload["ok"] is True
        assert model_payload["data"]["status"] == "selected"
        assert model_payload["data"]["selected_model_source"] == "preset"
        assert model_payload["data"]["selected_provider_id"] == "openai"
        assert model_payload["data"]["selected_model_id"] == "gpt-5.3"

        approval_response = client.post(
            "/api/v1/agent/sessions/sess-qq/approval",
            json={
                "approved": True,
                "token": "approval-1",
                "surface": "qq",
                "channel_type": "qq",
                "conversation_id": "group:demo",
                "sender_id": "user-1",
            },
        )
        assert approval_response.status_code == 200
        approval_payload = approval_response.json()
        assert approval_payload["ok"] is True
        assert approval_payload["data"]["decision"] == "approved"


def test_v1_runtime_session_create_share_rename_routes(monkeypatch) -> None:
    class _SurfaceServiceStub:
        async def list_sessions(self, *, workspace_dir=None, shared_only=False):
            assert workspace_dir == "."
            assert shared_only is True
            return [
                MainAgentSessionSummary(
                    session_id="sess-runtime-1",
                    workspace_dir="D:/file/Mini-Agent",
                    created_at="2026-04-11T00:00:00+00:00",
                    updated_at="2026-04-11T00:00:01+00:00",
                    title="Session 1",
                    message_count=0,
                    origin_surface="tui",
                    active_surface="tui",
                    shared=True,
                )
            ]

        async def create_session(self, request):
            assert request.workspace_dir == "."
            assert request.title == "Session 1"
            assert request.surface == "tui"
            assert request.shared is False
            return MainAgentSessionDetail(
                session_id="sess-runtime-1",
                workspace_dir="D:/file/Mini-Agent",
                created_at="2026-04-11T00:00:00+00:00",
                updated_at="2026-04-11T00:00:01+00:00",
                title="Session 1",
                message_count=0,
                origin_surface="tui",
                active_surface="tui",
                shared=False,
                recent_messages=[],
            )

    class _SessionTaskServiceStub:
        async def rename_session(self, session_id: str, request):
            assert session_id == "sess-runtime-1"
            assert request.title == "Focus Session"
            return MainAgentSessionMutationResponse(
                status="renamed",
                session_id=session_id,
                active_surface="tui",
                title="Focus Session",
                shared=False,
            )

        async def set_session_shared(self, session_id: str, request):
            assert session_id == "sess-runtime-1"
            assert request.shared is True
            return MainAgentSessionMutationResponse(
                status="shared",
                session_id=session_id,
                active_surface="tui",
                title="Focus Session",
                shared=True,
            )

    monkeypatch.setattr(gateway_main.GATEWAY_COMPOSITION, "_surface_service", _SurfaceServiceStub())
    monkeypatch.setattr(gateway_main.GATEWAY_COMPOSITION, "_session_task_service", _SessionTaskServiceStub())

    with TestClient(app) as client:
        list_response = client.get("/api/v1/agent/sessions", params={"workspace_dir": ".", "shared_only": True})
        assert list_response.status_code == 200
        list_payload = list_response.json()
        assert list_payload["ok"] is True
        assert list_payload["data"][0]["shared"] is True

        create_response = client.post(
            "/api/v1/agent/sessions",
            json={"workspace_dir": ".", "title": "Session 1", "surface": "tui", "shared": False},
        )
        assert create_response.status_code == 200
        create_payload = create_response.json()
        assert create_payload["ok"] is True
        assert create_payload["data"]["session_id"] == "sess-runtime-1"
        assert create_payload["data"]["shared"] is False

        rename_response = client.patch(
            "/api/v1/agent/sessions/sess-runtime-1",
            json={"title": "Focus Session"},
        )
        assert rename_response.status_code == 200
        rename_payload = rename_response.json()
        assert rename_payload["ok"] is True
        assert rename_payload["data"]["title"] == "Focus Session"

        share_response = client.post(
            "/api/v1/agent/sessions/sess-runtime-1/share",
            json={"shared": True},
        )
        assert share_response.status_code == 200
        share_payload = share_response.json()
        assert share_payload["ok"] is True
        assert share_payload["data"]["shared"] is True


def test_v1_main_agent_control_route_accepts_mcp_actions(monkeypatch) -> None:
    class _AgentServiceStub:
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
        ):
            assert session_id == "sess-qq"
            assert action == "mcp_list"
            assert reason is None
            assert surface == "tui"
            assert channel_type is None
            assert conversation_id is None
            assert sender_id is None
            return MainAgentSessionControlResponse(
                status="controlled",
                session_id="sess-qq",
                action="mcp_list",
                applied=False,
                active_surface="qq",
                stats={
                    "summary": "2 configured server(s) | 1 active",
                    "details": "MCP Status:\n- active 1\n- tools 2\n\nMCP Servers:\n- alpha [stdio] active | trusted",
                    "configured_total": 2,
                    "discoverable_total": 2,
                    "disabled_total": 0,
                    "active_total": 1,
                    "tool_total": 2,
                },
            )

    monkeypatch.setattr(gateway_main.GATEWAY_COMPOSITION, "_agent_service", _AgentServiceStub())

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/agent/sessions/sess-qq/control",
            json={
                "action": "mcp_list",
                "surface": "tui",
            },
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["ok"] is True
        assert payload["data"]["action"] == "mcp_list"
        assert payload["data"]["stats"]["summary"] == "2 configured server(s) | 1 active"
        assert "MCP Servers:" in payload["data"]["stats"]["details"]


def test_v1_main_agent_skill_mode_route_forwards_mode_field(monkeypatch) -> None:
    class _AgentServiceStub:
        async def manage_session_skills(
            self,
            session_id: str,
            *,
            action: str,
            mode: str | None = None,
            surface: str | None = None,
            channel_type: str | None = None,
            conversation_id: str | None = None,
            sender_id: str | None = None,
            skill_name: str | None = None,
            path: str | None = None,
            query: str | None = None,
        ):
            assert session_id == "sess-qq"
            assert action == "mode"
            assert mode == "allowlist"
            assert surface == "qq"
            assert channel_type == "qq"
            assert conversation_id == "group:demo"
            assert sender_id == "user-1"
            assert skill_name is None
            assert path is None
            assert query is None
            return MainAgentSessionSkillResponse(
                status="ok",
                session_id="sess-qq",
                action="mode",
                active_surface="qq",
                result={
                    "summary": "skill mode set to allowlist",
                    "details": "Workspace Skill Policy:\n- mode allowlist\n- active 0 / ready 1",
                    "policy": {
                        "mode": "allowlist",
                        "allowlist": [],
                        "denylist": [],
                    },
                },
            )

    monkeypatch.setattr(gateway_main.GATEWAY_COMPOSITION, "_agent_service", _AgentServiceStub())

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/agent/sessions/sess-qq/skill",
            json={
                "action": "mode",
                "mode": "allowlist",
                "surface": "qq",
                "channel_type": "qq",
                "conversation_id": "group:demo",
                "sender_id": "user-1",
            },
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["ok"] is True
        assert payload["data"]["action"] == "mode"
        assert payload["data"]["result"]["policy"]["mode"] == "allowlist"


def test_v1_main_agent_skill_install_route_forwards_path_field(monkeypatch) -> None:
    class _AgentServiceStub:
        async def manage_session_skills(
            self,
            session_id: str,
            *,
            action: str,
            path: str | None = None,
            surface: str | None = None,
            channel_type: str | None = None,
            conversation_id: str | None = None,
            sender_id: str | None = None,
            skill_name: str | None = None,
            query: str | None = None,
            mode: str | None = None,
        ):
            assert session_id == "sess-qq"
            assert action == "install"
            assert path == "C:/skills/repo-helper"
            assert surface == "qq"
            assert channel_type is None
            assert conversation_id is None
            assert sender_id is None
            assert skill_name is None
            assert query is None
            assert mode is None
            return MainAgentSessionSkillResponse(
                status="ok",
                session_id="sess-qq",
                action="install",
                active_surface="qq",
                result={
                    "summary": "installed repo-helper",
                    "details": "Installed Skill:\n- name repo-helper\n- ledger D:/file/Mini-Agent/.mini-agent/skill_sources.json",
                },
            )

    monkeypatch.setattr(gateway_main.GATEWAY_COMPOSITION, "_agent_service", _AgentServiceStub())

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/agent/sessions/sess-qq/skill",
            json={
                "action": "install",
                "path": "C:/skills/repo-helper",
                "surface": "qq",
            },
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["ok"] is True
        assert payload["data"]["action"] == "install"
        assert payload["data"]["result"]["summary"] == "installed repo-helper"


def test_v1_main_agent_skill_mode_invalid_returns_http_400(monkeypatch) -> None:
    class _AgentServiceStub:
        async def manage_session_skills(self, session_id: str, **kwargs):
            _ = (session_id, kwargs)
            raise HTTPException(status_code=400, detail="Unsupported skill policy mode: invalid-mode")

    monkeypatch.setattr(gateway_main.GATEWAY_COMPOSITION, "_agent_service", _AgentServiceStub())

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/agent/sessions/sess-qq/skill",
            json={
                "action": "mode",
                "mode": "invalid-mode",
                "surface": "qq",
                "channel_type": "qq",
                "conversation_id": "group:demo",
                "sender_id": "user-1",
            },
        )
        assert response.status_code == 400
        assert response.json()["detail"] == "Unsupported skill policy mode: invalid-mode"


def test_v1_agent_chat_stream_dry_run() -> None:
    with TestClient(app) as client:
        response = client.get(
            "/api/v1/agent/chat/stream",
            params={"message": "stream ping", "dry_run": "true"},
            headers={"Accept": "text/event-stream"},
        )
        assert response.status_code == 200
        assert "event: session" in response.text
        assert "event: done" in response.text


def test_v1_novel_config_chapters_assets_empty_project() -> None:
    project_dir = f"p18-v1-novel-{uuid4().hex[:8]}"
    with TestClient(app) as client:
        config_resp = client.get("/api/v1/novel/config", params={"project_dir": project_dir})
        assert config_resp.status_code == 200
        config_payload = config_resp.json()
        assert config_payload["exists"] is False

        chapters_resp = client.get("/api/v1/novel/chapters", params={"project_dir": project_dir})
        assert chapters_resp.status_code == 200
        chapters_payload = chapters_resp.json()
        assert chapters_payload["project_dir"].endswith(project_dir.replace("/", "\\"))
        assert isinstance(chapters_payload["chapters"], list)
        assert chapters_payload["chapters"] == []

        assets_resp = client.get("/api/v1/novel/assets", params={"project_dir": project_dir})
        assert assets_resp.status_code == 200
        assets_payload = assets_resp.json()
        assert assets_payload["project_dir"].endswith(project_dir.replace("/", "\\"))
        assert isinstance(assets_payload["assets"], list)


def test_legacy_api_prefix_routes_are_removed() -> None:
    with TestClient(app) as client:
        assert client.get("/api/health").status_code == 404
        assert client.get("/api/sessions").status_code == 404
        assert client.delete("/api/sessions/legacy-session").status_code in {404, 405}
        assert client.post("/api/sessions/legacy-session/reset").status_code in {404, 405}
        assert client.post("/api/chat", json={"message": "legacy", "dry_run": True}).status_code in {404, 405}
        assert client.get("/api/chat/stream", params={"message": "legacy", "dry_run": "true"}).status_code == 404
        assert client.get("/api/novel/config").status_code == 404
        assert client.post(
            "/api/novel/setup",
            json={"topic": "x", "genre": "y", "num_chapters": 2, "words_per_chapter": 500},
        ).status_code in {404, 405}

