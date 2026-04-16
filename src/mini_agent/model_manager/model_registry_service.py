"""Unified model registry service for custom and preset providers."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import json
from pathlib import Path
import threading
from typing import Any

from mini_agent.config_bootstrap import load_local_env_files
from mini_agent.model_manager.bootstrap import BootstrapLLMSettings
from mini_agent.model_manager.model_discovery import (
    ModelDiscoveryService,
    ProviderType,
    discovery_confidence_for_source,
    infer_model_capabilities,
    recommend_discovered_model,
    resolve_known_context_window,
)
from mini_agent.model_manager.preset_providers import (
    PRESET_PROVIDERS,
    PresetProvider,
    get_preset_provider_config,
)
from mini_agent.model_manager.provider import (
    ProviderAPIType,
    ProviderCatalog,
    ProviderConfig,
    normalize_provider_catalog,
)


PRESET_STATE_PATH = Path.home() / ".mini-agent" / "preset_models.json"
BOOTSTRAP_PROVIDER_ID = "bootstrap-config"
_MODEL_METADATA_KEYS = (
    "discovered_at",
    "discovery_source",
    "discovery_confidence",
    "supports_tools",
    "supports_tools_truth",
    "supports_tools_confidence",
    "supports_tools_source",
    "supports_thinking",
    "supports_thinking_truth",
    "supports_thinking_confidence",
    "supports_thinking_source",
)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _run_coroutine_sync(coro: Any) -> Any:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    result: dict[str, Any] = {}
    error: dict[str, Exception] = {}

    def _runner() -> None:
        try:
            result["value"] = asyncio.run(coro)
        except Exception as exc:  # pragma: no cover - defensive
            error["value"] = exc

    thread = threading.Thread(target=_runner, daemon=True)
    thread.start()
    thread.join()

    if "value" in error:
        raise error["value"]
    return result.get("value")


def _normalize_source(value: str) -> str:
    normalized = " ".join((value or "").strip().split()).lower()
    if normalized not in {"custom", "preset"}:
        raise ValueError(f"unsupported source: {value}")
    return normalized


def _to_discovery_type(api_type: str) -> ProviderType:
    normalized = " ".join((api_type or "").strip().split()).lower()
    if normalized == "openai":
        return ProviderType.OPENAI
    if normalized == "anthropic":
        return ProviderType.ANTHROPIC
    if normalized == "minimax":
        return ProviderType.MINIMAX
    if normalized == "ollama":
        return ProviderType.OLLAMA
    if normalized == "custom":
        return ProviderType.OPENAI
    # Unknown provider protocols fall back to OpenAI-compatible discovery only
    # for defensive loading paths. Active ops/runtime inputs should validate
    # earlier and avoid arriving here with unsupported protocol names.
    return ProviderType.OPENAI


def _build_models_endpoint(api_base: str, discovery_type: ProviderType) -> str:
    base = api_base.rstrip("/")
    if base.endswith("/models"):
        return base
    if discovery_type == ProviderType.OLLAMA:
        if base.endswith("/v1"):
            return f"{base}/models"
        return f"{base}/v1/models"
    return f"{base}/models"


def _bootstrap_provider_api_type(value: str | None) -> ProviderAPIType:
    normalized = " ".join((value or "").strip().split()).lower()
    if normalized == ProviderAPIType.ANTHROPIC.value:
        return ProviderAPIType.ANTHROPIC
    return ProviderAPIType.OPENAI


def _build_bootstrap_provider(bootstrap_llm: BootstrapLLMSettings) -> ProviderConfig:
    return ProviderConfig(
        id=BOOTSTRAP_PROVIDER_ID,
        name="Bootstrap Config Provider",
        api_type=_bootstrap_provider_api_type(bootstrap_llm.provider),
        api_base=str(bootstrap_llm.api_base),
        api_key=str(bootstrap_llm.api_key),
        models=[str(bootstrap_llm.model)],
        enabled=True,
        priority=0,
    )


def _normalize_model_id(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _normalize_context_window(value: Any) -> int | None:
    try:
        parsed = int(value)
    except Exception:
        return None
    return parsed if parsed > 0 else None


def _normalize_token_limit(value: Any) -> int | None:
    try:
        parsed = int(value)
    except Exception:
        return None
    return parsed if parsed > 0 else None


def _normalize_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = " ".join(value.strip().split()).lower()
        if normalized in {"true", "1", "yes", "on"}:
            return True
        if normalized in {"false", "0", "no", "off"}:
            return False
        return None
    if isinstance(value, int):
        return bool(value)
    return None


def _normalize_optional_text(value: Any) -> str | None:
    normalized = _normalize_model_id(value)
    return normalized or None


def _normalize_capability_truth(value: Any) -> str | None:
    normalized = _normalize_optional_text(value)
    if normalized is None:
        return None
    lowered = normalized.lower()
    if lowered not in {"supported", "unsupported", "unknown"}:
        return None
    return lowered


def _normalize_model_metadata_entry(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}

    normalized: dict[str, Any] = {}
    discovered_at = _normalize_optional_text(value.get("discovered_at"))
    if discovered_at:
        normalized["discovered_at"] = discovered_at
    discovery_source = _normalize_optional_text(value.get("discovery_source"))
    if discovery_source:
        normalized["discovery_source"] = discovery_source
    discovery_confidence = _normalize_optional_text(value.get("discovery_confidence"))
    if discovery_confidence:
        normalized["discovery_confidence"] = discovery_confidence
    supports_tools = _normalize_bool(value.get("supports_tools"))
    if supports_tools is not None:
        normalized["supports_tools"] = supports_tools
    supports_tools_truth = _normalize_capability_truth(value.get("supports_tools_truth"))
    if supports_tools_truth:
        normalized["supports_tools_truth"] = supports_tools_truth
    supports_tools_confidence = _normalize_optional_text(value.get("supports_tools_confidence"))
    if supports_tools_confidence:
        normalized["supports_tools_confidence"] = supports_tools_confidence.lower()
    supports_tools_source = _normalize_optional_text(value.get("supports_tools_source"))
    if supports_tools_source:
        normalized["supports_tools_source"] = supports_tools_source.lower()
    supports_thinking = _normalize_bool(value.get("supports_thinking"))
    if supports_thinking is not None:
        normalized["supports_thinking"] = supports_thinking
    supports_thinking_truth = _normalize_capability_truth(value.get("supports_thinking_truth"))
    if supports_thinking_truth:
        normalized["supports_thinking_truth"] = supports_thinking_truth
    supports_thinking_confidence = _normalize_optional_text(value.get("supports_thinking_confidence"))
    if supports_thinking_confidence:
        normalized["supports_thinking_confidence"] = supports_thinking_confidence.lower()
    supports_thinking_source = _normalize_optional_text(value.get("supports_thinking_source"))
    if supports_thinking_source:
        normalized["supports_thinking_source"] = supports_thinking_source.lower()
    return normalized


class ModelRegistryService:
    """Registry service joining custom providers and preset providers."""

    def __init__(
        self,
        *,
        catalog_path: Path | None = None,
        preset_state_path: Path | None = None,
    ) -> None:
        self.catalog_path = (
            catalog_path.expanduser().resolve()
            if catalog_path is not None
            else (Path.home() / ".mini-agent" / "providers.json").resolve()
        )
        self.preset_state_path = (
            preset_state_path.expanduser().resolve()
            if preset_state_path is not None
            else PRESET_STATE_PATH
        )

    def _load_custom_catalog(self) -> ProviderCatalog:
        if not self.catalog_path.exists():
            return ProviderCatalog(providers=[])
        payload = json.loads(self.catalog_path.read_text(encoding="utf-8"))
        return normalize_provider_catalog(payload)

    def _save_custom_catalog(self, catalog: ProviderCatalog) -> None:
        self.catalog_path.parent.mkdir(parents=True, exist_ok=True)
        self.catalog_path.write_text(
            json.dumps(catalog.model_dump(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _load_preset_state(self) -> dict[str, Any]:
        if not self.preset_state_path.exists():
            return {"providers": {}}
        try:
            payload = json.loads(self.preset_state_path.read_text(encoding="utf-8"))
        except Exception:
            return {"providers": {}}
        if not isinstance(payload, dict):
            return {"providers": {}}
        providers = payload.get("providers")
        if not isinstance(providers, dict):
            providers = {}
        return {"providers": providers}

    def _save_preset_state(self, payload: dict[str, Any]) -> None:
        self.preset_state_path.parent.mkdir(parents=True, exist_ok=True)
        self.preset_state_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _discover_models(
        self,
        *,
        provider_type: ProviderType,
        api_key: str,
        api_base: str,
        curated_order: list[str] | None = None,
        official_default: str | None = None,
    ) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
        service = ModelDiscoveryService()
        endpoint = _build_models_endpoint(api_base, provider_type)
        result = _run_coroutine_sync(
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
        deduped: list[dict[str, Any]] = []
        seen: set[str] = set()
        for item in result.available_models:
            model_id = _normalize_model_id(item.id)
            if not model_id:
                continue
            key = model_id.lower()
            if key in seen:
                continue
            seen.add(key)
            context_window = _normalize_context_window(item.context_window) or resolve_known_context_window(
                provider_type,
                model_id,
            )
            metadata = _normalize_model_metadata_entry(
                {
                    "discovered_at": result.fetched_at.isoformat(),
                    "discovery_source": result.discovery_source,
                    "discovery_confidence": discovery_confidence_for_source(result.discovery_source),
                    **infer_model_capabilities(
                        provider_type,
                        model_id,
                        raw_capabilities=item.capabilities,
                    ),
                }
            )
            entry = {
                "model_id": model_id,
                "display_name": _normalize_model_id(item.name) or model_id,
            }
            if context_window is not None:
                entry["context_window"] = context_window
            entry.update(metadata)
            deduped.append(entry)
        recommendation = recommend_discovered_model(
            provider_type,
            result,
            curated_order=curated_order,
            official_default=official_default,
        )
        recommendation_payload = (
            {
                "model_id": recommendation.model_id,
                "strategy": recommendation.strategy,
                "confidence": recommendation.confidence,
                "discovery_source": recommendation.discovery_source,
            }
            if recommendation is not None
            else None
        )
        return deduped, recommendation_payload

    def _preset_provider_from_id(self, provider_id: str) -> PresetProvider:
        normalized = " ".join((provider_id or "").strip().split()).lower()
        return PresetProvider(normalized)

    @staticmethod
    def _model_entries(
        model_ids: list[str],
        default_model_id: str | None,
        *,
        display_names: dict[str, str] | None = None,
        context_windows: dict[str, int] | None = None,
        learned_token_limits: dict[str, int] | None = None,
        model_metadata: dict[str, dict[str, Any]] | None = None,
    ) -> list[dict[str, Any]]:
        entries: list[dict[str, Any]] = []
        selected = default_model_id or (model_ids[0] if model_ids else None)
        for model_id in model_ids:
            entry = {
                "model_id": model_id,
                "display_name": _normalize_model_id((display_names or {}).get(model_id)) or model_id,
                "is_default": bool(selected and model_id == selected),
            }
            context_window = _normalize_context_window((context_windows or {}).get(model_id))
            if context_window is not None:
                entry["context_window"] = context_window
            learned_token_limit = _normalize_token_limit((learned_token_limits or {}).get(model_id))
            if learned_token_limit is not None:
                entry["learned_token_limit"] = learned_token_limit
            metadata = _normalize_model_metadata_entry((model_metadata or {}).get(model_id))
            if metadata:
                entry.update(metadata)
            entries.append(entry)
        return entries

    @staticmethod
    def _provider_summary_from_custom(
        *,
        provider: ProviderConfig,
        model_ids: list[str],
        default_model_id: str | None,
        default_model_strategy: str | None = None,
        default_model_confidence: str | None = None,
    ) -> dict[str, Any]:
        models = ModelRegistryService._model_entries(
            model_ids,
            default_model_id,
            display_names=provider.model_display_names,
            context_windows=provider.model_context_windows,
            learned_token_limits=provider.model_learned_token_limits,
            model_metadata=provider.model_metadata,
        )
        return {
            "source": "custom",
            "provider_id": provider.id,
            "provider_name": provider.name,
            "api_type": provider.api_type.value,
            "api_base": provider.api_base,
            "models": models,
            "default_model_id": default_model_id,
            "default_model_strategy": default_model_strategy,
            "default_model_confidence": default_model_confidence,
            "priority": provider.priority,
            "enabled": provider.enabled,
        }

    @staticmethod
    def _provider_summary_from_preset(
        *,
        provider_id: str,
        provider_name: str,
        api_type: str,
        api_base: str,
        model_ids: list[str],
        default_model_id: str | None,
        display_names: dict[str, str] | None = None,
        context_windows: dict[str, int] | None = None,
        learned_token_limits: dict[str, int] | None = None,
        model_metadata: dict[str, dict[str, Any]] | None = None,
        default_model_strategy: str | None = None,
        default_model_confidence: str | None = None,
    ) -> dict[str, Any]:
        return {
            "source": "preset",
            "provider_id": provider_id,
            "provider_name": provider_name,
            "api_type": api_type,
            "api_base": api_base,
            "models": ModelRegistryService._model_entries(
                model_ids,
                default_model_id,
                display_names=display_names,
                context_windows=context_windows,
                learned_token_limits=learned_token_limits,
                model_metadata=model_metadata,
            ),
            "default_model_id": default_model_id or (model_ids[0] if model_ids else None),
            "default_model_strategy": default_model_strategy,
            "default_model_confidence": default_model_confidence,
            "priority": -100,
            "enabled": True,
        }

    @staticmethod
    def _reorder_model_entries(
        entries: list[dict[str, Any]],
        selected_model_id: str | None,
    ) -> list[dict[str, Any]]:
        if not entries:
            return []
        normalized_selected = _normalize_model_id(selected_model_id)
        if not normalized_selected:
            return list(entries)
        selected: list[dict[str, Any]] = []
        others: list[dict[str, Any]] = []
        for entry in entries:
            model_id = _normalize_model_id(entry.get("model_id"))
            copied = dict(entry)
            if model_id == normalized_selected:
                selected.append(copied)
            else:
                others.append(copied)
        return [*selected, *others] if selected else list(entries)

    @staticmethod
    def _merge_custom_provider_discovery(
        *,
        provider: ProviderConfig,
        discovered_entries: list[dict[str, Any]],
        selected_model_id: str | None,
    ) -> ProviderConfig:
        existing_ids_by_lower = {
            model_id.lower(): model_id
            for model_id in provider.models
            if _normalize_model_id(model_id)
        }
        discovered_by_lower: dict[str, dict[str, Any]] = {}
        discovered_order: list[str] = []
        for entry in discovered_entries:
            model_id = _normalize_model_id(entry.get("model_id"))
            if not model_id:
                continue
            lowered = model_id.lower()
            if lowered not in discovered_by_lower:
                discovered_order.append(lowered)
            discovered_by_lower[lowered] = dict(entry)

        merged_order_lower: list[str] = []
        seen: set[str] = set()
        for model_id in provider.models:
            lowered = _normalize_model_id(model_id).lower()
            if not lowered or lowered in seen:
                continue
            seen.add(lowered)
            merged_order_lower.append(lowered)
        for lowered in discovered_order:
            if lowered in seen:
                continue
            seen.add(lowered)
            merged_order_lower.append(lowered)

        normalized_selected = _normalize_model_id(selected_model_id).lower()
        if normalized_selected and normalized_selected in merged_order_lower:
            merged_order_lower = [
                normalized_selected,
                *[item for item in merged_order_lower if item != normalized_selected],
            ]

        merged_models: list[str] = []
        merged_display_names: dict[str, str] = {}
        merged_context_windows: dict[str, int] = {}
        merged_learned_token_limits: dict[str, int] = {}
        merged_model_metadata: dict[str, dict[str, Any]] = {}

        for lowered in merged_order_lower:
            canonical_model_id = existing_ids_by_lower.get(lowered) or _normalize_model_id(
                discovered_by_lower.get(lowered, {}).get("model_id")
            )
            if not canonical_model_id:
                continue
            merged_models.append(canonical_model_id)

            discovered_entry = discovered_by_lower.get(lowered, {})
            discovered_display_name = _normalize_model_id(discovered_entry.get("display_name"))
            merged_display_names[canonical_model_id] = (
                provider.model_display_names.get(canonical_model_id)
                or discovered_display_name
                or canonical_model_id
            )

            discovered_context_window = _normalize_context_window(discovered_entry.get("context_window"))
            existing_context_window = _normalize_context_window(
                provider.model_context_windows.get(canonical_model_id)
            )
            effective_context_window = (
                discovered_context_window
                if discovered_context_window is not None
                else existing_context_window
            )
            if effective_context_window is not None:
                merged_context_windows[canonical_model_id] = effective_context_window

            existing_learned_token_limit = _normalize_token_limit(
                provider.model_learned_token_limits.get(canonical_model_id)
            )
            discovered_learned_token_limit = _normalize_token_limit(
                discovered_entry.get("learned_token_limit")
            )
            effective_learned_token_limit = (
                existing_learned_token_limit
                if existing_learned_token_limit is not None
                else discovered_learned_token_limit
            )
            if effective_learned_token_limit is not None:
                merged_learned_token_limits[canonical_model_id] = effective_learned_token_limit

            existing_metadata = dict(provider.model_metadata.get(canonical_model_id, {}))
            discovered_metadata = _normalize_model_metadata_entry(discovered_entry)
            effective_metadata = {
                **existing_metadata,
                **discovered_metadata,
            }
            if effective_metadata:
                merged_model_metadata[canonical_model_id] = effective_metadata

        return ProviderConfig.model_validate(
            {
                **provider.model_dump(),
                "models": merged_models,
                "model_display_names": merged_display_names,
                "model_context_windows": merged_context_windows,
                "model_learned_token_limits": merged_learned_token_limits,
                "model_metadata": merged_model_metadata,
            }
        )

    @staticmethod
    def _parse_state_models(
        raw_models: Any,
    ) -> tuple[list[str], dict[str, str], dict[str, int], dict[str, int], dict[str, dict[str, Any]]]:
        model_ids: list[str] = []
        display_names: dict[str, str] = {}
        context_windows: dict[str, int] = {}
        learned_token_limits: dict[str, int] = {}
        model_metadata: dict[str, dict[str, Any]] = {}
        seen: set[str] = set()

        if not isinstance(raw_models, list):
            return model_ids, display_names, context_windows, learned_token_limits, model_metadata

        for raw_item in raw_models:
            if isinstance(raw_item, dict):
                model_id = _normalize_model_id(raw_item.get("model_id"))
                display_name = _normalize_model_id(raw_item.get("display_name"))
                context_window = _normalize_context_window(raw_item.get("context_window"))
                learned_token_limit = _normalize_token_limit(raw_item.get("learned_token_limit"))
                metadata = _normalize_model_metadata_entry(raw_item)
            else:
                model_id = _normalize_model_id(raw_item)
                display_name = model_id
                context_window = None
                learned_token_limit = None
                metadata = {}
            if not model_id:
                continue
            lowered = model_id.lower()
            if lowered in seen:
                continue
            seen.add(lowered)
            model_ids.append(model_id)
            display_names[model_id] = display_name or model_id
            if context_window is not None:
                context_windows[model_id] = context_window
            if learned_token_limit is not None:
                learned_token_limits[model_id] = learned_token_limit
            if metadata:
                model_metadata[model_id] = metadata

        return model_ids, display_names, context_windows, learned_token_limits, model_metadata

    @staticmethod
    def _effective_limit_from_model(model: dict[str, Any]) -> int | None:
        learned = _normalize_token_limit(model.get("learned_token_limit"))
        if learned is not None:
            return learned
        return _normalize_context_window(model.get("context_window"))

    def list_registry(self) -> list[dict[str, Any]]:
        load_local_env_files()
        state = self._load_preset_state()
        state_providers: dict[str, Any] = state.get("providers", {})

        items: list[dict[str, Any]] = []

        custom_catalog = self._load_custom_catalog()
        for provider in custom_catalog.providers:
            model_ids = list(provider.models)
            default_model_id = provider.default_model if provider.models else None
            items.append(
                self._provider_summary_from_custom(
                    provider=provider,
                    model_ids=model_ids,
                    default_model_id=default_model_id,
                )
            )

        for provider in PresetProvider:
            preset = get_preset_provider_config(provider, use_latest_model=False)
            if not preset:
                continue

            state_item = state_providers.get(provider.value, {})
            stored_models = state_item.get("models", [])
            model_ids, display_names, context_windows, learned_token_limits, model_metadata = self._parse_state_models(
                stored_models
            )
            if not model_ids:
                model_ids = [str(m) for m in preset.get("models", []) if str(m).strip()]
            for model_id in model_ids:
                display_names.setdefault(model_id, model_id)
                known_context_window = resolve_known_context_window(provider.value, model_id)
                if known_context_window is not None:
                    context_windows.setdefault(model_id, known_context_window)

            default_model_id = str(state_item.get("default_model_id", "")).strip() or str(
                preset.get("model", "")
            ).strip()
            if default_model_id and default_model_id not in model_ids:
                model_ids = [default_model_id, *model_ids]
                display_names.setdefault(default_model_id, default_model_id)
                known_context_window = resolve_known_context_window(provider.value, default_model_id)
                if known_context_window is not None:
                    context_windows.setdefault(default_model_id, known_context_window)

            items.append(
                self._provider_summary_from_preset(
                    provider_id=provider.value,
                    provider_name=str(preset["name"]),
                    api_type=str(preset["api_type"]),
                    api_base=str(preset["api_base"]),
                    model_ids=model_ids,
                    default_model_id=default_model_id,
                    display_names=display_names,
                    context_windows=context_windows,
                    learned_token_limits=learned_token_limits,
                    model_metadata=model_metadata,
                    default_model_strategy=str(
                        state_item.get("default_model_strategy")
                        or preset.get("default_model_strategy")
                        or ""
                    ).strip()
                    or None,
                    default_model_confidence=str(
                        state_item.get("default_model_confidence")
                        or preset.get("default_model_confidence")
                        or ""
                    ).strip()
                    or None,
                )
            )

        custom_items = [item for item in items if item["source"] == "custom"]
        preset_items = [item for item in items if item["source"] == "preset"]
        return [*custom_items, *preset_items]

    def discover_models(self, *, source: str, provider_id: str) -> dict[str, Any]:
        normalized_source = _normalize_source(source)
        if normalized_source == "custom":
            catalog = self._load_custom_catalog()
            provider = catalog.find(provider_id)
            if provider is None:
                raise ValueError(f"custom provider not found: {provider_id}")

            provider_type = _to_discovery_type(provider.api_type.value)
            discovered_models, recommendation = self._discover_models(
                provider_type=provider_type,
                api_key=provider.api_key,
                api_base=provider.api_base,
            )
            if not discovered_models:
                raise ValueError(f"no models discovered for provider: {provider_id}")

            discovered_model_ids = [str(item["model_id"]) for item in discovered_models]
            selected = (
                str((recommendation or {}).get("model_id") or "").strip()
                if recommendation is not None
                else ""
            )
            if selected not in discovered_model_ids:
                selected = provider.default_model if provider.models else (discovered_model_ids[0] if discovered_model_ids else "")
            updated_provider = self._merge_custom_provider_discovery(
                provider=provider,
                discovered_entries=discovered_models,
                selected_model_id=selected,
            )
            updated_model_ids = list(updated_provider.models)
            new_providers = [
                updated_provider if item.id == provider.id else item for item in catalog.providers
            ]
            self._save_custom_catalog(ProviderCatalog(providers=new_providers).normalized())
            return self._provider_summary_from_custom(
                provider=updated_provider,
                model_ids=updated_model_ids,
                default_model_id=updated_provider.default_model if updated_provider.models else None,
                default_model_strategy=str((recommendation or {}).get("strategy") or "").strip() or None,
                default_model_confidence=str((recommendation or {}).get("confidence") or "").strip() or None,
            )

        provider = self._preset_provider_from_id(provider_id)
        preset = get_preset_provider_config(provider, use_latest_model=False)
        if not preset:
            raise ValueError(f"preset provider not configured: {provider_id}")

        config = PRESET_PROVIDERS[provider]
        provider_type = _to_discovery_type(config.discovery_type or provider.value)
        discovered_models, recommendation = self._discover_models(
            provider_type=provider_type,
            api_key=preset["api_key"],
            api_base=preset["api_base"],
            curated_order=list(config.models),
            official_default=config.default_model,
        )
        if not discovered_models:
            discovered_models = self._model_entries(
                [str(item) for item in preset["models"]],
                str(preset.get("model", "")).strip() or None,
                context_windows={
                    str(item): resolve_known_context_window(provider.value, str(item))
                    for item in preset["models"]
                },
                model_metadata={
                    str(item): _normalize_model_metadata_entry(
                        {
                            "discovery_source": str(preset.get("discovery_source") or "configured_default"),
                            "discovery_confidence": str(
                                preset.get("default_model_confidence") or "medium"
                            ),
                        }
                    )
                    for item in preset["models"]
                },
            )
        model_ids = [str(item["model_id"]) for item in discovered_models]
        selected = (
            str((recommendation or {}).get("model_id") or "").strip()
            if recommendation is not None
            else ""
        )
        if selected not in model_ids:
            selected = model_ids[0]
        reordered_models = self._reorder_model_entries(discovered_models, selected)
        model_ids = [str(item["model_id"]) for item in reordered_models]

        state = self._load_preset_state()
        providers_state = state.setdefault("providers", {})
        providers_state[provider.value] = {
            "models": [
                {
                    "model_id": _normalize_model_id(item.get("model_id")),
                    "display_name": _normalize_model_id(item.get("display_name"))
                    or _normalize_model_id(item.get("model_id")),
                    **(
                        {"context_window": _normalize_context_window(item.get("context_window"))}
                        if _normalize_context_window(item.get("context_window")) is not None
                        else {}
                    ),
                    **(
                        {"learned_token_limit": _normalize_token_limit(item.get("learned_token_limit"))}
                        if _normalize_token_limit(item.get("learned_token_limit")) is not None
                        else {}
                    ),
                    **_normalize_model_metadata_entry(item),
                }
                for item in reordered_models
            ],
            "default_model_id": selected,
            "default_model_strategy": str(
                (recommendation or {}).get("strategy")
                or preset.get("default_model_strategy")
                or ""
            ).strip()
            or None,
            "default_model_confidence": str(
                (recommendation or {}).get("confidence")
                or preset.get("default_model_confidence")
                or ""
            ).strip()
            or None,
            "updated_at": _utc_now_iso(),
        }
        self._save_preset_state(state)

        return self._provider_summary_from_preset(
            provider_id=provider.value,
            provider_name=str(preset["name"]),
            api_type=str(preset["api_type"]),
            api_base=str(preset["api_base"]),
            model_ids=model_ids,
            default_model_id=selected,
            display_names={
                str(item["model_id"]): _normalize_model_id(item.get("display_name")) or str(item["model_id"])
                for item in reordered_models
            },
            context_windows={
                str(item["model_id"]): context_window
                for item in reordered_models
                if (context_window := _normalize_context_window(item.get("context_window"))) is not None
            },
            learned_token_limits={
                str(item["model_id"]): token_limit
                for item in reordered_models
                if (token_limit := _normalize_token_limit(item.get("learned_token_limit"))) is not None
            },
            model_metadata={
                str(item["model_id"]): _normalize_model_metadata_entry(item)
                for item in reordered_models
                if _normalize_model_metadata_entry(item)
            },
            default_model_strategy=str(
                (recommendation or {}).get("strategy")
                or preset.get("default_model_strategy")
                or ""
            ).strip()
            or None,
            default_model_confidence=str(
                (recommendation or {}).get("confidence")
                or preset.get("default_model_confidence")
                or ""
            ).strip()
            or None,
        )

    def select_model(self, *, source: str, provider_id: str, model_id: str) -> dict[str, Any]:
        normalized_source = _normalize_source(source)
        selected_model_id = " ".join((model_id or "").strip().split())
        if not selected_model_id:
            raise ValueError("model_id must not be empty")

        if normalized_source == "custom":
            catalog = self._load_custom_catalog()
            provider = catalog.find(provider_id)
            if provider is None:
                raise ValueError(f"custom provider not found: {provider_id}")
            if selected_model_id not in provider.models:
                raise ValueError(f"model '{selected_model_id}' is not available in provider '{provider_id}'")
            reordered = [selected_model_id, *[item for item in provider.models if item != selected_model_id]]
            updated_provider = ProviderConfig.model_validate(
                {
                    **provider.model_dump(),
                    "models": reordered,
                }
            )
            new_providers = [
                updated_provider if item.id == provider.id else item for item in catalog.providers
            ]
            self._save_custom_catalog(ProviderCatalog(providers=new_providers).normalized())
            return self._provider_summary_from_custom(
                provider=updated_provider,
                model_ids=reordered,
                default_model_id=selected_model_id,
            )

        provider = self._preset_provider_from_id(provider_id)
        registry = self.list_registry()
        matched = next(
            (
                item
                for item in registry
                if item["source"] == "preset" and item["provider_id"] == provider.value
            ),
            None,
        )
        if matched is None:
            raise ValueError(f"preset provider not configured: {provider_id}")
        model_ids = [item["model_id"] for item in matched["models"]]
        if selected_model_id not in model_ids:
            raise ValueError(f"model '{selected_model_id}' is not available in provider '{provider_id}'")

        state = self._load_preset_state()
        providers_state = state.setdefault("providers", {})
        providers_state[provider.value] = {
            "models": [
                {
                    "model_id": item["model_id"],
                    "display_name": item["display_name"],
                    **(
                        {"context_window": item["context_window"]}
                        if _normalize_context_window(item.get("context_window")) is not None
                        else {}
                    ),
                    **(
                        {"learned_token_limit": item["learned_token_limit"]}
                        if _normalize_token_limit(item.get("learned_token_limit")) is not None
                        else {}
                    ),
                    **_normalize_model_metadata_entry(item),
                }
                for item in matched["models"]
            ],
            "default_model_id": selected_model_id,
            "default_model_strategy": matched.get("default_model_strategy"),
            "default_model_confidence": matched.get("default_model_confidence"),
            "updated_at": _utc_now_iso(),
        }
        self._save_preset_state(state)

        return self._provider_summary_from_preset(
            provider_id=provider.value,
            provider_name=str(matched["provider_name"]),
            api_type=str(matched["api_type"]),
            api_base=str(matched["api_base"]),
            model_ids=model_ids,
            default_model_id=selected_model_id,
            display_names={
                str(item["model_id"]): _normalize_model_id(item.get("display_name")) or str(item["model_id"])
                for item in matched["models"]
            },
            context_windows={
                str(item["model_id"]): context_window
                for item in matched["models"]
                if (context_window := _normalize_context_window(item.get("context_window"))) is not None
            },
            learned_token_limits={
                str(item["model_id"]): token_limit
                for item in matched["models"]
                if (token_limit := _normalize_token_limit(item.get("learned_token_limit"))) is not None
            },
            model_metadata={
                str(item["model_id"]): _normalize_model_metadata_entry(item)
                for item in matched["models"]
                if _normalize_model_metadata_entry(item)
            },
            default_model_strategy=str(matched.get("default_model_strategy") or "").strip() or None,
            default_model_confidence=str(matched.get("default_model_confidence") or "").strip() or None,
        )

    def record_learned_token_limit(
        self,
        *,
        source: str,
        provider_id: str,
        model_id: str,
        learned_token_limit: int,
    ) -> dict[str, Any]:
        normalized_source = _normalize_source(source)
        normalized_model_id = _normalize_model_id(model_id)
        normalized_limit = _normalize_token_limit(learned_token_limit)
        if not normalized_model_id:
            raise ValueError("model_id must not be empty")
        if normalized_limit is None:
            raise ValueError("learned_token_limit must be a positive integer")

        if normalized_source == "custom":
            catalog = self._load_custom_catalog()
            provider = catalog.find(provider_id)
            if provider is None:
                raise ValueError(f"custom provider not found: {provider_id}")
            if normalized_model_id not in provider.models:
                raise ValueError(f"model '{normalized_model_id}' is not available in provider '{provider_id}'")
            existing = _normalize_token_limit(provider.model_learned_token_limits.get(normalized_model_id))
            effective_limit = min(existing, normalized_limit) if existing is not None else normalized_limit
            updated_provider = ProviderConfig.model_validate(
                {
                    **provider.model_dump(),
                    "model_learned_token_limits": {
                        **provider.model_learned_token_limits,
                        normalized_model_id: effective_limit,
                    },
                }
            )
            new_providers = [
                updated_provider if item.id == provider.id else item for item in catalog.providers
            ]
            self._save_custom_catalog(ProviderCatalog(providers=new_providers).normalized())
            return self._provider_summary_from_custom(
                provider=updated_provider,
                model_ids=list(updated_provider.models),
                default_model_id=updated_provider.default_model if updated_provider.models else None,
            )

        provider = self._preset_provider_from_id(provider_id)
        registry = self.list_registry()
        matched = next(
            (
                item
                for item in registry
                if item["source"] == "preset" and item["provider_id"] == provider.value
            ),
            None,
        )
        if matched is None:
            raise ValueError(f"preset provider not configured: {provider_id}")

        updated_models: list[dict[str, Any]] = []
        found = False
        for item in matched["models"]:
            copied = dict(item)
            current_limit = _normalize_token_limit(copied.get("learned_token_limit"))
            if _normalize_model_id(copied.get("model_id")) == normalized_model_id:
                found = True
                copied["learned_token_limit"] = (
                    min(current_limit, normalized_limit) if current_limit is not None else normalized_limit
                )
            updated_models.append(copied)
        if not found:
            raise ValueError(f"model '{normalized_model_id}' is not available in provider '{provider_id}'")

        state = self._load_preset_state()
        providers_state = state.setdefault("providers", {})
        providers_state[provider.value] = {
            "models": [
                {
                    "model_id": item["model_id"],
                    "display_name": item["display_name"],
                    **(
                        {"context_window": item["context_window"]}
                        if _normalize_context_window(item.get("context_window")) is not None
                        else {}
                    ),
                    **(
                        {"learned_token_limit": item["learned_token_limit"]}
                        if _normalize_token_limit(item.get("learned_token_limit")) is not None
                        else {}
                    ),
                    **_normalize_model_metadata_entry(item),
                }
                for item in updated_models
            ],
            "default_model_id": matched.get("default_model_id"),
            "default_model_strategy": matched.get("default_model_strategy"),
            "default_model_confidence": matched.get("default_model_confidence"),
            "updated_at": _utc_now_iso(),
        }
        self._save_preset_state(state)

        return self._provider_summary_from_preset(
            provider_id=provider.value,
            provider_name=str(matched["provider_name"]),
            api_type=str(matched["api_type"]),
            api_base=str(matched["api_base"]),
            model_ids=[str(item["model_id"]) for item in updated_models],
            default_model_id=str(matched.get("default_model_id") or "").strip() or None,
            display_names={
                str(item["model_id"]): _normalize_model_id(item.get("display_name")) or str(item["model_id"])
                for item in updated_models
            },
            context_windows={
                str(item["model_id"]): context_window
                for item in updated_models
                if (context_window := _normalize_context_window(item.get("context_window"))) is not None
            },
            learned_token_limits={
                str(item["model_id"]): token_limit
                for item in updated_models
                if (token_limit := _normalize_token_limit(item.get("learned_token_limit"))) is not None
            },
            model_metadata={
                str(item["model_id"]): _normalize_model_metadata_entry(item)
                for item in updated_models
                if _normalize_model_metadata_entry(item)
            },
            default_model_strategy=str(matched.get("default_model_strategy") or "").strip() or None,
            default_model_confidence=str(matched.get("default_model_confidence") or "").strip() or None,
        )

    def list_learned_token_limits(
        self,
        *,
        source: str | None = None,
        provider_id: str | None = None,
        model_id: str | None = None,
    ) -> list[dict[str, Any]]:
        normalized_source = _normalize_source(source) if _normalize_model_id(source) else None
        normalized_provider_id = _normalize_model_id(provider_id)
        normalized_model_id = _normalize_model_id(model_id)

        rows: list[dict[str, Any]] = []
        for provider in self.list_registry():
            provider_source = _normalize_source(provider.get("source"))
            provider_name = _normalize_model_id(provider.get("provider_name"))
            current_provider_id = _normalize_model_id(provider.get("provider_id"))
            if normalized_source is not None and provider_source != normalized_source:
                continue
            if normalized_provider_id and current_provider_id != normalized_provider_id:
                continue
            for model in provider.get("models", []):
                if not isinstance(model, dict):
                    continue
                current_model_id = _normalize_model_id(model.get("model_id"))
                if normalized_model_id and current_model_id != normalized_model_id:
                    continue
                learned_limit = _normalize_token_limit(model.get("learned_token_limit"))
                if learned_limit is None:
                    continue
                rows.append(
                    {
                        "source": provider_source,
                        "provider_id": current_provider_id,
                        "provider_name": provider_name or current_provider_id,
                        "model_id": current_model_id,
                        "display_name": _normalize_model_id(model.get("display_name")) or current_model_id,
                        "learned_token_limit": learned_limit,
                        "context_window": _normalize_context_window(model.get("context_window")),
                        "is_default": bool(model.get("is_default")),
                    }
                )
        return rows

    def clear_learned_token_limit(
        self,
        *,
        source: str,
        provider_id: str,
        model_id: str | None = None,
    ) -> dict[str, Any]:
        normalized_source = _normalize_source(source)
        normalized_provider_id = _normalize_model_id(provider_id)
        normalized_model_id = _normalize_model_id(model_id)
        if not normalized_provider_id:
            raise ValueError("provider_id must not be empty")

        if normalized_source == "custom":
            catalog = self._load_custom_catalog()
            provider = catalog.find(normalized_provider_id)
            if provider is None:
                raise ValueError(f"custom provider not found: {provider_id}")
            if normalized_model_id and normalized_model_id not in provider.models:
                raise ValueError(f"model '{normalized_model_id}' is not available in provider '{provider_id}'")

            if normalized_model_id:
                removed_models = (
                    [normalized_model_id]
                    if normalized_model_id in provider.model_learned_token_limits
                    else []
                )
                updated_limits = {
                    key: value
                    for key, value in provider.model_learned_token_limits.items()
                    if key != normalized_model_id
                }
            else:
                removed_models = sorted(provider.model_learned_token_limits)
                updated_limits = {}

            updated_provider = ProviderConfig.model_validate(
                {
                    **provider.model_dump(),
                    "model_learned_token_limits": updated_limits,
                }
            )
            new_providers = [
                updated_provider if item.id == provider.id else item for item in catalog.providers
            ]
            self._save_custom_catalog(ProviderCatalog(providers=new_providers).normalized())
            return {
                "provider": self._provider_summary_from_custom(
                    provider=updated_provider,
                    model_ids=list(updated_provider.models),
                    default_model_id=updated_provider.default_model if updated_provider.models else None,
                ),
                "removed_models": removed_models,
                "removed_count": len(removed_models),
            }

        provider = self._preset_provider_from_id(normalized_provider_id)
        registry = self.list_registry()
        matched = next(
            (
                item
                for item in registry
                if item["source"] == "preset" and item["provider_id"] == provider.value
            ),
            None,
        )
        if matched is None:
            raise ValueError(f"preset provider not configured: {provider_id}")

        updated_models: list[dict[str, Any]] = []
        removed_models: list[str] = []
        found_model = not normalized_model_id
        for item in matched["models"]:
            copied = dict(item)
            current_model_id = _normalize_model_id(copied.get("model_id"))
            if normalized_model_id and current_model_id != normalized_model_id:
                updated_models.append(copied)
                continue
            found_model = True
            if _normalize_token_limit(copied.get("learned_token_limit")) is not None:
                removed_models.append(current_model_id)
            copied.pop("learned_token_limit", None)
            updated_models.append(copied)

        if not found_model:
            raise ValueError(f"model '{normalized_model_id}' is not available in provider '{provider_id}'")

        state = self._load_preset_state()
        providers_state = state.setdefault("providers", {})
        providers_state[provider.value] = {
            "models": [
                {
                    "model_id": item["model_id"],
                    "display_name": item["display_name"],
                    **(
                        {"context_window": item["context_window"]}
                        if _normalize_context_window(item.get("context_window")) is not None
                        else {}
                    ),
                    **_normalize_model_metadata_entry(item),
                }
                for item in updated_models
            ],
            "default_model_id": matched.get("default_model_id"),
            "default_model_strategy": matched.get("default_model_strategy"),
            "default_model_confidence": matched.get("default_model_confidence"),
            "updated_at": _utc_now_iso(),
        }
        self._save_preset_state(state)

        return {
            "provider": self._provider_summary_from_preset(
                provider_id=provider.value,
                provider_name=str(matched["provider_name"]),
                api_type=str(matched["api_type"]),
                api_base=str(matched["api_base"]),
                model_ids=[str(item["model_id"]) for item in updated_models],
                default_model_id=str(matched.get("default_model_id") or "").strip() or None,
                display_names={
                    str(item["model_id"]): _normalize_model_id(item.get("display_name")) or str(item["model_id"])
                    for item in updated_models
                },
                context_windows={
                    str(item["model_id"]): context_window
                    for item in updated_models
                    if (context_window := _normalize_context_window(item.get("context_window"))) is not None
                },
                learned_token_limits={},
                model_metadata={
                    str(item["model_id"]): _normalize_model_metadata_entry(item)
                    for item in updated_models
                    if _normalize_model_metadata_entry(item)
                },
                default_model_strategy=str(matched.get("default_model_strategy") or "").strip() or None,
                default_model_confidence=str(matched.get("default_model_confidence") or "").strip() or None,
            ),
            "removed_models": removed_models,
            "removed_count": len(removed_models),
        }

    def runtime_provider_catalog(
        self,
        *,
        bootstrap_llm: BootstrapLLMSettings | None = None,
    ) -> ProviderCatalog:
        load_local_env_files()
        state = self._load_preset_state()
        state_providers: dict[str, Any] = state.get("providers", {})
        custom_catalog = self._load_custom_catalog()
        providers: list[ProviderConfig] = []
        for provider in custom_catalog.providers:
            if provider.api_key and provider.models:
                providers.append(ProviderConfig.model_validate(provider.model_dump()))

        for provider in PresetProvider:
            state_item = state_providers.get(provider.value, {})
            stored_models = state_item.get("models", [])
            model_ids, display_names, context_windows, learned_token_limits, model_metadata = self._parse_state_models(
                stored_models
            )
            stored_default_model_id = _normalize_model_id(state_item.get("default_model_id")) or None
            allow_unreachable_local = (
                provider == PresetProvider.OLLAMA and bool(model_ids or stored_default_model_id)
            )
            preset = get_preset_provider_config(
                provider,
                use_latest_model=False,
                allow_unreachable_local=allow_unreachable_local,
                discover_inventory=False,
            )
            if not preset:
                continue

            if not model_ids and allow_unreachable_local and stored_default_model_id:
                model_ids = [stored_default_model_id]
                display_names[stored_default_model_id] = stored_default_model_id

            if not model_ids:
                model_ids = [str(item) for item in preset.get("models", []) if str(item).strip()]

            for model_id in model_ids:
                display_names.setdefault(model_id, model_id)
                known_context_window = resolve_known_context_window(provider.value, model_id)
                if known_context_window is not None:
                    context_windows.setdefault(model_id, known_context_window)

            default_model_id = stored_default_model_id or _normalize_model_id(preset.get("model")) or None
            if default_model_id and default_model_id not in model_ids:
                model_ids = [default_model_id, *model_ids]
                display_names.setdefault(default_model_id, default_model_id)
                known_context_window = resolve_known_context_window(provider.value, default_model_id)
                if known_context_window is not None:
                    context_windows.setdefault(default_model_id, known_context_window)
            if default_model_id and default_model_id in model_ids:
                model_ids = [default_model_id, *[item for item in model_ids if item != default_model_id]]

            if not model_ids:
                continue

            providers.append(
                ProviderConfig.model_validate(
                    {
                        "id": f"preset-{provider.value}",
                        "name": str(preset["name"]),
                        "api_type": str(preset["api_type"]),
                        "api_base": str(preset["api_base"]),
                        "api_key": str(preset["api_key"]),
                        "models": model_ids,
                        "model_display_names": display_names,
                        "model_context_windows": context_windows,
                        "model_learned_token_limits": learned_token_limits,
                        "model_metadata": model_metadata,
                        "enabled": True,
                        "priority": -100,
                    }
                )
            )
        if not providers and bootstrap_llm is not None:
            providers.append(_build_bootstrap_provider(bootstrap_llm))
        return ProviderCatalog(providers=providers).normalized()
