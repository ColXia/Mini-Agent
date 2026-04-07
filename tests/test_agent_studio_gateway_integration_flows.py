"""Integration flows for main-agent, channel ingress, and novel profile via API v1."""

from __future__ import annotations

import shutil
from pathlib import Path
from uuid import uuid4

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


def test_integration_novel_profile_and_channel_novel_action() -> None:
    project = f"p18-novel-integration-{uuid4().hex[:8]}"
    project_dir = Path(__file__).resolve().parents[1] / "workspace" / project

    try:
        with TestClient(app) as client:
            config_before = client.get("/api/v1/novel/config", params={"project_dir": project})
            assert config_before.status_code == 200
            before_payload = config_before.json()
            assert before_payload["exists"] is False
            assert isinstance(before_payload.get("profile"), dict)

            setup_resp = client.post(
                "/api/v1/novel/setup",
                json={
                    "topic": "integration topic",
                    "genre": "科幻",
                    "num_chapters": 3,
                    "words_per_chapter": 500,
                    "project_dir": project,
                    "dry_run": True,
                },
            )
            assert setup_resp.status_code == 200
            setup_payload = setup_resp.json()
            assert setup_payload["status"] == "ok"
            assert "profile_binding_file" in setup_payload

            config_after = client.get("/api/v1/novel/config", params={"project_dir": project})
            assert config_after.status_code == 200
            after_payload = config_after.json()
            assert isinstance(after_payload.get("profile_binding"), dict)

            channel_action = client.post(
                "/api/v1/channel/message",
                json={
                    "channel_type": "wechat",
                    "conversation_id": "dm:integration-novel",
                    "message": "ignored",
                    "metadata": {
                        "novel_action": {
                            "action": "config",
                            "params": {"project_dir": project},
                        }
                    },
                },
            )
            assert channel_action.status_code == 200
            action_payload = channel_action.json()
            assert action_payload["ok"] is True
            reply = action_payload["data"]["reply"]
            assert "\"kind\": \"novel_action\"" in reply
            assert "\"action\": \"config\"" in reply
            assert project in reply
    finally:
        shutil.rmtree(project_dir, ignore_errors=True)
