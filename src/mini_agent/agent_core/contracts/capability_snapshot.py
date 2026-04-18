"""Resolved capability snapshot contracts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from ._common import clean_text, normalize_mapping, normalize_text_tuple, utc_now


@dataclass(frozen=True, slots=True)
class CapabilitySnapshot:
    """Stable resolved capability view consumed by one run."""

    capability_snapshot_id: str
    agent_profile_id: str
    agent_instance_id: str
    run_id: str
    workspace_id: str
    session_id: str
    resolved_tool_names: tuple[str, ...] = ()
    resolved_tool_policies: dict[str, Any] | None = None
    visible_skill_names: tuple[str, ...] = ()
    visible_memory_scopes: tuple[str, ...] = ()
    enabled_external_capabilities: tuple[str, ...] = ()
    agent_model_provider_id: str | None = None
    agent_model_id: str | None = None
    agent_model_capability_profile: dict[str, Any] | None = None
    workspace_runtime_mode: str | None = None
    approval_profile: dict[str, Any] | None = None
    context_policy: dict[str, Any] | None = None
    refresh_reason: str | None = None
    created_at: datetime | None = None
    revision: int = 1

    def __post_init__(self) -> None:
        required_fields = {
            "capability_snapshot_id": clean_text(self.capability_snapshot_id),
            "agent_profile_id": clean_text(self.agent_profile_id),
            "agent_instance_id": clean_text(self.agent_instance_id),
            "run_id": clean_text(self.run_id),
            "workspace_id": clean_text(self.workspace_id),
            "session_id": clean_text(self.session_id),
        }
        for field_name, value in required_fields.items():
            if not value:
                raise ValueError(f"{field_name} is required")
            object.__setattr__(self, field_name, value)
        if self.revision < 1:
            raise ValueError("revision must be >= 1")
        object.__setattr__(self, "resolved_tool_names", normalize_text_tuple(self.resolved_tool_names))
        object.__setattr__(
            self,
            "resolved_tool_policies",
            normalize_mapping(self.resolved_tool_policies),
        )
        object.__setattr__(self, "visible_skill_names", normalize_text_tuple(self.visible_skill_names))
        object.__setattr__(
            self,
            "visible_memory_scopes",
            normalize_text_tuple(self.visible_memory_scopes),
        )
        object.__setattr__(
            self,
            "enabled_external_capabilities",
            normalize_text_tuple(self.enabled_external_capabilities),
        )
        object.__setattr__(self, "agent_model_provider_id", clean_text(self.agent_model_provider_id))
        object.__setattr__(self, "agent_model_id", clean_text(self.agent_model_id))
        object.__setattr__(
            self,
            "agent_model_capability_profile",
            normalize_mapping(self.agent_model_capability_profile),
        )
        object.__setattr__(self, "workspace_runtime_mode", clean_text(self.workspace_runtime_mode))
        object.__setattr__(self, "approval_profile", normalize_mapping(self.approval_profile))
        object.__setattr__(self, "context_policy", normalize_mapping(self.context_policy))
        object.__setattr__(self, "refresh_reason", clean_text(self.refresh_reason))
        if self.created_at is None:
            object.__setattr__(self, "created_at", utc_now())

    @property
    def model_identity(self) -> tuple[str | None, str | None]:
        return self.agent_model_provider_id, self.agent_model_id

    def exposes_tool(self, tool_name: str) -> bool:
        normalized_tool_name = clean_text(tool_name)
        return bool(normalized_tool_name and normalized_tool_name in self.resolved_tool_names)


__all__ = ["CapabilitySnapshot"]

