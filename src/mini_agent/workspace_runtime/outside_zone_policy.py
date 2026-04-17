"""Baseline outside-workspace access policy."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


def _normalize_path(value: str | Path) -> Path:
    return Path(value).expanduser().resolve(strict=False)


def _is_relative_to(candidate: Path, root: Path) -> bool:
    try:
        candidate.relative_to(root)
        return True
    except ValueError:
        return False


def _default_protected_roots() -> tuple[Path, ...]:
    if os.name == "nt":
        values = (
            os.environ.get("SystemRoot"),
            os.environ.get("ProgramFiles"),
            os.environ.get("ProgramFiles(x86)"),
            os.environ.get("ProgramData"),
        )
    else:
        values = ("/bin", "/etc", "/sbin", "/usr", "/var")
    roots = []
    for value in values:
        if value:
            roots.append(_normalize_path(value))
    return tuple(dict.fromkeys(roots))


class OutsideZoneOperation(str, Enum):
    """Baseline operations evaluated outside the workspace root."""

    READ = "read"
    WRITE = "write"
    DELETE = "delete"


@dataclass(frozen=True, slots=True)
class OutsideZoneDecision:
    """Result of evaluating one outside-workspace operation."""

    allowed: bool
    requires_approval: bool
    reason: str
    protected: bool = False

    @property
    def denied(self) -> bool:
        return not self.allowed and not self.requires_approval


@dataclass(frozen=True, slots=True)
class DefaultOutsideZonePolicy:
    """Outside-zone default policy aligned with the v11.1 baseline."""

    protected_roots: tuple[Path, ...] = field(default_factory=_default_protected_roots)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "protected_roots",
            tuple(_normalize_path(root) for root in self.protected_roots),
        )

    def is_protected(self, value: str | Path) -> bool:
        candidate = _normalize_path(value)
        return any(_is_relative_to(candidate, root) for root in self.protected_roots)

    def decide(self, operation: OutsideZoneOperation, path: str | Path) -> OutsideZoneDecision:
        candidate = _normalize_path(path)
        protected = self.is_protected(candidate)

        if protected:
            if operation is OutsideZoneOperation.READ:
                return OutsideZoneDecision(
                    allowed=True,
                    requires_approval=False,
                    reason="protected outside path is read-only",
                    protected=True,
                )
            return OutsideZoneDecision(
                allowed=False,
                requires_approval=False,
                reason="protected outside path cannot be modified",
                protected=True,
            )

        if operation is OutsideZoneOperation.READ:
            return OutsideZoneDecision(
                allowed=True,
                requires_approval=False,
                reason="outside-workspace read is allowed",
            )

        if operation is OutsideZoneOperation.WRITE:
            return OutsideZoneDecision(
                allowed=False,
                requires_approval=True,
                reason="outside-workspace write requires approval",
            )

        return OutsideZoneDecision(
            allowed=False,
            requires_approval=False,
            reason="outside-workspace delete is denied",
        )


__all__ = [
    "DefaultOutsideZonePolicy",
    "OutsideZoneDecision",
    "OutsideZoneOperation",
]
