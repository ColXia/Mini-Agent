from __future__ import annotations

from pathlib import Path
import json

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from mini_agent.application.operations_provider_use_cases import ProviderOperationsUseCases
from mini_agent.interfaces import (
    StudioFeatureModelBindingRequest,
    StudioModelCapabilityProbeRequest,
    StudioModelRoleRequest,
    StudioProviderModelDiscoveryRequest,
    StudioProviderUpsertRequest,
    StudioProviderValidationRequest,
)


def _build_use_cases(repo_root: Path, workspace_root: Path) -> ProviderOperationsUseCases:
    repo_root.mkdir(parents=True, exist_ok=True)
    workspace_root.mkdir(parents=True, exist_ok=True)
    return ProviderOperationsUseCases(repo_root=repo_root, workspace_root=workspace_root)


def test_provider_operations_use_cases_crud(tmp_path: Path) -> None:
    repo_root = (tmp_path / "repo").resolve()
    workspace_root = (tmp_path / "workspace").resolve()
    catalog_path = (workspace_root / "providers.json").resolve()
    use_cases = _build_use_cases(repo_root=repo_root, workspace_root=workspace_root)

    listed = use_cases.list_providers(catalog_path=str(catalog_path))
    assert listed.provider_count == 0

    created = use_cases.create_provider(
        payload=StudioProviderUpsertRequest(
            name="OpenAI Primary",
            api_type="openai",
            api_base="https://api.openai.example.com/v1",
            api_key="sk-openai-primary-0001",
            models=["gpt-4o-mini"],
            enabled=True,
            priority=8,
            timeout=45,
            headers={},
        ),
        catalog_path=str(catalog_path),
    )
    assert created.id == "openai-primary"
    assert created.catalog_path == str(catalog_path)

    updated = use_cases.update_provider(
        provider_id=created.id,
        payload=StudioProviderUpsertRequest(
            name="OpenAI Primary Updated",
            api_type="openai",
            api_base="https://api.openai.example.com/v1",
            api_key="sk-openai-primary-9999",
            models=["gpt-4o-mini", "gpt-4.1-mini"],
            enabled=False,
            priority=3,
            timeout=60,
            headers={"x-studio": "1"},
        ),
        catalog_path=str(catalog_path),
    )
    assert updated.id == created.id
    assert updated.enabled is False
    assert sorted(updated.models) == ["gpt-4.1-mini", "gpt-4o-mini"]

    health = use_cases.get_provider_health(provider_id=created.id, catalog_path=str(catalog_path))
    assert health.provider_id == created.id
    assert health.breaker_state in {"closed", "open", "half_open"}

    deleted = use_cases.delete_provider(provider_id=created.id, catalog_path=str(catalog_path))
    assert deleted.status == "deleted"

    after_delete = use_cases.list_providers(catalog_path=str(catalog_path))
    assert after_delete.provider_count == 0


def test_create_provider_auto_discover_requires_selected_model_id(tmp_path: Path, monkeypatch) -> None:
    repo_root = (tmp_path / "repo").resolve()
    workspace_root = (tmp_path / "workspace").resolve()
    catalog_path = (workspace_root / "providers.json").resolve()
    use_cases = _build_use_cases(repo_root=repo_root, workspace_root=workspace_root)

    monkeypatch.setattr(
        ProviderOperationsUseCases,
        "_discover_models_for_provider_payload",
        lambda self, **kwargs: (["model-a", "model-b"], "model-b"),
    )

    with pytest.raises(HTTPException) as exc_info:
        use_cases.create_provider(
            payload=StudioProviderUpsertRequest(
                name="Auto Discover Missing Selection",
                api_type="openai",
                api_base="https://api.openai.example.com/v1",
                api_key="sk-openai-primary-0001",
                models=[],
                auto_discover_models=True,
                enabled=True,
                priority=5,
                timeout=45,
                headers={},
            ),
            catalog_path=str(catalog_path),
        )

    assert exc_info.value.status_code == 400
    assert "no selected_model_id provided" in str(exc_info.value.detail)


def test_provider_upsert_request_rejects_removed_custom_api_type() -> None:
    with pytest.raises(ValidationError, match="api_type 'custom' was removed"):
        StudioProviderUpsertRequest(
            name="Legacy Custom",
            api_type="custom",
            api_base="https://legacy.example.com/v1",
            api_key="sk-legacy-primary-0001",
            models=["legacy-model"],
            enabled=True,
            priority=1,
            timeout=45,
            headers={},
        )


