"""History compaction and summarization services for agent-core."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Iterable

from mini_agent.agent_core.context.context_compaction import estimate_tokens
from mini_agent.agent_core.presentation import AgentRuntimePresenter, NullAgentRuntimePresenter
from mini_agent.schema.schema import Message


@dataclass(frozen=True)
class HistoryCompactionResult:
    """Result of one history-compaction attempt."""

    messages: tuple[Message, ...]
    compacted: bool
    skip_next_token_check: bool
    estimated_tokens: int | None = None
    compacted_tokens: int | None = None
    user_message_count: int = 0
    summary_message_count: int = 0


class AgentHistoryCompactionService:
    """Own history summarization and safe summary-message representation."""

    INTERNAL_SUMMARY_MESSAGE_NAME = "__mini_agent_history_summary__"
    INTERNAL_SUMMARY_PREFIX = "[Internal Assistant Summary]"
    LEGACY_SUMMARY_PREFIX = "[Assistant Execution Summary]"

    def __init__(
        self,
        *,
        llm_client: Any,
        presenter: AgentRuntimePresenter | None = None,
        token_estimator: Callable[[Iterable[Message]], int] = estimate_tokens,
    ) -> None:
        self.llm = llm_client
        self.presenter = presenter or NullAgentRuntimePresenter()
        self.token_estimator = token_estimator

    @classmethod
    def _clean_summary_text(cls, text: str) -> str:
        return str(text or "").strip()

    @classmethod
    def _strip_summary_prefix(cls, text: str, prefix: str) -> str:
        content = str(text or "")
        if not content.startswith(prefix):
            return content.strip()
        remainder = content[len(prefix) :]
        return remainder.lstrip("\n\r :").strip()

    @classmethod
    def is_internal_summary_message(cls, message: Message) -> bool:
        if str(getattr(message, "role", "") or "").strip().lower() != "assistant":
            return False
        if str(getattr(message, "name", "") or "").strip() == cls.INTERNAL_SUMMARY_MESSAGE_NAME:
            return True
        content = getattr(message, "content", "")
        return isinstance(content, str) and content.strip().startswith(cls.INTERNAL_SUMMARY_PREFIX)

    @classmethod
    def is_legacy_summary_message(cls, message: Message) -> bool:
        if str(getattr(message, "role", "") or "").strip().lower() != "user":
            return False
        content = getattr(message, "content", "")
        return isinstance(content, str) and content.strip().startswith(cls.LEGACY_SUMMARY_PREFIX)

    @classmethod
    def summary_body(cls, message: Message) -> str:
        content = getattr(message, "content", "")
        if not isinstance(content, str):
            return str(content).strip()
        stripped = content.strip()
        if cls.is_internal_summary_message(message):
            return cls._strip_summary_prefix(stripped, cls.INTERNAL_SUMMARY_PREFIX)
        if cls.is_legacy_summary_message(message):
            return cls._strip_summary_prefix(stripped, cls.LEGACY_SUMMARY_PREFIX)
        return stripped

    @classmethod
    def build_internal_summary_message(
        cls,
        summary_text: str,
    ) -> Message:
        clean_text = cls._clean_summary_text(summary_text)
        content = cls.INTERNAL_SUMMARY_PREFIX
        if clean_text:
            content = f"{content}\n\n{clean_text}"
        return Message(
            role="assistant",
            content=content,
            name=cls.INTERNAL_SUMMARY_MESSAGE_NAME,
        )

    def _normalize_message(self, message: Message) -> Message:
        item = message.model_copy(deep=True)
        if self.is_legacy_summary_message(item):
            return self.build_internal_summary_message(self.summary_body(item))
        if self.is_internal_summary_message(item) and item.name != self.INTERNAL_SUMMARY_MESSAGE_NAME:
            return item.model_copy(update={"name": self.INTERNAL_SUMMARY_MESSAGE_NAME})
        return item

    def _render_summary_source(
        self,
        messages: list[Message],
        *,
        round_num: int,
    ) -> str:
        summary_content = f"Round {round_num} execution process:\n\n"
        for msg in messages:
            if self.is_internal_summary_message(msg):
                summary_body = self.summary_body(msg)
                if summary_body:
                    summary_content += f"Existing summary: {summary_body}\n"
                continue

            if msg.role == "assistant":
                content_text = msg.content if isinstance(msg.content, str) else str(msg.content)
                summary_content += f"Assistant: {content_text}\n"
                if msg.tool_calls:
                    tool_names = [tc.function.name for tc in msg.tool_calls]
                    summary_content += f"  -> Called tools: {', '.join(tool_names)}\n"
            elif msg.role == "tool":
                result_preview = msg.content if isinstance(msg.content, str) else str(msg.content)
                summary_content += f"  -> Tool returned: {result_preview}...\n"
        return summary_content

    async def create_summary(
        self,
        messages: list[Message],
        *,
        round_num: int,
    ) -> str:
        """Create a concise summary for one execution round."""
        if not messages:
            return ""

        summary_content = self._render_summary_source(messages, round_num=round_num)
        try:
            summary_prompt = f"""Please provide a concise summary of the following Agent execution process:

