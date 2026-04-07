"""Tests for security audit risk reporting."""

import json
from pathlib import Path

from mini_agent.config import AgentConfig, Config, LLMConfig, SecurityConfig, ToolsConfig
from mini_agent.security.audit import run_security_audit


def _make_config(mcp_path: Path, security: SecurityConfig) -> Config:
    return Config(
        llm=LLMConfig(api_key="test-key"),
        agent=AgentConfig(workspace_dir=str(mcp_path.parent / "workspace")),
        tools=ToolsConfig(enable_mcp=True, enable_skills=False, mcp_config_path=str(mcp_path)),
        security=security,
    )


def test_security_audit_reports_high_risk_for_full_auto_and_insecure_mcp(tmp_path):
    mcp_path = tmp_path / "mcp.json"
    mcp_path.write_text(
        json.dumps(
            {
                "mcpServers": {
                    "remote": {
                        "url": "http://mcp.example.com/mcp",
                        "policy": {"trust": True},
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    config = _make_config(
        mcp_path,
        SecurityConfig(
            approval_profile="full-auto",
            sandbox_mode="unrestricted",
            elevated_exec="allow",
        ),
    )

    findings = run_security_audit(config, workspace=tmp_path / "workspace")
    titles = {item.title for item in findings}
    severities = [item.severity for item in findings]

    assert "Full Auto Enabled" in titles
    assert "Sandbox Unrestricted" in titles
    assert "Elevated Execution Allowed" in titles
    assert "MCP Insecure Transport: remote" in titles
    assert "high" in severities


def test_security_audit_reports_missing_mcp_config(tmp_path):
    missing_path = tmp_path / "missing-mcp.json"
    config = _make_config(
        missing_path,
        SecurityConfig(approval_profile="auto-edit"),
    )

    findings = run_security_audit(config, workspace=tmp_path / "workspace")
    titles = {item.title for item in findings}
    assert "MCP Config Missing" in titles
