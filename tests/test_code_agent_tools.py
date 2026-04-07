"""Tests for P14 T2.3 declarative code-agent tool baseline."""

from __future__ import annotations

import pytest

from mini_agent.code_agent.tools import (
    DeclarativeToolAttributes,
    ToolBuilder,
    ToolKind,
    build_runtime_adapter_path,
)
from mini_agent.tools.base import Tool, ToolResult
from mini_agent.tools.file_tools import ReadTool, WriteTool


class _EchoTool(Tool):
    @property
    def name(self) -> str:
        return "echo"

    @property
    def description(self) -> str:
        return "Echo input text."

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "text": {"type": "string"},
            },
            "required": ["text"],
            "additionalProperties": False,
        }

    async def execute(self, text: str) -> ToolResult:
        return ToolResult(success=True, content=text)


def test_builder_from_tool_infers_read_contract(tmp_path):
    declarative = ToolBuilder.from_tool(ReadTool(workspace_dir=str(tmp_path)))
    assert declarative.name == "read_file"
    assert declarative.attributes.kind == ToolKind.READ
    assert declarative.attributes.is_read_only is True
    assert "path" in declarative.schema["required"]
    assert declarative.to_openai_schema()["function"]["name"] == "read_file"


def test_invocation_validate_rejects_missing_required():
    declarative = ToolBuilder.from_callable(
        name="sample",
        description="sample tool",
        schema={
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
            "additionalProperties": False,
        },
        execute=lambda _args: ToolResult(success=True, content="ok"),
    )
    invocation = declarative.build({})
    with pytest.raises(ValueError, match="required"):
        invocation.validate()


def test_invocation_should_confirm_for_write_tool(tmp_path):
    declarative = ToolBuilder.from_tool(WriteTool(workspace_dir=str(tmp_path)))
    invocation = declarative.build({"path": "test.txt", "content": "hello"})
    assert invocation.should_confirm_execute() is True


def test_invocation_tool_locations_extracts_path():
    declarative = ToolBuilder.from_callable(
        name="path_tool",
        description="path tool",
        schema={
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
        execute=lambda _args: ToolResult(success=True, content="ok"),
    )
    invocation = declarative.build({"path": "src/main.py"})
    assert invocation.tool_locations() == ["src/main.py"]


@pytest.mark.asyncio
async def test_invocation_execute_applies_result_size_limit():
    declarative = ToolBuilder.from_callable(
        name="limited",
        description="limit tool",
        schema={"type": "object", "properties": {}, "additionalProperties": False},
        execute=lambda _args: ToolResult(success=True, content="0123456789ABCDE"),
        attributes=DeclarativeToolAttributes(
            kind=ToolKind.READ,
            is_read_only=True,
            max_result_size_chars=10,
        ),
    )
    result = await declarative.build({}).execute()
    assert result.success is True
    assert result.content.startswith("0123456789")
    assert "truncated to 10 chars" in result.content


@pytest.mark.asyncio
async def test_runtime_adapter_path_executes_wrapped_tool():
    adapters, registry = build_runtime_adapter_path([_EchoTool()])
    assert "echo" in registry
    assert len(adapters) == 1

    result = await adapters[0].execute(text="hello declarative")
    assert result.success is True
    assert result.content == "hello declarative"
