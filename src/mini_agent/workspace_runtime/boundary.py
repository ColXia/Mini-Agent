"""Workspace-root boundary helpers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


def _normalize_path(value: str | Path) -> Path:
    return Path(value).expanduser().resolve(strict=False)


def _is_relative_to(candidate: Path, root: Path) -> bool:
    try:
        candidate.relative_to(root)
        return True
    except ValueError:
        return False


@dataclass(frozen=True, slots=True)
class WorkspaceBoundary:
    """Normalized workspace root and containment checks."""

    root: Path

    def __post_init__(self) -> None:
        object.__setattr__(self, "root", _normalize_path(self.root))

    def resolve_path(self, value: str | Path) -> Path:
        candidate = Path(value).expanduser()
        if not candidate.is_absolute():
            candidate = self.root / candidate
        return candidate.resolve(strict=False)

    def contains_path(self, value: str | Path) -> bool:
        return _is_relative_to(self.resolve_path(value), self.root)

    def relative_path(self, value: str | Path) -> Path | None:
        resolved = self.resolve_path(value)
        if not _is_relative_to(resolved, self.root):
            return None
        return resolved.relative_to(self.root)


__all__ = ["WorkspaceBoundary"]
