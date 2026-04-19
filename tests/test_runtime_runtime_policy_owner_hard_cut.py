from __future__ import annotations

from mini_agent.runtime.handlers.session_runtime_policy_handler import (
    RuntimeSessionRuntimePolicyHandler,
)


def test_runtime_policy_owner_exports_required_methods() -> None:
    extracted_methods = {
        "update_runtime_policy",
        "ensure_runtime_policy_ready_for_turn",
    }
    assert RuntimeSessionRuntimePolicyHandler.__module__ == (
        "mini_agent.runtime.handlers.session_runtime_policy_handler"
    )
    for name in sorted(extracted_methods):
        assert hasattr(RuntimeSessionRuntimePolicyHandler, name), (
            f"Runtime policy owner lost required method {name!r} after the hard cut."
        )
