"""Legacy compatibility exports for the shared main-agent surface service."""

from __future__ import annotations

from .main_agent_surface_service import MainAgentGatewayUseCases, MainAgentSurfaceService
from .surface_service_types import (
    FormatBootstrapErrorFn,
    ResolveWorkspaceDirFn,
    SseEventFn,
    ToUtcIsoFn,
)

__all__ = [
    "FormatBootstrapErrorFn",
    "MainAgentGatewayUseCases",
    "MainAgentSurfaceService",
    "ResolveWorkspaceDirFn",
    "SseEventFn",
    "ToUtcIsoFn",
]
