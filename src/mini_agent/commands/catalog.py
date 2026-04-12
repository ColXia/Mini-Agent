"""Helpers for the shared command catalog."""

from __future__ import annotations

import difflib
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


def _action_variants_from_token(token: str) -> list[str]:
    raw = _clean_text(token).strip()
    if not raw:
        return []
    stripped = raw.strip("[]")
    parts = stripped.split("|")
    values: list[str] = []
    seen: set[str] = set()
    for part in parts:
        normalized = _normalize_token(str(part).strip("[]<>"))
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        values.append(normalized)
    return values


def command_action_candidates(surface: str, command_name: str) -> list[str]:
    target = _normalize_token(command_name)
    candidates: list[str] = []
    seen: set[str] = set()
    entry = command_entry_for_surface(surface, command_name)
    if not isinstance(entry, dict):
        return []
    values: list[str] = []
    forms = entry.get("forms_for_surface")
    if isinstance(forms, list):
        values.extend(forms)
    completion_tokens = entry.get("completion_tokens_for_surface")
    if isinstance(completion_tokens, list):
        values.extend(completion_tokens)
    for value in values:
        tokens = _clean_text(value).split()
        if len(tokens) < 2 or _normalize_token(tokens[0]) != target:
            continue
        for action in _action_variants_from_token(tokens[1]):
            if action in seen:
                continue
            seen.add(action)
            candidates.append(action)
    return sorted(candidates)


def suggest_command_action(command_name: str, value: str, *, surface: str) -> str:
    target = _normalize_token(value)
    if not target:
        return ""
    matches = difflib.get_close_matches(
        target,
        command_action_candidates(surface, command_name),
        n=3,
        cutoff=0.45,
    )
    if not matches:
        return ""
    return f" Did you mean: {', '.join(matches)}?"


def build_command_usage_text(
    surface: str,
    command_name: str,
    *,
    action: str | None = None,
    leading_slash: bool = True,
    fallback: str = "",
) -> str:
    forms = command_forms_for_surface(surface, command_name)
    if not forms:
        return fallback

    selected = forms[0]
    normalized_command = _normalize_token(command_name)
    normalized_action = _normalize_token(action)
    if normalized_action:
        ranked: list[tuple[int, int, int, str]] = []
        for index, form in enumerate(forms):
            tokens = _clean_text(form).split()
            if len(tokens) < 2 or _normalize_token(tokens[0]) != normalized_command:
                continue
            variants = _action_variants_from_token(tokens[1])
            if normalized_action not in variants:
                continue
            exact = len(variants) == 1 and variants[0] == normalized_action
            ranked.append((2 if exact else 1, -len(tokens), -index, form))
        if ranked:
            ranked.sort(reverse=True)
            selected = ranked[0][3]

    prefix = "/" if leading_slash else ""
    return f"Usage: {prefix}{selected}"


def build_unknown_action_text(
    surface: str,
    command_name: str,
    action: str,
    *,
    leading_slash: bool = True,
    fallback: str = "",
) -> str:
    cleaned_action = _clean_text(action) or "(empty)"
    suggestion = suggest_command_action(command_name, action, surface=surface)
    usage = build_command_usage_text(
        surface,
        command_name,
        leading_slash=leading_slash,
        fallback=fallback,
    )
    header = f"Unknown {_normalize_token(command_name)} action: {cleaned_action}.{suggestion}"
    if not usage:
        return header
    return f"{header}\n{usage}"


def build_command_help_text(
    surface: str,
    *,
    include_header: bool = True,
    leading_slash: bool = True,
) -> str:
    normalized_surface = _normalized_surface(surface)
    entries = command_entries_for_surface(normalized_surface)
    prefix = "/" if leading_slash else ""
    lines: list[str] = []
    if include_header:
        lines.append("Commands:")

    current_category = None
    for entry in entries:
        forms = entry.get("forms_for_surface") if isinstance(entry.get("forms_for_surface"), list) else []
        if not forms:
            continue
        category = _clean_text(entry.get("category")) or "Other"
        if category != current_category:
            if lines and lines[-1] != "":
                lines.append("")
            lines.append(category)
            current_category = category
        summary = _clean_text(entry.get("summary"))
        lines.append(f"  {prefix}{forms[0]}" + (f" - {summary}" if summary else ""))
        for form in forms[1:]:
            lines.append(f"  {prefix}{form}")
    return "\n".join(lines).strip()


def build_command_example_text(
    surface: str,
    *,
    include_header: bool = True,
    leading_slash: bool = True,
    max_examples: int = 12,
) -> str:
    normalized_surface = _normalized_surface(surface)
    prefix = "/" if leading_slash else ""
    examples: list[str] = []
    seen: set[str] = set()
    for entry in command_entries_for_surface(normalized_surface):
        for example in entry.get("examples_for_surface", []):
            cleaned = _clean_text(example)
            if not cleaned or cleaned in seen:
                continue
            seen.add(cleaned)
            examples.append(f"{prefix}{cleaned}")
            if len(examples) >= max(1, int(max_examples)):
                break
        if len(examples) >= max(1, int(max_examples)):
            break
    if include_header:
        return "\n".join(["Examples:", *[f"  {item}" for item in examples]]).strip()
    return "\n".join(examples).strip()


def command_completion_tokens(
    surface: str,
    *,
    include_leading_slash: bool = False,
    include_plain: bool = True,
) -> list[str]:
    normalized_surface = _normalized_surface(surface)
    tokens: list[str] = []
    seen: set[str] = set()
    for entry in command_entries_for_surface(normalized_surface):
        candidates = entry.get("completion_tokens_for_surface")
        if not isinstance(candidates, list) or not candidates:
            candidates = entry.get("forms_for_surface") if isinstance(entry.get("forms_for_surface"), list) else []
        for candidate in candidates:
            cleaned = _clean_text(candidate)
            if not cleaned:
                continue
            variants: list[str] = []
            if include_plain:
                variants.append(cleaned)
            if include_leading_slash:
                variants.append(f"/{cleaned}")
            for item in variants:
                if item in seen:
                    continue
                seen.add(item)
                tokens.append(item)
    return sorted(tokens)


__all__ = [
    "CATALOG_PATH",
    "build_command_usage_text",
    "build_command_example_text",
    "build_command_help_text",
    "build_unknown_action_text",
    "command_action_candidates",
    "command_completion_tokens",
    "command_entry_for_surface",
    "command_entries_for_surface",
    "command_forms_for_surface",
    "load_command_catalog",
    "suggest_command_action",
]
