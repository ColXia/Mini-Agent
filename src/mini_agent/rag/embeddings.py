"""Shared embedding provider protocols."""

from __future__ import annotations

from typing import Protocol


class EmbeddingProvider(Protocol):
    """Optional sync embedding provider used for vector/semantic ranking."""

    def embed(self, text: str) -> list[float]:
        ...


__all__ = ["EmbeddingProvider"]
