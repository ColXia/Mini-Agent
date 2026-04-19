from __future__ import annotations

from mini_agent.commands.catalog import (
    command_entries_for_surface,
)
from mini_agent.commands.completions import (
    command_completion_tokens,
)
from mini_agent.commands.metadata import (
    build_command_example_text,
    build_command_help_text,
    build_command_usage_text,
    build_unknown_action_text,
    command_action_candidates,
)


def test_command_catalog_exposes_cli_model_command() -> None:
    cli_entries = {entry["name"]: entry for entry in command_entries_for_surface("cli")}
    qq_entries = {entry["name"]: entry for entry in command_entries_for_surface("qq")}

    assert "model" in cli_entries
    assert "mcp" in cli_entries
    assert "sandbox" in cli_entries
    assert "skill" in cli_entries
    assert "skill" in qq_entries
    assert "mcp" in qq_entries
    assert cli_entries["model"]["forms_for_surface"] == [
        "model [show|list|use]",
        "model show",
        "model list",
        "model use <provider_id> <model_id>",
    ]
    assert cli_entries["skill"]["forms_for_surface"] == [
        "skill [list|active|show|search|mode|enable|disable|reset|refresh|install|uninstall|rollback]",
        "skill list",
        "skill active",
        "skill show <skill_name>",
        "skill install <path_or_url>",
        "skill uninstall <skill_name>",
        "skill rollback <skill_name>",
        "skill search <query>",
        "skill mode <all|allowlist>",
        "skill enable <skill_name>",
        "skill disable <skill_name>",
        "skill reset",
        "skill refresh",
    ]
    assert cli_entries["mcp"]["forms_for_surface"] == [
        "mcp [status|list|reload]",
        "mcp status",
        "mcp list",
        "mcp reload",
    ]
    assert cli_entries["sandbox"]["forms_for_surface"] == [
        "sandbox status",
        "sandbox [status]",
    ]
    assert qq_entries["skill"]["forms_for_surface"] == cli_entries["skill"]["forms_for_surface"]
    assert qq_entries["mcp"]["forms_for_surface"] == cli_entries["mcp"]["forms_for_surface"]


def test_command_help_and_examples_are_surface_specific() -> None:
    cli_help = build_command_help_text("cli", include_header=True, leading_slash=True)
    tui_examples = build_command_example_text("tui", include_header=True, leading_slash=True, max_examples=80)

    assert "/model [show|list|use]" in cli_help
    assert "/mcp [status|list|reload]" in cli_help
    assert "/sandbox [status]" in cli_help
    assert "/skill [list|active|show|search|mode|enable|disable|reset|refresh|install|uninstall|rollback]" in cli_help
    assert "/history" in cli_help
    assert "/model use maas astron-code-latest" in tui_examples
    assert "/mcp status" in tui_examples
    assert "/sandbox status" in tui_examples
    assert "/skill show doc-coauthoring" in tui_examples
    assert "/skill install .mini-agent/skills/repo-helper" in tui_examples
    assert "/skill uninstall repo-helper" in tui_examples
    assert "/skill rollback repo-helper" in tui_examples
    assert "/skill active" in tui_examples
    assert "/session share" in tui_examples


def test_command_completion_tokens_include_prefixed_and_plain_variants() -> None:
    tokens = command_completion_tokens(
        "tui",
        include_leading_slash=True,
        include_plain=True,
    )

    assert "model use" in tokens
    assert "/model use" in tokens
    assert "/sandbox" in tokens
    assert "/session new" in tokens


def test_command_usage_and_action_candidates_are_catalog_driven() -> None:
    assert build_command_usage_text("cli", "model", action="use") == "Usage: /model use <provider_id> <model_id>"
    assert build_command_usage_text("cli", "mcp", action="status") == "Usage: /mcp status"
    assert build_command_usage_text("cli", "mcp", action="list") == "Usage: /mcp list"
    assert build_command_usage_text("cli", "mcp", action="reload") == "Usage: /mcp reload"
    assert build_command_usage_text("cli", "sandbox", action="status") == "Usage: /sandbox status"
    assert build_command_usage_text("qq", "mcp", action="status") == "Usage: /mcp status"
    assert build_command_usage_text("cli", "skill", action="show") == "Usage: /skill show <skill_name>"
    assert build_command_usage_text("cli", "skill", action="install") == "Usage: /skill install <path_or_url>"
    assert build_command_usage_text("cli", "skill", action="uninstall") == "Usage: /skill uninstall <skill_name>"
    assert build_command_usage_text("cli", "skill", action="rollback") == "Usage: /skill rollback <skill_name>"
    assert build_command_usage_text("cli", "skill", action="active") == "Usage: /skill active"
    assert build_command_usage_text("cli", "skill", action="mode") == "Usage: /skill mode <all|allowlist>"
    assert build_command_usage_text("tui", "skill", action="enable") == "Usage: /skill enable <skill_name>"
    assert build_command_usage_text("tui", "skill", action="refresh") == "Usage: /skill refresh"
    assert build_command_usage_text("qq", "skill", action="search") == "Usage: /skill search <query>"
    assert build_command_usage_text("tui", "session", action="rename") == "Usage: /session rename [session_id] <new_title>"
    assert build_command_usage_text("qq", "memory", action="shared") == "Usage: /memory shared [list|show|clear]"
    assert build_command_usage_text("cli", "memory", action="show") == "Usage: /memory show [brief|full|<selector>]"
    assert build_command_usage_text("cli", "memory", action="overview") == "Usage: /memory overview"
    assert build_command_usage_text("cli", "memory", action="consolidated") == "Usage: /memory consolidated [show|search]"
    assert build_command_usage_text("cli", "memory", action="export") == "Usage: /memory export [jsonl|markdown]"
    assert command_action_candidates("qq", "context") == [
        "budget",
        "exclude",
        "include",
        "reset",
        "show",
        "stats",
    ]
    assert "shared" in command_action_candidates("cli", "memory")
    assert "consolidated" in command_action_candidates("cli", "memory")
    assert "profile" in command_action_candidates("cli", "memory")
    assert "notes" in command_action_candidates("cli", "memory")
    assert "daily" in command_action_candidates("cli", "memory")
    assert "overview" in command_action_candidates("cli", "memory")
    assert "export" in command_action_candidates("cli", "memory")
    assert "status" in command_action_candidates("cli", "mcp")
    assert "list" in command_action_candidates("cli", "mcp")
    assert "reload" in command_action_candidates("cli", "mcp")
    assert command_action_candidates("cli", "sandbox") == ["status"]
    assert command_action_candidates("qq", "mcp") == ["list", "reload", "status"]
    assert "active" in command_action_candidates("cli", "skill")
    assert "install" in command_action_candidates("cli", "skill")
    assert "uninstall" in command_action_candidates("cli", "skill")
    assert "rollback" in command_action_candidates("cli", "skill")
    assert "mode" in command_action_candidates("cli", "skill")
    assert "enable" in command_action_candidates("cli", "skill")


def test_unknown_action_text_suggests_catalog_actions() -> None:
    text = build_unknown_action_text("cli", "memory", "statuz")

    assert "Unknown memory action: statuz." in text
    assert "status" in text
    assert "Usage: /memory [status|show|list|overview|consolidated|profile|notes|daily|export|shared|refresh|runtime|promote|save]" in text