{summary_content}

Requirements:
1. Focus on what tasks were completed and which tools were called
2. Keep key execution results and important findings
3. Be concise and clear, within 1000 words
4. Use English
5. Do not include "user" related content, only summarize the Agent's execution process"""

            response = await self.llm.generate(
                messages=[
                    Message(
                        role="system",
                        content="You are an assistant skilled at summarizing Agent execution processes.",
                    ),
                    Message(role="user", content=summary_prompt),
                ]
            )
            summary_text = self._clean_summary_text(getattr(response, "content", ""))
            self.presenter.history_summary_generated(round_num=round_num)
            return summary_text
        except Exception as exc:
            self.presenter.history_summary_generation_failed(
                round_num=round_num,
                error=str(exc),
            )
            return summary_content

    def _reuse_existing_summary(
        self,
        messages: list[Message],
    ) -> Message | None:
        if not messages or not all(self.is_internal_summary_message(msg) for msg in messages):
            return None
        if len(messages) == 1:
            return messages[0].model_copy(deep=True)

        combined = "\n\n".join(
            summary_body
            for summary_body in (self.summary_body(msg) for msg in messages)
            if summary_body
        ).strip()
        if not combined:
            return None
        return self.build_internal_summary_message(combined)

    async def compact_history(
        self,
        *,
        messages: list[Message],
        token_limit: int,
        api_total_tokens: int,
        skip_next_token_check: bool,
    ) -> HistoryCompactionResult:
        """Compact conversation history when token limits are exceeded."""
        normalized_messages = [self._normalize_message(message) for message in messages]

        if skip_next_token_check:
            return HistoryCompactionResult(
                messages=tuple(normalized_messages),
                compacted=False,
                skip_next_token_check=False,
            )

        estimated_tokens = self.token_estimator(normalized_messages)
        should_summarize = estimated_tokens > token_limit or api_total_tokens > token_limit
        if not should_summarize:
            return HistoryCompactionResult(
                messages=tuple(normalized_messages),
                compacted=False,
                skip_next_token_check=False,
                estimated_tokens=estimated_tokens,
            )

        self.presenter.history_summary_triggered(
            estimated_tokens=estimated_tokens,
            api_total_tokens=api_total_tokens,
            token_limit=token_limit,
        )

        user_indices = [index for index, message in enumerate(normalized_messages) if message.role == "user" and index > 0]
        if not user_indices:
            self.presenter.history_summary_insufficient_messages()
            return HistoryCompactionResult(
                messages=tuple(normalized_messages),
                compacted=False,
                skip_next_token_check=False,
                estimated_tokens=estimated_tokens,
            )

        new_messages = [normalized_messages[0]]
        summary_count = 0

        for index, user_idx in enumerate(user_indices):
            new_messages.append(normalized_messages[user_idx].model_copy(deep=True))
            next_user_idx = user_indices[index + 1] if index < len(user_indices) - 1 else len(normalized_messages)
            execution_messages = [msg.model_copy(deep=True) for msg in normalized_messages[user_idx + 1 : next_user_idx]]
            if not execution_messages:
                continue

            preserved_summary = self._reuse_existing_summary(execution_messages)
            if preserved_summary is not None:
                new_messages.append(preserved_summary)
                summary_count += 1
                continue

            summary_text = await self.create_summary(execution_messages, round_num=index + 1)
            if not summary_text:
                continue
            new_messages.append(self.build_internal_summary_message(summary_text))
            summary_count += 1

        compacted_tokens = self.token_estimator(new_messages)
        effective_compaction = compacted_tokens < estimated_tokens
        if not effective_compaction:
            return HistoryCompactionResult(
                messages=tuple(normalized_messages),
                compacted=False,
                skip_next_token_check=False,
                estimated_tokens=estimated_tokens,
                compacted_tokens=compacted_tokens,
                user_message_count=len(user_indices),
                summary_message_count=summary_count,
            )
        self.presenter.history_summary_completed(
            estimated_tokens=estimated_tokens,
            compacted_tokens=compacted_tokens,
            user_message_count=len(user_indices),
            summary_message_count=summary_count,
        )
        return HistoryCompactionResult(
            messages=tuple(new_messages),
            compacted=True,
            skip_next_token_check=True,
            estimated_tokens=estimated_tokens,
            compacted_tokens=compacted_tokens,
            user_message_count=len(user_indices),
            summary_message_count=summary_count,
        )


__all__ = [
    "AgentHistoryCompactionService",
    "HistoryCompactionResult",
]
