"""Model pool core contracts for v11.2.

This module provides the core model pool objects that serve only Agent,
not Workspace or Session. The model system is completely separated from
workspace/session logic.

Key principles:
- ModelPool only serves Agent
- Model does not mix with Workspace
- Model selection/binding/adapter/switching are Agent-ModelCore module affairs
- Session does not participate
- Workspace does not participate
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from mini_agent.utils.text import safe_text


def _safe_text(value: Any) -> str:
    return safe_text(value)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ProviderSource(str, Enum):
    """Provider source types."""

    PRESET = "preset"
    CUSTOM = "custom"


class ProtocolFamily(str, Enum):
    """Supported provider protocol families."""

    OPENAI = "openai"
    ANTHROPIC = "anthropic"


class ModelKind(str, Enum):
    """Model kinds for Agent main model selection."""

    CHAT = "chat"
    REASONING = "reasoning"


class CapabilityTruth(str, Enum):
    """Capability truth values."""

    SUPPORTED = "supported"
    UNSUPPORTED = "unsupported"
    UNKNOWN = "unknown"


class CapabilityConfidence(str, Enum):
    """Capability confidence levels."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class CapabilitySource(str, Enum):
    """Capability source types."""

    STATIC_DECLARATION = "static_declaration"
    ACTIVE_PROBE_TOOL_CALL = "active_probe_tool_call"
    ACTIVE_PROBE_THINKING_CONTENT = "active_probe_thinking_content"
    ACTIVE_PROBE_NO_TOOL_CALL = "active_probe_no_tool_call"
    ACTIVE_PROBE_NO_THINKING = "active_probe_no_thinking"
    ACTIVE_PROBE_TOOL_ERROR = "active_probe_tool_error"
    ACTIVE_PROBE_THINKING_ERROR = "active_probe_thinking_error"
    PROVIDER_MODELS_ENDPOINT = "provider_models_endpoint"
    OLLAMA_API_TAGS = "ollama_api_tags"
    OPENROUTER_MODELS = "openrouter_models"
    MINIMAX_MODELS = "minimax_models"
    KNOWN_MODEL_DEFAULTS = "known_model_defaults"


@dataclass(frozen=True, slots=True)
class ProviderEntry:
    """Unified provider definition.

    This represents a single provider entry in the model pool,
    supporting both preset and custom sources.
    """

    provider_id: str
    provider_source: ProviderSource
    protocol_family: ProtocolFamily
    api_base: str
    provider_name: str
    enabled: bool = True
    priority: int = 0
    timeout: int = 60
    headers: dict[str, str] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        normalized_id = _safe_text(self.provider_id)
        if not normalized_id:
            raise ValueError("provider_id is required")
        object.__setattr__(self, "provider_id", normalized_id)
        object.__setattr__(self, "api_base", _safe_text(self.api_base))
        object.__setattr__(self, "provider_name", _safe_text(self.provider_name))
        object.__setattr__(self, "headers", dict(self.headers) if self.headers else {})
        object.__setattr__(self, "metadata", dict(self.metadata) if self.metadata else {})

    @property
    def full_id(self) -> str:
        """Return the fully qualified provider id."""
        return f"{self.provider_source.value}.{self.provider_id}"


@dataclass(frozen=True, slots=True)
class ModelDescriptor:
    """Model catalog entry.

    This represents a single model in the model pool,
    with its capability metadata.
    """

    provider_id: str
    model_id: str
    display_name: str
    model_kind: ModelKind = ModelKind.CHAT
    context_window: int | None = None
    learned_token_limit: int | None = None
    supports_tools: bool | None = None
    supports_tools_truth: CapabilityTruth = CapabilityTruth.UNKNOWN
    supports_tools_confidence: CapabilityConfidence = CapabilityConfidence.LOW
    supports_tools_source: CapabilitySource = CapabilitySource.KNOWN_MODEL_DEFAULTS
    supports_thinking: bool | None = None
    supports_thinking_truth: CapabilityTruth = CapabilityTruth.UNKNOWN
    supports_thinking_confidence: CapabilityConfidence = CapabilityConfidence.LOW
    supports_thinking_source: CapabilitySource = CapabilitySource.KNOWN_MODEL_DEFAULTS
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        normalized_provider_id = _safe_text(self.provider_id)
        normalized_model_id = _safe_text(self.model_id)
        if not normalized_provider_id:
            raise ValueError("provider_id is required")
        if not normalized_model_id:
            raise ValueError("model_id is required")
        object.__setattr__(self, "provider_id", normalized_provider_id)
        object.__setattr__(self, "model_id", normalized_model_id)
        object.__setattr__(self, "display_name", _safe_text(self.display_name) or normalized_model_id)
        object.__setattr__(self, "metadata", dict(self.metadata) if self.metadata else {})

    @property
    def full_id(self) -> str:
        """Return the fully qualified model id."""
        return f"{self.provider_id}.{self.model_id}"

    @property
    def token_limit(self) -> int | None:
        """Return the effective token limit."""
        if self.learned_token_limit is not None:
            return self.learned_token_limit
        if self.context_window is not None:
            return int(self.context_window * 0.8)
        return None

    @property
    def is_tools_capable(self) -> bool:
        """Return True if model supports tools."""
        if self.supports_tools_truth == CapabilityTruth.SUPPORTED:
            return True
        if self.supports_tools_truth == CapabilityTruth.UNSUPPORTED:
            return False
        return self.supports_tools is True

    @property
    def is_thinking_capable(self) -> bool:
        """Return True if model supports thinking."""
        if self.supports_thinking_truth == CapabilityTruth.SUPPORTED:
            return True
        if self.supports_thinking_truth == CapabilityTruth.UNSUPPORTED:
            return False
        return self.supports_thinking is True


