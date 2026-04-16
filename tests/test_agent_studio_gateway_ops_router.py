"""Tests for gateway ops provider/memory management contract routes."""

from __future__ import annotations

from datetime import datetime
import json

import pytest
from fastapi.testclient import TestClient

import apps.agent_studio_gateway.main as gateway_main
from apps.agent_studio_gateway.main import app
from mini_agent.tools.note_tool import MarkdownMemoryStore


@pytest.fixture(autouse=True)
def _ops_default_env(monkeypatch, tmp_path):
    monkeypatch.delenv("MINI_AGENT_STUDIO_API_KEYS", raising=False)
    monkeypatch.setenv("MINI_AGENT_STUDIO_ALLOWED_ROOTS", str(tmp_path))


@pytest.fixture
def _catalog_path(monkeypatch, tmp_path):
    catalog_path = (tmp_path / "providers.json").resolve()
    monkeypatch.setenv("MINI_AGENT_PROVIDER_CATALOG_PATH", str(catalog_path))
    return catalog_path


def test_ops_provider_crud_contract(_catalog_path):
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


def test_ops_provider_validation_error_returns_400(_catalog_path):
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


def test_ops_provider_contract_rejects_removed_custom_api_type(_catalog_path):
    with TestClient(app) as client:
        bad = client.post(
            "/api/v1/ops/providers",
            json={
                "name": "Legacy Custom",
                "api_type": "custom",
                "api_base": "https://legacy.example.com/v1",
                "api_key": "sk-legacy-primary-0001",
                "models": ["legacy-model"],
                "enabled": True,
                "priority": 1,
                "timeout": 30,
                "headers": {},
            },
        )
        assert bad.status_code == 422
        assert "api_type 'custom' was removed" in bad.text


def test_ops_models_contract_merges_custom_and_preset(monkeypatch, _catalog_path):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai-test")

    from mini_agent.model_manager.model_registry_service import ModelRegistryService

    def _fake_discover_models(
        self,
        *,
        provider_type,
        api_key,
        api_base,
        curated_order=None,
        official_default=None,
    ):
        _ = (self, api_key, api_base, curated_order, official_default)
        if str(provider_type.value) == "openai":
            return [
                {
                    "model_id": "gpt-5.4",
                    "display_name": "GPT-5.4",
                    "context_window": 1_050_000,
                    "supports_tools": True,
                    "supports_thinking": True,
                    "discovery_source": "api_discovery",
                    "discovery_confidence": "high",
                },
                {
                    "model_id": "gpt-5.3",
                    "display_name": "GPT-5.3",
                    "context_window": 400_000,
                    "supports_tools": True,
                    "supports_thinking": True,
                    "discovery_source": "api_discovery",
                    "discovery_confidence": "high",
                },
            ], {
                "model_id": "gpt-5.4",
                "strategy": "curated_latest",
                "confidence": "high",
                "discovery_source": "api_discovery",
            }
        return [{"model_id": "default-model", "display_name": "default-model"}], {
            "model_id": "default-model",
            "strategy": "discovered_latest",
            "confidence": "medium",
            "discovery_source": "api_discovery",
        }

    monkeypatch.setattr(ModelRegistryService, "_discover_models", _fake_discover_models)

    with TestClient(app) as client:
        created = client.post(
            "/api/v1/ops/providers",
            json={
                "name": "Custom Router",
                "api_type": "openai",
                "api_base": "https://custom.openai.example.com/v1",
                "api_key": "sk-custom-1234",
                "models": ["custom-model-1"],
                "enabled": True,
                "priority": 9,
                "timeout": 45,
                "headers": {},
            },
        )
        assert created.status_code == 200

        listed = client.get("/api/v1/ops/models")
        assert listed.status_code == 200
        items = listed.json()["items"]
        assert len(items) >= 2
        assert items[0]["source"] == "custom"
        openai_item = next(
            item for item in items if item["source"] == "preset" and item["provider_id"] == "openai"
        )
        assert openai_item["models"][0]["context_window"] == 1_050_000

        discover = client.post(
            "/api/v1/ops/models/discover",
            json={"source": "preset", "provider_id": "openai"},
        )
        assert discover.status_code == 200
        assert discover.json()["default_model_id"] == "gpt-5.4"
        assert discover.json()["default_model_strategy"] == "curated_latest"
        assert discover.json()["models"][0]["context_window"] == 1_050_000

        select = client.patch(
            "/api/v1/ops/models/selection",
            json={
                "source": "custom",
                "provider_id": "custom-router",
                "model_id": "custom-model-1",
            },
        )
        assert select.status_code == 200
        assert select.json()["default_model_id"] == "custom-model-1"


