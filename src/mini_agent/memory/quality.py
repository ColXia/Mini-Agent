"""Shared quality filters for memory writeback decisions."""

from __future__ import annotations

import re
from typing import Any


_LOW_SIGNAL_CONTROL_EXACT = {
    "1",
    "2",
    "3",
    "4",
    "5",
    "ok",
    "okay",
    "yes",
    "y",
    "continue",
    "go ahead",
    "do it",
    "sounds good",
    "approved",
    "good",
    "fine",
    "sure",
    "can do",
    "hao",
    "haode",
    "ke yi",
    "keyi",
    "xing",
    "ji xu",
    "jixu",
    "hao de",
    "continue please",
    "please continue",
    "可以",
    "可以做",
    "可以，做",
    "可以，继续",
    "继续",
    "继续做",
    "做吧",
    "好",
    "好的",
    "行",
    "收到",
    "明白",
    "嗯",
    "嗯嗯",
}
_LOW_SIGNAL_CONTROL_RE = re.compile(r"^(?:[0-9]+|[一二三四五六七八九十]+)$")


def clean_memory_text(value: Any) -> str:
    return " ".join(str(value or "").split())


def is_low_signal_control_turn(
    *,
    user_message: str,
    assistant_message: str = "",
    tool_count: int = 0,
    max_substantive_assistant_chars: int = 120,
) -> bool:
    """Return whether a turn looks like control chatter instead of reusable memory.

    This intentionally filters short approvals, numeric option picks, and command-only
    interactions when they did not produce substantive work.
    """

    normalized_user = clean_memory_text(user_message)
    if not normalized_user:
        return False

    if int(tool_count) > 0:
        return False

    normalized_assistant = clean_memory_text(assistant_message)
    if len(normalized_assistant) >= max(40, int(max_substantive_assistant_chars)):
        return False

    lowered_user = normalized_user.lower()
    if normalized_user.startswith("/"):
        return True
    if lowered_user in _LOW_SIGNAL_CONTROL_EXACT or normalized_user in _LOW_SIGNAL_CONTROL_EXACT:
        return True
    if _LOW_SIGNAL_CONTROL_RE.fullmatch(normalized_user):
        return True
    return False


__all__ = [
    "clean_memory_text",
    "is_low_signal_control_turn",
]
