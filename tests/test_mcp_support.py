from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from mini_agent.commands import mcp_support
from mini_agent.commands.mcp_support import (
    collect_mcp_operator_snapshot,
    format_mcp_server_list,
    format_mcp_status,
    resolve_runtime_mcp_config_path,
)
from mini_agent.tools.mcp.naming import mcp_tool_alias
from mini_agent.tools.mcp.types import MCPServerPolicy


def _make_config(*, mcp_config_path: str = "mcp.json", enable_mcp: bool = True) -> SimpleNamespace:
    return SimpleNamespace(
        tools=SimpleNamespace(
            enable_mcp=enable_mcp,
            mcp_config_path=mcp_config_path,
        )
    )


def test_resolve_runtime_mcp_config_path_uses_existing_absolute_path(tmp_path: Path) -> None:
    config_path = tmp_path / "custom-mcp.json"
    config_path.write_text(json.dumps({"mcpServers": {}}), encoding="utf-8")

    resolved = resolve_runtime_mcp_config_path(
        _make_config(mcp_config_path=str(config_path))
    )

    assert resolved == config_path.resolve()


def test_resolve_runtime_mcp_config_path_falls_back_to_mcp_example(
    monkeypatch,
    tmp_path: Path,
) -> None:
    example_path = tmp_path / "mcp-example.json"
    example_path.write_text(json.dumps({"mcpServers": {}}), encoding="utf-8")

    monkeypatch.setattr(
        mcp_support.Config,
        "find_config_file",
        classmethod(
            lambda cls, filename: example_path if filename == "mcp-example.json" else None
        ),
    )

    resolved = resolve_runtime_mcp_config_path(_make_config())

    assert resolved == example_path.resolve()


def test_collect_mcp_operator_snapshot_summarizes_configured_and_active_servers(
    monkeypatch,
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "mcp.json"
    config_path.write_text(
        json.dumps(
            {
                "mcpServers": {
                    "alpha": {
                        "url": "https://alpha.example.com/mcp",
                        "policy": {"trust": True},
                    },
                    "beta": {
                        "command": "npx",
                        "args": ["example-mcp"],
                        "disabled": True,
                    },
                }
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        mcp_support,
        "discover_servers",
        lambda raw_path: (
            Path(raw_path),
            [
                SimpleNamespace(
                    name="alpha",
                    connection_type="streamable_http",
                    url="https://alpha.example.com/mcp",
                    command=None,
                    policy=MCPServerPolicy(trust=True),
                )
            ],
        ),
    )
    monkeypatch.setattr(
        mcp_support,
        "get_registered_connections",
        lambda: [
            SimpleNamespace(
                name="alpha",
                connection_type="streamable_http",
                tools=[
                    SimpleNamespace(
                        name=mcp_tool_alias("alpha", "search_docs"),
                        remote_name="search_docs",
                    ),
                    SimpleNamespace(
                        name=mcp_tool_alias("alpha", "read_resource"),
                        remote_name="read_resource",
                    ),
                ],
            )
        ],
    )

    snapshot = collect_mcp_operator_snapshot(
        _make_config(mcp_config_path=str(config_path), enable_mcp=True)
    )

    assert snapshot.enabled is True
    assert snapshot.config_path == str(config_path.resolve())
    assert snapshot.using_template is False
    assert snapshot.configured_total == 2
    assert snapshot.discoverable_total == 1
    assert snapshot.disabled_total == 1
    assert snapshot.active_total == 1
    assert snapshot.tool_total == 2
    assert [server.name for server in snapshot.servers] == ["alpha", "beta"]
    assert snapshot.servers[0].trust is True
    assert snapshot.servers[0].tool_names == (
        f"{mcp_tool_alias('alpha', 'search_docs')} <- search_docs",
        f"{mcp_tool_alias('alpha', 'read_resource')} <- read_resource",
    )
    assert snapshot.servers[1].disabled is True
    assert snapshot.servers[1].active is False

    status_text = format_mcp_status(snapshot)
    server_text = format_mcp_server_list(snapshot)

    assert "MCP Status:" in status_text
    assert "- configured 2" in status_text
    assert "- active 1" in status_text
    assert "- exposed tools 2" in status_text
    assert "- alpha [streamable_http] active | trusted" in server_text
    assert (
        "tools: "
        f"{mcp_tool_alias('alpha', 'search_docs')} <- search_docs, "
        f"{mcp_tool_alias('alpha', 'read_resource')} <- read_resource"
    ) in server_text
    assert "- beta [stdio] disabled | untrusted" in server_text


def test_collect_mcp_operator_snapshot_marks_template_fallback(
    monkeypatch,
    tmp_path: Path,
) -> None:
    example_path = tmp_path / "mcp-example.json"
    example_path.write_text(
        json.dumps(
            {
                "mcpServers": {
                    "docs": {
                        "command": "uvx",
                        "args": ["example-docs-mcp"],
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        mcp_support.Config,
        "find_config_file",
        classmethod(
            lambda cls, filename: example_path if filename == "mcp-example.json" else None
        ),
    )
    monkeypatch.setattr(
        mcp_support,
        "discover_servers",
        lambda raw_path: (Path(raw_path), []),
    )
    monkeypatch.setattr(mcp_support, "get_registered_connections", lambda: [])

    snapshot = collect_mcp_operator_snapshot(_make_config(mcp_config_path="mcp.json"))

    assert snapshot.using_template is True
    assert snapshot.config_path == str(example_path.resolve())
    assert snapshot.configured_total == 1
    assert snapshot.discoverable_total == 1
    assert snapshot.active_total == 0
