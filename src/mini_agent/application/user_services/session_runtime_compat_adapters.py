"""Stable wrapper for session-runtime compatibility adapters used by user-service assembly."""

from __future__ import annotations

from mini_agent.application.legacy.session_runtime_compat import (
    SessionBackedRunRuntimeAdapter,
    SessionTaskCompatibilityAdapter,
    UnavailableRunRuntimeAdapter,
)

__all__ = [
    "SessionBackedRunRuntimeAdapter",
    "SessionTaskCompatibilityAdapter",
    "UnavailableRunRuntimeAdapter",
]
