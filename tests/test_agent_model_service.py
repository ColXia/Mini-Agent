from __future__ import annotations

import json
from pathlib import Path

import pytest

from mini_agent.model_manager.agent_model_service import AgentModelService
from mini_agent.model_manager.runtime import reset_model_manager_runtime_state


def _write_catalog(path: Path, providers: list[dict[str, object]]) -> None:
    path.write_text(
        json.dumps({"providers": providers}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


@pytest.fixture(autouse=True)
def _reset_model_runtime_state(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in (
        "MINI_AGENT_PROVIDER_CATALOG_PATH",
        "MINIMAX_API_KEY",
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "MINI_AGENT_OLLAMA_ENABLED",
    ):
        monkeypatch.delenv(key, raising=False)
    reset_model_manager_runtime_state()


def test_agent_model_service_uses_automatic_binding_for_current_display(tmp_path: Path) -> None:
    catalog_path = tmp_path / "providers.json"
    binding_state_path = tmp_path / "agent_model_binding.json"
    _write_catalog(
        catalog_path,
        [
            {
                "id": "maas",
                "name": "MaaS",
                "api_type": "openai",
                "api_base": "https://maas.example.com/v1",
                "api_key": "sk-maas",
                "models": ["astron-code-latest"],
                "enabled": True,
                "priority": 10,
            }
        ],
    )

    service = AgentModelService(
        binding_state_path=binding_state_path,
        catalog_path=catalog_path,
    )

    binding = service.get_model_binding()
    diagnostics = service.get_model_binding_diagnostics()
    bindings = service.list_model_bindings()

    assert binding["binding_kind"] == "automatic"
    assert binding["provider_source"] == "custom"
    assert binding["provider_id"] == "maas"
    assert binding["model_id"] == "astron-code-latest"
    assert diagnostics["configured_binding"] is None
    assert diagnostics["latest_route"]["catalog_source"] == "provider_catalog"
    assert bindings[0]["provider_id"] == "maas"
    assert bindings[0]["models"][0]["model_id"] == "astron-code-latest"
    assert bindings[0]["models"][0]["is_current_binding"] is True


def test_agent_model_service_persists_explicit_binding_and_switch_generation(tmp_path: Path) -> None:
    catalog_path = tmp_path / "providers.json"
    binding_state_path = tmp_path / "agent_model_binding.json"
    _write_catalog(
        catalog_path,
        [
            {
                "id": "maas",
                "name": "MaaS",
                "api_type": "openai",
                "api_base": "https://maas.example.com/v1",
                "api_key": "sk-maas",
                "models": ["astron-code-latest", "astron-code-stable"],
                "enabled": True,
                "priority": 10,
            }
        ],
    )

    service = AgentModelService(
        binding_state_path=binding_state_path,
        catalog_path=catalog_path,
    )

    updated = service.update_model_binding(
        provider_source="custom",
        provider_id="maas",
        model_id="astron-code-stable",
    )
    reloaded = AgentModelService(
        binding_state_path=binding_state_path,
        catalog_path=catalog_path,
    )
    persisted = reloaded.get_model_binding()
    explicit_identity = reloaded.explicit_model_identity()
    switched = reloaded.update_model_binding(
        provider_source="custom",
        provider_id="maas",
        model_id="astron-code-latest",
    )

    assert updated["binding_kind"] == "explicit"
    assert updated["switch_generation"] == 1
    assert updated["model_id"] == "astron-code-stable"
    assert explicit_identity == ("custom", "maas", "astron-code-stable")
    assert persisted["binding_kind"] == "explicit"
    assert persisted["configured_binding"]["model_id"] == "astron-code-stable"
    assert switched["switch_generation"] == 2
    assert switched["model_id"] == "astron-code-latest"


def test_agent_model_service_invalid_explicit_binding_falls_back_but_does_not_expose_identity(
    tmp_path: Path,
) -> None:
    catalog_path = tmp_path / "providers.json"
    binding_state_path = tmp_path / "agent_model_binding.json"
    _write_catalog(
        catalog_path,
        [
            {
                "id": "maas",
                "name": "MaaS",
                "api_type": "openai",
                "api_base": "https://maas.example.com/v1",
                "api_key": "sk-maas",
                "models": ["astron-code-latest"],
                "enabled": True,
                "priority": 10,
            }
        ],
    )

    service = AgentModelService(
        binding_state_path=binding_state_path,
        catalog_path=catalog_path,
    )
    service.update_model_binding(
        provider_source="custom",
        provider_id="maas",
        model_id="astron-code-latest",
    )

    _write_catalog(
        catalog_path,
        [
            {
                "id": "ollama-local",
                "name": "Ollama Local",
                "api_type": "openai",
                "api_base": "http://localhost:11434/v1",
                "api_key": "ollama",
                "models": ["qwen3.5:9b"],
                "enabled": True,
                "priority": 5,
            }
        ],
    )

    binding = service.get_model_binding()
    diagnostics = service.get_model_binding_diagnostics()

    assert binding["binding_kind"] == "automatic"
    assert binding["provider_id"] == "ollama-local"
    assert binding["model_id"] == "qwen3.5:9b"
    assert service.explicit_model_identity() is None
    assert diagnostics["configured_binding"]["provider_id"] == "maas"
    assert diagnostics["configured_binding_error"] is not None
