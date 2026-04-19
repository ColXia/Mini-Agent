"""Tests for P14 T2.3 declarative agent-core execution tool baseline."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from mini_agent.agent_core.execution.tools.attributes import DeclarativeToolAttributes, ToolKind
from mini_agent.agent_core.execution.tools.builder import ToolBuilder
from mini_agent.agent_core.execution.tools.runtime_adapter import build_runtime_adapter_path
from mini_agent.agent_core.execution.tool_execution_coordinator import (
    AgentToolExecutionCoordinator,
    AgentToolExecutionRuntime,
    ToolExecutionBatchState,
)
from mini_agent.schema.schema import FunctionCall, ToolCall
from mini_agent.tools.base import Tool, ToolResult
from mini_agent.tools.file_tools import ReadTool, WriteTool
from mini_agent.tools.skill_tool import create_skill_tools


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


def test_builder_from_install_skill_tool_infers_write_contract(tmp_path):
    builtin_dir = tmp_path / "builtin-skills"
    builtin_dir.mkdir()
    workspace_dir = tmp_path / "workspace"
    workspace_dir.mkdir()

    tools, _loader = create_skill_tools(
        str(builtin_dir),
        workspace_dir=str(workspace_dir),
    )
    install_tool = next(tool for tool in tools if tool.name == "install_skill")

    declarative = ToolBuilder.from_tool(install_tool)
    assert declarative.name == "install_skill"
    assert declarative.attributes.kind == ToolKind.WRITE
    assert declarative.attributes.is_read_only is False


def test_builder_from_install_skill_from_path_tool_infers_write_contract(tmp_path):
    builtin_dir = tmp_path / "builtin-skills"
    builtin_dir.mkdir()
    workspace_dir = tmp_path / "workspace"
    workspace_dir.mkdir()

    tools, _loader = create_skill_tools(
        str(builtin_dir),
        workspace_dir=str(workspace_dir),
    )
    install_tool = next(tool for tool in tools if tool.name == "install_skill_from_path")

    declarative = ToolBuilder.from_tool(install_tool)
    assert declarative.name == "install_skill_from_path"
    assert declarative.attributes.kind == ToolKind.WRITE
    assert declarative.attributes.is_read_only is False


def test_builder_from_uninstall_skill_tool_infers_write_contract(tmp_path):
    builtin_dir = tmp_path / "builtin-skills"
    builtin_dir.mkdir()
    workspace_dir = tmp_path / "workspace"
    workspace_dir.mkdir()

    tools, _loader = create_skill_tools(
        str(builtin_dir),
        workspace_dir=str(workspace_dir),
    )
    uninstall_tool = next(tool for tool in tools if tool.name == "uninstall_skill")

    declarative = ToolBuilder.from_tool(uninstall_tool)
    assert declarative.name == "uninstall_skill"
    assert declarative.attributes.kind == ToolKind.WRITE
    assert declarative.attributes.is_read_only is False


def test_builder_from_rollback_skill_tool_infers_write_contract(tmp_path):
    builtin_dir = tmp_path / "builtin-skills"
    builtin_dir.mkdir()
    workspace_dir = tmp_path / "workspace"
    workspace_dir.mkdir()

    tools, _loader = create_skill_tools(
        str(builtin_dir),
        workspace_dir=str(workspace_dir),
    )
    rollback_tool = next(tool for tool in tools if tool.name == "rollback_skill")

    declarative = ToolBuilder.from_tool(rollback_tool)
    assert declarative.name == "rollback_skill"
    assert declarative.attributes.kind == ToolKind.WRITE
    assert declarative.attributes.is_read_only is False


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


@pytest.mark.asyncio
async def test_tool_execution_coordinator_runs_against_explicit_runtime_contract():
    tool = _EchoTool()
    declarative = ToolBuilder.from_tool(tool)
    runtime_messages = []
    runtime_events = []
    tool_result_events = []
    presenter_events = []

    class _Presenter:
        def tool_call(self, *, function_name: str, arguments: dict[str, object]) -> None:
            presenter_events.append(("tool_call", function_name, dict(arguments)))

        def tool_result(self, *, result: ToolResult) -> None:
            presenter_events.append(("tool_result", result.success, result.content, result.error))

    async def _emit_hook(_callback, *_args):  # noqa: ANN001
        return None

    runtime = AgentToolExecutionRuntime(
        cancel_event_getter=lambda: None,
        cancelled_checker=lambda: False,
        hook_emitter=_emit_hook,
        tool_getter=lambda tool_name: tool if tool_name == "echo" else None,
        invocation_builder=lambda function_name, arguments: (
            declarative.build(arguments)
            if function_name == "echo"
            else (_ for _ in ()).throw(KeyError(function_name))
        ),
        tool_approval_handler_getter=lambda: None,
        runtime_policy_engine_getter=lambda: None,
        approval_engine_getter=lambda: None,
        message_appender=runtime_messages.append,
        event_logger=lambda event_type, payload, level: runtime_events.append(
            (event_type, level, dict(payload))
        ),
        tool_result_logger=lambda tool_name, arguments, result_success, result_content, result_error: (
            tool_result_events.append(
                (tool_name, dict(arguments), result_success, result_content, result_error)
            )
        ),
    )
    coordinator = AgentToolExecutionCoordinator(runtime=runtime, presenter=_Presenter())
    step_state = SimpleNamespace(executed_tool_calls=0)

    batch = await coordinator.execute_tool_calls(
        step=1,
        tool_calls=[
            ToolCall(
                id="tool-1",
                type="function",
                function=FunctionCall(name="echo", arguments={"text": "hello contract"}),
            )
        ],
        step_state=step_state,
    )

    assert batch.state == ToolExecutionBatchState.CONTINUE
    assert step_state.executed_tool_calls == 1
    assert presenter_events[0] == ("tool_call", "echo", {"text": "hello contract"})
    assert presenter_events[1] == ("tool_result", True, "hello contract", None)
    assert runtime_events[0][0] == "tool.call"
    assert tool_result_events == [
        ("echo", {"text": "hello contract"}, True, "hello contract", None)
    ]
    assert len(runtime_messages) == 1
    assert runtime_messages[0].role == "tool"
    assert runtime_messages[0].content == "hello contract"
