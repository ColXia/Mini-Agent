"""Built-in memory provider for workspace or global profile entries."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import re
from typing import Any

from mini_agent.memory.memory_files import (
    discover_memory_layout,
    ensure_memory_file,
    resolve_workspace_root,
)
from mini_agent.memory.paths import resolve_global_memory_dir
from mini_agent.memory.memory_provider import MemoryProvider


_PROFILE_SECTION_BEGIN = "<!-- MINI_AGENT_USER_PROFILE_BEGIN -->"
_PROFILE_SECTION_END = "<!-- MINI_AGENT_USER_PROFILE_END -->"
_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_\u4e00-\u9fff]+")


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_text(value: str) -> str:
    return " ".join(value.strip().split())


def _tokenize(text: str) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for token in _TOKEN_PATTERN.findall(text.lower()):
        if token in seen:
            continue
        seen.add(token)
        deduped.append(token)
    return deduped


@dataclass(frozen=True)
class UserFactHit:
    fact: str
    score: float
    index: int


class BuiltinMemoryProvider(MemoryProvider):
    """Builtin profile memory provider with substring-based entry operations."""

    def __init__(
        self,
        workspace_root: str | Path = "./workspace",
        *,
        profile_scope: str = "workspace",
        global_root: str | Path | None = None,
    ):
        requested_root = resolve_workspace_root(workspace_root)
        self._workspace_root = requested_root
        self.profile_scope = " ".join(str(profile_scope or "workspace").split()).lower() or "workspace"
        if self.profile_scope not in {"workspace", "global"}:
            raise ValueError("profile_scope must be workspace or global.")

        if self.profile_scope == "global":
            self.anchor_dir = resolve_global_memory_dir(global_root)
            self.memory_file = self.anchor_dir / "AGENT.md"
            ensure_memory_file(self.memory_file, title="# Agent Memory")
        else:
            layout = discover_memory_layout(requested_root)
            self.anchor_dir = layout.anchor_dir
            self.memory_file = layout.memory_file or (self.anchor_dir / "MEMORY.md")
            ensure_memory_file(self.memory_file, title="# Long-Term Memory")
        self.user_file = self.anchor_dir / "USER.md"
        self._ensure_user_file()

    @property
    def name(self) -> str:
        return "builtin_memory_provider"

    @property
    def workspace_root(self) -> Path:
        return self._workspace_root

    def prefetch(self) -> dict[str, Any]:
        return self.profile()

    def sync_turn(
        self,
        *,
        user_message: str | None = None,
        assistant_message: str | None = None,
    ) -> None:
        # Baseline provider keeps this hook side-effect free.
        _ = user_message
        _ = assistant_message

    def on_session_end(self) -> None:
        # Baseline provider does not mutate profile automatically on session end.
        return None

    def on_delegation(
        self,
        *,
        delegated_task: str,
        delegation_summary: str | None = None,
    ) -> None:
        # Baseline provider does not mutate profile automatically on delegation.
        _ = delegated_task
        _ = delegation_summary

    def profile(self) -> dict[str, Any]:
        facts, updated = self._read_profile_section()
        return {
            "scope": self.profile_scope,
            "anchor_dir": str(self.anchor_dir),
            "memory_file": str(self.memory_file),
            "user_file": str(self.user_file),
            "fact_count": len(facts),
            "facts": facts,
            "last_updated_utc": updated,
        }

    def search(self, query: str, *, limit: int = 5) -> list[dict[str, Any]]:
        normalized_query = _normalize_text(query)
        if not normalized_query:
            raise ValueError("query must not be empty.")

        facts, _ = self._read_profile_section()
        query_lower = normalized_query.lower()
        query_tokens = set(_tokenize(normalized_query))
        ranked: list[UserFactHit] = []

        for index, fact in enumerate(facts):
            fact_lower = fact.lower()
            score = 0.0
            if query_lower in fact_lower:
                score += 4.0
            if query_tokens:
                fact_tokens = set(_tokenize(fact))
                overlap = len(query_tokens & fact_tokens)
                if overlap > 0:
                    score += overlap * 1.5
                    score += float(overlap) / float(max(1, len(query_tokens)))
            if score <= 0.0:
                continue
            ranked.append(UserFactHit(fact=fact, score=score, index=index))

        ranked.sort(key=lambda item: (-item.score, item.index, item.fact))
        bounded = max(1, min(int(limit), 100))
        return [
            {
                "fact": item.fact,
                "score": round(item.score, 6),
                "index": item.index,
            }
            for item in ranked[:bounded]
        ]

    def add_fact(self, fact: str) -> dict[str, Any]:
        normalized_fact = _normalize_text(fact)
        if not normalized_fact:
            raise ValueError("fact must not be empty.")

        facts, _ = self._read_profile_section()
        existing = {item.lower() for item in facts}
        if normalized_fact.lower() in existing:
            return {
                "status": "exists",
                "changed": False,
                "fact_count": len(facts),
                "fact": normalized_fact,
            }

        facts.append(normalized_fact)
        self._write_profile_section(facts)
        return {
            "status": "added",
            "changed": True,
            "fact_count": len(facts),
            "fact": normalized_fact,
        }

    def replace_fact(self, *, match: str, fact: str) -> dict[str, Any]:
        normalized_match = _normalize_text(match).lower()
        normalized_fact = _normalize_text(fact)
        if not normalized_match:
            raise ValueError("match must not be empty.")
        if not normalized_fact:
            raise ValueError("fact must not be empty.")

        facts, _ = self._read_profile_section()
        replaced = 0
        updated_facts: list[str] = []
        for existing in facts:
            if normalized_match in existing.lower():
                updated_facts.append(normalized_fact)
                replaced += 1
            else:
                updated_facts.append(existing)

        # Dedupe after replacement while preserving order.
        deduped: list[str] = []
        seen: set[str] = set()
        for item in updated_facts:
            lowered = item.lower()
            if lowered in seen:
                continue
            seen.add(lowered)
            deduped.append(item)

        if replaced > 0:
            self._write_profile_section(deduped)
            status = "replaced"
            changed = True
        else:
            status = "not_found"
            changed = False

        return {
            "status": status,
            "changed": changed,
            "replaced": replaced,
            "fact_count": len(deduped if replaced > 0 else facts),
            "fact": normalized_fact,
            "match": match,
        }

    def remove_fact(self, *, match: str) -> dict[str, Any]:
        normalized_match = _normalize_text(match).lower()
        if not normalized_match:
            raise ValueError("match must not be empty.")

        facts, _ = self._read_profile_section()
        remaining = [fact for fact in facts if normalized_match not in fact.lower()]
        removed = len(facts) - len(remaining)

        if removed > 0:
            self._write_profile_section(remaining)
            status = "removed"
            changed = True
        else:
            status = "not_found"
            changed = False

        return {
            "status": status,
            "changed": changed,
            "removed": removed,
            "fact_count": len(remaining if removed > 0 else facts),
            "match": match,
        }

    def _ensure_user_file(self) -> None:
        self.user_file.parent.mkdir(parents=True, exist_ok=True)
        if not self.user_file.exists():
            section = self._render_profile_section([])
            self.user_file.write_text(f"# User Profile\n\n{section}\n", encoding="utf-8")
            return

        text = self.user_file.read_text(encoding="utf-8")
        if _PROFILE_SECTION_BEGIN not in text or _PROFILE_SECTION_END not in text:
            section = self._render_profile_section([])
            patched = f"{text.rstrip()}\n\n{section}\n"
            self.user_file.write_text(patched, encoding="utf-8")

    def _read_profile_section(self) -> tuple[list[str], str | None]:
        self._ensure_user_file()
        text = self.user_file.read_text(encoding="utf-8")
        if _PROFILE_SECTION_BEGIN not in text or _PROFILE_SECTION_END not in text:
            return [], None

        begin = text.index(_PROFILE_SECTION_BEGIN) + len(_PROFILE_SECTION_BEGIN)
        end = text.index(_PROFILE_SECTION_END, begin)
        body = text[begin:end]

        facts: list[str] = []
        seen: set[str] = set()
        updated_utc: str | None = None
        for line in body.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.startswith("last_updated_utc:"):
                updated_utc = stripped.split(":", 1)[1].strip() or None
                continue
            if stripped.startswith("- "):
                candidate = stripped[2:].strip()
                if not candidate or candidate == "(no facts yet)":
                    continue
                lowered = candidate.lower()
                if lowered in seen:
                    continue
                seen.add(lowered)
                facts.append(candidate)
        return facts, updated_utc

    def _write_profile_section(self, facts: list[str]) -> None:
        self._ensure_user_file()
        section = self._render_profile_section(facts)
        text = self.user_file.read_text(encoding="utf-8")

        if _PROFILE_SECTION_BEGIN in text and _PROFILE_SECTION_END in text:
            begin = text.index(_PROFILE_SECTION_BEGIN)
            end = text.index(_PROFILE_SECTION_END, begin) + len(_PROFILE_SECTION_END)
            patched = f"{text[:begin].rstrip()}\n\n{section}\n{text[end:].lstrip()}"
        else:
            patched = f"{text.rstrip()}\n\n{section}\n"
        self.user_file.write_text(patched, encoding="utf-8")

    def _render_profile_section(self, facts: list[str]) -> str:
        lines = [
            _PROFILE_SECTION_BEGIN,
            "## User Facts",
        ]
        if facts:
            lines.extend(f"- {fact}" for fact in facts)
        else:
            lines.append("- (no facts yet)")
        lines.append(f"last_updated_utc: {_utc_now_iso()}")
        lines.append(_PROFILE_SECTION_END)
        return "\n".join(lines)
