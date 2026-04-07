"""Tool-output masking helpers for compact context windows."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Iterable

from mini_agent.schema.schema import Message


@dataclass(frozen=True)
class MaskedOutputRecord:
    """Metadata about one masked message."""

    index: int
    reason: str


def _query_terms(query: str | None) -> set[str]:
    if not query:
        return set()
    return {
        token.lower()
        for token in re.findall(r"[A-Za-z0-9_]{3,}", query)
        if token.strip()
    }


class ToolOutputMasker:
    """Mask older tool outputs that are likely irrelevant for the current task."""

    def __init__(self, *, min_length_for_mask: int = 240) -> None:
        self.min_length_for_mask = max(40, int(min_length_for_mask))

    def mask_messages(
        self,
        messages: Iterable[Message],
        *,
        query: str | None = None,
        preserve_recent: int = 2,
    ) -> tuple[list[Message], list[MaskedOutputRecord]]:
        items = [msg.model_copy(deep=True) for msg in messages]
        terms = _query_terms(query)
        preserve_recent = max(0, int(preserve_recent))

        tool_indices = [index for index, msg in enumerate(items) if msg.role == "tool"]
        preserved = set(tool_indices[-preserve_recent:]) if preserve_recent else set()

        masked_records: list[MaskedOutputRecord] = []
        for index, msg in enumerate(items):
            if msg.role != "tool" or index in preserved:
                continue
            if not isinstance(msg.content, str):
                continue
            content_lower = msg.content.lower()
            matches_query = bool(terms) and any(term in content_lower for term in terms)
            if matches_query:
                continue
            if len(msg.content) < self.min_length_for_mask and terms:
                continue

            reason = "irrelevant_to_query" if terms else "old_tool_output"
            summary = f"[Tool output masked: {reason}; chars={len(msg.content)}]"
            items[index] = msg.model_copy(update={"content": summary})
            masked_records.append(MaskedOutputRecord(index=index, reason=reason))

        return items, masked_records
