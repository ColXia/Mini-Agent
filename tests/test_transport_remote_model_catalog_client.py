from __future__ import annotations

from mini_agent.interfaces import (
    MainAgentModelBindingRequest,
    StudioFeatureModelBindingRequest,
    StudioModelCapabilityProbeRequest,
    StudioModelRoleRequest,
)
from mini_agent.transport.remote_model_catalog_client import RemoteModelCatalogClient


class _DummyGatewayClient:
    def list_agent_models_sync(self):
        return {
            "items": [
                {
                    "source": "custom",
                    "provider_id": "maas",
                    "provider_name": "MaaS",
                    "api_type": "openai",
                    "api_base": "https://example.com/v1",
                    "models": [],
                }
            ]
        }

    def list_agent_model_candidates_sync(self, *, agent_id: str | None = None):
        assert agent_id == "main-agent"
        return {
            "items": [
                {
                    "source": "custom",
                    "provider_id": "maas",
                    "provider_name": "MaaS",
                    "api_type": "openai",
                    "api_base": "https://example.com/v1",
                    "models": [
                        {
                            "model_id": "astron-code-latest",
                            "display_name": "Astron",
                            "is_default": True,
                            "is_current_binding": True,
                        }
                    ],
                }
            ]
        }

    def get_current_agent_model_binding_sync(self, *, agent_id: str | None = None):
        assert agent_id == "main-agent"
        return {
            "agent_id": "main-agent",
            "binding_kind": "explicit",
            "provider_source": "custom",
            "provider_id": "maas",
            "model_id": "astron-code-latest",
            "switch_generation": 2,
        }

    def set_agent_model_binding_sync(
        self,
        *,
        agent_id: str | None = None,
        provider_source: str | None = None,
        provider_id: str,
        model_id: str,
    ):
        assert agent_id == "main-agent"
        assert provider_source == "custom"
        assert provider_id == "maas"
        assert model_id == "astron-code-stable"
        return {
            "agent_id": "main-agent",
            "binding_kind": "explicit",
            "provider_source": "custom",
            "provider_id": "maas",
            "model_id": "astron-code-stable",
            "switch_generation": 3,
        }

    def get_current_agent_model_capabilities_sync(self, *, agent_id: str | None = None):
        assert agent_id == "main-agent"
        return {
            "agent_id": "main-agent",
            "binding_kind": "explicit",
            "provider_source": "custom",
            "provider_id": "maas",
            "model_id": "astron-code-latest",
            "supports_tools": True,
            "supports_thinking": True,
        }

    def get_agent_model_binding_diagnostics_sync(self, *, agent_id: str | None = None):
        assert agent_id == "main-agent"
        return {
            "agent_id": "main-agent",
            "current_binding": {
                "agent_id": "main-agent",
                "binding_kind": "explicit",
                "provider_source": "custom",
                "provider_id": "maas",
                "model_id": "astron-code-latest",
                "switch_generation": 2,
            },
            "latest_route": {
                "selected_provider_id": "maas",
                "selected_model": "astron-code-latest",
                "candidate_count": 1,
                "candidates": [],
            },
        }

    def list_ops_models_sync(self, *, catalog_path: str | None = None):
        return {
            "items": [
                {
                    "source": "custom",
                    "provider_id": "ollama",
                    "provider_name": "Ollama",
                    "api_type": "ollama",
                    "api_base": "http://127.0.0.1:11434/v1",
                    "models": [
                        {
                            "model_id": "qwen3.5:9b",
                            "display_name": "Qwen",
                            "is_default": True,
                            "model_role": "chat",
                        }
                    ],
                }
            ]
        }

    def list_feature_model_bindings_sync(self, *, catalog_path: str | None = None):
        return {
            "items": [
                {
                    "feature_role": "embedding",
                    "provider_id": "ollama",
                    "model_id": "qwen3-embedding:0.6b",
                    "resolved": True,
                }
            ]
        }

    def set_model_role_sync(
        self,
        *,
        source: str,
        provider_id: str,
        model_id: str,
        model_role: str,
        catalog_path: str | None = None,
    ):
        return {
            "source": source,
            "provider_id": provider_id,
            "provider_name": "Ollama",
            "api_type": "ollama",
            "api_base": "http://127.0.0.1:11434/v1",
            "default_model_id": model_id,
            "models": [
                {
                    "model_id": model_id,
                    "display_name": "Qwen",
                    "is_default": False,
                    "model_role": model_role,
                }
            ],
            "enabled": True,
            "priority": 0,
        }

    def probe_model_capabilities_sync(
        self,
        *,
        source: str,
        provider_id: str,
        model_id: str,
        catalog_path: str | None = None,
    ):
        return {
            "source": source,
            "provider_id": provider_id,
            "provider_name": "Ollama",
            "api_type": "ollama",
            "api_base": "http://127.0.0.1:11434/v1",
            "model_id": model_id,
            "default_model_id": model_id,
            "updated_fields": ["supports_tools"],
            "discovery_attempted": True,
            "active_probe_attempted": True,
            "notes": ["capability probe"],
            "models": [
                {
                    "model_id": model_id,
                    "display_name": "Qwen",
                    "is_default": False,
                    "supports_tools": True,
                    "supports_tools_truth": "supported",
                    "supports_thinking_truth": "unknown",
                }
            ],
            "enabled": True,
            "priority": 0,
            "model": {
                "model_id": model_id,
                "display_name": "Qwen",
                "is_default": False,
                "supports_tools": True,
                "supports_tools_truth": "supported",
                "supports_thinking_truth": "unknown",
            },
        }

    def bind_feature_model_sync(
        self,
        *,
        feature_role: str,
        source: str,
        provider_id: str,
        model_id: str,
        catalog_path: str | None = None,
    ):
        return {
            "feature_role": feature_role,
            "source": source,
            "provider_id": provider_id,
            "provider_name": "Ollama",
            "provider_family": "ollama",
            "provider_variant": "local",
            "api_type": "ollama",
            "api_base": "http://127.0.0.1:11434/v1",
            "model_id": model_id,
            "display_name": "Qwen Embedding",
            "model_role": feature_role,
            "updated_at": "2026-04-18T08:00:00+00:00",
            "resolved": True,
        }

    def clear_feature_model_binding_sync(
        self,
        *,
        feature_role: str,
        catalog_path: str | None = None,
    ):
        return {"status": "cleared", "feature_role": feature_role}


