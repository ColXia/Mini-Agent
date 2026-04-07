"""Tests for Agent Studio API v1 contract envelope routes."""

from __future__ import annotations

from fastapi.testclient import TestClient
from uuid import uuid4

from apps.agent_studio_gateway.main import app


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
                "channel_type": "wechat",
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


def test_v1_agent_sessions_envelope_empty() -> None:
    with TestClient(app) as client:
        response = client.get("/api/v1/agent/sessions")
        assert response.status_code == 200
        payload = response.json()
        assert payload["ok"] is True
        assert payload["error"] is None
        assert isinstance(payload["data"], list)


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