def test_discover_provider_models_for_setup(tmp_path: Path, monkeypatch) -> None:
    repo_root = (tmp_path / "repo").resolve()
    workspace_root = (tmp_path / "workspace").resolve()
    use_cases = _build_use_cases(repo_root=repo_root, workspace_root=workspace_root)

    monkeypatch.setattr(
        ProviderOperationsUseCases,
        "_discover_models_for_provider_payload",
        lambda self, **kwargs: (["model-a", "model-b"], "model-b"),
    )

    payload = use_cases.discover_provider_models(
        payload=StudioProviderModelDiscoveryRequest(
            api_type="openai",
            api_base="https://api.openai.example.com/v1",
            api_key="sk-openai-primary-0001",
        )
    )
    assert payload.latest_model_id == "model-b"
    assert [item.model_id for item in payload.models] == ["model-a", "model-b"]


def test_discover_provider_models_for_local_ollama_uses_ollama_discovery_type(
    tmp_path: Path,
    monkeypatch,
) -> None:
    repo_root = (tmp_path / "repo").resolve()
    workspace_root = (tmp_path / "workspace").resolve()
    use_cases = _build_use_cases(repo_root=repo_root, workspace_root=workspace_root)

    from mini_agent.model_manager.model_discovery import ProviderType

    captured: dict[str, object] = {}

    async def _fake_discover_models(self, provider, api_key, api_base=None, use_cache=True):
        _ = (self, api_key, api_base, use_cache)
        captured["provider"] = provider
        return type(
            "_Result",
            (),
            {
                "available_models": [
                    type("_Model", (), {"id": "qwen3.5:9b"})(),
                    type("_Model", (), {"id": "qwen3-embedding:0.6b"})(),
                ],
            },
        )()

    monkeypatch.setattr(
        "mini_agent.application.operations_provider_use_cases.ModelDiscoveryService.discover_models",
        _fake_discover_models,
    )
    monkeypatch.setattr(
        "mini_agent.application.operations_provider_use_cases.recommend_discovered_model",
        lambda provider_type, result, curated_order=None, official_default=None: type(
            "_Recommendation",
            (),
            {"model_id": "qwen3.5:9b"},
        )(),
    )

    payload = use_cases.discover_provider_models(
        payload=StudioProviderModelDiscoveryRequest(
            api_type="openai",
            api_base="http://localhost:11434/v1",
            api_key="ollama",
        )
    )
    assert captured["provider"] == ProviderType.OLLAMA
    assert payload.latest_model_id == "qwen3.5:9b"
    assert [item.model_id for item in payload.models] == ["qwen3.5:9b", "qwen3-embedding:0.6b"]


def test_validate_provider_connection_reports_reachable_no_models_for_empty_inventory(
    tmp_path: Path,
    monkeypatch,
) -> None:
    repo_root = (tmp_path / "repo").resolve()
    workspace_root = (tmp_path / "workspace").resolve()
    use_cases = _build_use_cases(repo_root=repo_root, workspace_root=workspace_root)

    async def _fake_discover_models(self, provider, api_key, api_base=None, use_cache=True):
        _ = (self, provider, api_key, api_base, use_cache)
        return type("_Result", (), {"available_models": []})()

    monkeypatch.setattr(
        "mini_agent.application.operations_provider_use_cases.ModelDiscoveryService.discover_models",
        _fake_discover_models,
    )
    monkeypatch.setattr(
        "mini_agent.application.operations_provider_use_cases.recommend_discovered_model",
        lambda provider_type, result, curated_order=None, official_default=None: None,
    )

    payload = use_cases.validate_provider_connection(
        payload=StudioProviderValidationRequest(
            api_type="openai",
            api_base="https://maas.example.com/v2",
            api_key="sk-maas",
        )
    )

    assert payload.status == "reachable_no_models"
    assert payload.connection_ok is True
    assert payload.model_count == 0
    assert "returned no models" in payload.message


def test_discover_provider_models_request_rejects_removed_custom_api_type() -> None:
    with pytest.raises(ValidationError, match="api_type 'custom' was removed"):
        StudioProviderModelDiscoveryRequest(
            api_type="custom",
            api_base="https://legacy.example.com/v1",
            api_key="sk-legacy-primary-0001",
        )


def test_create_provider_persists_advanced_model_metadata(tmp_path: Path) -> None:
    repo_root = (tmp_path / "repo").resolve()
    workspace_root = (tmp_path / "workspace").resolve()
    catalog_path = (workspace_root / "providers.json").resolve()
    use_cases = _build_use_cases(repo_root=repo_root, workspace_root=workspace_root)

    created = use_cases.create_provider(
        payload=StudioProviderUpsertRequest(
            name="MaaS",
            api_type="openai",
            api_base="https://maas.example.com/v2",
            api_key="sk-maas-primary-0001",
            models=["astron-code-latest"],
            model_id="astron-code-latest",
            model_display_name="Astron Latest",
            model_role="chat",
            model_context_window=256000,
            model_learned_token_limit=128000,
            supports_tools=True,
            supports_thinking=True,
            enabled=True,
            priority=8,
            timeout=45,
            headers={"X-Tenant": "tenant-a"},
        ),
        catalog_path=str(catalog_path),
    )

    assert created.id == "maas"

    payload = json.loads(catalog_path.read_text(encoding="utf-8"))
    provider = payload["providers"][0]
    assert provider["headers"] == {"X-Tenant": "tenant-a"}
    assert provider["timeout"] == 45
    assert provider["model_context_windows"]["astron-code-latest"] == 256000
    assert provider["model_learned_token_limits"]["astron-code-latest"] == 128000
    assert provider["model_metadata"]["astron-code-latest"]["model_role"] == "chat"
    assert provider["model_metadata"]["astron-code-latest"]["supports_tools"] is True
    assert provider["model_metadata"]["astron-code-latest"]["supports_thinking"] is True


