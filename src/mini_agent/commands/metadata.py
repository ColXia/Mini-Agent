"""Command metadata shaping helpers built from the shared catalog."""

from __future__ import annotations

import difflib

from .catalog import (
    _clean_text,
    _normalize_token,
    _normalized_surface,
    command_entries_for_surface,
    command_entry_for_surface,
    command_forms_for_surface,
)


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


__all__ = [
    "build_command_example_text",
    "build_command_help_text",
    "build_command_usage_text",
    "build_unknown_action_text",
    "command_action_candidates",
    "suggest_command_action",
]
