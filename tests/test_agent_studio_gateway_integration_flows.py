"""Integration flows for main-agent and channel ingress via API v1."""

from __future__ import annotations

from fastapi.testclient import TestClient

from apps.agent_studio_gateway.main import app


def test_integration_main_agent_and_channel_ingress_dry_run() -> None:
    with TestClient(app) as client:
        main_resp = client.post(
            "/api/v1/agent/chat",
            json={
                "message": "integration ping",
                "workspace_dir": ".",
                "dry_run": True,
            },
        )
        assert main_resp.status_code == 200
        main_payload = main_resp.json()
        assert main_payload["ok"] is True
        assert main_payload["data"]["session_id"] == "dry-run-session"
        assert "integration ping" in main_payload["data"]["reply"]

        channel_resp = client.post(
            "/api/v1/channel/message",
            json={
                "channel_type": "qq",
                "conversation_id": "group:integration",
                "sender_id": "user-123",
                "message": "integration channel ping",
                "workspace_dir": ".",
                "dry_run": True,
            },
        )
        assert channel_resp.status_code == 200
        channel_payload = channel_resp.json()
        assert channel_payload["ok"] is True
        assert channel_payload["data"]["session_id"] == "dry-run-session"
        assert "integration channel ping" in channel_payload["data"]["reply"]
