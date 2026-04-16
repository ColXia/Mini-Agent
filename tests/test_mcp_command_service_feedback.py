from __future__ import annotations

from mini_agent.tools.mcp.command_service import (
    McpReloadOutcome,
    build_mcp_reload_warm_prefix,
    format_cli_mcp_reload_success,
)


def test_format_cli_mcp_reload_success_includes_active_model_when_runtime_rebuilt() -> None:
    message = format_cli_mcp_reload_success(
        McpReloadOutcome(
            rebuilt_runtime=True,
            active_model_label="openai/gpt-5.4",
        )
    )

    assert message == "Reloaded MCP bindings; current CLI agent reloaded on openai/gpt-5.4"


def test_format_cli_mcp_reload_success_falls_back_without_model_label() -> None:
    message = format_cli_mcp_reload_success(
        McpReloadOutcome(
            rebuilt_runtime=False,
            active_model_label=None,
        )
    )

    assert message == "Reloaded MCP bindings"


def test_build_mcp_reload_warm_prefix_uses_session_label() -> None:
    assert build_mcp_reload_warm_prefix("Session 3") == "MCP bindings reloaded for Session 3"
    assert build_mcp_reload_warm_prefix("") == "MCP bindings reloaded"
