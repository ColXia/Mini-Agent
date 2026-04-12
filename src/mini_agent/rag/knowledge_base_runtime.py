"""Shared runtime helpers for the built-in lightweight knowledge base."""

from __future__ import annotations

from pathlib import Path

from subprograms.knowledge_base.config import KnowledgeBaseSettings


def resolve_knowledge_base_store_path(
    *,
    workspace_dir: str | Path | None = None,
    store_path: str | Path | None = None,
    must_exist: bool = False,
) -> Path | None:
    """Resolve the active knowledge-base store path.

    Relative store paths prefer the active workspace, then the repository cwd.
    When ``must_exist`` is true, returns only an existing file path.
    """

    settings = KnowledgeBaseSettings.from_env()
    raw_path = Path(store_path).expanduser() if store_path is not None else settings.store_path

    candidates: list[Path] = []
    if raw_path.is_absolute():
        candidates.append(raw_path.resolve())
    else:
        resolved_workspace = None
        if workspace_dir is not None:
            resolved_workspace = Path(workspace_dir).expanduser().resolve()
        if resolved_workspace is not None:
            candidates.append((resolved_workspace / raw_path).resolve())
            if raw_path.parts and raw_path.parts[0].lower() == "workspace":
                candidates.append((resolved_workspace.parent / raw_path).resolve())
        candidates.append((Path.cwd() / raw_path).resolve())

    seen: set[Path] = set()
    preferred: Path | None = None
    for candidate in candidates:
        if candidate in seen:
            continue
        seen.add(candidate)
        if preferred is None:
            preferred = candidate
        if candidate.exists():
            return candidate

    if must_exist:
        return None
    return preferred


__all__ = ["resolve_knowledge_base_store_path"]
