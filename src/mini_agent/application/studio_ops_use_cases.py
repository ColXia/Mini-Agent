"""Application-layer use cases for Studio Ops provider and memory flows."""

from __future__ import annotations

from datetime import datetime
import json
import os
from pathlib import Path
import re
from typing import Any

from fastapi import HTTPException

from mini_agent.interfaces import (
    StudioModelDiscoverRequest,
    StudioModelListResponse,
    StudioModelProviderSummary,
    StudioModelSelectionRequest,
    StudioMemoryDailyResponse,
    StudioMemoryNote,
    StudioMemorySearchResponse,
    StudioMemorySummaryResponse,
    StudioProviderDeleteResponse,
    StudioProviderHealthResponse,
    StudioProviderListResponse,
    StudioProviderModelDiscoveryRequest,
    StudioProviderModelDiscoveryResponse,
    StudioProviderModelSummary,
    StudioProviderSummary,
    StudioProviderUpsertRequest,
)
from mini_agent.memory.service import MemoryService
from mini_agent.model_manager import (
    get_circuit_breaker_registry,
    get_health_monitor,
    normalize_provider_catalog,
    normalize_provider_config,
)
from mini_agent.model_manager.model_registry_service import ModelRegistryService
from mini_agent.model_manager.model_discovery import ModelDiscoveryService, ProviderType
from mini_agent.tools.note_tool import MemoryNote


