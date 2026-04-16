"""Sandbox primitives for agent-core execution runtime."""

from mini_agent.agent_core.execution.sandbox.manager import SandboxBackend, SandboxManager, SandboxSelection
from mini_agent.agent_core.execution.sandbox.network import (
    NetworkAccessMode,
    NetworkDomainPolicy,
    extract_domains_from_command,
)
from mini_agent.agent_core.execution.sandbox.windows import (
    SandboxTransformResult,
    WindowsRestrictedSandbox,
    WindowsSandboxPolicy,
)

__all__ = [
    "SandboxBackend",
    "SandboxSelection",
    "SandboxManager",
    "NetworkAccessMode",
    "NetworkDomainPolicy",
    "extract_domains_from_command",
    "SandboxTransformResult",
    "WindowsSandboxPolicy",
    "WindowsRestrictedSandbox",
]
