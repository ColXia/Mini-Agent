"""Workspace-internal permission table primitives."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from .mutation_ledger import MutationKind


def _normalize_relative_path(value: str | Path | None) -> Path | None:
    if value is None:
        return None
    normalized = Path(str(value).replace("\\", "/")).expanduser()
    if normalized.is_absolute():
        raise ValueError("permission rule paths must be workspace-relative")
    parts = [part for part in normalized.parts if part not in ("", ".")]
    if any(part == ".." for part in parts):
        raise ValueError("permission rule paths cannot escape the workspace root")
    if not parts:
        return None
    return Path(*parts)


class WorkspacePermissionEffect(str, Enum):
    """Decision effect for one workspace permission rule."""

    ALLOW = "allow"
    DENY = "deny"


@dataclass(frozen=True, slots=True)
class WorkspacePermissionRule:
    """One workspace-internal path/operation permission rule."""

    effect: WorkspacePermissionEffect
    kinds: tuple[MutationKind, ...] = ()
    relative_path: Path | None = None
    reason: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "relative_path", _normalize_relative_path(self.relative_path))
        normalized_kinds = tuple(kind for kind in self.kinds if isinstance(kind, MutationKind))
        object.__setattr__(self, "kinds", normalized_kinds)

    def matches(self, *, kind: MutationKind, relative_path: Path | None) -> bool:
        if self.kinds and kind not in self.kinds:
            return False
        if self.relative_path is None:
            return True
        if relative_path is None:
            return False
        try:
            relative_path.relative_to(self.relative_path)
            return True
        except ValueError:
            return False


@dataclass(frozen=True, slots=True)
class WorkspacePermissionDecision:
    """Evaluated result for one workspace-internal access request."""

    allowed: bool
    reason: str | None = None
    matched_rule: WorkspacePermissionRule | None = None


@dataclass(slots=True)
class WorkspacePermissionTable:
    """Workspace-internal permission owner for executor-level checks."""

    rules: tuple[WorkspacePermissionRule, ...] = field(default_factory=tuple)
    default_allow: bool = True

    def decide(
        self,
        *,
        kind: MutationKind,
        relative_path: str | Path | None,
    ) -> WorkspacePermissionDecision:
        normalized_relative_path = _normalize_relative_path(relative_path)
        for rule in self.rules:
            if not rule.matches(kind=kind, relative_path=normalized_relative_path):
                continue
            return WorkspacePermissionDecision(
                allowed=rule.effect is WorkspacePermissionEffect.ALLOW,
                reason=rule.reason,
                matched_rule=rule,
            )
        return WorkspacePermissionDecision(
            allowed=bool(self.default_allow),
            reason=None if self.default_allow else "workspace permission table denied the operation",
            matched_rule=None,
        )


__all__ = [
    "WorkspacePermissionDecision",
    "WorkspacePermissionEffect",
    "WorkspacePermissionRule",
    "WorkspacePermissionTable",
]
