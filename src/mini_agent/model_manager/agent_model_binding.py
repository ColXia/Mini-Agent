"""Persistent state models for agent-owned main model binding."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator


def _safe_text(value: Any) -> str:
    return " ".join(str(value or "").split())


class AgentModelBindingRecord(BaseModel):
    """One explicit agent-owned main model binding record."""

    agent_id: str = Field(min_length=1, default="main-agent")
    provider_source: str = Field(min_length=1)
    provider_id: str = Field(min_length=1)
    model_id: str = Field(min_length=1)
    binding_kind: str = Field(min_length=1, default="explicit")
    bound_at: str | None = None
    switch_generation: int = Field(default=1, ge=0)

    @field_validator("agent_id", "provider_source", "provider_id", "model_id", "binding_kind")
    @classmethod
    def _normalize_required_text(cls, value: str) -> str:
        normalized = _safe_text(value)
        if not normalized:
            raise ValueError("value must not be empty")
        return normalized

    @field_validator("provider_source")
    @classmethod
    def _normalize_provider_source(cls, value: str) -> str:
        normalized = _safe_text(value).lower()
        if normalized not in {"custom", "preset"}:
            raise ValueError("provider_source must be custom or preset")
        return normalized

    @field_validator("binding_kind")
    @classmethod
    def _normalize_binding_kind(cls, value: str) -> str:
        normalized = _safe_text(value).lower()
        if normalized not in {"explicit"}:
            raise ValueError("binding_kind must be explicit")
        return normalized


class AgentModelBindingStore(BaseModel):
    """Persistent collection of explicit agent-owned model bindings."""

    version: int = Field(default=1, ge=1)
    bindings: dict[str, AgentModelBindingRecord] = Field(default_factory=dict)


__all__ = ["AgentModelBindingRecord", "AgentModelBindingStore"]
