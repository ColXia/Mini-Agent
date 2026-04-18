"""Compatibility re-export for legacy session runtime compatibility adapters."""

from .legacy.session_runtime_compat import (
    SessionBackedRunRuntimeAdapter,
    SessionAgentCompatibilityAdapter,
    SessionModelSelectionCompatibilityAdapter,
    SessionTaskCompatibilityAdapter,
    UnavailableRunRuntimeAdapter,
)
from .user_services.model_runtime_adapter import AgentModelRuntimeAdapter

__all__ = [
    "AgentModelRuntimeAdapter",
    "SessionBackedRunRuntimeAdapter",
    "SessionAgentCompatibilityAdapter",
    "SessionModelSelectionCompatibilityAdapter",
    "SessionTaskCompatibilityAdapter",
    "UnavailableRunRuntimeAdapter",
]
