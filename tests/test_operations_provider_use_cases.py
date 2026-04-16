from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from mini_agent.application.operations_provider_use_cases import ProviderOperationsUseCases
from mini_agent.interfaces import (
    StudioProviderModelDiscoveryRequest,
    StudioProviderUpsertRequest,
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


def test_discover_provider_models_request_rejects_removed_custom_api_type() -> None:
    with pytest.raises(ValidationError, match="api_type 'custom' was removed"):
        StudioProviderModelDiscoveryRequest(
            api_type="custom",
            api_base="https://legacy.example.com/v1",
            api_key="sk-legacy-primary-0001",
        )


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
