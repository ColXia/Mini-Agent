"""Shared helpers for durable kernel contract models."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def clean_text(value: object) -> str | None:
    text = " ".join(str(value or "").split())
    return text or None


def normalize_text_tuple(values: Iterable[object] | None) -> tuple[str, ...]:
    if values is None:
        return ()
    normalized: list[str] = []
    for item in values:
        text = clean_text(item)
        if text:
            normalized.append(text)
    return tuple(normalized)


def normalize_mapping(value: Mapping[str, Any] | None) -> dict[str, Any]:
    if value is None:
        return {}
    return deepcopy(dict(value))

