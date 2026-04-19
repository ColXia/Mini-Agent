from __future__ import annotations

from mini_agent.runtime.handlers.session_context_policy_handler import (
    RuntimeSessionContextPolicyHandler,
)


def test_context_policy_owner_exports_required_methods() -> None:
    extracted_methods = {
        "update_context_policy",
        "_execute_context_policy_update",
    }
    assert RuntimeSessionContextPolicyHandler.__module__ == (
        "mini_agent.runtime.handlers.session_context_policy_handler"
    )
    for name in sorted(extracted_methods):
        assert hasattr(RuntimeSessionContextPolicyHandler, name), (
            f"Context policy owner lost required method {name!r} after the hard cut."
        )
