"""Runtime doctor checks and startup preflight validation."""

from __future__ import annotations

import asyncio
import shutil
import socket
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from mini_agent.security.audit import run_security_audit
from mini_agent.tools.mcp.discovery import discover_servers
from mini_agent.tools.mcp.registry import MCPServerConnection


@dataclass
class DoctorFinding:
    status: str  # pass | warn | fail | info
    title: str
    detail: str
    remediation: str | None = None


def _add(
    findings: list[DoctorFinding],
    status: str,
    title: str,
    detail: str,
    remediation: str | None = None,
) -> None:
    findings.append(
        DoctorFinding(
            status=status,
            title=title,
            detail=detail,
            remediation=remediation,
        )
    )


def _check_workspace_writable(workspace: Path) -> DoctorFinding:
    try:
        workspace.mkdir(parents=True, exist_ok=True)
        probe = workspace / ".mini_agent_write_probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        return DoctorFinding("pass", "Workspace Writable", f"Workspace is writable: {workspace}")
    except Exception as exc:
        return DoctorFinding(
            "fail",
            "Workspace Permission",
            f"Cannot write workspace '{workspace}': {exc}",
            remediation="Verify workspace path and grant current user write permission.",
        )


def _check_stdio_command(command: str) -> tuple[bool, str]:
    executable = command.split()[0] if command else ""
    if not executable:
        return False, "No command configured."
    if shutil.which(executable):
        return True, f"Command '{executable}' is available."
    return False, f"Command '{executable}' was not found in PATH."


def _check_remote_endpoint(url: str, timeout: float = 1.5) -> tuple[bool, str]:
    parsed = urlparse(url)
    host = parsed.hostname
    if not host:
        return False, "URL host is missing."

    port = parsed.port
    if port is None:
        port = 443 if parsed.scheme == "https" else 80

    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True, f"TCP reachable: {host}:{port}"
    except OSError as exc:
        return False, f"TCP unreachable: {host}:{port} ({exc})"


async def _probe_mcp_handshake_async(server) -> tuple[bool, str]:
    connection = MCPServerConnection(
        name=server.name,
        connection_type=server.connection_type,
        command=server.command,
        args=server.args,
        env=server.env,
        url=server.url,
        headers=server.headers,
        connect_timeout=server.connect_timeout,
        execute_timeout=server.execute_timeout,
        sse_read_timeout=server.sse_read_timeout,
        policy=server.policy,
    )

    try:
        success = await connection.connect()
        if success:
            return True, f"Handshake succeeded; discovered {len(connection.tools)} tool(s)."
        reason = connection.last_error or "Unknown handshake failure."
        return False, f"Handshake failed: {reason}"
    finally:
        await connection.disconnect()


def _probe_mcp_handshake(server) -> tuple[bool, str]:
    try:
        return asyncio.run(_probe_mcp_handshake_async(server))
    except RuntimeError as exc:
        return False, f"Handshake probe skipped (event loop context): {exc}"
    except Exception as exc:
        return False, f"Handshake probe failed to execute: {exc}"


