"""Raw command-catalog loading and per-surface entry access."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any


CATALOG_PATH = Path(__file__).with_name("catalog.json")


def _clean_text(value: Any) -> str:
    return " ".join(str(value or "").split())


def _normalize_token(value: Any) -> str:
    return _clean_text(value).lower().replace("-", "_")


def _normalized_surface(surface: str) -> str:
    normalized = _clean_text(surface).lower()
    if normalized not in {"tui", "cli", "qq"}:
        raise ValueError(f"Unsupported command surface: {surface}")
    return normalized


def _clean_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    items: list[str] = []
    seen: set[str] = set()
    for item in value:
        cleaned = _clean_text(item)
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        items.append(cleaned)
    return items


def _surface_values(entry: dict[str, Any], key: str, surface: str) -> list[str]:
    raw = entry.get(key)
    if isinstance(raw, list):
        return _clean_list(raw)
    if isinstance(raw, dict):
        specific = raw.get(surface)
        if isinstance(specific, list):
            return _clean_list(specific)
        shared = raw.get("all")
        if isinstance(shared, list):
            return _clean_list(shared)
    return []


@lru_cache(maxsize=1)
def load_command_catalog() -> dict[str, Any]:
    payload = json.loads(CATALOG_PATH.read_text(encoding="utf-8-sig"))
    commands = payload.get("commands")
    if not isinstance(commands, list):
        raise ValueError("command catalog is missing commands")
    return payload


def command_entries_for_surface(surface: str) -> list[dict[str, Any]]:
    normalized_surface = _normalized_surface(surface)
    catalog = load_command_catalog()
    entries: list[dict[str, Any]] = []
    for raw in catalog.get("commands", []):
        if not isinstance(raw, dict):
            continue
        surfaces = raw.get("surfaces")
        if not isinstance(surfaces, list) or normalized_surface not in surfaces:
            continue
        entry = dict(raw)
        entry["forms_for_surface"] = _surface_values(raw, "forms", normalized_surface)
        entry["completion_tokens_for_surface"] = _surface_values(raw, "completion_tokens", normalized_surface)
        entry["examples_for_surface"] = _surface_values(raw, "examples", normalized_surface)
        entries.append(entry)
    return entries


def command_entry_for_surface(surface: str, command_name: str) -> dict[str, Any] | None:
    target = _normalize_token(command_name)
    if not target:
        return None
    for entry in command_entries_for_surface(surface):
        if _normalize_token(entry.get("name")) == target:
            return entry
    return None


def command_forms_for_surface(surface: str, command_name: str) -> list[str]:
    entry = command_entry_for_surface(surface, command_name)
    forms = entry.get("forms_for_surface") if isinstance(entry, dict) else []
    return list(forms) if isinstance(forms, list) else []


__all__ = [
    "CATALOG_PATH",
    "command_entry_for_surface",
    "command_entries_for_surface",
    "command_forms_for_surface",
    "load_command_catalog",
]
