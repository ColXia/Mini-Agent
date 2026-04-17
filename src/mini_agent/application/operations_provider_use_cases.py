"""Application-layer provider and model operations use cases."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from fastapi import HTTPException

from mini_agent.interfaces import (
    StudioFeatureModelBindingClearResponse,
    StudioFeatureModelBindingRequest,
    StudioFeatureModelBindingSummary,
    StudioFeatureModelBindingsResponse,
    StudioModelCapabilityProbeRequest,
    StudioModelCapabilityProbeResponse,
    StudioModelDiscoverRequest,
    StudioModelListResponse,
    StudioModelProviderSummary,
    StudioModelRoleRequest,
    StudioModelSelectionRequest,
    StudioProviderDeleteResponse,
    StudioProviderHealthResponse,
    StudioProviderListResponse,
    StudioProviderModelDiscoveryRequest,
    StudioProviderModelDiscoveryResponse,
    StudioProviderModelSummary,
    StudioProviderSummary,
    StudioProviderUpsertRequest,
    StudioProviderValidationRequest,
    StudioProviderValidationResponse,
)
from mini_agent.model_manager import (
    get_circuit_breaker_registry,
    get_health_monitor,
    normalize_provider_catalog,
    normalize_provider_config,
)
from mini_agent.model_manager.provider import normalize_model_role, normalize_provider_api_type
from mini_agent.model_manager.capability_probe import ModelCapabilityProbeService
from mini_agent.model_manager.model_discovery import (
    ModelDiscoveryService,
    ProviderType,
    recommend_discovered_model,
)
from mini_agent.model_manager.model_registry_service import ModelRegistryService

from .operations_path_policy import OperationsPathPolicy


_OLLAMA_SENTINEL_API_KEY = "ollama"


class ProviderOperationsUseCases:
    """Provider/model CRUD and discovery flows for gateway operations."""

    def __init__(
        self,
        *,
        repo_root: Path,
        workspace_root: Path,
        path_policy: OperationsPathPolicy | None = None,
    ) -> None:
        self._path_policy = path_policy or OperationsPathPolicy(
            repo_root=repo_root,
            workspace_root=workspace_root,
        )

    def list_providers(self, catalog_path: str | None) -> StudioProviderListResponse:
        resolved_path = self._path_policy.resolve_provider_catalog_path(catalog_path)
        providers = self._load_provider_catalog(resolved_path)
        items = [self._provider_summary(provider, resolved_path) for provider in providers]
        return StudioProviderListResponse(
            catalog_path=str(resolved_path),
            provider_count=len(items),
            items=items,
        )

    def list_models(self, *, catalog_path: str | None) -> StudioModelListResponse:
        resolved_path = self._path_policy.resolve_provider_catalog_path(catalog_path)
        service = ModelRegistryService(catalog_path=resolved_path)
        items = service.list_registry()
        return StudioModelListResponse(
            items=[StudioModelProviderSummary.model_validate(item) for item in items]
        )

    def discover_models(
        self,
        *,
        payload: StudioModelDiscoverRequest,
        catalog_path: str | None,
    ) -> StudioModelProviderSummary:
        resolved_path = self._path_policy.resolve_provider_catalog_path(catalog_path)
        service = ModelRegistryService(catalog_path=resolved_path)
        try:
            item = service.discover_models(
                source=payload.source,
                provider_id=payload.provider_id,
            )
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=400, detail=f"failed to discover models: {exc}") from exc
        return StudioModelProviderSummary.model_validate(item)

    def select_model(
        self,
        *,
        payload: StudioModelSelectionRequest,
        catalog_path: str | None,
    ) -> StudioModelProviderSummary:
        resolved_path = self._path_policy.resolve_provider_catalog_path(catalog_path)
        service = ModelRegistryService(catalog_path=resolved_path)
        try:
            item = service.select_model(
                source=payload.source,
                provider_id=payload.provider_id,
                model_id=payload.model_id,
            )
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=400, detail=f"failed to select model: {exc}") from exc
        return StudioModelProviderSummary.model_validate(item)

    def set_model_role(
        self,
        *,
        payload: StudioModelRoleRequest,
        catalog_path: str | None,
    ) -> StudioModelProviderSummary:
        resolved_path = self._path_policy.resolve_provider_catalog_path(catalog_path)
        service = ModelRegistryService(catalog_path=resolved_path)
        try:
            item = service.set_model_role(
                source=payload.source,
                provider_id=payload.provider_id,
                model_id=payload.model_id,
                model_role=payload.model_role,
            )
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=400, detail=f"failed to set model role: {exc}") from exc
        return StudioModelProviderSummary.model_validate(item)

    def probe_model_capabilities(
        self,
        *,
        payload: StudioModelCapabilityProbeRequest,
        catalog_path: str | None,
    ) -> StudioModelCapabilityProbeResponse:
        resolved_path = self._path_policy.resolve_provider_catalog_path(catalog_path)
        service = ModelCapabilityProbeService(catalog_path=resolved_path)
        try:
            item = service.probe_model(
                source=payload.source,
                provider_id=payload.provider_id,
                model_id=payload.model_id,
            )
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(
                status_code=400,
                detail=f"failed to probe model capabilities: {exc}",
            ) from exc
        return StudioModelCapabilityProbeResponse.model_validate(item)

    def list_feature_bindings(
        self,
        *,
        catalog_path: str | None,
    ) -> StudioFeatureModelBindingsResponse:
        resolved_path = self._path_policy.resolve_provider_catalog_path(catalog_path)
        service = ModelRegistryService(catalog_path=resolved_path)
        items = service.list_feature_bindings()
        return StudioFeatureModelBindingsResponse(
            items=[StudioFeatureModelBindingSummary.model_validate(item) for item in items]
        )

    def bind_feature_model(
        self,
        *,
        payload: StudioFeatureModelBindingRequest,
        catalog_path: str | None,
    ) -> StudioFeatureModelBindingSummary:
        resolved_path = self._path_policy.resolve_provider_catalog_path(catalog_path)
        service = ModelRegistryService(catalog_path=resolved_path)
        try:
            item = service.bind_feature_model(
                feature_role=payload.feature_role,
                source=payload.source,
                provider_id=payload.provider_id,
                model_id=payload.model_id,
            )
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=400, detail=f"failed to bind feature model: {exc}") from exc
        return StudioFeatureModelBindingSummary.model_validate(item)

    def clear_feature_model_binding(
        self,
        *,
        feature_role: str,
        catalog_path: str | None,
    ) -> StudioFeatureModelBindingClearResponse:
        resolved_path = self._path_policy.resolve_provider_catalog_path(catalog_path)
        service = ModelRegistryService(catalog_path=resolved_path)
        try:
            item = service.clear_feature_model_binding(feature_role=feature_role)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=400, detail=f"failed to clear feature model binding: {exc}") from exc
        return StudioFeatureModelBindingClearResponse.model_validate(item)

    def validate_provider_connection(
        self,
        *,
        payload: StudioProviderValidationRequest,
    ) -> StudioProviderValidationResponse:
        api_base = self._path_policy.normalize_text(payload.api_base)
        if not api_base:
            raise HTTPException(status_code=400, detail="api_base is required")
        api_type = str(payload.api_type)
        provider_type = self._to_discovery_provider_type(api_type, api_base)
        api_key = self._effective_provider_api_key(
            api_type=api_type,
            api_base=api_base,
            api_key=payload.api_key,
        )
        if not api_key and provider_type != ProviderType.OLLAMA:
            raise HTTPException(status_code=400, detail="api_key is required")

        try:
            discovered, latest = self._discover_models_for_provider_payload(
                api_type=api_type,
                api_base=api_base,
                api_key=api_key,
            )
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(
                status_code=400,
                detail=f"failed to validate provider connection: {exc}",
            ) from exc

        status = "reachable" if discovered else "reachable_no_models"
        if discovered:
            message = (
                f"Connection ok. Discovered {len(discovered)} model(s). "
                "Use Discover Models to import them into the draft."
            )
        else:
            message = (
                "Connection ok, but the provider returned no models. "
                "Enter a model id manually if this supplier requires explicit onboarding."
            )
        return StudioProviderValidationResponse(
            status=status,
            api_type=str(payload.api_type),
            api_base=api_base,
            resolved_provider_type=provider_type.value,
            connection_ok=True,
            model_count=len(discovered),
            latest_model_id=latest,
            message=message,
            models=[
                StudioProviderModelSummary(
                    model_id=model_id,
                    display_name=model_id,
                    is_default=bool(latest and model_id == latest),
                )
                for model_id in discovered
            ],
        )

    def discover_provider_models(
        self,
        *,
        payload: StudioProviderModelDiscoveryRequest,
    ) -> StudioProviderModelDiscoveryResponse:
        api_base = self._path_policy.normalize_text(payload.api_base)
        if not api_base:
            raise HTTPException(status_code=400, detail="api_base is required")
        api_key = self._effective_provider_api_key(
            api_type=str(payload.api_type),
            api_base=api_base,
            api_key=payload.api_key,
        )
        if not api_key and self._to_discovery_provider_type(str(payload.api_type), api_base) != ProviderType.OLLAMA:
            raise HTTPException(status_code=400, detail="api_key is required")
        try:
            discovered, latest = self._discover_models_for_provider_payload(
                api_type=str(payload.api_type),
                api_base=api_base,
                api_key=api_key,
            )
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(
                status_code=400,
                detail=f"failed to discover models for provider setup: {exc}",
            ) from exc
        if not discovered:
            raise HTTPException(status_code=400, detail="no models discovered")
        return StudioProviderModelDiscoveryResponse(
            latest_model_id=latest,
            models=[
                StudioProviderModelSummary(
                    model_id=model_id,
                    display_name=model_id,
                    is_default=bool(latest and model_id == latest),
                )
                for model_id in discovered
            ],
        )

    def create_provider(
        self,
        *,
        payload: StudioProviderUpsertRequest,
        catalog_path: str | None,
    ) -> StudioProviderSummary:
        resolved_path = self._path_policy.resolve_provider_catalog_path(catalog_path)
        providers = self._load_provider_catalog(resolved_path)
        try:
            provider = normalize_provider_config(self._prepare_provider_payload(payload))
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=400, detail=f"invalid provider payload: {exc}") from exc

        for item in providers:
            if item.id == provider.id:
                raise HTTPException(status_code=409, detail=f"provider id already exists: {provider.id}")

        providers.append(provider)
        try:
            catalog = normalize_provider_catalog({"providers": [item.model_dump() for item in providers]})
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=400, detail=f"invalid provider catalog update: {exc}") from exc
        self._atomic_write_json(resolved_path, catalog.model_dump())

        for item in catalog.providers:
            if item.id == provider.id:
                return self._provider_summary(item, resolved_path)
        raise HTTPException(status_code=500, detail="failed to persist provider.")

    def update_provider(
        self,
        *,
        provider_id: str,
        payload: StudioProviderUpsertRequest,
        catalog_path: str | None,
    ) -> StudioProviderSummary:
        resolved_path = self._path_policy.resolve_provider_catalog_path(catalog_path)
        providers = self._load_provider_catalog(resolved_path)
        target = self._path_policy.normalize_text(provider_id)

        existing_ids = {item.id for item in providers}
        if target not in existing_ids:
            raise HTTPException(status_code=404, detail=f"provider not found: {provider_id}")

        update_payload = self._prepare_provider_payload(payload)
        update_payload["id"] = target
        try:
            updated = normalize_provider_config(update_payload)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=400, detail=f"invalid provider payload: {exc}") from exc

        merged: list[Any] = []
        for item in providers:
            if item.id == target:
                merged.append(updated)
            else:
                merged.append(item)

        try:
            catalog = normalize_provider_catalog({"providers": [item.model_dump() for item in merged]})
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=400, detail=f"invalid provider catalog update: {exc}") from exc
        self._atomic_write_json(resolved_path, catalog.model_dump())

        for item in catalog.providers:
            if item.id == target:
                return self._provider_summary(item, resolved_path)
        raise HTTPException(status_code=500, detail="failed to update provider.")

    def delete_provider(
        self,
        *,
        provider_id: str,
        catalog_path: str | None,
    ) -> StudioProviderDeleteResponse:
        resolved_path = self._path_policy.resolve_provider_catalog_path(catalog_path)
        providers = self._load_provider_catalog(resolved_path)
        target = self._path_policy.normalize_text(provider_id)
        retained = [item for item in providers if item.id != target]
        if len(retained) == len(providers):
            raise HTTPException(status_code=404, detail=f"provider not found: {provider_id}")

        catalog = normalize_provider_catalog({"providers": [item.model_dump() for item in retained]})
        self._atomic_write_json(resolved_path, catalog.model_dump())
        return StudioProviderDeleteResponse(
            status="deleted",
            provider_id=target,
            catalog_path=str(resolved_path),
        )

    def get_provider_health(
        self,
        *,
        provider_id: str,
        catalog_path: str | None,
    ) -> StudioProviderHealthResponse:
        resolved_path = self._path_policy.resolve_provider_catalog_path(catalog_path)
        providers = self._load_provider_catalog(resolved_path)
        target = self._path_policy.normalize_text(provider_id)
        provider = next((item for item in providers if item.id == target), None)
        if provider is None:
            raise HTTPException(status_code=404, detail=f"provider not found: {provider_id}")

        breakers = get_circuit_breaker_registry()
        health_monitor = get_health_monitor()
        breaker = breakers.snapshot(str(provider.id))
        health = health_monitor.snapshot(str(provider.id), breaker_state=str(breaker.get("state", "closed")))
        return StudioProviderHealthResponse(
            provider_id=str(provider.id),
            status=str(health.get("status", "unknown")),
            breaker_state=str(breaker.get("state", "closed")),
            selected_count=int(health.get("selected_count", 0)),
            total_requests=int(health.get("total_requests", 0)),
            total_successes=int(health.get("total_successes", 0)),
            total_failures=int(health.get("total_failures", 0)),
            consecutive_failures=int(health.get("consecutive_failures", 0)),
            error_rate=float(health.get("error_rate", 0.0)),
            last_selected_at=health.get("last_selected_at"),
            last_success_at=health.get("last_success_at"),
            last_failure_at=health.get("last_failure_at"),
            last_failure_reason=health.get("last_failure_reason"),
        )

    @staticmethod
    def _load_provider_catalog(path: Path) -> list[Any]:
        if not path.exists():
            return []
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            catalog = normalize_provider_catalog(payload)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=400, detail=f"invalid provider catalog: {exc}") from exc
        return list(catalog.providers)

    @staticmethod
    def _run_coroutine_sync(coro: Any) -> Any:
        try:
            import asyncio

            asyncio.get_running_loop()
        except RuntimeError:
            import asyncio

            return asyncio.run(coro)

        result: dict[str, Any] = {}
        error: dict[str, Exception] = {}

        def _runner() -> None:
            import asyncio

            try:
                result["value"] = asyncio.run(coro)
            except Exception as exc:  # pragma: no cover - defensive
                error["value"] = exc

        import threading

        thread = threading.Thread(target=_runner, daemon=True)
        thread.start()
        thread.join()
        if "value" in error:
            raise error["value"]
        return result.get("value")

    @staticmethod
    def _looks_like_ollama_endpoint(api_base: str) -> bool:
        normalized = " ".join((api_base or "").strip().split())
        if not normalized:
            return False
        try:
            parsed = urlsplit(normalized)
        except Exception:
            return "11434" in normalized
        host = str(parsed.hostname or "").strip().lower()
        if host in {"localhost", "127.0.0.1", "::1"} and parsed.port == 11434:
            return True
        return "11434" in normalized

    @classmethod
    def _to_discovery_provider_type(cls, api_type: str, api_base: str | None = None) -> ProviderType:
        normalized = normalize_provider_api_type(api_type).value
        if normalized == "openai" and cls._looks_like_ollama_endpoint(api_base or ""):
            return ProviderType.OLLAMA
        if normalized == "openai":
            return ProviderType.OPENAI
        if normalized == "anthropic":
            return ProviderType.ANTHROPIC
        raise ValueError(f"unsupported provider api_type for discovery: {api_type}")

    def _build_models_endpoint(self, api_base: str, api_type: str) -> str:
        base = api_base.rstrip("/")
        if base.endswith("/models"):
            return base
        if self._to_discovery_provider_type(api_type, api_base) == ProviderType.OLLAMA:
            if base.endswith("/v1"):
                return f"{base}/models"
            return f"{base}/v1/models"
        return f"{base}/models"

    def _effective_provider_api_key(
        self,
        *,
        api_type: str,
        api_base: str,
        api_key: str | None,
    ) -> str:
        normalized_key = self._path_policy.normalize_text(api_key)
        if normalized_key:
            return normalized_key
        if self._to_discovery_provider_type(api_type, api_base) == ProviderType.OLLAMA:
            return _OLLAMA_SENTINEL_API_KEY
        return ""

    def _discover_models_for_provider_payload(
        self,
        *,
        api_type: str,
        api_base: str,
        api_key: str,
    ) -> tuple[list[str], str | None]:
        service = ModelDiscoveryService()
        provider_type = self._to_discovery_provider_type(api_type, api_base)
        endpoint = self._build_models_endpoint(api_base, api_type)
        import asyncio

        result = self._run_coroutine_sync(
            asyncio.wait_for(
                service.discover_models(
                    provider=provider_type,
                    api_key=api_key,
                    api_base=endpoint,
                    use_cache=False,
                ),
                timeout=15.0,
            )
        )
        models = [
            item.id
            for item in result.available_models
            if isinstance(item.id, str) and item.id.strip()
        ]
        deduped: list[str] = []
        seen: set[str] = set()
        for model_id in models:
            lowered = model_id.lower()
            if lowered in seen:
                continue
            seen.add(lowered)
            deduped.append(model_id)
        recommendation = recommend_discovered_model(provider_type, result)
        return deduped, recommendation.model_id if recommendation is not None else None

    def _prepare_provider_payload(self, payload: StudioProviderUpsertRequest) -> dict[str, Any]:
        prepared = payload.model_dump()
        prepared["api_type"] = normalize_provider_api_type(prepared.get("api_type")).value
        prepared["api_key"] = self._effective_provider_api_key(
            api_type=str(prepared.get("api_type") or ""),
            api_base=str(prepared.get("api_base") or ""),
            api_key=prepared.get("api_key"),
        )
        model_id = self._path_policy.normalize_text(payload.model_id)
        model_display_name = self._path_policy.normalize_text(payload.model_display_name)
        model_role = self._path_policy.normalize_text(payload.model_role)
        selected_model_id = self._path_policy.normalize_text(payload.selected_model_id)

        models = [self._path_policy.normalize_text(item) for item in prepared.get("models", [])]
        models = [item for item in models if item]
        model_display_names = {
            self._path_policy.normalize_text(str(key)): self._path_policy.normalize_text(str(value))
            for key, value in prepared.get("model_display_names", {}).items()
            if self._path_policy.normalize_text(str(key)) and self._path_policy.normalize_text(str(value))
        }
        model_context_windows = {
            self._path_policy.normalize_text(str(key)): int(value)
            for key, value in prepared.get("model_context_windows", {}).items()
            if self._path_policy.normalize_text(str(key)) and int(value) > 0
        }
        model_learned_token_limits = {
            self._path_policy.normalize_text(str(key)): int(value)
            for key, value in prepared.get("model_learned_token_limits", {}).items()
            if self._path_policy.normalize_text(str(key)) and int(value) > 0
        }
        model_metadata = self._sanitize_model_metadata(prepared.get("model_metadata"))

        for raw_key, raw_role in prepared.get("model_roles", {}).items():
            normalized_model_id = self._path_policy.normalize_text(str(raw_key))
            if not normalized_model_id:
                continue
            role = normalize_model_role(raw_role, allow_unclassified=True).value
            model_metadata.setdefault(normalized_model_id, {})["model_role"] = role

        if model_id:
            models = [model_id, *[item for item in models if item != model_id]]
            if model_display_name:
                model_display_names[model_id] = model_display_name

        if not models and payload.auto_discover_models:
            discovered, latest = self._discover_models_for_provider_payload(
                api_type=str(payload.api_type),
                api_base=str(payload.api_base),
                api_key=str(prepared.get("api_key") or ""),
            )
            if not discovered:
                raise HTTPException(
                    status_code=400,
                    detail="no models discovered; provider not created",
                )
            selected = selected_model_id
            if not selected:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"models discovered ({len(discovered)} available, latest={latest or '-'}) "
                        "but no selected_model_id provided; "
                        "provider not created"
                    ),
                )
            if selected not in discovered:
                raise HTTPException(
                    status_code=400,
                    detail=f"selected_model_id '{selected}' is not in discovered models",
                )
            models = [selected, *[item for item in discovered if item != selected]]
            model_display_names = {item: item for item in models}
            if not model_id:
                model_id = selected

        if not models:
            raise HTTPException(
                status_code=400,
                detail="provider requires at least one model; provider not created",
            )

        target_model_id = model_id or selected_model_id
        if target_model_id:
            if target_model_id not in models:
                models = [target_model_id, *[item for item in models if item != target_model_id]]
            if model_display_name:
                model_display_names[target_model_id] = model_display_name
            if model_role:
                model_metadata.setdefault(target_model_id, {})["model_role"] = normalize_model_role(
                    model_role,
                    allow_unclassified=True,
                ).value
            if payload.model_context_window is not None:
                model_context_windows[target_model_id] = int(payload.model_context_window)
            if payload.model_learned_token_limit is not None:
                model_learned_token_limits[target_model_id] = int(payload.model_learned_token_limit)
            if payload.supports_tools is not None:
                model_metadata.setdefault(target_model_id, {})["supports_tools"] = bool(
                    payload.supports_tools
                )
            if payload.supports_thinking is not None:
                model_metadata.setdefault(target_model_id, {})["supports_thinking"] = bool(
                    payload.supports_thinking
                )

        prepared["models"] = models
        prepared["model_display_names"] = model_display_names
        prepared["model_context_windows"] = model_context_windows
        prepared["model_learned_token_limits"] = model_learned_token_limits
        prepared["model_metadata"] = model_metadata
        prepared.pop("model_id", None)
        prepared.pop("model_display_name", None)
        prepared.pop("model_role", None)
        prepared.pop("model_roles", None)
        prepared.pop("model_context_window", None)
        prepared.pop("model_learned_token_limit", None)
        prepared.pop("supports_tools", None)
        prepared.pop("supports_thinking", None)
        prepared.pop("auto_discover_models", None)
        prepared.pop("selected_model_id", None)
        return prepared

    def _sanitize_model_metadata(self, raw_metadata: Any) -> dict[str, dict[str, Any]]:
        if not isinstance(raw_metadata, dict):
            return {}
        sanitized: dict[str, dict[str, Any]] = {}
        for raw_key, raw_value in raw_metadata.items():
            model_id = self._path_policy.normalize_text(str(raw_key))
            if not model_id or not isinstance(raw_value, dict):
                continue
            cleaned: dict[str, Any] = {}
            for raw_meta_key, raw_meta_value in raw_value.items():
                meta_key = self._path_policy.normalize_text(str(raw_meta_key))
                if not meta_key:
                    continue
                if meta_key == "model_role":
                    cleaned[meta_key] = normalize_model_role(
                        raw_meta_value,
                        allow_unclassified=True,
                    ).value
                    continue
                if isinstance(raw_meta_value, (str, int, float, bool)) or raw_meta_value is None:
                    cleaned[meta_key] = raw_meta_value
            if cleaned:
                sanitized[model_id] = cleaned
        return sanitized

    @staticmethod
    def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_suffix(path.suffix + ".tmp")
        tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp_path.replace(path)

    @staticmethod
    def _provider_summary(provider: Any, catalog_path: Path) -> StudioProviderSummary:
        health_monitor = get_health_monitor()
        breakers = get_circuit_breaker_registry()
        breaker = breakers.snapshot(str(provider.id))
        health = health_monitor.snapshot(str(provider.id), breaker_state=str(breaker.get("state", "closed")))
        redacted = provider.redacted()

        return StudioProviderSummary(
            id=str(provider.id),
            name=provider.name,
            api_type=provider.api_type.value,
            api_base=provider.api_base,
            api_key_masked=str(redacted.get("api_key", "")),
            models=list(provider.models),
            model_display_names=dict(provider.model_display_names),
            enabled=bool(provider.enabled),
            priority=int(provider.priority),
            timeout=int(provider.timeout),
            headers=dict(provider.headers),
            catalog_path=str(catalog_path),
            health_status=str(health.get("status", "unknown")),
            breaker_state=str(breaker.get("state", "closed")),
            selected_count=int(health.get("selected_count", 0)),
            error_rate=float(health.get("error_rate", 0.0)),
            consecutive_failures=int(health.get("consecutive_failures", 0)),
        )
