"""In-memory baseline mutation ledger for workspace-runtime slices."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class MutationKind(str, Enum):
    """Baseline recorded operation kinds."""

    READ = "read"
    WRITE = "write"
    EDIT = "edit"
    DELETE = "delete"
    EXECUTE = "execute"


@dataclass(frozen=True, slots=True)
class MutationRecord:
    """One recorded mutation or side-effect attempt."""

    kind: MutationKind
    path: Path | None = None
    detail: str | None = None
    inside_workspace: bool = True
    approved: bool | None = None
    created_at: datetime = field(default_factory=_utc_now)

    def __post_init__(self) -> None:
        if self.path is not None:
            object.__setattr__(self, "path", Path(self.path).expanduser().resolve(strict=False))


@dataclass(slots=True)
class InMemoryMutationLedger:
    """Append-only in-memory ledger used by Stage 1 seams."""

    _records: list[MutationRecord] = field(default_factory=list)

    def append(self, record: MutationRecord) -> MutationRecord:
        self._records.append(record)
        return record

    def record(
        self,
        kind: MutationKind,
        *,
        path: str | Path | None = None,
        detail: str | None = None,
        inside_workspace: bool = True,
        approved: bool | None = None,
    ) -> MutationRecord:
        return self.append(
            MutationRecord(
                kind=kind,
                path=Path(path) if path is not None else None,
                detail=detail,
                inside_workspace=inside_workspace,
                approved=approved,
            )
        )

    def snapshot(self) -> list[MutationRecord]:
        return list(self._records)

    def clear(self) -> None:
        self._records.clear()

    def __len__(self) -> int:
        return len(self._records)


__all__ = [
    "InMemoryMutationLedger",
    "MutationKind",
    "MutationRecord",
]
