"""Mini memory engine (working -> STM -> LTM) for P12 kickoff."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from mini_agent.memory.engram import Engram, MemoryLayer

_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_\u4e00-\u9fff]+")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _tokenize(text: str) -> set[str]:
    return {token.lower() for token in _TOKEN_PATTERN.findall(text)}


@dataclass(frozen=True)
class MemoryQueryResult:
    """Scored retrieval result."""

    engram_id: str
    layer: MemoryLayer
    content: str
    score: float
    metadata: dict[str, Any]


class MemoriaEngine:
    """Lightweight memory lifecycle with deterministic retrieval."""

    def __init__(
        self,
        *,
        max_working: int = 32,
        max_stm: int = 128,
        max_ltm: int = 512,
    ) -> None:
        self.max_working = max(1, int(max_working))
        self.max_stm = max(1, int(max_stm))
        self.max_ltm = max(1, int(max_ltm))
        self._layers: dict[MemoryLayer, list[Engram]] = {
            "working": [],
            "stm": [],
            "ltm": [],
        }

    def save(
        self,
        content: str,
        *,
        importance: float = 0.5,
        metadata: dict[str, Any] | None = None,
    ) -> Engram:
        """Save one memory unit into working layer."""
        normalized_content = content.strip()
        if not normalized_content:
            raise ValueError("Memory content cannot be empty.")
        engram = Engram(
            content=normalized_content,
            layer="working",
            importance=max(0.0, min(1.0, float(importance))),
            metadata={} if metadata is None else dict(metadata),
        )
        self._layers["working"].append(engram)
        self._enforce_limits()
        return engram

    def list_layer(self, layer: MemoryLayer) -> list[Engram]:
        """List memory units from one layer."""
        return list(self._layers[layer])

    def stats(self) -> dict[str, int]:
        """Return per-layer counts."""
        return {layer: len(items) for layer, items in self._layers.items()}

    def consolidate(self) -> None:
        """Run one explicit consolidation pass."""
        self._enforce_limits(force=True)

    def retrieve(self, query: str, *, limit: int = 5, include_ltm: bool = True) -> list[MemoryQueryResult]:
        """Retrieve top memories by lexical relevance + light recency/importance scoring."""
        max_results = max(1, int(limit))
        query_tokens = _tokenize(query)
        now = _utc_now()
        candidates: list[tuple[float, Engram]] = []

        layers: tuple[MemoryLayer, ...]
        if include_ltm:
            layers = ("working", "stm", "ltm")
        else:
            layers = ("working", "stm")

        for layer in layers:
            for engram in self._layers[layer]:
                score = self._score_engram(engram, query_tokens, now)
                if query_tokens and score <= 0.0:
                    continue
                candidates.append((score, engram))

        # Stable ordering for deterministic tests and reproducible behavior.
        candidates.sort(
            key=lambda item: (-item[0], -item[1].updated_at.timestamp(), item[1].engram_id),
        )

        results: list[MemoryQueryResult] = []
        for score, engram in candidates[:max_results]:
            engram.touch()
            results.append(
                MemoryQueryResult(
                    engram_id=engram.engram_id,
                    layer=engram.layer,
                    content=engram.content,
                    score=score,
                    metadata=dict(engram.metadata),
                )
            )
        return results

    def _score_engram(
        self,
        engram: Engram,
        query_tokens: set[str],
        now: datetime,
    ) -> float:
        content_tokens = _tokenize(engram.content)
        overlap = len(query_tokens & content_tokens) if query_tokens else 0
        if query_tokens and overlap == 0:
            return 0.0

        age_seconds = max(0.0, (now - engram.updated_at).total_seconds())
        recency_bonus = 1.0 / (1.0 + (age_seconds / 86400.0))
        layer_bonus = {"working": 0.3, "stm": 0.2, "ltm": 0.1}[engram.layer]
        access_bonus = min(engram.access_count, 5) * 0.05
        if not query_tokens:
            return recency_bonus + layer_bonus + access_bonus + engram.importance
        return (overlap * 2.0) + recency_bonus + layer_bonus + access_bonus + engram.importance

    def _demote_one(self, src: MemoryLayer, dst: MemoryLayer) -> None:
        candidates = self._layers[src]
        if not candidates:
            return
        # Prefer older and less-accessed units when demoting.
        candidates.sort(key=lambda item: (item.access_count, item.updated_at.timestamp()))
        target = candidates.pop(0)
        target.layer = dst
        target.updated_at = _utc_now()
        self._layers[dst].append(target)

    def _enforce_limits(self, *, force: bool = False) -> None:
        while len(self._layers["working"]) > self.max_working or (force and len(self._layers["working"]) > 0):
            if not force and len(self._layers["working"]) <= self.max_working:
                break
            self._demote_one("working", "stm")
            if not force:
                break

        while len(self._layers["stm"]) > self.max_stm:
            self._demote_one("stm", "ltm")

        if len(self._layers["ltm"]) > self.max_ltm:
            # Keep the most recently updated entries in LTM.
            self._layers["ltm"].sort(key=lambda item: item.updated_at.timestamp(), reverse=True)
            self._layers["ltm"] = self._layers["ltm"][: self.max_ltm]