def test_ops_model_role_and_feature_binding_contracts(_catalog_path):
    with TestClient(app) as client:
        created = client.post(
            "/api/v1/ops/providers",
            json={
                "name": "Ollama Local",
                "api_type": "openai",
                "api_base": "http://localhost:11434/v1",
                "api_key": "ollama",
                "models": ["qwen3.5:9b", "qwen3-embedding:0.6b"],
                "enabled": True,
                "priority": 9,
                "timeout": 45,
                "headers": {},
            },
        )
        assert created.status_code == 200

        role_resp = client.patch(
            "/api/v1/ops/models/role",
            json={
                "source": "custom",
                "provider_id": "ollama-local",
                "model_id": "qwen3-embedding:0.6b",
                "model_role": "embedding",
            },
        )
        assert role_resp.status_code == 200
        assert any(
            item["model_id"] == "qwen3-embedding:0.6b" and item["model_role"] == "embedding"
            for item in role_resp.json()["models"]
        )

        bind_resp = client.put(
            "/api/v1/ops/models/bindings",
            json={
                "feature_role": "embedding",
                "source": "custom",
                "provider_id": "ollama-local",
                "model_id": "qwen3-embedding:0.6b",
            },
        )
        assert bind_resp.status_code == 200
        assert bind_resp.json()["feature_role"] == "embedding"
        assert bind_resp.json()["provider_id"] == "ollama-local"

        list_resp = client.get("/api/v1/ops/models/bindings")
        assert list_resp.status_code == 200
        assert list_resp.json()["items"][0]["feature_role"] == "embedding"

        clear_resp = client.delete("/api/v1/ops/models/bindings/embedding")
        assert clear_resp.status_code == 200
        assert clear_resp.json()["status"] == "cleared"


def test_ops_model_probe_contract(monkeypatch):
    monkeypatch.setattr(
        "mini_agent.application.operations_provider_use_cases.ModelCapabilityProbeService.probe_model",
        lambda self, **kwargs: {
            "source": "custom",
            "provider_id": "maas",
            "provider_name": "MaaS",
            "api_type": "openai",
            "api_base": "https://maas.example.com/v2",
            "model_id": "astron-code-latest",
            "updated_fields": ["supports_tools"],
            "discovery_attempted": True,
            "active_probe_attempted": True,
            "notes": [],
            "model": {
                "model_id": "astron-code-latest",
                "display_name": "Astron Latest",
                "is_default": True,
                "supports_tools": True,
                "supports_tools_truth": "supported",
                "supports_tools_confidence": "high",
                "supports_tools_source": "active_probe_tool_call",
            },
        },
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/ops/models/probe",
            json={
                "source": "custom",
                "provider_id": "maas",
                "model_id": "astron-code-latest",
            },
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["provider_id"] == "maas"
        assert payload["updated_fields"] == ["supports_tools"]
        assert payload["model"]["supports_tools"] is True
        assert payload["model"]["supports_tools_source"] == "active_probe_tool_call"


def test_ops_provider_model_discovery_contract(monkeypatch):
    class _OpsStub:
        def discover_provider_models(self, *, payload):
            _ = payload
            return {
                "latest_model_id": "model-b",
                "models": [
                    {"model_id": "model-a", "display_name": "model-a", "is_default": False},
                    {"model_id": "model-b", "display_name": "model-b", "is_default": True},
                ],
            }

    monkeypatch.setattr(
        gateway_main,
        "GATEWAY_PROVIDER_OPERATIONS_USE_CASES",
        _OpsStub(),
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/ops/providers/model-discovery",
            json={
                "api_type": "openai",
                "api_base": "https://api.openai.example.com/v1",
                "api_key": "sk-openai-test",
            },
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["latest_model_id"] == "model-b"
        assert [item["model_id"] for item in payload["models"]] == ["model-a", "model-b"]


def test_ops_provider_model_discovery_contract_rejects_removed_custom_api_type():
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/ops/providers/model-discovery",
            json={
                "api_type": "custom",
                "api_base": "https://legacy.example.com/v1",
                "api_key": "sk-legacy-primary-0001",
            },
        )
        assert response.status_code == 422
        assert "api_type 'custom' was removed" in response.text


def test_ops_memory_summary_search_and_daily(tmp_path):
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


def test_ops_runtime_diagnostics_contract():
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


def test_ops_routing_diagnostics_contract():
    with TestClient(app) as client:
        _ = client.post(
            "/api/v1/agent/chat",
            json={"message": "hello routing", "dry_run": True},
        )
        response = client.get("/api/v1/ops/diagnostics/routing")
        assert response.status_code == 200
        payload = response.json()
        assert payload["total_resolutions"] >= 0
        assert payload["cache_hits"] >= 0
        assert payload["fallback_resolutions"] >= 0
        assert isinstance(payload["matched_scope_counts"], dict)
        assert isinstance(payload["matched_agent_counts"], dict)
        assert payload["model_route_resolutions"] >= 0
        assert "latest_model_route" in payload
        if payload["latest_model_route"] is not None:
            assert payload["latest_model_route"]["candidate_count"] >= 0
            assert isinstance(payload["latest_model_route"]["candidates"], list)


def test_ops_auth_token_required_when_configured(monkeypatch, tmp_path):
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
        routing_unauthorized = client.get("/api/v1/ops/diagnostics/routing")
        assert routing_unauthorized.status_code == 401

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
        routing_by_bearer = client.get(
            "/api/v1/ops/diagnostics/routing",
            headers={"Authorization": "Bearer studio-token"},
        )
        assert routing_by_bearer.status_code == 200

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
        routing_by_api_key = client.get(
            "/api/v1/ops/diagnostics/routing",
            headers={"x-api-key": "studio-token"},
        )
        assert routing_by_api_key.status_code == 200


def test_ops_path_boundaries_reject_external_targets(tmp_path):
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
