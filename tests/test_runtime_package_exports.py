from __future__ import annotations

from mini_agent import runtime as runtime_pkg
from mini_agent.runtime.main_agent_runtime_contracts import (
    MainAgentRuntimeDiagnostics,
    MainAgentRuntimeMode,
    MainAgentRuntimePolicy,
)


def test_runtime_package_exports_contract_types_from_runtime_contract_module() -> None:
    assert runtime_pkg.MainAgentRuntimeDiagnostics is MainAgentRuntimeDiagnostics
    assert runtime_pkg.MainAgentRuntimeMode is MainAgentRuntimeMode
    assert runtime_pkg.MainAgentRuntimePolicy is MainAgentRuntimePolicy
