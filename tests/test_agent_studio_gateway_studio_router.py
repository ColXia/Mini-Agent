"""Tests for Agent Studio provider/memory management contract routes."""

from __future__ import annotations

from datetime import datetime
import json

import pytest
from fastapi.testclient import TestClient

from apps.agent_studio_gateway.main import app
from mini_agent.tools.note_tool import MarkdownMemoryStore


@pytest.fixture(autouse=True)
def _studio_default_env(monkeypatch, tmp_path):
    monkeypatch.delenv("MINI_AGENT_STUDIO_API_KEYS", raising=False)
    monkeypatch.setenv("MINI_AGENT_STUDIO_ALLOWED_ROOTS", str(tmp_path))


@pytest.fixture
def _catalog_path(monkeypatch, tmp_path):
    catalog_path = (tmp_path / "providers.json").resolve()
    monkeypatch.setenv("MINI_AGENT_PROVIDER_CATALOG_PATH", str(catalog_path))
    return catalog_path


def test_studio_provider_crud_contract(_catalog_path):
    with TestClient(app) as client:
        empty = client.get("/api/v1/ops/providers")
        assert empty.status_code == 200
        assert empty.json()["provider_count"] == 0
        assert empty.json()["catalog_path"] == str(_catalog_path)

        created = client.post(
            "/api/v1/ops/providers",
            json={
                "name": "OpenAI Primary",
                "api_type": "openai",
                "api_base": "https://api.openai.example.com/v1",
                "api_key": "sk-openai-primary-0001",
                "models": ["gpt-4o-mini"],
                "enabled": True,
                "priority": 8,
                "timeout": 45,
                "headers": {},
            },
        )
        assert created.status_code == 200
        provider_id = created.json()["id"]
        assert provider_id == "openai-primary"

        listed = client.get("/api/v1/ops/providers")
        assert listed.status_code == 200
        assert listed.json()["provider_count"] == 1
        assert listed.json()["items"][0]["name"] == "OpenAI Primary"
        assert listed.json()["items"][0]["api_key_masked"].startswith("sk-o")

        updated = client.put(
            f"/api/v1/ops/providers/{provider_id}",
            json={
                "name": "OpenAI Primary Updated",
                "api_type": "openai",
                "api_base": "https://api.openai.example.com/v1",
                "api_key": "sk-openai-primary-9999",
                "models": ["gpt-4o-mini", "gpt-4.1-mini"],
                "enabled": False,
                "priority": 2,
                "timeout": 60,
                "headers": {"x-studio": "1"},
            },
        )
        assert updated.status_code == 200
        assert updated.json()["enabled"] is False
        assert sorted(updated.json()["models"]) == ["gpt-4.1-mini", "gpt-4o-mini"]

        health = client.get(f"/api/v1/ops/providers/{provider_id}/health")
        assert health.status_code == 200
        assert health.json()["provider_id"] == provider_id
        assert health.json()["breaker_state"] in {"closed", "open", "half_open"}

        deleted = client.delete(f"/api/v1/ops/providers/{provider_id}")
        assert deleted.status_code == 200
        assert deleted.json()["status"] == "deleted"

        after_delete = client.get("/api/v1/ops/providers")
        assert after_delete.status_code == 200
        assert after_delete.json()["provider_count"] == 0

        persisted_payload = json.loads(_catalog_path.read_text(encoding="utf-8"))
        assert persisted_payload == {"providers": []}


def test_studio_provider_validation_error_returns_400(_catalog_path):
    with TestClient(app) as client:
        bad = client.post(
            "/api/v1/ops/providers",
            json={
                "name": "Bad Key Provider",
                "api_type": "openai",
                "api_base": "https://api.openai.example.com/v1",
                "api_key": "YOUR_API_KEY_HERE",
                "models": ["gpt-4o-mini"],
                "enabled": True,
                "priority": 1,
                "timeout": 30,
                "headers": {},
            },
        )
        assert bad.status_code == 400
        assert "invalid provider payload" in bad.json()["detail"]