def test_create_provider_accepts_ollama_alias_and_blank_api_key(tmp_path: Path) -> None:
    repo_root = (tmp_path / "repo").resolve()
    workspace_root = (tmp_path / "workspace").resolve()
    catalog_path = (workspace_root / "providers.json").resolve()
    use_cases = _build_use_cases(repo_root=repo_root, workspace_root=workspace_root)

    created = use_cases.create_provider(
        payload=StudioProviderUpsertRequest(
            name="Ollama Local",
            api_type="ollama",
            api_base="http://127.0.0.1:11434/v1",
            api_key="",
            models=["qwen3.5:9b"],
            enabled=True,
            priority=5,
            timeout=45,
            headers={},
        ),
        catalog_path=str(catalog_path),
    )

    assert created.id == "ollama-local"

    payload = json.loads(catalog_path.read_text(encoding="utf-8"))
    provider = payload["providers"][0]
    assert provider["api_type"] == "openai"
    assert provider["api_key"] == "ollama"


def test_provider_use_cases_set_model_role_and_bind_feature_model(tmp_path: Path) -> None:
    repo_root = (tmp_path / "repo").resolve()
    workspace_root = (tmp_path / "workspace").resolve()
    catalog_path = (workspace_root / "providers.json").resolve()
    use_cases = _build_use_cases(repo_root=repo_root, workspace_root=workspace_root)

    use_cases.create_provider(
        payload=StudioProviderUpsertRequest(
            name="Ollama Local",
            api_type="openai",
            api_base="http://localhost:11434/v1",
            api_key="ollama",
            models=["qwen3.5:9b", "qwen3-embedding:0.6b"],
            enabled=True,
            priority=5,
            timeout=45,
            headers={},
        ),
        catalog_path=str(catalog_path),
    )

    summary = use_cases.set_model_role(
        payload=StudioModelRoleRequest(
            source="custom",
            provider_id="ollama-local",
            model_id="qwen3-embedding:0.6b",
            model_role="embedding",
        ),
        catalog_path=str(catalog_path),
    )
    assert any(
        item.model_id == "qwen3-embedding:0.6b" and item.model_role == "embedding"
        for item in summary.models
    )

    binding = use_cases.bind_feature_model(
        payload=StudioFeatureModelBindingRequest(
            feature_role="embedding",
            source="custom",
            provider_id="ollama-local",
            model_id="qwen3-embedding:0.6b",
        ),
        catalog_path=str(catalog_path),
    )
    assert binding.feature_role == "embedding"
    assert binding.provider_id == "ollama-local"

    listed = use_cases.list_feature_bindings(catalog_path=str(catalog_path))
    assert listed.items[0].feature_role == "embedding"

    cleared = use_cases.clear_feature_model_binding(
        feature_role="embedding",
        catalog_path=str(catalog_path),
    )
    assert cleared.status == "cleared"


def test_provider_use_cases_probe_model_capabilities(tmp_path: Path, monkeypatch) -> None:
    repo_root = (tmp_path / "repo").resolve()
    workspace_root = (tmp_path / "workspace").resolve()
    catalog_path = (workspace_root / "providers.json").resolve()
    use_cases = _build_use_cases(repo_root=repo_root, workspace_root=workspace_root)

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

    response = use_cases.probe_model_capabilities(
        payload=StudioModelCapabilityProbeRequest(
            source="custom",
            provider_id="maas",
            model_id="astron-code-latest",
        ),
        catalog_path=str(catalog_path),
    )

    assert response.provider_id == "maas"
    assert response.updated_fields == ["supports_tools"]
    assert response.model.supports_tools is True
    assert response.model.supports_tools_source == "active_probe_tool_call"


def test_discover_provider_models_rejects_removed_gemini_api_type(tmp_path: Path) -> None:
    repo_root = (tmp_path / "repo").resolve()
    workspace_root = (tmp_path / "workspace").resolve()
    _ = _build_use_cases(repo_root=repo_root, workspace_root=workspace_root)

    with pytest.raises(ValidationError, match="api_type must be one of: openai, anthropic"):
        StudioProviderModelDiscoveryRequest(
            api_type="gemini",
            api_base="https://generativelanguage.googleapis.com/v1beta",
            api_key="test-key",
        )
