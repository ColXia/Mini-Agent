"""Skill-directory path resolution shared across runtime and operator flows."""

from __future__ import annotations

import os
from pathlib import Path


def _safe_path(value: str | os.PathLike[str] | None) -> Path | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return Path(text).expanduser()


def resolve_builtin_skills_dir(config) -> Path:
    configured = _safe_path(getattr(config.tools, "skills_dir", None))
    candidates: list[Path] = []
    if configured is not None:
        if configured.is_absolute():
            candidates.append(configured.resolve())
        else:
            candidates.append((Path.cwd() / configured).resolve())

    package_default = (Path(__file__).parent.parent.parent / "skills").resolve()
    candidates.append(package_default)

    seen: set[Path] = set()
    for candidate in candidates:
        if candidate in seen:
            continue
        seen.add(candidate)
        if candidate.exists():
            return candidate
    return package_default


def resolve_workspace_skills_dir(
    workspace_dir: str | os.PathLike[str] | None = None,
) -> Path | None:
    workspace_root = _safe_path(workspace_dir)
    if workspace_root is not None:
        workspace_root = workspace_root.resolve()

    explicit = _safe_path(os.getenv("MINI_AGENT_WORKSPACE_SKILLS_DIR"))
    candidates: list[Path] = []
    if explicit is not None:
        if explicit.is_absolute():
            candidates.append(explicit.resolve())
        else:
            base_dir = workspace_root or Path.cwd().resolve()
            candidates.append((base_dir / explicit).resolve())

    if workspace_root is not None:
        candidates.append((workspace_root / ".mini-agent" / "skills").resolve())
        candidates.append((workspace_root / "skills").resolve())

    if not candidates:
        return None

    seen: set[Path] = set()
    first_candidate: Path | None = None
    for candidate in candidates:
        if candidate in seen:
            continue
        seen.add(candidate)
        if first_candidate is None:
            first_candidate = candidate
        if candidate.exists():
            return candidate
    return first_candidate


__all__ = ["resolve_builtin_skills_dir", "resolve_workspace_skills_dir"]
