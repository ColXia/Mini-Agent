"""Compatibility re-export for surface delegation execution helpers."""

from .facades.agent_delegation_execution_handler import (
    AgentDelegationExecutionHandler,
    AgentDelegationExecutionResult,
)

__all__ = [
    "AgentDelegationExecutionHandler",
    "AgentDelegationExecutionResult",
]
