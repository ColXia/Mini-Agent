"""Runtime doctor checks and startup preflight validation."""

from __future__ import annotations

import asyncio
import shutil
import socket
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from mini_agent.model_manager.bootstrap import bootstrap_llm_settings_from_config
from mini_agent.model_manager.feature_runtime import FeatureModelRuntime
from mini_agent.model_manager.model_registry_service import ModelRegistryService
from mini_agent.model_manager.provider import ModelRole, ProviderAPIType
from mini_agent.model_manager.runtime import (
    resolve_provider_catalog,
    resolve_routed_llm_candidates,
)
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


def _normalize_text(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _iter_registry_models(registry: list[dict[str, Any]]) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    items: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for provider in registry:
        if not isinstance(provider, dict):
            continue
        for model in provider.get("models", []):
            if isinstance(model, dict):
                items.append((provider, model))
    return items


def _model_reference(provider: dict[str, Any], model: dict[str, Any]) -> str:
    source = _normalize_text(provider.get("source")).lower() or "?"
    provider_id = _normalize_text(provider.get("provider_id")) or "?"
    model_id = _normalize_text(model.get("model_id")) or "?"
    return f"{source}/{provider_id}/{model_id}"


def _binding_reference(binding: dict[str, Any]) -> str:
    source = _normalize_text(binding.get("source")).lower() or "?"
    provider_id = _normalize_text(binding.get("provider_id")) or "?"
    model_id = _normalize_text(binding.get("model_id")) or "?"
    return f"{source}/{provider_id}/{model_id}"


def _summarize_references(items: list[str], *, limit: int = 3) -> str:
    cleaned: list[str] = []
    for item in items:
        normalized = _normalize_text(item)
        if normalized:
            cleaned.append(normalized)
    if not cleaned:
        return "none"
    if len(cleaned) <= limit:
        return ", ".join(cleaned)
    return f"{', '.join(cleaned[:limit])}, +{len(cleaned) - limit} more"


def _is_local_or_discovered_model(provider: dict[str, Any], model: dict[str, Any]) -> bool:
    provider_family = _normalize_text(provider.get("provider_family")).lower()
    api_base = _normalize_text(provider.get("api_base")).lower()
    discovery_source = _normalize_text(model.get("discovery_source")).lower()
    if provider_family == "ollama":
        return True
    if discovery_source and discovery_source not in {"configured_default", "official_default"}:
        return True
    return any(host in api_base for host in ("localhost", "127.0.0.1", "::1"))


def _feature_binding_title(feature_role: str) -> str:
    if feature_role == ModelRole.EMBEDDING.value:
        return "Embedding Binding"
    if feature_role == ModelRole.OCR.value:
        return "OCR Binding"
    return f"{feature_role.title()} Binding"


def _feature_binding_fallback_detail(feature_role: str) -> str:
    if feature_role == ModelRole.EMBEDDING.value:
        return (
            "No embedding model is bound; knowledge retrieval will fall back to BM25/hash-vector "
            "retrieval until one is configured."
        )
    if feature_role == ModelRole.OCR.value:
        return (
            "No OCR model is bound; document parsing will continue with the standard non-model OCR "
            "fallback path."
        )
    return f"No {feature_role} model is bound."


def _feature_binding_remediation(feature_role: str) -> str:
    return (
        "Bind one with 'mini-agent provider bind-feature --feature-role "
        f"{feature_role} --source <custom|preset> --id <provider> --model-id <model>'."
    )


def _collect_model_supply_findings(config) -> list[DoctorFinding]:
    findings: list[DoctorFinding] = []
    bootstrap_llm = bootstrap_llm_settings_from_config(config)
    try:
        catalog_resolution = resolve_provider_catalog(
            bootstrap_llm=bootstrap_llm,
            supported_api_types={ProviderAPIType.ANTHROPIC, ProviderAPIType.OPENAI},
        )
        catalog_path = (
            Path(catalog_resolution.catalog_path).expanduser().resolve()
            if catalog_resolution.catalog_path
            else None
        )
        service = ModelRegistryService(catalog_path=catalog_path)
        registry = service.list_registry()
    except Exception as exc:
        _add(
            findings,
            "fail",
            "Model Catalog",
            f"Failed to inspect model supply state: {exc}",
            remediation=(
                "Validate provider catalog JSON, preset provider environment variables, and model "
                "registry state before retrying."
            ),
        )
        return findings

    registry_models = _iter_registry_models(registry)
    registry_chat_model_count = sum(
        1
        for _provider, model in registry_models
        if _normalize_text(model.get("model_role")).lower()
        not in {ModelRole.EMBEDDING.value, ModelRole.OCR.value}
    )
    runtime_provider_count = len(catalog_resolution.providers)
    runtime_model_count = sum(len(provider.models) for provider in catalog_resolution.providers)
    catalog_state = (
        "exists"
        if catalog_path is not None and catalog_path.exists()
        else "missing"
    )
    catalog_detail = (
        f"catalog={catalog_path or '<default>'} ({catalog_state}); "
        f"runtime_source={catalog_resolution.source}; "
        f"registry={len(registry)} provider(s)/{len(registry_models)} model(s); "
        f"chat_runtime={runtime_provider_count} provider(s)/{runtime_model_count} model(s)."
    )
    if catalog_resolution.source == "bootstrap_provider_catalog":
        _add(
            findings,
            "warn",
            "Model Catalog",
            catalog_detail,
            remediation=(
                "Persist providers in the catalog instead of relying on bootstrap-only config, so "
                "model supply remains visible and editable across surfaces."
            ),
        )
    else:
        _add(findings, "pass", "Model Catalog", catalog_detail)

    if registry_models and registry_chat_model_count <= 0:
        _add(
            findings,
            "fail",
            "Chat Runtime Availability",
            (
                "Visible registry inventory contains only feature-role models, so the project has no "
                "catalog-backed chat runtime even if bootstrap fallback is still available."
            ),
            remediation=(
                "Add or reclassify at least one chat model in the catalog before continuing normal "
                "runtime iteration."
            ),
        )
    elif runtime_provider_count <= 0 or runtime_model_count <= 0:
        feature_only_count = sum(
            1
            for _provider, model in registry_models
            if _normalize_text(model.get("model_role")).lower()
            in {ModelRole.EMBEDDING.value, ModelRole.OCR.value}
        )
        detail = "No chat-routable models are available to the runtime."
        if feature_only_count and feature_only_count == len(registry_models):
            detail += " Every visible model is currently feature-role only."
        elif registry_models:
            detail += " Visible registry models may be unbound, disabled, or filtered out of chat routing."
        _add(
            findings,
            "fail",
            "Chat Runtime Availability",
            detail,
            remediation=(
                "Ensure at least one enabled chat model/provider is configured, and keep embedding/OCR "
                "models separated from the chat runtime inventory."
            ),
        )
    else:
        _add(
            findings,
            "pass",
            "Chat Runtime Availability",
            f"Runtime can route across {runtime_provider_count} provider(s) and {runtime_model_count} chat model(s).",
        )

    unclassified_local_or_discovered = [
        _model_reference(provider, model)
        for provider, model in registry_models
        if _is_local_or_discovered_model(provider, model)
        and _normalize_text(model.get("model_role")).lower()
        in {"", ModelRole.UNCLASSIFIED.value}
    ]
    if unclassified_local_or_discovered:
        _add(
            findings,
            "warn",
            "Model Role Coverage",
            (
                f"{len(unclassified_local_or_discovered)} local/discovered model(s) remain unclassified: "
                f"{_summarize_references(unclassified_local_or_discovered)}"
            ),
            remediation=(
                "Set model_role explicitly to chat, embedding, or ocr so routing and feature bindings "
                "stay predictable."
            ),
        )
    else:
        _add(
            findings,
            "pass",
            "Model Role Coverage",
            "All local/discovered models have explicit roles.",
        )

    if runtime_provider_count > 0 and runtime_model_count > 0:
        try:
            selected_route = resolve_routed_llm_candidates(
                bootstrap_llm=bootstrap_llm,
                catalog_path=catalog_path,
            )[0]
            selected_ref = (
                f"{_normalize_text(selected_route.provider_source) or 'bootstrap'}/"
                f"{_normalize_text(selected_route.provider_id) or '?'}"
                f"/{_normalize_text(selected_route.model) or '?'}"
            )
            gaps: list[str] = []
            if _normalize_text(selected_route.supports_tools_truth).lower() in {"", "unknown"}:
                gaps.append("supports_tools")
            if _normalize_text(selected_route.supports_thinking_truth).lower() in {"", "unknown"}:
                gaps.append("supports_thinking")
            if selected_route.token_limit is None:
                gaps.append("token_limit/context_window")
            if _normalize_text(selected_route.model_role).lower() in {
                ModelRole.EMBEDDING.value,
                ModelRole.OCR.value,
            }:
                gaps.append("chat_runtime_model_role")
            if gaps:
                _add(
                    findings,
                    "warn",
                    "Selected Chat Capability Evidence",
                    (
                        f"Selected chat route {selected_ref} is missing readiness facts: "
                        f"{', '.join(gaps)}."
                    ),
                    remediation=(
                        "Discover or annotate the active chat model with supports_tools, "
                        "supports_thinking, and token/context evidence before relying on it in upper layers."
                    ),
                )
            else:
                _add(
                    findings,
                    "pass",
                    "Selected Chat Capability Evidence",
                    (
                        f"Selected chat route {selected_ref} has tools={selected_route.supports_tools_truth}, "
                        f"thinking={selected_route.supports_thinking_truth}, limit={selected_route.token_limit}."
                    ),
                )
        except Exception as exc:
            _add(
                findings,
                "fail",
                "Selected Chat Route",
                f"Runtime failed to resolve an active chat route: {exc}",
                remediation=(
                    "Repair provider/model selection state and verify the runtime has at least one supported "
                    "chat provider."
                ),
            )

    feature_runtime = FeatureModelRuntime(catalog_path=catalog_path)
    binding_map = {
        _normalize_text(item.get("feature_role")).lower(): item
        for item in service.list_feature_bindings()
        if isinstance(item, dict)
    }
    feature_model_refs: dict[str, list[str]] = {
        ModelRole.EMBEDDING.value: [],
        ModelRole.OCR.value: [],
    }
    for provider, model in registry_models:
        role = _normalize_text(model.get("model_role")).lower()
        if role in feature_model_refs:
            feature_model_refs[role].append(_model_reference(provider, model))

    for feature_role in (ModelRole.EMBEDDING.value, ModelRole.OCR.value):
        title = _feature_binding_title(feature_role)
        binding = binding_map.get(feature_role)
        available_refs = feature_model_refs.get(feature_role, [])
        if feature_role == ModelRole.EMBEDDING.value:
            runtime_binding = feature_runtime.get_embedding_provider()
        else:
            runtime_binding = feature_runtime.get_docling_ocr_adapter()
        if binding is None:
            if available_refs:
                _add(
                    findings,
                    "warn",
                    title,
                    (
                        f"{len(available_refs)} {feature_role} model(s) are classified but no binding is set: "
                        f"{_summarize_references(available_refs)}"
                    ),
                    remediation=_feature_binding_remediation(feature_role),
                )
            else:
                _add(findings, "info", title, _feature_binding_fallback_detail(feature_role))
            continue

        if not bool(binding.get("resolved")):
            _add(
                findings,
                "warn",
                title,
                f"Binding points to a missing or stale target: {_binding_reference(binding)}.",
                remediation=(
                    "Clear or rebind the feature model so registry state and runtime state point to the same model."
                ),
            )
            continue

        binding_role = _normalize_text(binding.get("model_role")).lower()
        if binding_role != feature_role:
            _add(
                findings,
                "warn",
                title,
                (
                    f"Binding resolves to {_binding_reference(binding)} but model_role="
                    f"'{binding_role or 'unset'}' does not match '{feature_role}'."
                ),
                remediation=(
                    f"Set model_role={feature_role} for the bound model, then rebind the feature role."
                ),
            )
            continue

        if runtime_binding is None:
            _add(
                findings,
                "warn",
                title,
                (
                    f"Binding resolves to {_binding_reference(binding)} but the runtime cannot build a "
                    f"{feature_role} helper from provider_family="
                    f"'{_normalize_text(binding.get('provider_family')) or '?'}' / api_type="
                    f"'{_normalize_text(binding.get('api_type')) or '?'}'."
                ),
                remediation=(
                    "Use an OpenAI-compatible or Ollama embedding model for embedding, and an Ollama "
                    "multimodal model for OCR."
                ),
            )
            continue

        _add(
            findings,
            "pass",
            title,
            f"Bound to {_binding_reference(binding)}.",
        )

    return findings


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

    findings.extend(_collect_model_supply_findings(config))

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