def test_studio_memory_summary_search_and_daily(tmp_path):
    workspace_dir = tmp_path / "workspace"
    workspace_dir.mkdir(parents=True, exist_ok=True)

    store = MarkdownMemoryStore(memory_root=str(workspace_dir))
    now = datetime.now()
    store.append_note(content="alpha launch decision", category="planning", scope="long_term", now=now)
    store.append_note(content="alpha rollout today", category="daily", scope="daily", now=now)
    day = now.date().isoformat()

    with TestClient(app) as client:
        summary = client.get("/api/v1/ops/memory/summary", params={"workspace_dir": str(workspace_dir)})
        assert summary.status_code == 200
        summary_payload = summary.json()
        assert summary_payload["notes_count"] >= 2
        assert "planning" in summary_payload["categories"]
        assert f"{day}.md" in summary_payload["daily_files"]

        search = client.get(
            "/api/v1/ops/memory/search",
            params={
                "workspace_dir": str(workspace_dir),
                "query": "alpha",
                "limit": 10,
            },
        )
        assert search.status_code == 200
        search_payload = search.json()
        assert search_payload["total"] >= 2
        assert any("alpha" in item["content"] for item in search_payload["items"])

        daily = client.get(f"/api/v1/ops/memory/daily/{day}", params={"workspace_dir": str(workspace_dir)})
        assert daily.status_code == 200
        daily_payload = daily.json()
        assert daily_payload["day"] == day
        assert daily_payload["note_count"] >= 1
        assert "alpha rollout today" in daily_payload["content"]

        bad_day = client.get("/api/v1/ops/memory/daily/not-a-day", params={"workspace_dir": str(workspace_dir)})
        assert bad_day.status_code == 400


def test_studio_runtime_diagnostics_contract():
    with TestClient(app) as client:
        response = client.get("/api/v1/ops/diagnostics/runtime")
        assert response.status_code == 200
        payload = response.json()
        assert payload["mode"] in {"single_main", "team"}
        assert payload["active_sessions"] >= 0
        assert payload["max_active_sessions"] >= 1
        assert payload["available_session_slots"] >= 0
        assert payload["reserved_team_slots"] >= 1
        assert payload["team_saturation_rejections"] >= 0
        assert payload["team_workspace_conflict_rejections"] >= 0
        assert isinstance(payload["workspace_application_required"], bool)
        assert isinstance(payload.get("main_workspace_dir"), (str, type(None)))


def test_studio_auth_token_required_when_configured(monkeypatch, tmp_path):
    monkeypatch.setenv("MINI_AGENT_STUDIO_API_KEYS", "studio-token")
    catalog_path = (tmp_path / "providers.json").resolve()

    with TestClient(app) as client:
        unauthorized = client.get("/api/v1/ops/providers", params={"catalog_path": str(catalog_path)})
        assert unauthorized.status_code == 401

        wrong = client.get(
            "/api/v1/ops/providers",
            params={"catalog_path": str(catalog_path)},
            headers={"Authorization": "Bearer wrong-token"},
        )
        assert wrong.status_code == 401

        runtime_unauthorized = client.get("/api/v1/ops/diagnostics/runtime")
        assert runtime_unauthorized.status_code == 401

        ok_by_bearer = client.get(
            "/api/v1/ops/providers",
            params={"catalog_path": str(catalog_path)},
            headers={"Authorization": "Bearer studio-token"},
        )
        assert ok_by_bearer.status_code == 200

        runtime_by_bearer = client.get(
            "/api/v1/ops/diagnostics/runtime",
            headers={"Authorization": "Bearer studio-token"},
        )
        assert runtime_by_bearer.status_code == 200

        ok_by_api_key = client.get(
            "/api/v1/ops/providers",
            params={"catalog_path": str(catalog_path)},
            headers={"x-api-key": "studio-token"},
        )
        assert ok_by_api_key.status_code == 200

        runtime_by_api_key = client.get(
            "/api/v1/ops/diagnostics/runtime",
            headers={"x-api-key": "studio-token"},
        )
        assert runtime_by_api_key.status_code == 200


def test_studio_path_boundaries_reject_external_targets(tmp_path):
    catalog_path = (tmp_path / "providers.json").resolve()

    with TestClient(app) as client:
        outside_catalog = client.get(
            "/api/v1/ops/providers",
            params={"catalog_path": "C:/Windows/providers.json"},
        )
        assert outside_catalog.status_code == 400

        inside_catalog = client.get(
            "/api/v1/ops/providers",
            params={"catalog_path": str(catalog_path)},
        )
        assert inside_catalog.status_code == 200

        outside_workspace = client.get(
            "/api/v1/ops/memory/summary",
            params={"workspace_dir": "C:/Windows"},
        )
        assert outside_workspace.status_code == 400


def test_legacy_studio_prefix_is_removed():
    with TestClient(app) as client:
        legacy = client.get("/api/studio/providers")
        assert legacy.status_code == 404

