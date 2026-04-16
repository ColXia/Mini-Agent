"""Shared tool-approval request models for agent-core execution."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ToolApprovalRequest:
    """Interactive approval request for one tool invocation."""

    token: str
    step: int
    tool_name: str
    arguments: dict[str, Any]
    kind: str
    reason: str
    cache_key: str | None = None
    can_escalate: bool = False


__all__ = ["ToolApprovalRequest"]
