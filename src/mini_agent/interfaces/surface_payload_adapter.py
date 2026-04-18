"""Compatibility adapters from typed interface DTOs to surface payload dicts."""

from __future__ import annotations

from typing import Any, Iterable


def surface_payload_from_dto(value: Any) -> dict[str, Any]:
    """Convert a typed DTO or mapping into a plain surface payload dictionary.

    Surfaces still keep some transitional dict-shaped view state. This adapter
    centralizes the DTO-to-payload compatibility boundary so surfaces do not
    reach for ``model_dump()`` directly on every read path.
    """

    if isinstance(value, dict):
        return dict(value)
    if hasattr(value, "model_dump"):
        payload = value.model_dump(mode="json")
        return dict(payload) if isinstance(payload, dict) else {}
    if hasattr(value, "__dict__"):
        return dict(vars(value))
    return {}


def surface_payload_list_from_dtos(values: Iterable[Any] | None) -> list[dict[str, Any]]:
    """Convert an iterable of typed DTOs into plain surface payload dictionaries."""

    return [surface_payload_from_dto(value) for value in values or ()]


__all__ = ["surface_payload_from_dto", "surface_payload_list_from_dtos"]
