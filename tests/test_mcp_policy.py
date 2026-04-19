"""Tests for MCP modular discovery/policy/resource behavior (P5)."""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from mini_agent.tools.mcp.discovery import discover_servers
from mini_agent.tools.mcp.executor import MCPTool
from mini_agent.tools.mcp.naming import mcp_tool_alias
from mini_agent.tools.mcp.registry import MCPServerConnection
from mini_agent.tools.mcp_loader import load_mcp_tools_async


def _write_config(path: Path, payload: dict) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_discover_servers_merges_policy_and_applies_stdio_trust(tmp_path: Path):
    config_path = _write_config(
        tmp_path / "mcp.json",
        {
            "policy": {
                "allow": ["global_tool"],
                "exclude": ["blocked_global"],
                "trust": False,
                "enable_resources": True,
            },
            "mcpServers": {
                "local": {
                    "command": "npx",
                    "args": ["-y", "local-server"],
                    "policy": {
                        "exclude": ["local_blocked"],
                    },
                },
                "remote": {
                    "url": "https://mcp.example.com/mcp",
                    "policy": {
                        "trust": True,
                        "allow": ["remote_tool"],
                        "enable_resources": False,
                    },
                },
            },
        },
    )

    _, servers = discover_servers(str(config_path))
    assert len(servers) == 2

    local = next(item for item in servers if item.name == "local")
    remote = next(item for item in servers if item.name == "remote")

    assert local.connection_type == "stdio"
    assert local.policy.trust is True
    assert local.policy.allow == {"global_tool"}
    assert local.policy.exclude == {"local_blocked"}
    assert local.policy.enable_resources is True

    assert remote.connection_type == "streamable_http"
    assert remote.policy.trust is True
    assert remote.policy.allow == {"remote_tool"}
    assert remote.policy.enable_resources is False


@pytest.mark.asyncio
async def test_untrusted_remote_server_is_skipped_without_network():
    connection = MCPServerConnection(
        name="remote",
        connection_type="streamable_http",
        url="https://10.255.255.1:9999/mcp",
    )

    success = await connection.connect()
    assert success is False
    assert connection.session is None


@pytest.mark.asyncio
async def test_load_tools_skips_untrusted_remote_server(tmp_path: Path):
    config_path = _write_config(
        tmp_path / "mcp.json",
        {
            "mcpServers": {
                "remote": {
                    "url": "https://10.255.255.1:9999/mcp",
                }
            }
        },
    )

    tools = await load_mcp_tools_async(str(config_path))
    assert tools == []


class _FakeSessionWithResources:
    async def list_resources(self):
        return None

    async def read_resource(self, uri: str):
        return uri


class _FakeSessionWithoutResources:
    pass


def test_resource_tools_registration_helpers(tmp_path: Path):
    connection = MCPServerConnection(
        name="my-server",
        connection_type="stdio",
        command="npx",
        policy=None,
    )

    tools = connection._resource_tools(_FakeSessionWithResources(), execute_timeout=10.0)
    tool_names = [tool.name for tool in tools]
    assert mcp_tool_alias("my-server", "list_resources") in tool_names
    assert mcp_tool_alias("my-server", "read_resource") in tool_names

    no_tools = connection._resource_tools(_FakeSessionWithoutResources(), execute_timeout=10.0)
    assert no_tools == []


class _FakeCallSession:
    async def call_tool(self, name: str, arguments: dict | None = None):
        _ = arguments
        return SimpleNamespace(content=[SimpleNamespace(text=f"called:{name}")], isError=False)


@pytest.mark.asyncio
async def test_load_mcp_tools_namespaces_same_remote_tool_across_servers(monkeypatch):
    import mini_agent.tools.mcp.registry as mcp_registry

    definitions = [
        SimpleNamespace(
            name="alpha",
            connection_type="stdio",
            command="npx",
            args=[],
            env={},
            url=None,
            headers={},
            connect_timeout=None,
            execute_timeout=None,
            sse_read_timeout=None,
            policy=SimpleNamespace(enable_resources=False),
        ),
        SimpleNamespace(
            name="alpha",
            connection_type="stdio",
            command="uvx",
            args=[],
            env={},
            url=None,
            headers={},
            connect_timeout=None,
            execute_timeout=None,
            sse_read_timeout=None,
            policy=SimpleNamespace(enable_resources=False),
        ),
    ]

    class _FakeConnection:
        def __init__(self, *, name: str, **kwargs):  # noqa: ANN003
            _ = kwargs
            self.name = name
            self.tools: list[MCPTool] = []

        async def connect(self, *, reserved_aliases=None) -> bool:
            alias = mcp_registry.reserve_mcp_tool_alias(
                self.name,
                "search",
                reserved_aliases,
            )
            self.tools = [
                MCPTool(
                    server_name=self.name,
                    remote_name="search",
                    description="Search docs.",
                    parameters={},
                    session=_FakeCallSession(),
                    execute_timeout=10.0,
                    expose_name=alias,
                )
            ]
            return True

    monkeypatch.setattr(
        mcp_registry,
        "discover_servers",
        lambda config_path: (Path(config_path), definitions),
    )
    monkeypatch.setattr(mcp_registry, "MCPServerConnection", _FakeConnection)

    tools = await load_mcp_tools_async("mcp.json")
    assert [tool.name for tool in tools] == [
        mcp_tool_alias("alpha", "search"),
        f"{mcp_tool_alias('alpha', 'search')}_2",
    ]
    assert [getattr(tool, "remote_name", "") for tool in tools] == ["search", "search"]
