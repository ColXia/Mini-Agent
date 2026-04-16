from __future__ import annotations

import json

import pytest

from mini_agent.model_manager.model_registry_service import ModelRegistryService


@pytest.fixture(autouse=True)
def _clear_ollama_env(monkeypatch):
    monkeypatch.setenv("MINI_AGENT_OLLAMA_ENABLED", "")
    monkeypatch.setenv("MINI_AGENT_ENABLE_OLLAMA", "")
    monkeypatch.setenv("OLLAMA_HOST", "")
    monkeypatch.setenv("MINI_AGENT_OLLAMA_BASE_URL", "")
    monkeypatch.setenv("MINI_AGENT_OLLAMA_PROTOCOL", "")


def test_preset_discovery_persists_model_metadata_and_strategy(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai-test")

    service = ModelRegistryService(
        catalog_path=tmp_path / "providers.json",
        preset_state_path=tmp_path / "preset_models.json",
    )

    def _fake_discover_models(
        self,
        *,
        provider_type,
        api_key,
        api_base,
        curated_order=None,
        official_default=None,
    ):
        _ = (self, provider_type, api_key, api_base, curated_order, official_default)
        return (
            [
                {
                    "model_id": "gpt-5.4",
                    "display_name": "GPT-5.4",
                    "context_window": 1_050_000,
                    "discovered_at": "2026-04-15T00:00:00+00:00",
                    "discovery_source": "api_discovery",
                    "discovery_confidence": "high",
                    "supports_tools": True,
                    "supports_thinking": True,
                },
                {
                    "model_id": "gpt-5.3",
                    "display_name": "GPT-5.3",
                    "context_window": 400_000,
                    "discovered_at": "2026-04-15T00:00:00+00:00",
                    "discovery_source": "api_discovery",
                    "discovery_confidence": "high",
                    "supports_tools": True,
                    "supports_thinking": True,
                },
            ],
            {
                "model_id": "gpt-5.4",
                "strategy": "curated_latest",
                "confidence": "high",
                "discovery_source": "api_discovery",
            },
        )

    monkeypatch.setattr(ModelRegistryService, "_discover_models", _fake_discover_models)

    discovered = service.discover_models(source="preset", provider_id="openai")

    assert discovered["default_model_id"] == "gpt-5.4"
    assert discovered["default_model_strategy"] == "curated_latest"
    assert discovered["default_model_confidence"] == "high"
    assert discovered["models"][0]["supports_tools"] is True
    assert discovered["models"][0]["supports_thinking"] is True
    assert discovered["models"][0]["discovery_source"] == "api_discovery"

    state_payload = json.loads((tmp_path / "preset_models.json").read_text(encoding="utf-8"))
    provider_state = state_payload["providers"]["openai"]
    assert provider_state["default_model_strategy"] == "curated_latest"
    assert provider_state["default_model_confidence"] == "high"
    assert provider_state["models"][0]["supports_tools"] is True
    assert provider_state["models"][0]["discovery_source"] == "api_discovery"

    listed = service.list_registry()
    openai_item = next(item for item in listed if item["source"] == "preset" and item["provider_id"] == "openai")
    assert openai_item["default_model_strategy"] == "curated_latest"
    assert openai_item["models"][0]["supports_thinking"] is True


def test_runtime_provider_catalog_preserves_model_metadata(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai-test")

    service = ModelRegistryService(
        catalog_path=tmp_path / "providers.json",
        preset_state_path=tmp_path / "preset_models.json",
    )
    (tmp_path / "preset_models.json").write_text(
        json.dumps(
            {
                "providers": {
                    "openai": {
                        "models": [
                            {
                                "model_id": "gpt-5.4",
                                "display_name": "GPT-5.4",
                                "context_window": 1_050_000,
                                "supports_tools": True,
                                "supports_thinking": True,
                                "discovered_at": "2026-04-15T00:00:00+00:00",
                                "discovery_source": "api_discovery",
                                "discovery_confidence": "high",
                            }
                        ],
                        "default_model_id": "gpt-5.4",
                        "default_model_strategy": "curated_latest",
                        "default_model_confidence": "high",
                    }
                }
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    catalog = service.runtime_provider_catalog()
    provider = next(item for item in catalog.providers if item.id == "preset-openai")

    assert provider.models == ["gpt-5.4"]
    assert provider.model_metadata["gpt-5.4"]["supports_tools"] is True
    assert provider.model_metadata["gpt-5.4"]["supports_thinking"] is True
    assert provider.model_metadata["gpt-5.4"]["discovery_source"] == "api_discovery"


def test_runtime_provider_catalog_preserves_custom_headers_and_timeout(tmp_path) -> None:
    catalog_path = tmp_path / "providers.json"
    catalog_path.write_text(
        json.dumps(
            {
                "providers": [
                    {
                        "id": "maas",
                        "name": "MaaS",
                        "api_type": "openai",
                        "api_base": "https://maas.example.com/v1",
                        "api_key": "sk-maas",
                        "models": ["astron-code-latest"],
                        "headers": {
                            "X-Tenant": "tenant-a",
                            "X-Workspace": "workspace-a",
                        },
                        "timeout": 45,
                        "enabled": True,
                        "priority": 10,
                    }
                ]
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    service = ModelRegistryService(
        catalog_path=catalog_path,
        preset_state_path=tmp_path / "preset_models.json",
    )

    catalog = service.runtime_provider_catalog()
    provider = next(item for item in catalog.providers if item.id == "maas")

    assert provider.headers == {
        "X-Tenant": "tenant-a",
        "X-Workspace": "workspace-a",
    }
    assert provider.timeout == 45


def test_record_model_capabilities_updates_preset_state_and_registry(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai-test")
    preset_state_path = tmp_path / "preset_models.json"
    preset_state_path.write_text(
        json.dumps(
            {
                "providers": {
                    "openai": {
                        "models": [
                            {
                                "model_id": "gpt-5.4",
                                "display_name": "GPT-5.4",
                            }
                        ],
                        "default_model_id": "gpt-5.4",
                    }
                }
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    service = ModelRegistryService(
        catalog_path=tmp_path / "providers.json",
        preset_state_path=preset_state_path,
    )

    summary = service.record_model_capabilities(
        source="preset",
        provider_id="openai",
        model_id="gpt-5.4",
        context_window=1_050_000,
        metadata_patch={
            "supports_tools": True,
            "supports_tools_truth": "supported",
            "supports_tools_confidence": "high",
            "supports_tools_source": "active_probe_tool_call",
        },
    )

    model = summary["models"][0]
    assert model["context_window"] == 1_050_000
    assert model["supports_tools"] is True
    assert model["supports_tools_truth"] == "supported"
    assert model["supports_tools_source"] == "active_probe_tool_call"

    state_payload = json.loads(preset_state_path.read_text(encoding="utf-8"))
    state_model = state_payload["providers"]["openai"]["models"][0]
    assert state_model["context_window"] == 1_050_000
    assert state_model["supports_tools"] is True
    assert state_model["supports_tools_truth"] == "supported"


def test_list_registry_exposes_provider_family_and_model_role(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("MINIMAX_API_KEY", "minimax-test-key")
    catalog_path = tmp_path / "providers.json"
    catalog_path.write_text(
        json.dumps(
            {
                "providers": [
                    {
                        "id": "maas",
                        "name": "MaaS",
                        "api_type": "openai",
                        "api_base": "https://maas.example.com/v2",
                        "api_key": "sk-maas",
                        "models": ["astron-code-latest"],
                        "model_metadata": {
                            "astron-code-latest": {
                                "model_role": "chat",
                                "supports_tools": True,
                            }
                        },
                    }
                ]
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    service = ModelRegistryService(
        catalog_path=catalog_path,
        preset_state_path=tmp_path / "preset_models.json",
    )

    listed = service.list_registry()
    custom = next(item for item in listed if item["source"] == "custom" and item["provider_id"] == "maas")
    preset = next(item for item in listed if item["source"] == "preset" and item["provider_id"] == "minimax")

    assert custom["provider_family"] == "openai"
    assert custom["models"][0]["model_role"] == "chat"
    assert preset["provider_family"] == "anthropic"
    assert preset["provider_variant"] == "minimax"


def test_set_model_role_and_feature_binding_persist_for_preset_models(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("MINI_AGENT_OLLAMA_ENABLED", "1")

    import mini_agent.model_manager.preset_providers as preset_providers

    monkeypatch.setattr(preset_providers, "_is_ollama_reachable", lambda host: True)
    monkeypatch.setattr(
        preset_providers,
        "_discover_preset_inventory",
        lambda provider, api_key, api_base=None: {
            "selected_model": "qwen3.5:9b",
            "selection_strategy": "curated_latest",
            "selection_confidence": "high",
            "discovery_source": "api_discovery",
            "discovered_models": ["qwen3.5:9b", "qwen3-embedding:0.6b", "glm-ocr:bf16"],
        },
    )

    preset_state_path = tmp_path / "preset_models.json"
    preset_state_path.write_text(
        json.dumps(
            {
                "providers": {
                    "ollama": {
                        "models": [
                            {"model_id": "qwen3.5:9b", "display_name": "qwen3.5:9b"},
                            {"model_id": "qwen3-embedding:0.6b", "display_name": "qwen3-embedding:0.6b"},
                            {"model_id": "glm-ocr:bf16", "display_name": "glm-ocr:bf16"},
                        ],
                        "default_model_id": "qwen3.5:9b",
                    }
                }
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    service = ModelRegistryService(
        catalog_path=tmp_path / "providers.json",
        preset_state_path=preset_state_path,
        feature_bindings_path=tmp_path / "feature_model_bindings.json",
    )

    role_summary = service.set_model_role(
        source="preset",
        provider_id="ollama",
        model_id="qwen3-embedding:0.6b",
        model_role="embedding",
    )
    assert any(
        item["model_id"] == "qwen3-embedding:0.6b" and item["model_role"] == "embedding"
        for item in role_summary["models"]
    )

    binding = service.bind_feature_model(
        feature_role="embedding",
        source="preset",
        provider_id="ollama",
        model_id="qwen3-embedding:0.6b",
    )
    assert binding["feature_role"] == "embedding"
    assert binding["provider_id"] == "ollama"
    assert binding["model_id"] == "qwen3-embedding:0.6b"

    listed = service.list_feature_bindings()
    assert listed[0]["resolved"] is True
    assert listed[0]["model_role"] == "embedding"


def test_runtime_provider_catalog_filters_feature_models_from_chat_runtime(tmp_path) -> None:
    catalog_path = tmp_path / "providers.json"
    catalog_path.write_text(
        json.dumps(
            {
                "providers": [
                    {
                        "id": "ollama-local",
                        "name": "Ollama Local",
                        "api_type": "openai",
                        "api_base": "http://localhost:11434/v1",
                        "api_key": "ollama",
                        "models": ["qwen3.5:9b", "qwen3-embedding:0.6b", "glm-ocr:bf16"],
                        "model_metadata": {
                            "qwen3.5:9b": {"model_role": "chat"},
                            "qwen3-embedding:0.6b": {"model_role": "embedding"},
                            "glm-ocr:bf16": {"model_role": "ocr"},
                        },
                    }
                ]
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    service = ModelRegistryService(
        catalog_path=catalog_path,
        preset_state_path=tmp_path / "preset_models.json",
    )

    catalog = service.runtime_provider_catalog()
    provider = next(item for item in catalog.providers if item.id == "ollama-local")

    assert provider.models == ["qwen3.5:9b"]


def test_runtime_provider_catalog_keeps_stateful_ollama_without_probe_or_rediscovery(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("MINI_AGENT_OLLAMA_ENABLED", "1")
    preset_state_path = tmp_path / "preset_models.json"
    preset_state_path.write_text(
        json.dumps(
            {
                "providers": {
                    "ollama": {
                        "models": [
                            {
                                "model_id": "qwen3-coder",
                                "display_name": "Qwen3 Coder",
                                "supports_tools": True,
                            }
                        ],
                        "default_model_id": "qwen3-coder",
                    }
                }
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    import mini_agent.model_manager.preset_providers as preset_providers

    def _unexpected_probe(host: str) -> bool:
        raise AssertionError(f"unexpected reachability probe for {host}")

    def _unexpected_discovery(provider, api_key, api_base=None):
        raise AssertionError(f"unexpected inventory discovery for {provider} {api_base}")

    monkeypatch.setattr(preset_providers, "_is_ollama_reachable", _unexpected_probe)
    monkeypatch.setattr(preset_providers, "_discover_preset_inventory", _unexpected_discovery)

    service = ModelRegistryService(
        catalog_path=tmp_path / "providers.json",
        preset_state_path=preset_state_path,
    )

    catalog = service.runtime_provider_catalog()
    provider = next(item for item in catalog.providers if item.id == "preset-ollama")

    assert provider.models == ["qwen3-coder"]
    assert provider.default_model == "qwen3-coder"
    assert provider.model_display_names["qwen3-coder"] == "Qwen3 Coder"
    assert provider.model_metadata["qwen3-coder"]["supports_tools"] is True


def test_ollama_preset_discovery_persists_local_models(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("MINI_AGENT_OLLAMA_ENABLED", "1")

    import mini_agent.model_manager.preset_providers as preset_providers

    monkeypatch.setattr(preset_providers, "_is_ollama_reachable", lambda host: True)

    service = ModelRegistryService(
        catalog_path=tmp_path / "providers.json",
        preset_state_path=tmp_path / "preset_models.json",
    )

    def _fake_discover_models(
        self,
        *,
        provider_type,
        api_key,
        api_base,
        curated_order=None,
        official_default=None,
    ):
        _ = (self, provider_type, api_key, api_base, curated_order, official_default)
        return (
            [
                {
                    "model_id": "qwen3-coder",
                    "display_name": "qwen3-coder",
                    "discovered_at": "2026-04-15T00:00:00+00:00",
                    "discovery_source": "api_discovery",
                    "discovery_confidence": "high",
                    "supports_tools": True,
                    "supports_thinking": True,
                },
                {
                    "model_id": "gpt-oss:20b",
                    "display_name": "gpt-oss:20b",
                    "discovered_at": "2026-04-15T00:00:00+00:00",
                    "discovery_source": "api_discovery",
                    "discovery_confidence": "high",
                    "supports_tools": True,
                    "supports_thinking": True,
                },
            ],
            {
                "model_id": "qwen3-coder",
                "strategy": "curated_latest",
                "confidence": "high",
                "discovery_source": "api_discovery",
            },
        )

    monkeypatch.setattr(ModelRegistryService, "_discover_models", _fake_discover_models)

    discovered = service.discover_models(source="preset", provider_id="ollama")

    assert discovered["provider_id"] == "ollama"
    assert discovered["default_model_id"] == "qwen3-coder"
    assert discovered["models"][0]["model_id"] == "qwen3-coder"
    assert discovered["models"][0]["supports_tools"] is True

    state_payload = json.loads((tmp_path / "preset_models.json").read_text(encoding="utf-8"))
    provider_state = state_payload["providers"]["ollama"]
    assert provider_state["default_model_id"] == "qwen3-coder"
    assert provider_state["models"][1]["model_id"] == "gpt-oss:20b"


def test_custom_discovery_merges_with_configured_inventory_without_shrinking(
    tmp_path,
    monkeypatch,
) -> None:
    catalog_path = tmp_path / "providers.json"
    catalog_path.write_text(
        json.dumps(
            {
                "providers": [
                    {
                        "id": "maas",
                        "name": "MaaS",
                        "api_type": "openai",
                        "api_base": "https://maas.example.com/v1",
                        "api_key": "sk-maas",
                        "models": ["astron-code-stable", "astron-code-preview"],
                        "model_display_names": {
                            "astron-code-preview": "Astron Preview"
                        },
                        "model_context_windows": {
                            "astron-code-preview": 128000
                        },
                        "model_metadata": {
                            "astron-code-preview": {
                                "supports_tools": False
                            }
                        },
                        "enabled": True,
                        "priority": 10,
                    }
                ]
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    service = ModelRegistryService(
        catalog_path=catalog_path,
        preset_state_path=tmp_path / "preset_models.json",
    )

    def _fake_discover_models(
        self,
        *,
        provider_type,
        api_key,
        api_base,
        curated_order=None,
        official_default=None,
    ):
        _ = (self, provider_type, api_key, api_base, curated_order, official_default)
        return (
            [
                {
                    "model_id": "astron-code-stable",
                    "display_name": "Astron Stable",
                    "context_window": 256000,
                    "discovery_source": "api_discovery",
                    "discovery_confidence": "high",
                },
                {
                    "model_id": "astron-code-latest",
                    "display_name": "Astron Latest",
                    "context_window": 512000,
                    "discovery_source": "api_discovery",
                    "discovery_confidence": "high",
                },
            ],
            {
                "model_id": "astron-code-latest",
                "strategy": "discovered_latest",
                "confidence": "high",
                "discovery_source": "api_discovery",
            },
        )

    monkeypatch.setattr(ModelRegistryService, "_discover_models", _fake_discover_models)

    discovered = service.discover_models(source="custom", provider_id="maas")

    assert [item["model_id"] for item in discovered["models"]] == [
        "astron-code-latest",
        "astron-code-stable",
        "astron-code-preview",
    ]
    assert discovered["default_model_id"] == "astron-code-latest"

    saved_catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    saved_provider = saved_catalog["providers"][0]
    assert saved_provider["models"] == [
        "astron-code-latest",
        "astron-code-stable",
        "astron-code-preview",
    ]
    assert saved_provider["model_context_windows"]["astron-code-latest"] == 512000
    assert saved_provider["model_context_windows"]["astron-code-stable"] == 256000
    assert saved_provider["model_context_windows"]["astron-code-preview"] == 128000
    assert saved_provider["model_metadata"]["astron-code-stable"]["discovery_source"] == "api_discovery"
    assert saved_provider["model_metadata"]["astron-code-preview"]["supports_tools"] is False


def test_custom_ollama_compatible_discovery_uses_ollama_provider_type(tmp_path, monkeypatch) -> None:
    catalog_path = tmp_path / "providers.json"
    catalog_path.write_text(
        json.dumps(
            {
                "providers": [
                    {
                        "id": "ollama-local",
                        "name": "Ollama Local",
                        "api_type": "openai",
                        "api_base": "http://localhost:11434/v1",
                        "api_key": "ollama",
                        "models": ["qwen3.5:9b"],
                    }
                ]
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    service = ModelRegistryService(
        catalog_path=catalog_path,
        preset_state_path=tmp_path / "preset_models.json",
    )

    from mini_agent.model_manager.model_discovery import ProviderType

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
        assert provider_type == ProviderType.OLLAMA
        return (
            [
                {
                    "model_id": "qwen3.5:9b",
                    "display_name": "qwen3.5:9b",
                    "discovery_source": "api_discovery",
                    "discovery_confidence": "high",
                },
                {
                    "model_id": "qwen3-embedding:0.6b",
                    "display_name": "qwen3-embedding:0.6b",
                    "discovery_source": "api_discovery",
                    "discovery_confidence": "high",
                },
            ],
            {
                "model_id": "qwen3.5:9b",
                "strategy": "discovered_latest",
                "confidence": "high",
                "discovery_source": "api_discovery",
            },
        )

    monkeypatch.setattr(ModelRegistryService, "_discover_models", _fake_discover_models)

    discovered = service.discover_models(source="custom", provider_id="ollama-local")

    assert [item["model_id"] for item in discovered["models"]] == [
        "qwen3.5:9b",
        "qwen3-embedding:0.6b",
    ]
