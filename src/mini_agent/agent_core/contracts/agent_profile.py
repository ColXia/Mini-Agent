"""Durable agent-profile contract."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from ._common import clean_text, normalize_mapping, normalize_text_tuple, utc_now


@dataclass(frozen=True, slots=True)
class AgentProfile:
    """Static agent identity and built-in capability definition."""

    agent_profile_id: str
    role: str | None = None
    identity_label: str | None = None
    static_policy_hints: dict[str, Any] | None = None
    built_in_tool_names: tuple[str, ...] = ()
    built_in_internal_skill_names: tuple[str, ...] = ()
    default_model_routing_intent: str | None = None
    stable_behavior_defaults: dict[str, Any] | None = None
    capability_hints: tuple[str, ...] = ()
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def __post_init__(self) -> None:
        normalized_id = clean_text(self.agent_profile_id)
        if not normalized_id:
            raise ValueError("agent_profile_id is required")
        object.__setattr__(self, "agent_profile_id", normalized_id)
        object.__setattr__(self, "role", clean_text(self.role))
        object.__setattr__(self, "identity_label", clean_text(self.identity_label))
        object.__setattr__(
            self,
            "default_model_routing_intent",
            clean_text(self.default_model_routing_intent),
        )
        object.__setattr__(self, "static_policy_hints", normalize_mapping(self.static_policy_hints))
        object.__setattr__(
            self,
            "built_in_tool_names",
            normalize_text_tuple(self.built_in_tool_names),
        )
        object.__setattr__(
            self,
            "built_in_internal_skill_names",
            normalize_text_tuple(self.built_in_internal_skill_names),
        )
        object.__setattr__(
            self,
            "stable_behavior_defaults",
            normalize_mapping(self.stable_behavior_defaults),
        )
        object.__setattr__(self, "capability_hints", normalize_text_tuple(self.capability_hints))
        if self.created_at is None:
            object.__setattr__(self, "created_at", utc_now())

    def has_tool(self, tool_name: str) -> bool:
        normalized_tool_name = clean_text(tool_name)
        return bool(normalized_tool_name and normalized_tool_name in self.built_in_tool_names)

    def has_internal_skill(self, skill_name: str) -> bool:
        normalized_skill_name = clean_text(skill_name)
        return bool(
            normalized_skill_name
            and normalized_skill_name in self.built_in_internal_skill_names
        )


__all__ = ["AgentProfile"]

