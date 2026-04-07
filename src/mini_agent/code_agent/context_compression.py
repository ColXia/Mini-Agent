"""Context compression baseline with reverse-budget and layered compaction."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import tiktoken

from mini_agent.code_agent.output_masking import ToolOutputMasker
from mini_agent.schema.schema import Message


@dataclass(frozen=True)
class CompressionStats:
    """Compression metrics for one compaction pass."""

    original_messages: int
    compressed_messages: int
    original_tokens: int
    compressed_tokens: int
    masked_messages: int = 0
    snipped_messages: int = 0
    merged_messages: int = 0


@dataclass(frozen=True)
class ContextCompressionResult:
    """Compaction output payload."""

    messages: tuple[Message, ...]
    stats: CompressionStats


def _message_token_count(encoding, message: Message) -> int:  # noqa: ANN001
    total = 4
    if isinstance(message.content, str):
        total += len(encoding.encode(message.content))
    elif isinstance(message.content, list):
        total += len(encoding.encode(str(message.content)))
    if message.thinking:
        total += len(encoding.encode(message.thinking))
    if message.tool_calls:
        total += len(encoding.encode(str(message.tool_calls)))
    return total


def estimate_tokens(messages: Iterable[Message]) -> int:
    """Estimate message tokens with `cl100k_base` fallback."""
    items = list(messages)
    try:
        encoding = tiktoken.get_encoding("cl100k_base")
        return sum(_message_token_count(encoding, msg) for msg in items)
    except Exception:
        total_chars = 0
        for msg in items:
            total_chars += len(str(msg.content))
            if msg.thinking:
                total_chars += len(msg.thinking)
            if msg.tool_calls:
                total_chars += len(str(msg.tool_calls))
        return int(total_chars / 2.5)


class LayeredContextCompactor:
    """Small, strong context compactor for code-agent turns."""

    def __init__(
        self,
        *,
        token_budget: int,
        keep_recent_tool_messages: int = 2,
        snip_tail_lines: int = 30,
        masker: ToolOutputMasker | None = None,
    ) -> None:
        self.token_budget = max(200, int(token_budget))
        self.keep_recent_tool_messages = max(0, int(keep_recent_tool_messages))
        self.snip_tail_lines = max(1, int(snip_tail_lines))
        self.masker = masker or ToolOutputMasker()

    def _snip_tool_outputs(self, messages: list[Message]) -> tuple[list[Message], int]:
        items = [msg.model_copy(deep=True) for msg in messages]
        tool_indices = [index for index, msg in enumerate(items) if msg.role == "tool"]
        preserved = set(tool_indices[-self.keep_recent_tool_messages :]) if self.keep_recent_tool_messages else set()
        snipped_count = 0

        for index in tool_indices:
            if index in preserved:
                continue
            msg = items[index]
            if not isinstance(msg.content, str):
                continue
            lines = msg.content.splitlines()
            if len(lines) <= self.snip_tail_lines:
                continue
            tail = "\n".join(lines[-self.snip_tail_lines :])
            header = f"[Tool output snipped: kept last {self.snip_tail_lines} lines of {len(lines)}]"
            items[index] = msg.model_copy(update={"content": f"{header}\n{tail}"})
            snipped_count += 1
        return items, snipped_count

    def _microcompact(self, messages: list[Message]) -> tuple[list[Message], int]:
        compacted: list[Message] = []
        merged = 0
        for msg in messages:
            if (
                compacted
                and msg.role == "assistant"
                and compacted[-1].role == "assistant"
                and isinstance(msg.content, str)
                and isinstance(compacted[-1].content, str)
            ):
                merged += 1
                merged_content = f"{compacted[-1].content}\n{msg.content}".strip()
                compacted[-1] = compacted[-1].model_copy(update={"content": merged_content})
                continue
            compacted.append(msg.model_copy(deep=True))
        return compacted, merged

    def _reverse_budget_select(self, messages: list[Message]) -> list[Message]:
        if not messages:
            return []
        token_counts = [estimate_tokens([msg]) for msg in messages]

        selected: set[int] = set()
        for index, msg in enumerate(messages):
            if msg.role in {"system", "user"}:
                selected.add(index)

        used = sum(token_counts[index] for index in selected)
        for index in range(len(messages) - 1, -1, -1):
            if index in selected:
                continue
            candidate = token_counts[index]
            if used + candidate > self.token_budget:
                continue
            selected.add(index)
            used += candidate

        return [messages[index] for index in sorted(selected)]

    def compact(
        self,
        messages: Iterable[Message],
        *,
        query: str | None = None,
        enable_masking: bool = True,
    ) -> ContextCompressionResult:
        original_items = [msg.model_copy(deep=True) for msg in messages]
        original_tokens = estimate_tokens(original_items)

        snipped_items, snipped_count = self._snip_tool_outputs(original_items)
        masked_count = 0
        if enable_masking:
            snipped_items, masked_records = self.masker.mask_messages(
                snipped_items,
                query=query,
                preserve_recent=self.keep_recent_tool_messages,
            )
            masked_count = len(masked_records)

        compacted_items, merged_count = self._microcompact(snipped_items)
        selected_items = self._reverse_budget_select(compacted_items)
        compressed_tokens = estimate_tokens(selected_items)

        return ContextCompressionResult(
            messages=tuple(selected_items),
            stats=CompressionStats(
                original_messages=len(original_items),
                compressed_messages=len(selected_items),
                original_tokens=original_tokens,
                compressed_tokens=compressed_tokens,
                masked_messages=masked_count,
                snipped_messages=snipped_count,
                merged_messages=merged_count,
            ),
        )
