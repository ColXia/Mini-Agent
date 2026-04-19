from __future__ import annotations

from mini_agent.runtime.support.sandbox_state import collect_sandbox_diagnostics
from tests.runtime_contract_fixtures import (
    RuntimeContractAgentStub,
    runtime_policy_engine_stub,
    sandbox_manager_stub,
)


def test_collect_sandbox_diagnostics_reads_runtime_services_contract(tmp_path) -> None:
    sandbox_manager = sandbox_manager_stub(
        backend="windows_restricted_token",
        reason="windows_workspace_sandbox",
        metadata={
            "backend": "windows_restricted_token",
            "sandbox_mode": "workspace",
            "workspace_root": str(tmp_path),
            "network_mode": "allow_all",
            "restricted_token": True,
            "low_integrity": True,
            "mandatory_policy": 3,
            "disable_admin_groups": True,
            "restrict_ui": True,
            "die_on_unhandled_exception": True,
            "max_processes": 12,
            "max_process_memory_mb": 768,
        },
        allow_domains=("api.openai.com",),
        block_domains=("example.com",),
    )
    agent = RuntimeContractAgentStub()
    agent.runtime_policy_engine = runtime_policy_engine_stub(
        approval_profile="plan",
        access_level="default",
        sandbox_mode="workspace",
    )
    agent.sandbox_manager = sandbox_manager

    diagnostics = collect_sandbox_diagnostics(agent=agent)

    assert diagnostics["backend"] == "windows_restricted_token"
    assert diagnostics["approval_profile"] == "plan"
    assert diagnostics["access_level"] == "default"
    assert diagnostics["restricted_token"] is True
    assert diagnostics["network_allow_domains"] == ["api.openai.com"]
    assert diagnostics["network_block_domains"] == ["example.com"]
    assert diagnostics["max_processes"] == 12
    assert diagnostics["max_process_memory_mb"] == 768
