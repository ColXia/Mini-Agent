"""Sandbox primitives for code-agent runtime."""

from mini_agent.code_agent.sandbox.manager import SandboxBackend, SandboxManager, SandboxSelection
from mini_agent.code_agent.sandbox.network import (
    NetworkAccessMode,
    NetworkDomainPolicy,
    extract_domains_from_command,
)
from mini_agent.code_agent.sandbox.windows import (
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

