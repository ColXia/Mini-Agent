"""Tests for v11.3 CommandUserService."""

from __future__ import annotations

import pytest

from mini_agent.user_services.command_user_service import (
    CommandExecuteResult,
    CommandExecuteResultKind,
    CommandInfo,
    CommandParseResult,
    CommandParseResultKind,
    CommandUserService,
)


class TestCommandInfo:
    """Tests for CommandInfo."""

    def test_command_info_creation(self) -> None:
        info = CommandInfo(
            name="help",
            description="Show help",
            usage="[command]",
            aliases=("h", "?"),
            category="general",
        )
        assert info.name == "help"
        assert info.aliases == ("h", "?")
        assert "aliases:" in info.full_usage

    def test_command_info_full_usage_no_aliases(self) -> None:
        info = CommandInfo(
            name="clear",
            description="Clear screen",
            usage="",
        )
        assert info.full_usage == "/clear "


class TestCommandUserService:
    """Tests for CommandUserService."""

    def test_service_creation(self) -> None:
        service = CommandUserService()
        assert len(service.list_commands()) == 0

    def test_register_command(self) -> None:
        service = CommandUserService()
        info = CommandInfo(
            name="help",
            description="Show help",
            usage="[command]",
        )
        service.register_command(info)
        assert len(service.list_commands()) == 1
        assert service.get_command_help("help") is not None

    def test_register_command_with_aliases(self) -> None:
        service = CommandUserService()
        info = CommandInfo(
            name="help",
            description="Show help",
            usage="[command]",
            aliases=("h", "?"),
        )
        service.register_command(info)
        assert service.get_command_help("h") is not None
        assert service.get_command_help("?") is not None

    def test_unregister_command(self) -> None:
        service = CommandUserService()
        info = CommandInfo(
            name="help",
            description="Show help",
            usage="[command]",
            aliases=("h",),
        )
        service.register_command(info)
        removed = service.unregister_command("help")
        assert removed is not None
        assert removed.name == "help"
        assert service.get_command_help("h") is None

    def test_parse_command_empty(self) -> None:
        service = CommandUserService()
        result = service.parse_command("")
        assert result.result_kind == CommandParseResultKind.EMPTY_INPUT

    def test_parse_command_no_slash(self) -> None:
        service = CommandUserService()
        result = service.parse_command("help")
        assert result.result_kind == CommandParseResultKind.INVALID_SYNTAX
        assert "must start with /" in result.error_message

    def test_parse_command_unknown(self) -> None:
        service = CommandUserService()
        result = service.parse_command("/unknown")
        assert result.result_kind == CommandParseResultKind.UNKNOWN_COMMAND

    def test_parse_command_valid(self) -> None:
        service = CommandUserService()
        info = CommandInfo(
            name="help",
            description="Show help",
            usage="[command]",
        )
        service.register_command(info)
        result = service.parse_command("/help")
        assert result.result_kind == CommandParseResultKind.VALID
        assert result.command_name == "help"

    def test_parse_command_with_args(self) -> None:
        service = CommandUserService()
        info = CommandInfo(
            name="model",
            description="Switch model",
            usage="<model_id>",
        )
        service.register_command(info)
        result = service.parse_command("/model gpt-4")
        assert result.result_kind == CommandParseResultKind.VALID
        assert result.command_name == "model"
        assert result.arguments.get("raw_args") == "gpt-4"

    def test_parse_command_alias(self) -> None:
        service = CommandUserService()
        info = CommandInfo(
            name="help",
            description="Show help",
            usage="[command]",
            aliases=("h",),
        )
        service.register_command(info)
        result = service.parse_command("/h")
        assert result.result_kind == CommandParseResultKind.VALID
        assert result.command_name == "help"

    def test_execute_command_unknown(self) -> None:
        service = CommandUserService()
        result = service.execute_command("unknown", {})
        assert result.result_kind == CommandExecuteResultKind.REJECTED

    def test_execute_command_success(self) -> None:
        service = CommandUserService()
        info = CommandInfo(
            name="help",
            description="Show help",
            usage="[command]",
        )
        service.register_command(info)
        result = service.execute_command("help", {})
        assert result.result_kind == CommandExecuteResultKind.SUCCESS

    def test_execute_command_with_handler(self) -> None:
        service = CommandUserService()
        info = CommandInfo(
            name="model",
            description="Switch model",
            usage="<model_id>",
        )
        service.register_command(info)

        def custom_executor(name: str, args: dict) -> CommandExecuteResult:
            return CommandExecuteResult(
                result_kind=CommandExecuteResultKind.SUCCESS,
                command_name=name,
                output=f"Switched to {args.get('raw_args')}",
            )

        service.set_executor(custom_executor)
        result = service.execute_command("model", {"raw_args": "gpt-4"})
        assert result.result_kind == CommandExecuteResultKind.SUCCESS
        assert "gpt-4" in result.output

    def test_list_commands_with_category(self) -> None:
        service = CommandUserService()
        service.register_command(CommandInfo(
            name="help",
            description="Show help",
            usage="[command]",
            category="general",
        ))
        service.register_command(CommandInfo(
            name="model",
            description="Switch model",
            usage="<model_id>",
            category="config",
        ))
        general = service.list_commands(category="general")
        assert len(general) == 1
        assert general[0].name == "help"

    def test_clear(self) -> None:
        service = CommandUserService()
        service.register_command(CommandInfo(
            name="help",
            description="Show help",
            usage="[command]",
            aliases=("h",),
        ))
        service.clear()
        assert len(service.list_commands()) == 0
        assert service.get_command_help("h") is None