def run_doctor(
    config,
    workspace: Path,
    deep_mcp_probe: bool = False,
) -> list[DoctorFinding]:
    """Run operational diagnostics for runtime startup health."""
    findings: list[DoctorFinding] = []

    if sys.version_info >= (3, 10):
        _add(
            findings,
            "pass",
            "Python Version",
            f"Python {sys.version_info.major}.{sys.version_info.minor} is supported.",
        )
    else:
        _add(
            findings,
            "fail",
            "Python Version",
            (
                f"Python {sys.version_info.major}.{sys.version_info.minor} is unsupported "
                "(requires >= 3.10)."
            ),
            remediation="Install Python 3.10+ and ensure the runtime points to that interpreter.",
        )

    findings.append(_check_workspace_writable(workspace))

    prompt_path = config.find_config_file(config.agent.system_prompt_path)
    if prompt_path and prompt_path.exists():
        _add(findings, "pass", "System Prompt", f"Found system prompt: {prompt_path}")
    else:
        _add(
            findings,
            "warn",
            "System Prompt",
            f"System prompt '{config.agent.system_prompt_path}' not found; default prompt will be used.",
            remediation="Add the configured system prompt file or update system_prompt_path in config.",
        )

    if config.tools.enable_mcp:
        mcp_path = config.find_config_file(config.tools.mcp_config_path)
        if mcp_path is None:
            _add(
                findings,
                "warn",
                "MCP Config",
                f"MCP is enabled but config '{config.tools.mcp_config_path}' was not found.",
                remediation="Create mcp.json or disable tools.enable_mcp when MCP is not required.",
            )
        else:
            _add(findings, "pass", "MCP Config", f"Using MCP config: {mcp_path}")
            _, servers = discover_servers(str(mcp_path))
            if not servers:
                _add(
                    findings,
                    "warn",
                    "MCP Servers",
                    "No active MCP servers discovered.",
                    remediation="Define at least one enabled server in mcp.json.",
                )
            else:
                _add(findings, "pass", "MCP Servers", f"Discovered {len(servers)} MCP server(s).")

            for server in servers:
                if server.connection_type == "stdio":
                    ok, detail = _check_stdio_command(server.command or "")
                    _add(
                        findings,
                        "pass" if ok else "fail",
                        f"MCP STDIO {server.name}",
                        detail,
                        None
                        if ok
                        else "Install the command or fix 'command' in mcp.json; disable server if unused.",
                    )
                    if deep_mcp_probe and ok:
                        hs_ok, hs_detail = _probe_mcp_handshake(server)
                        _add(
                            findings,
                            "pass" if hs_ok else "fail",
                            f"MCP Handshake {server.name}",
                            hs_detail,
                            None
                            if hs_ok
                            else (
                                "Run the MCP server command manually, validate startup logs, and verify "
                                "stdio protocol compatibility."
                            ),
                        )
                    continue

                if not server.url:
                    _add(
                        findings,
                        "warn",
                        f"MCP Remote {server.name}",
                        "Remote server has no URL.",
                        remediation="Set a valid url for the remote MCP server.",
                    )
                    continue

                if not server.policy.trust:
                    _add(
                        findings,
                        "info",
                        f"MCP Remote {server.name}",
                        "Remote server is untrusted and will be skipped by loader.",
                        remediation="Set policy.trust=true only for endpoints you explicitly trust.",
                    )
                    continue

                ok, detail = _check_remote_endpoint(server.url)
                _add(
                    findings,
                    "pass" if ok else "warn",
                    f"MCP Remote {server.name}",
                    detail,
                    None if ok else "Verify network routing/firewall and remote MCP endpoint availability.",
                )
                if deep_mcp_probe and ok:
                    hs_ok, hs_detail = _probe_mcp_handshake(server)
                    _add(
                        findings,
                        "pass" if hs_ok else "warn",
                        f"MCP Handshake {server.name}",
                        hs_detail,
                        None
                        if hs_ok
                        else (
                            "Verify server supports MCP handshake at configured URL and credentials/headers "
                            "are correct."
                        ),
                    )
    else:
        _add(findings, "info", "MCP Disabled", "MCP tooling is disabled in config.")

    security_findings = run_security_audit(config, workspace=workspace)
    high_count = sum(1 for item in security_findings if item.severity == "high")
    medium_count = sum(1 for item in security_findings if item.severity == "medium")
    if high_count:
        _add(
            findings,
            "warn",
            "Security Posture",
            f"Security audit reports {high_count} high and {medium_count} medium risk item(s).",
            remediation="Run 'mini-agent security-audit' and address high-severity findings first.",
        )
    else:
        _add(
            findings,
            "pass",
            "Security Posture",
            f"Security audit reports 0 high and {medium_count} medium risk item(s).",
        )

    return findings


def run_startup_self_check(
    config,
    workspace: Path,
    deep_mcp_probe: bool = False,
) -> tuple[bool, list[DoctorFinding]]:
    """Run startup preflight checks used by CLI/Gateway boot paths."""
    findings = run_doctor(config=config, workspace=workspace, deep_mcp_probe=deep_mcp_probe)
    has_failure = any(item.status == "fail" for item in findings)
    return (not has_failure), findings


def format_doctor_report(findings: list[DoctorFinding], title: str = "Doctor Report") -> str:
    order = {"fail": 0, "warn": 1, "pass": 2, "info": 3}
    icon = {"fail": "X", "warn": "!", "pass": "OK", "info": "i"}

    sorted_findings = sorted(findings, key=lambda item: order.get(item.status, 9))
    lines = [title, "=" * len(title)]
    for finding in sorted_findings:
        marker = icon.get(finding.status, "?")
        lines.append(f"[{marker}] {finding.title}")
        lines.append(f"  {finding.detail}")
        if finding.remediation:
            lines.append(f"  Hint: {finding.remediation}")

    fail_count = sum(1 for item in sorted_findings if item.status == "fail")
    warn_count = sum(1 for item in sorted_findings if item.status == "warn")
    lines.append("")
    lines.append(f"Summary: fail={fail_count}, warn={warn_count}, total={len(sorted_findings)}")
    return "\n".join(lines)