def test_remote_model_catalog_client_shapes_gateway_payloads_into_typed_models() -> None:
    service = RemoteModelCatalogClient(model_transport=_DummyGatewayClient())

    agent_models = service.list_agent_models_sync()
    candidates = service.list_agent_model_candidates_sync(agent_id="main-agent")
    agent_binding = service.get_current_agent_model_binding_sync(agent_id="main-agent")
    updated = service.set_agent_model_binding_sync(
        MainAgentModelBindingRequest(
            agent_id="main-agent",
            provider_source="custom",
            provider_id="maas",
            model_id="astron-code-stable",
        )
    )
    capabilities = service.get_current_agent_model_capabilities_sync(agent_id="main-agent")
    diagnostics = service.get_agent_model_binding_diagnostics_sync(agent_id="main-agent")
    registry_models = service.list_registry_models_sync()
    bindings = service.list_feature_model_bindings_sync()
    role = service.set_model_role_sync(
        StudioModelRoleRequest(
            source="custom",
            provider_id="ollama",
            model_id="qwen3.5:9b",
            model_role="chat",
        )
    )
    probe = service.probe_model_capabilities_sync(
        StudioModelCapabilityProbeRequest(
            source="custom",
            provider_id="ollama",
            model_id="qwen3.5:9b",
        )
    )
    feature_binding = service.bind_feature_model_sync(
        StudioFeatureModelBindingRequest(
            feature_role="embedding",
            source="custom",
            provider_id="ollama",
            model_id="qwen3-embedding:0.6b",
        )
    )
    cleared = service.clear_feature_model_binding_sync(feature_role="embedding")

    assert agent_models.items[0].provider_id == "maas"
    assert candidates.items[0].models[0].is_current_binding is True
    assert agent_binding.model_id == "astron-code-latest"
    assert updated.switch_generation == 3
    assert capabilities.supports_tools is True
    assert diagnostics.latest_route is not None
    assert diagnostics.latest_route.selected_model == "astron-code-latest"
    assert registry_models.items[0].models[0].model_id == "qwen3.5:9b"
    assert bindings.items[0].feature_role == "embedding"
    assert role.models[0].model_role == "chat"
    assert probe.model.supports_tools is True
    assert feature_binding.feature_role == "embedding"
    assert cleared.feature_role == "embedding"
