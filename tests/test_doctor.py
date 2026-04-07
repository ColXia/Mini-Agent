"""Tests for doctor diagnostics and startup self-check."""

import json
from pathlib import Path

from mini_agent.config import AgentConfig, Config, LLMConfig, SecurityConfig, ToolsConfig
from mini_agent.ops.doctor import format_doctor_report, run_doctor, run_startup_self_check


def _make_config(tmp_path: Path, *, enable_mcp: bool, mcp_path: Path | None = None) -> Config:
    tools = ToolsConfig(
        enable_mcp=enable_mcp,
        enable_skills=False,
        mcp_config_path=str(mcp_path) if mcp_path else "missing-mcp.json",
    )
    return Config(
        llm=LLMConfig(api_key="test-key"),
        agent=AgentConfig(workspace_dir=str(tmp_path / "workspace")),
        tools=tools,
        security=SecurityConfig(),
    )


def test_doctor_reports_pass_without_mcp(tmp_path: Path):
    config = _make_config(tmp_path, enable_mcp=False)
    findings = run_doctor(config=config, workspace=tmp_path / "workspace")

    assert any(item.status == "pass" and item.title == "Python Version" for item in findings)
    assert any(item.status == "pass" and item.title == "Workspace Writable" for item in findings)
    assert any(item.title == "MCP Disabled" for item in findings)

    report = format_doctor_report(findings)
    assert "Doctor Report" in report
    assert "Summary:" in report


def test_startup_self_check_fails_on_missing_stdio_command(tmp_path: Path):
    mcp_path = tmp_path / "mcp.json"
    mcp_path.write_text(
        json.dumps(
            {
                "mcpServers": {
                    "broken": {
                        "command": "command-that-definitely-does-not-exist-xyz",
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    config = _make_config(tmp_path, enable_mcp=True, mcp_path=mcp_path)
    is_ready, findings = run_startup_self_check(config=config, workspace=tmp_path / "workspace")

    assert is_ready is False
    assert any(
        item.status == "fail" and item.title == "MCP STDIO broken"
        for item in findings
    )


def test_doctor_deep_probe_includes_handshake_and_hint(tmp_path: Path):
    mcp_path = tmp_path / "mcp.json"
    mcp_path.write_text(
        json.dumps(
            {
                "mcpServers": {
                    "broken": {
                        "command": "command-that-definitely-does-not-exist-xyz",
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    config = _make_config(tmp_path, enable_mcp=True, mcp_path=mcp_path)
    findings = run_doctor(
        config=config,
        workspace=tmp_path / "workspace",
        deep_mcp_probe=True,
    )

    stdio_failure = next(
        (
            item
            for item in findings
            if item.title == "MCP STDIO broken" and item.status == "fail"
        ),
        None,
    )
    assert stdio_failure is not None
    assert stdio_failure.remediation is not None

    report = format_doctor_report(findings)
    assert "Hint:" in report