_DAY_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class StudioOpsUseCases:
    """Use cases for Studio provider and memory management contracts."""

    def __init__(self, *, repo_root: Path, workspace_root: Path) -> None:
        self._repo_root = repo_root.resolve()
        self._workspace_root = workspace_root.resolve()

    def list_providers(self, catalog_path: str | None) -> StudioProviderListResponse:
        resolved_path = self._resolve_provider_catalog_path(catalog_path)
        providers = self._load_provider_catalog(resolved_path)
        items = [self._provider_summary(provider, resolved_path) for provider in providers]
        return StudioProviderListResponse(
            catalog_path=str(resolved_path),
            provider_count=len(items),
            items=items,
        )

    def list_models(self, *, catalog_path: str | None) -> StudioModelListResponse:
        resolved_path = self._resolve_provider_catalog_path(catalog_path)
        service = ModelRegistryService(catalog_path=resolved_path)
        items = service.list_registry()
        return StudioModelListResponse(
            items=[
                StudioModelProviderSummary.model_validate(item)
                for item in items
            ]
        )

    def discover_models(
        self,
        *,
        payload: StudioModelDiscoverRequest,
        catalog_path: str | None,
    ) -> StudioModelProviderSummary:
        resolved_path = self._resolve_provider_catalog_path(catalog_path)
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
        resolved_path = self._resolve_provider_catalog_path(catalog_path)
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

    def discover_provider_models(
        self,
        *,
        payload: StudioProviderModelDiscoveryRequest,
    ) -> StudioProviderModelDiscoveryResponse:
        try:
            discovered, latest = self._discover_models_for_provider_payload(
                api_type=str(payload.api_type),
                api_base=str(payload.api_base),
                api_key=str(payload.api_key),
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
        resolved_path = self._resolve_provider_catalog_path(catalog_path)
        providers = self._load_provider_catalog(resolved_path)
        try:
            provider = normalize_provider_config(
                self._prepare_provider_payload(payload)
            )
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
        resolved_path = self._resolve_provider_catalog_path(catalog_path)
        providers = self._load_provider_catalog(resolved_path)
        target = self._normalize_text(provider_id)

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
        resolved_path = self._resolve_provider_catalog_path(catalog_path)
        providers = self._load_provider_catalog(resolved_path)
        target = self._normalize_text(provider_id)
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
        resolved_path = self._resolve_provider_catalog_path(catalog_path)
        providers = self._load_provider_catalog(resolved_path)
        target = self._normalize_text(provider_id)
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

    def get_memory_summary(self, *, workspace_dir: str | None) -> StudioMemorySummaryResponse:
        resolved_workspace = self._resolve_workspace_dir(workspace_dir)
        memory = MemoryService(resolved_workspace)
        summary = memory.summary()
        return StudioMemorySummaryResponse(
            workspace_dir=summary.workspace_dir,
            memory_root=summary.memory_root,
            long_term_file=summary.long_term_file,
            daily_dir=summary.daily_dir,
            daily_files=summary.daily_files,
            notes_count=summary.notes_count,
            categories=summary.categories,
        )

    def search_memory(
        self,
        *,
        query: str,
        limit: int,
        workspace_dir: str | None,
    ) -> StudioMemorySearchResponse:
        resolved_workspace = self._resolve_workspace_dir(workspace_dir)
        memory = MemoryService(resolved_workspace)
        matches = memory.search_notes(query=query, limit=limit)
        return StudioMemorySearchResponse(
            workspace_dir=str(resolved_workspace),
            query=query,
            limit=limit,
            total=len(matches),
            items=[self._note_to_dict(memory, note) for note in matches],
        )

    def get_memory_daily(
        self,
        *,
        day: str,
        workspace_dir: str | None,
    ) -> StudioMemoryDailyResponse:
        normalized_day = self._normalize_text(day)
        if not _DAY_PATTERN.fullmatch(normalized_day):
            raise HTTPException(status_code=400, detail="day must be YYYY-MM-DD.")

        resolved_workspace = self._resolve_workspace_dir(workspace_dir)
        memory = MemoryService(resolved_workspace)
        try:
            snapshot = memory.daily_snapshot(day=normalized_day)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return StudioMemoryDailyResponse(
            workspace_dir=snapshot.workspace_dir,
            day=snapshot.day,
            path=snapshot.path,
            note_count=snapshot.note_count,
            content=snapshot.content,
            items=[self._note_to_dict(memory, note) for note in snapshot.notes],
        )

    def _load_allowed_roots(self) -> tuple[Path, ...]:
        raw = os.getenv("MINI_AGENT_STUDIO_ALLOWED_ROOTS", "")
        roots: list[Path] = [self._repo_root, self._workspace_root]
        for item in raw.split(","):
            normalized = " ".join(item.strip().split())
            if not normalized:
                continue
            raw_path = Path(normalized).expanduser()
            resolved = (raw_path if raw_path.is_absolute() else (self._repo_root / raw_path)).resolve()
            roots.append(resolved)

        dedup: dict[str, Path] = {}
        for root in roots:
            dedup[str(root).lower()] = root
        return tuple(dedup.values())

    @staticmethod
    def _is_under_root(path: Path, root: Path) -> bool:
        try:
            path.relative_to(root)
            return True
        except Exception:
            return False

    def _enforce_allowed_path(self, path: Path, *, field_name: str) -> Path:
        resolved = path.resolve()
        allowed_roots = self._load_allowed_roots()
        for root in allowed_roots:
            if self._is_under_root(resolved, root):
                return resolved
        allowed = ", ".join(str(item) for item in allowed_roots)
        raise HTTPException(
            status_code=400,
            detail=f"{field_name} is outside allowed roots: {resolved}; allowed_roots={allowed}",
        )

    def _resolve_workspace_dir(self, workspace_dir: str | None) -> Path:
        if not workspace_dir:
            return self._enforce_allowed_path(self._repo_root, field_name="workspace_dir")
        raw = Path(workspace_dir).expanduser()
        resolved = (raw if raw.is_absolute() else (self._repo_root / raw)).resolve()
        return self._enforce_allowed_path(resolved, field_name="workspace_dir")

    def _resolve_provider_catalog_path(self, catalog_path: str | None) -> Path:
        explicit_path = self._normalize_text(catalog_path)
        env_path = self._normalize_text(os.getenv("MINI_AGENT_PROVIDER_CATALOG_PATH"))
        selected_path = explicit_path or env_path
        if selected_path:
            raw = Path(selected_path).expanduser()
            resolved = (raw if raw.is_absolute() else (self._repo_root / raw)).resolve()
            return self._enforce_allowed_path(resolved, field_name="catalog_path")
        return self._enforce_allowed_path((self._workspace_root / "providers.json").resolve(), field_name="catalog_path")

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
    def _to_discovery_provider_type(api_type: str) -> ProviderType:
        normalized = " ".join((api_type or "").strip().split()).lower()
        if normalized == "openai":
            return ProviderType.OPENAI
        if normalized == "anthropic":
            return ProviderType.ANTHROPIC
        if normalized == "gemini":
            return ProviderType.GEMINI
        if normalized == "minimax":
            return ProviderType.MINIMAX
        return ProviderType.OPENAI

    @staticmethod
    def _build_models_endpoint(api_base: str) -> str:
        base = api_base.rstrip("/")
        if base.endswith("/models"):
            return base
        return f"{base}/models"

    def _discover_models_for_provider_payload(
        self,
        *,
        api_type: str,
        api_base: str,
        api_key: str,
    ) -> tuple[list[str], str | None]:
        service = ModelDiscoveryService()
        provider_type = self._to_discovery_provider_type(api_type)
        endpoint = self._build_models_endpoint(api_base)
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
        latest = result.latest_base_model.id if result.latest_base_model else None
        return deduped, latest

    def _prepare_provider_payload(self, payload: StudioProviderUpsertRequest) -> dict[str, Any]:
        prepared = payload.model_dump()
        model_id = self._normalize_text(payload.model_id)
        model_display_name = self._normalize_text(payload.model_display_name)

        models = [self._normalize_text(item) for item in prepared.get("models", [])]
        models = [item for item in models if item]
        model_display_names = {
            self._normalize_text(str(key)): self._normalize_text(str(value))
            for key, value in prepared.get("model_display_names", {}).items()
            if self._normalize_text(str(key)) and self._normalize_text(str(value))
        }

        if model_id:
            models = [model_id, *[item for item in models if item != model_id]]
            if model_display_name:
                model_display_names[model_id] = model_display_name

        if not models and payload.auto_discover_models:
            discovered, latest = self._discover_models_for_provider_payload(
                api_type=str(payload.api_type),
                api_base=str(payload.api_base),
                api_key=str(payload.api_key),
            )
            if not discovered:
                raise HTTPException(
                    status_code=400,
                    detail="no models discovered; provider not created",
                )
            selected = self._normalize_text(payload.selected_model_id)
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

        if not models:
            raise HTTPException(
                status_code=400,
                detail="provider requires at least one model; provider not created",
            )

        prepared["models"] = models
        prepared["model_display_names"] = model_display_names
        prepared.pop("model_id", None)
        prepared.pop("model_display_name", None)
        prepared.pop("auto_discover_models", None)
        prepared.pop("selected_model_id", None)
        return prepared

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

    @staticmethod
    def _note_to_dict(memory: MemoryService, note: MemoryNote) -> StudioMemoryNote:
        return StudioMemoryNote(
            timestamp=note.timestamp,
            category=note.category,
            content=note.content,
            path=memory.relative_path(note.path),
        )

    @staticmethod
    def _search_notes(notes: list[MemoryNote], query: str, limit: int) -> list[MemoryNote]:
        terms = [token for token in query.lower().split() if token.strip()]
        if not terms:
            return notes[:limit]

        scored: list[tuple[int, MemoryNote]] = []
        for note in notes:
            haystack = f"{note.category} {note.content}".lower()
            score = sum(1 for token in terms if token in haystack)
            if score > 0:
                scored.append((score, note))
        scored.sort(key=lambda item: item[0], reverse=True)
        return [item[1] for item in scored[:limit]]

    @staticmethod
    def _note_sort_key(note: MemoryNote) -> datetime:
        try:
            return datetime.fromisoformat(note.timestamp)
        except Exception:
            return datetime.min

    @staticmethod
    def _normalize_text(value: str | None) -> str:
        if value is None:
            return ""
        return " ".join(value.strip().split())