@dataclass(frozen=True, slots=True)
class ModelCapabilityProfile:
    """Model capability profile that Agent truly cares about.

    This is the object that Agent Core uses to adapt its behavior.
    All capability decisions are based on this object, not on
    session/workspace logic.
    """

    model_id: str
    provider_id: str
    supports_tools: bool
    supports_thinking: bool
    context_window: int | None
    token_limit: int | None
    structured_output_support: bool = False
    streaming_support: bool = True
    capability_source: CapabilitySource = CapabilitySource.KNOWN_MODEL_DEFAULTS
    capability_confidence: CapabilityConfidence = CapabilityConfidence.LOW
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "model_id", _safe_text(self.model_id))
        object.__setattr__(self, "provider_id", _safe_text(self.provider_id))
        object.__setattr__(self, "metadata", dict(self.metadata) if self.metadata else {})

    @classmethod
    def from_descriptor(cls, descriptor: ModelDescriptor) -> "ModelCapabilityProfile":
        """Create a capability profile from a model descriptor."""
        return cls(
            model_id=descriptor.model_id,
            provider_id=descriptor.provider_id,
            supports_tools=descriptor.is_tools_capable,
            supports_thinking=descriptor.is_thinking_capable,
            context_window=descriptor.context_window,
            token_limit=descriptor.token_limit,
            capability_source=descriptor.supports_tools_source,
            capability_confidence=descriptor.supports_tools_confidence,
            metadata=descriptor.metadata,
        )

    @property
    def is_capable_for_tools(self) -> bool:
        """Return True if model can use tools."""
        return self.supports_tools

    @property
    def is_capable_for_thinking(self) -> bool:
        """Return True if model can use thinking."""
        return self.supports_thinking

    @property
    def is_capable_for_streaming(self) -> bool:
        """Return True if model supports streaming."""
        return self.streaming_support


@dataclass(frozen=True, slots=True)
class AgentModelPolicy:
    """Agent static model policy.

    This belongs to AgentProfile, not to workspace or session.
    It defines the agent's model preferences and fallback behavior.
    """

    agent_id: str
    default_model_preference: str | None = None
    local_remote_preference: str = "remote"
    fallback_enabled: bool = True
    tool_heavy_tendency: bool = False
    reasoning_heavy_tendency: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        normalized_agent_id = _safe_text(self.agent_id)
        if not normalized_agent_id:
            raise ValueError("agent_id is required")
        object.__setattr__(self, "agent_id", normalized_agent_id)
        object.__setattr__(self, "default_model_preference", _safe_text(self.default_model_preference) or None)
        object.__setattr__(self, "metadata", dict(self.metadata) if self.metadata else {})


@dataclass(frozen=True, slots=True)
class AgentModelBinding:
    """Agent current main model binding.

    This is the key runtime object that determines which model
    the agent is currently using. It belongs to AgentInstance,
    not to session or workspace.
    """

    agent_id: str
    provider_id: str
    model_id: str
    provider_source: ProviderSource
    binding_kind: str = "explicit"
    capability_profile: ModelCapabilityProfile | None = None
    fallback_chain: tuple[str, ...] = ()
    bound_at: datetime | None = None
    switch_generation: int = 0

    def __post_init__(self) -> None:
        normalized_agent_id = _safe_text(self.agent_id)
        normalized_provider_id = _safe_text(self.provider_id)
        normalized_model_id = _safe_text(self.model_id)
        if not normalized_agent_id:
            raise ValueError("agent_id is required")
        if not normalized_provider_id:
            raise ValueError("provider_id is required")
        if not normalized_model_id:
            raise ValueError("model_id is required")
        object.__setattr__(self, "agent_id", normalized_agent_id)
        object.__setattr__(self, "provider_id", normalized_provider_id)
        object.__setattr__(self, "model_id", normalized_model_id)
        object.__setattr__(self, "fallback_chain", tuple(self.fallback_chain) if self.fallback_chain else ())
        if self.bound_at is None:
            object.__setattr__(self, "bound_at", _utc_now())

    @property
    def full_model_id(self) -> str:
        """Return the fully qualified model id."""
        return f"{self.provider_id}.{self.model_id}"

    @property
    def is_explicit(self) -> bool:
        """Return True if this is an explicit binding."""
        return self.binding_kind == "explicit"

    @property
    def is_automatic(self) -> bool:
        """Return True if this is an automatic binding."""
        return self.binding_kind == "automatic"


__all__ = [
    "AgentModelBinding",
    "AgentModelPolicy",
    "CapabilityConfidence",
    "CapabilitySource",
    "CapabilityTruth",
    "ModelCapabilityProfile",
    "ModelDescriptor",
    "ModelKind",
    "ProviderEntry",
    "ProviderSource",
    "ProtocolFamily",
]
