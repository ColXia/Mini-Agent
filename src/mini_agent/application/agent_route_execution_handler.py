"""Compatibility re-export for surface route execution helpers."""

from mini_agent.model_manager.runtime import get_model_route_diagnostics_state

from .facades.agent_route_execution_handler import AgentRouteExecutionHandler

__all__ = [
    "AgentRouteExecutionHandler",
    "get_model_route_diagnostics_state",
]
