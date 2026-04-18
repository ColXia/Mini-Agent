"""Legacy re-export for session-runtime compatibility adapters."""

from __future__ import annotations

from mini_agent.application.user_services.model_runtime_adapter import AgentModelRuntimeAdapter
from mini_agent.application.user_services.session_runtime_compat_adapters import (
    SessionAgentCompatibilityAdapter,
    SessionBackedRunRuntimeAdapter,
    SessionModelSelectionCompatibilityAdapter,
    SessionTaskCompatibilityAdapter,
    UnavailableRunRuntimeAdapter,
)

__all__ = [
    "AgentModelRuntimeAdapter",
    "SessionBackedRunRuntimeAdapter",
    "SessionAgentCompatibilityAdapter",
    "SessionModelSelectionCompatibilityAdapter",
    "SessionTaskCompatibilityAdapter",
    "UnavailableRunRuntimeAdapter",
]
