"""Security audit helpers for runtime configuration risk checks."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mini_agent.security.policy import RuntimePolicyEngine
from mini_agent.tools.mcp.discovery import discover_servers


@dataclass
class SecurityFinding:
    severity: str
    title: str
    detail: str


def _add(finding_list: list[SecurityFinding], severity: str, title: str, detail: str) -> None:
    finding_list.append(SecurityFinding(severity=severity, title=title, detail=detail))


def run_security_audit(config, workspace: Path | None = None) -> list[SecurityFinding]:
    findings: list[SecurityFinding] = []
    policy = RuntimePolicyEngine.from_config(config).policy

    _add(
        findings,
        "info",
        "Runtime Mode",
        (
            f"Mode='{policy.approval_profile}', access='{getattr(policy, 'access_level', 'default')}', "
            f"sandbox='{policy.sandbox_mode}', elevated_exec='{policy.elevated_exec}'."
        ),
    )

    if getattr(policy, "access_level", "default") == "full-access":
        _add(
            findings,
            "high",
            "Full Access Enabled",
            "Access level 'full-access' removes the normal sandbox and approval guardrails.",
        )
    elif policy.approval_profile == "plan":
        _add(
            findings,
            "low",
            "Plan Mode",
            "Mode 'plan' is read-first and blocks shell execution and workspace mutations.",
        )

    if policy.sandbox_mode == "unrestricted":
        _add(
            findings,
            "high",
            "Sandbox Unrestricted",
            "Sandbox mode is unrestricted; shell tools may operate outside workspace boundaries.",
        )

    if policy.elevated_exec == "allow":
        _add(
            findings,
            "high",
            "Elevated Execution Allowed",
            "Elevated host commands are allowed without approval gate.",
        )
    elif policy.elevated_exec == "require_approval":
        _add(
            findings,
            "low",
            "Elevated Execution Requires Approval",
            "Elevated commands are gated behind the live approval flow before execution.",
        )

    if policy.tool_allow:
        _add(
            findings,
            "info",
            "Tool Allowlist Active",
            f"Allowlist contains {len(policy.tool_allow)} entries: {sorted(policy.tool_allow)}.",
        )
    if policy.tool_exclude:
        _add(
            findings,
            "info",
            "Tool Exclude List Active",
            f"Exclude list contains {len(policy.tool_exclude)} entries: {sorted(policy.tool_exclude)}.",
        )

    if config.tools.enable_mcp:
        mcp_path = config.find_config_file(config.tools.mcp_config_path)
        if not mcp_path:
            _add(
                findings,
                "medium",
                "MCP Config Missing",
                f"MCP enabled but config file '{config.tools.mcp_config_path}' was not found.",
            )
        else:
            _, servers = discover_servers(str(mcp_path))
            for server in servers:
                if server.connection_type in ("sse", "http", "streamable_http"):
                    if not server.policy.trust:
                        _add(
                            findings,
                            "low",
                            f"MCP Remote Untrusted: {server.name}",
                            "Remote MCP server is configured but trust=false, so it will be skipped.",
                        )
                        continue
                    if server.url and server.url.startswith("http://"):
                        _add(
                            findings,
                            "high",
                            f"MCP Insecure Transport: {server.name}",
                            "Trusted remote MCP server uses plaintext HTTP transport.",
                        )
                    if server.policy.allow is None and server.policy.exclude is None:
                        _add(
                            findings,
                            "medium",
                            f"MCP Broad Exposure: {server.name}",
                            "Trusted remote MCP server has no tool allow/exclude constraints.",
                        )

    if workspace is not None and not workspace.exists():
        _add(
            findings,
            "medium",
            "Workspace Missing",
            f"Configured workspace does not exist: {workspace}",
        )

    return findings


def format_security_audit_report(findings: list[SecurityFinding]) -> str:
    order = {"high": 0, "medium": 1, "low": 2, "info": 3}
    findings_sorted = sorted(findings, key=lambda item: order.get(item.severity, 9))

    lines = ["Security Audit Report", "===================="]
    for finding in findings_sorted:
        lines.append(f"[{finding.severity.upper()}] {finding.title}")
        lines.append(f"  {finding.detail}")
    high_count = sum(1 for f in findings_sorted if f.severity == "high")
    medium_count = sum(1 for f in findings_sorted if f.severity == "medium")
    lines.append("")
    lines.append(f"Summary: high={high_count}, medium={medium_count}, total={len(findings_sorted)}")
    return "\n".join(lines)

