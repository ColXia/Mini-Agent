"""Automatic post-turn memory writeback policy."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import re
from typing import Any

from mini_agent.memory.knowledge_base_grounding import extract_knowledge_base_grounding_from_turn_messages
from mini_agent.memory.quality import clean_memory_text, is_low_signal_control_turn
from mini_agent.memory.service import MemoryService


_QUESTION_HINTS = ("?", "？", "什么", "怎么", "如何", "为什么", "吗", "吗？", "what", "how", "why", "when")
_PROFILE_PATTERNS = (
    re.compile(r"(我喜欢|我偏好|我希望|我习惯|我更倾向|我的目标是)"),
    re.compile(r"(请用中文|请用英文|用中文回复|用英文回复)"),
    re.compile(r"(简洁一点|详细一点|尽量简洁|尽量详细)"),
)
_DECISION_PATTERNS = (
    re.compile(r"(改为|统一|暂停开发|暂停|仅\s*TUI/CLI|只用|优先|默认|按.+为主|采用|接入|不安装)"),
    re.compile(r"(先.+后.+)"),
    re.compile(r"(删除|新增|保留|去掉)"),
)


@dataclass(frozen=True)
class TurnMemoryAutomationResult:
    enabled: bool
    skipped_reason: str
    stored_daily_note: bool
    stored_long_term_note: bool
    stored_profile_fact: bool
    explicit_note_tool_used: bool
    explicit_profile_tool_used: bool
    explicit_note_tool_succeeded: bool
    explicit_profile_tool_succeeded: bool
    knowledge_base_grounded: bool
    action_count: int
    actions: list[dict[str, Any]]

    def to_payload(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "skipped_reason": self.skipped_reason,
            "stored_daily_note": self.stored_daily_note,
            "stored_long_term_note": self.stored_long_term_note,
            "stored_profile_fact": self.stored_profile_fact,
            "explicit_note_tool_used": self.explicit_note_tool_used,
            "explicit_profile_tool_used": self.explicit_profile_tool_used,
            "explicit_note_tool_succeeded": self.explicit_note_tool_succeeded,
            "explicit_profile_tool_succeeded": self.explicit_profile_tool_succeeded,
            "knowledge_base_grounded": self.knowledge_base_grounded,
            "action_count": self.action_count,
            "actions": [dict(item) for item in self.actions],
        }


class TurnMemoryAutomation:
    """Conservative automatic memory writeback after a successful turn."""

    def __init__(
        self,
        workspace_dir: str,
        *,
        session_store_dir: str | None = None,
        enabled: bool = True,
        max_message_chars: int = 220,
        min_assistant_chars_for_daily: int = 120,
    ) -> None:
        self.enabled = bool(enabled)
        self.memory = MemoryService(workspace_dir, session_store_dir=session_store_dir)
        self.max_message_chars = max(80, int(max_message_chars))
        self.min_assistant_chars_for_daily = max(40, int(min_assistant_chars_for_daily))

    def process_turn(
        self,
        *,
        stop_reason: str,
        turn_messages: list[Any],
        turn_context: Any | None = None,
        assistant_message: str = "",
    ) -> TurnMemoryAutomationResult:
        if not self.enabled:
            return self._result(skipped_reason="disabled")
        if str(stop_reason or "").strip().lower() != "end_turn":
            return self._result(skipped_reason="turn_not_completed")

        metadata = self._turn_context_metadata(turn_context)
        if self._is_workflow_turn(metadata):
            return self._result(skipped_reason="workflow_turn")

        user_message = self._last_message_text(turn_messages, role="user")
        assistant_text = self._clean_text(assistant_message) or self._last_message_text(turn_messages, role="assistant")
        if not user_message or not assistant_text:
            return self._result(skipped_reason="missing_turn_messages")

        used_tools = self._tool_names(turn_messages)
        successful_tools = self._successful_tool_names(turn_messages)
        explicit_note_tool_used = "record_note" in used_tools
        explicit_profile_tool_used = "user_modeling" in used_tools
        explicit_note_tool_succeeded = "record_note" in successful_tools
        explicit_profile_tool_succeeded = "user_modeling" in successful_tools
        kb_grounding = extract_knowledge_base_grounding_from_turn_messages(turn_messages)
        knowledge_base_grounded = bool(kb_grounding.get("grounded"))
        tool_count = len(used_tools)

        if is_low_signal_control_turn(
            user_message=user_message,
            assistant_message=assistant_text,
            tool_count=tool_count,
        ):
            return self._result(
                skipped_reason="low_signal_control_turn",
                explicit_note_tool_used=explicit_note_tool_used,
                explicit_profile_tool_used=explicit_profile_tool_used,
                explicit_note_tool_succeeded=explicit_note_tool_succeeded,
                explicit_profile_tool_succeeded=explicit_profile_tool_succeeded,
                knowledge_base_grounded=knowledge_base_grounded,
            )

        now = datetime.now()
        actions: list[dict[str, Any]] = []
        stored_daily_note = False
        stored_long_term_note = False
        stored_profile_fact = False

        if not explicit_profile_tool_succeeded:
            fact = self._extract_profile_fact(user_message)
            if fact:
                result = self.memory.add_profile_fact(fact=fact)
                if bool(result.get("changed")):
                    profile_snapshot = self.memory.profile()
                    stored_profile_fact = True
                    actions.append(
                        {
                            "kind": "profile_fact",
                            "target": str(profile_snapshot.get("user_file") or "USER.md"),
                            "fact": fact,
                        }
                    )

        if not explicit_note_tool_succeeded:
            decision = self._extract_project_decision(user_message)
            if (
                not knowledge_base_grounded
                and decision
                and not self._long_term_note_exists(content=decision, category="decision")
            ):
                self.memory.append_note(
                    content=decision,
                    category="decision",
                    scope="long_term",
                    now=now,
                )
                stored_long_term_note = True
                actions.append(
                    {
                        "kind": "long_term_note",
                        "target": "MEMORY.md",
                        "category": "decision",
                        "content": decision,
                    }
                )

            if (
                not knowledge_base_grounded
                and self._should_store_daily_note(
                    user_message=user_message,
                    assistant_message=assistant_text,
                    turn_messages=turn_messages,
                    stored_profile_fact=stored_profile_fact,
                    stored_long_term_note=stored_long_term_note,
                )
            ):
                summary = self._build_daily_summary(
                    user_message=user_message,
                    assistant_message=assistant_text,
                    tool_count=len(used_tools),
                )
                if summary and not self._daily_note_exists(content=summary, category="turn_summary", day=now.date().isoformat()):
                    self.memory.append_note(
                        content=summary,
                        category="turn_summary",
                        scope="daily",
                        now=now,
                    )
                    stored_daily_note = True
                    actions.append(
                        {
                            "kind": "daily_note",
                            "target": f"memory/{now.date().isoformat()}.md",
                            "category": "turn_summary",
                            "content": summary,
                        }
                    )

        if not actions:
            return self._result(
                skipped_reason=(
                    "knowledge_base_grounded_turn_requires_explicit_confirmation"
                    if knowledge_base_grounded
                    else "no_candidate_memory"
                ),
                explicit_note_tool_used=explicit_note_tool_used,
                explicit_profile_tool_used=explicit_profile_tool_used,
                explicit_note_tool_succeeded=explicit_note_tool_succeeded,
                explicit_profile_tool_succeeded=explicit_profile_tool_succeeded,
                knowledge_base_grounded=knowledge_base_grounded,
            )

        return TurnMemoryAutomationResult(
            enabled=True,
            skipped_reason="",
            stored_daily_note=stored_daily_note,
            stored_long_term_note=stored_long_term_note,
            stored_profile_fact=stored_profile_fact,
            explicit_note_tool_used=explicit_note_tool_used,
            explicit_profile_tool_used=explicit_profile_tool_used,
            explicit_note_tool_succeeded=explicit_note_tool_succeeded,
            explicit_profile_tool_succeeded=explicit_profile_tool_succeeded,
            knowledge_base_grounded=knowledge_base_grounded,
            action_count=len(actions),
            actions=actions,
        )

    def _result(
        self,
        *,
        skipped_reason: str,
        explicit_note_tool_used: bool = False,
        explicit_profile_tool_used: bool = False,
        explicit_note_tool_succeeded: bool = False,
        explicit_profile_tool_succeeded: bool = False,
        knowledge_base_grounded: bool = False,
    ) -> TurnMemoryAutomationResult:
        return TurnMemoryAutomationResult(
            enabled=self.enabled,
            skipped_reason=skipped_reason,
            stored_daily_note=False,
            stored_long_term_note=False,
            stored_profile_fact=False,
            explicit_note_tool_used=explicit_note_tool_used,
            explicit_profile_tool_used=explicit_profile_tool_used,
            explicit_note_tool_succeeded=explicit_note_tool_succeeded,
            explicit_profile_tool_succeeded=explicit_profile_tool_succeeded,
            knowledge_base_grounded=knowledge_base_grounded,
            action_count=0,
            actions=[],
        )

    def _extract_profile_fact(self, user_message: str) -> str | None:
        normalized = self._clean_text(user_message)
        if not normalized or self._looks_like_question(normalized):
            return None
        if len(normalized) > self.max_message_chars:
            return None
        if not any(pattern.search(normalized) for pattern in _PROFILE_PATTERNS):
            return None
        return normalized

    def _extract_project_decision(self, user_message: str) -> str | None:
        normalized = self._clean_text(user_message)
        if not normalized or self._looks_like_question(normalized):
            return None
        if len(normalized) > self.max_message_chars:
            return None
        if not any(pattern.search(normalized) for pattern in _DECISION_PATTERNS):
            return None
        return normalized

    def _should_store_daily_note(
        self,
        *,
        user_message: str,
        assistant_message: str,
        turn_messages: list[Any],
        stored_profile_fact: bool,
        stored_long_term_note: bool,
    ) -> bool:
        if stored_profile_fact or stored_long_term_note:
            return True
        if len(self._clean_text(assistant_message)) >= self.min_assistant_chars_for_daily:
            return True
        used_tools = self._tool_names(turn_messages)
        return len(used_tools) > 0

    def _build_daily_summary(
        self,
        *,
        user_message: str,
        assistant_message: str,
        tool_count: int,
    ) -> str:
        user_part = self._truncate(user_message)
        assistant_part = self._truncate(assistant_message)
        tool_suffix = f" | tools={tool_count}" if tool_count > 0 else ""
        return f"user: {user_part} | outcome: {assistant_part}{tool_suffix}".strip()

    def _tool_names(self, turn_messages: list[Any]) -> set[str]:
        names: set[str] = set()
        for message in turn_messages:
            role = self._clean_text(getattr(message, "role", "")).lower()
            if role == "tool":
                tool_name = self._clean_text(getattr(message, "name", "")).lower()
                if tool_name:
                    names.add(tool_name)
            tool_calls = getattr(message, "tool_calls", None)
            if isinstance(tool_calls, list):
                for tool_call in tool_calls:
                    function = getattr(tool_call, "function", None)
                    tool_name = self._clean_text(getattr(function, "name", "")).lower()
                    if tool_name:
                        names.add(tool_name)
        return names

    def _successful_tool_names(self, turn_messages: list[Any]) -> set[str]:
        names: set[str] = set()
        for message in turn_messages:
            role = self._clean_text(getattr(message, "role", "")).lower()
            if role != "tool":
                continue
            tool_name = self._clean_text(getattr(message, "name", "")).lower()
            if not tool_name:
                continue
            content_text = self._message_content_text(message).lower()
            if content_text.startswith("error:"):
                continue
            names.add(tool_name)
        return names

    def _daily_note_exists(self, *, content: str, category: str, day: str) -> bool:
        target_name = f"{day}.md"
        for note in self.memory.load_notes():
            if note.category != category or self._clean_text(note.content) != self._clean_text(content):
                continue
            if note.path.name == target_name:
                return True
        return False

    def _long_term_note_exists(self, *, content: str, category: str) -> bool:
        long_term_file = self.memory.long_term_file.resolve()
        for note in self.memory.load_notes():
            if note.path.resolve() != long_term_file:
                continue
            if note.category == category and self._clean_text(note.content) == self._clean_text(content):
                return True
        return False

    @staticmethod
    def _turn_context_metadata(turn_context: Any | None) -> dict[str, Any]:
        if isinstance(turn_context, dict):
            metadata = turn_context.get("metadata")
            return dict(metadata) if isinstance(metadata, dict) else {}
        metadata = getattr(turn_context, "metadata", None)
        return dict(metadata) if isinstance(metadata, dict) else {}

    @staticmethod
    def _is_workflow_turn(metadata: dict[str, Any]) -> bool:
        mode = " ".join(str(metadata.get("mode", "") or "").split()).lower()
        workflow = " ".join(str(metadata.get("workflow", "") or "").split()).lower()
        return mode == "workflow" or bool(workflow)

    @staticmethod
    def _last_message_text(turn_messages: list[Any], *, role: str) -> str:
        normalized_role = role.strip().lower()
        for message in reversed(turn_messages):
            message_role = " ".join(str(getattr(message, "role", "") or "").split()).lower()
            if message_role != normalized_role:
                continue
            text = TurnMemoryAutomation._message_content_text(message)
            if text:
                return text
        return ""

    @staticmethod
    def _message_content_text(message: Any) -> str:
        content = getattr(message, "content", "")
        if isinstance(content, list):
            content = " ".join(str(item) for item in content)
        return TurnMemoryAutomation._clean_text(content)

    @staticmethod
    def _clean_text(value: Any) -> str:
        return clean_memory_text(value)

    def _truncate(self, value: str) -> str:
        text = self._clean_text(value)
        if len(text) <= self.max_message_chars:
            return text
        return f"{text[: max(0, self.max_message_chars - 3)]}..."

    @staticmethod
    def _looks_like_question(value: str) -> bool:
        normalized = " ".join(str(value or "").split()).lower()
        return any(token in normalized for token in _QUESTION_HINTS)
