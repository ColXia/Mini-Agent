"""Tests for P14 T2.6 agent-core execution MCP client baseline."""

from __future__ import annotations

from pathlib import Path

import pytest

from mini_agent.agent_core.execution.mcp_client import ExecutionMCPClient
from mini_agent.agent_core.execution.mcp_tools import mcp_tool_alias
from mini_agent.agent_core.execution.mcp_tools import infer_mcp_tool_attributes
from mini_agent.agent_core.execution.tools.attributes import ToolKind
from mini_agent.tools.base import Tool, ToolResult
from mini_agent.tools.mcp.types import MCPServerDefinition


class _FakeMCPTool(Tool):
    def __init__(self, name: str):
        self._name = name

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return f"Fake MCP tool: {self._name}"

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
        }

    async def execute(self, text: str) -> ToolResult:
        return ToolResult(success=True, content=f"{self._name}:{text}")


class _FakeConnection:
    def __init__(self, *, name: str, **kwargs):  # noqa: ANN003
        del kwargs
        self.name = name
        self.connected = False
        self.disconnected = False
        self.tools = [_FakeMCPTool("echo")] if name == "alpha" else []

    async def connect(self) -> bool:
        self.connected = self.name != "broken"
        return self.connected

    async def disconnect(self) -> None:
        self.disconnected = True
        self.connected = False


def _discover_stub(_config_path: str):
    definitions = [
        MCPServerDefinition(name="alpha", connection_type="stdio", command="cmd-a"),
        MCPServerDefinition(name="broken", connection_type="stdio", command="cmd-b"),
    ]
    return Path("mcp.json"), definitions


@pytest.mark.asyncio
async def test_execution_mcp_client_connects_lists_and_calls():
    client = ExecutionMCPClient(
        config_path="mcp.json",
        discover_fn=_discover_stub,
        connection_factory=_FakeConnection,
    )

    statuses = await client.connect()
    assert statuses["alpha"] is True
    assert statuses["broken"] is False

    tools = client.list_tools()
    assert len(tools) == 1
    assert tools[0].server_name == "alpha"
    assert tools[0].tool_name == "echo"

    success = await client.call_tool(server_name="alpha", tool_name="echo", arguments={"text": "hello"})
    assert success.success is True
    assert success.content == "echo:hello"

    missing = await client.call_tool(server_name="unknown", tool_name="echo", arguments={"text": "x"})
    assert missing.success is False
    assert "not connected" in (missing.error or "")

    await client.disconnect()


@pytest.mark.asyncio
async def test_execution_mcp_client_builds_namespaced_declarative_registry():
    client = ExecutionMCPClient(
        config_path="mcp.json",
        discover_fn=_discover_stub,
        connection_factory=_FakeConnection,
    )
    await client.connect()

    registry = client.build_declarative_registry()
    alias = mcp_tool_alias("alpha", "echo")
    assert alias in registry

    invocation = registry[alias].build({"text": "from-contract"})
    result = await invocation.execute()
    assert result.success is True
    assert result.content == "echo:from-contract"

    await client.disconnect()


def test_infer_mcp_tool_attributes_for_resource_tools_is_read_only():
    attrs = infer_mcp_tool_attributes("alpha_read_resource")
    assert attrs.kind == ToolKind.READ
    assert attrs.is_read_only is True

    attrs_exec = infer_mcp_tool_attributes("execute_remote")
    assert attrs_exec.kind == ToolKind.NETWORK
    assert attrs_exec.is_read_only is False
