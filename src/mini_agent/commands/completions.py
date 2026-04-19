"""Command completion helpers built on the shared command catalog."""

from __future__ import annotations

import difflib

from .catalog import _clean_text, _normalized_surface, command_entries_for_surface
from .parser import normalize_command_name


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


def suggest_command_name(
    value: str,
    *,
    surface: str,
    extra_candidates: list[str] | tuple[str, ...] | set[str] | None = None,
) -> str:
    candidates = {
        normalize_command_name(entry.get("name"))
        for entry in command_entries_for_surface(surface)
        if normalize_command_name(entry.get("name"))
    }
    for item in list(extra_candidates or []):
        normalized = normalize_command_name(item)
        if normalized:
            candidates.add(normalized)
    matches = difflib.get_close_matches(
        normalize_command_name(value),
        sorted(candidates),
        n=3,
        cutoff=0.45,
    )
    if not matches:
        return ""
    return f" Did you mean: {', '.join(matches)}?"


__all__ = [
    "command_completion_tokens",
    "suggest_command_name",
]
