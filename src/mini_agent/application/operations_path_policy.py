"""Shared path/policy helpers for gateway operations use cases."""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import HTTPException


class OperationsPathPolicy:
    """Resolve and validate operation file-system targets."""

    def __init__(self, *, repo_root: Path, workspace_root: Path) -> None:
        self._repo_root = repo_root.resolve()
        self._workspace_root = workspace_root.resolve()

    def load_allowed_roots(self) -> tuple[Path, ...]:
        raw = os.getenv("MINI_AGENT_STUDIO_ALLOWED_ROOTS", "")
        roots: list[Path] = [self._repo_root, self._workspace_root]
        for item in raw.split(","):
            normalized = self.normalize_text(item)
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
    def is_under_root(path: Path, root: Path) -> bool:
        try:
            path.relative_to(root)
            return True
        except Exception:
            return False

    def enforce_allowed_path(self, path: Path, *, field_name: str) -> Path:
        resolved = path.resolve()
        allowed_roots = self.load_allowed_roots()
        for root in allowed_roots:
            if self.is_under_root(resolved, root):
                return resolved
        allowed = ", ".join(str(item) for item in allowed_roots)
        raise HTTPException(
            status_code=400,
            detail=f"{field_name} is outside allowed roots: {resolved}; allowed_roots={allowed}",
        )

    def resolve_workspace_dir(self, workspace_dir: str | None) -> Path:
        if not workspace_dir:
            return self.enforce_allowed_path(self._repo_root, field_name="workspace_dir")
        raw = Path(workspace_dir).expanduser()
        resolved = (raw if raw.is_absolute() else (self._repo_root / raw)).resolve()
        return self.enforce_allowed_path(resolved, field_name="workspace_dir")

    def resolve_provider_catalog_path(self, catalog_path: str | None) -> Path:
        explicit_path = self.normalize_text(catalog_path)
        env_path = self.normalize_text(os.getenv("MINI_AGENT_PROVIDER_CATALOG_PATH"))
        selected_path = explicit_path or env_path
        if selected_path:
            raw = Path(selected_path).expanduser()
            resolved = (raw if raw.is_absolute() else (self._repo_root / raw)).resolve()
            return self.enforce_allowed_path(resolved, field_name="catalog_path")
        default_catalog = (self._workspace_root / "providers.json").resolve()
        return self.enforce_allowed_path(default_catalog, field_name="catalog_path")

    @staticmethod
    def normalize_text(value: str | None) -> str:
        if value is None:
            return ""
        return " ".join(value.strip().split())
