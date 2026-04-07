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
    StudioMemoryDailyResponse,
    StudioMemoryNote,
    StudioMemorySearchResponse,
    StudioMemorySummaryResponse,
    StudioProviderDeleteResponse,
    StudioProviderHealthResponse,
    StudioProviderListResponse,
    StudioProviderSummary,
    StudioProviderUpsertRequest,
)
from mini_agent.model_manager import (
    get_circuit_breaker_registry,
    get_health_monitor,
    normalize_provider_catalog,
    normalize_provider_config,
)
from mini_agent.tools.note_tool import MarkdownMemoryStore, MemoryNote


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

    def create_provider(
        self,
        *,
        payload: StudioProviderUpsertRequest,
        catalog_path: str | None,
    ) -> StudioProviderSummary:
        resolved_path = self._resolve_provider_catalog_path(catalog_path)
        providers = self._load_provider_catalog(resolved_path)
        try:
            provider = normalize_provider_config(payload.model_dump())
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

        update_payload = payload.model_dump()
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
        store = MarkdownMemoryStore(memory_root=str(resolved_workspace))
        notes = store.load_notes()
        daily_files = sorted(path.name for path in store.daily_dir.glob("*.md"))
        categories = sorted({note.category for note in notes})
        return StudioMemorySummaryResponse(
            workspace_dir=str(resolved_workspace),
            memory_root=str(store.memory_root),
            long_term_file=str(store.long_term_file),
            daily_dir=str(store.daily_dir),
            daily_files=daily_files,
            notes_count=len(notes),
            categories=categories,
        )

    def search_memory(
        self,
        *,
        query: str,
        limit: int,
        workspace_dir: str | None,
    ) -> StudioMemorySearchResponse:
        resolved_workspace = self._resolve_workspace_dir(workspace_dir)
        store = MarkdownMemoryStore(memory_root=str(resolved_workspace))
        notes = store.load_notes()
        matches = self._search_notes(notes, query=query, limit=limit)
        return StudioMemorySearchResponse(
            workspace_dir=str(resolved_workspace),
            query=query,
            limit=limit,
            total=len(matches),
            items=[self._note_to_dict(store, note) for note in matches],
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
        store = MarkdownMemoryStore(memory_root=str(resolved_workspace))
        daily_path = store.daily_dir / f"{normalized_day}.md"
        if not daily_path.exists():
            raise HTTPException(status_code=404, detail=f"daily memory file not found: {normalized_day}")

        content = daily_path.read_text(encoding="utf-8")
        notes = [note for note in store.load_notes() if note.path.resolve() == daily_path.resolve()]
        notes.sort(key=self._note_sort_key, reverse=True)
        return StudioMemoryDailyResponse(
            workspace_dir=str(resolved_workspace),
            day=normalized_day,
            path=str(daily_path),
            note_count=len(notes),
            content=content,
            items=[self._note_to_dict(store, note) for note in notes],
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
    def _note_to_dict(store: MarkdownMemoryStore, note: MemoryNote) -> StudioMemoryNote:
        return StudioMemoryNote(
            timestamp=note.timestamp,
            category=note.category,
            content=note.content,
            path=store.relative_path(note.path),
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
