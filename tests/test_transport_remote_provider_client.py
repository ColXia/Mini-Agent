from __future__ import annotations

from mini_agent.interfaces.ops import (
    StudioProviderModelDiscoveryRequest,
    StudioProviderUpsertRequest,
    StudioProviderValidationRequest,
)
from mini_agent.transport.remote_provider_client import RemoteProviderClient


class _DummyGatewayClient:
    def list_ops_providers_sync(self, *, catalog_path: str | None = None):
        return {
            "catalog_path": catalog_path or "D:/file/Mini-Agent",
            "provider_count": 1,
            "items": [
                {
                    "id": "ollama-local",
                    "name": "Ollama Local",
                    "api_type": "ollama",
                    "api_base": "http://127.0.0.1:11434/v1",
                    "api_key_masked": "***",
                    "models": ["qwen3.5:9b"],
                    "model_display_names": {"qwen3.5:9b": "Qwen"},
                    "enabled": True,
                    "priority": 0,
                    "timeout": 60,
                    "headers": {},
                    "catalog_path": catalog_path or "D:/file/Mini-Agent",
                    "health_status": "healthy",
                    "breaker_state": "closed",
                    "selected_count": 2,
                    "error_rate": 0.0,
                    "consecutive_failures": 0,
                }
            ],
        }

    def validate_provider_connection_sync(self, *, api_type: str, api_base: str, api_key: str | None = None):
        return {
            "status": "reachable",
            "api_type": api_type,
            "api_base": api_base,
            "resolved_provider_type": "ollama",
            "connection_ok": True,
            "model_count": 1,
            "latest_model_id": "qwen3.5:9b",
            "message": "Connection ok.",
            "models": [
                {
                    "model_id": "qwen3.5:9b",
                    "display_name": "Qwen",
                    "is_default": True,
                }
            ],
        }

    def discover_provider_models_sync(self, *, api_type: str, api_base: str, api_key: str):
        return {
            "models": [
                {
                    "model_id": "qwen3.5:9b",
                    "display_name": "Qwen",
                    "is_default": True,
                }
            ],
            "latest_model_id": "qwen3.5:9b",
        }

    def create_provider_sync(self, *, payload: dict[str, object], catalog_path: str | None = None):
        return {
            "id": str(payload.get("id") or "ollama-local"),
            "name": str(payload.get("name") or "Ollama"),
            "api_type": str(payload.get("api_type") or "openai"),
            "api_base": str(payload.get("api_base") or ""),
            "api_key_masked": "***",
            "models": list(payload.get("models") or []),
            "model_display_names": dict(payload.get("model_display_names") or {}),
            "enabled": bool(payload.get("enabled", True)),
            "priority": int(payload.get("priority") or 0),
            "timeout": int(payload.get("timeout") or 60),
            "headers": dict(payload.get("headers") or {}),
            "catalog_path": catalog_path or "D:/file/Mini-Agent",
            "health_status": "healthy",
            "breaker_state": "closed",
            "selected_count": 0,
            "error_rate": 0.0,
            "consecutive_failures": 0,
        }

    def update_provider_sync(self, *, provider_id: str, payload: dict[str, object], catalog_path: str | None = None):
        return {
            "id": provider_id,
            "name": str(payload.get("name") or "Ollama"),
            "api_type": str(payload.get("api_type") or "openai"),
            "api_base": str(payload.get("api_base") or ""),
            "api_key_masked": "***",
            "models": list(payload.get("models") or []),
            "model_display_names": dict(payload.get("model_display_names") or {}),
            "enabled": bool(payload.get("enabled", True)),
            "priority": int(payload.get("priority") or 0),
            "timeout": int(payload.get("timeout") or 60),
            "headers": dict(payload.get("headers") or {}),
            "catalog_path": catalog_path or "D:/file/Mini-Agent",
            "health_status": "healthy",
            "breaker_state": "closed",
            "selected_count": 0,
            "error_rate": 0.0,
            "consecutive_failures": 0,
        }

    def delete_provider_sync(self, *, provider_id: str, catalog_path: str | None = None):
        return {"status": "deleted", "provider_id": provider_id, "catalog_path": catalog_path or "D:/file/Mini-Agent"}

    def get_provider_health_sync(self, *, provider_id: str, catalog_path: str | None = None):
        return {
            "provider_id": provider_id,
            "status": "healthy",
            "breaker_state": "closed",
            "selected_count": 2,
            "total_requests": 10,
            "total_successes": 10,
            "total_failures": 0,
            "consecutive_failures": 0,
            "error_rate": 0.0,
            "last_selected_at": "2026-04-18T08:00:00+00:00",
            "last_success_at": "2026-04-18T08:00:01+00:00",
            "last_failure_at": None,
            "last_failure_reason": None,
        }


def test_remote_provider_client_shapes_gateway_payloads_into_typed_models() -> None:
    service = RemoteProviderClient(provider_transport=_DummyGatewayClient())

    listed = service.list_providers_sync(catalog_path="D:/file/Mini-Agent")
    validation = service.validate_provider_connection_sync(
        StudioProviderValidationRequest(
            api_type="ollama",
            api_base="http://127.0.0.1:11434/v1",
            api_key=None,
        )
    )
    discovery = service.discover_provider_models_sync(
        StudioProviderModelDiscoveryRequest(
            api_type="ollama",
            api_base="http://127.0.0.1:11434/v1",
            api_key=None,
        )
    )
    created = service.create_provider_sync(
        StudioProviderUpsertRequest(
            id="ollama-local",
            name="Ollama Local",
            api_type="ollama",
            api_base="http://127.0.0.1:11434/v1",
            api_key="ollama",
            models=["qwen3.5:9b"],
            selected_model_id="qwen3.5:9b",
            enabled=True,
            priority=0,
            timeout=60,
        ),
    )
    updated = service.update_provider_sync(
        "ollama-local",
        StudioProviderUpsertRequest(
            id="ollama-local",
            name="Ollama Local",
            api_type="ollama",
            api_base="http://127.0.0.1:11434/v1",
            api_key="ollama",
            models=["qwen3.5:9b"],
            selected_model_id="qwen3.5:9b",
            enabled=True,
            priority=1,
            timeout=45,
        ),
    )
    deleted = service.delete_provider_sync("ollama-local")
    health = service.get_provider_health_sync("ollama-local")

    assert listed.provider_count == 1
    assert validation.latest_model_id == "qwen3.5:9b"
    assert discovery.models[0].model_id == "qwen3.5:9b"
    assert created.id == "ollama-local"
    assert updated.priority == 1
    assert deleted.status == "deleted"
    assert health.status == "healthy"
