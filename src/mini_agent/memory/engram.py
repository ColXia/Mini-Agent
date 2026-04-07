"""Lightweight engram model for mini memory core."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

MemoryLayer = Literal["working", "stm", "ltm"]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class Engram:
    """One memory unit with minimal metadata and lifecycle markers."""

    content: str
    layer: MemoryLayer = "working"
    importance: float = 0.5
    metadata: dict[str, Any] = field(default_factory=dict)
    engram_id: str = field(default_factory=lambda: f"eng_{uuid4().hex[:16]}")
    created_at: datetime = field(default_factory=_utc_now)
    updated_at: datetime = field(default_factory=_utc_now)
    access_count: int = 0

    def touch(self) -> None:
        """Mark one access and refresh update timestamp."""
        self.access_count += 1
        self.updated_at = _utc_now()
