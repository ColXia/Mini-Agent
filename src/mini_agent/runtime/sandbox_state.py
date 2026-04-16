"""Sandbox status helpers shared by runtime surfaces."""

from __future__ import annotations

from typing import Any

from mini_agent.agent_core.runtime_bindings import get_agent_runtime_services


def _safe_text(value: Any) -> str:
    return " ".join(str(value or "").split())


def _safe_bool(value: Any) -> bool:
    return bool(value)


def _safe_int(value: Any, *, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return int(default)


def normalize_sandbox_diagnostics(value: Any) -> dict[str, Any]:
    payload = dict(value) if isinstance(value, dict) else {}
    return {
        "backend": _safe_text(payload.get("backend")) or "none",
        "reason": _safe_text(payload.get("reason")) or None,
        "sandbox_mode": _safe_text(payload.get("sandbox_mode")) or None,
        "approval_profile": _safe_text(payload.get("approval_profile")) or None,
        "access_level": _safe_text(payload.get("access_level")) or None,
        "workspace_root": _safe_text(payload.get("workspace_root")) or None,
        "network_mode": _safe_text(payload.get("network_mode")) or "allow_all",
        "network_allow_domains": [
            _safe_text(item)
            for item in list(payload.get("network_allow_domains") or [])
            if _safe_text(item)
        ],
        "network_block_domains": [
            _safe_text(item)
            for item in list(payload.get("network_block_domains") or [])
            if _safe_text(item)
        ],
        "restricted_token": _safe_bool(payload.get("restricted_token")),
        "low_integrity": _safe_bool(payload.get("low_integrity")),
        "mandatory_policy": max(0, _safe_int(payload.get("mandatory_policy"))),
        "disable_admin_groups": _safe_bool(payload.get("disable_admin_groups")),
        "restrict_ui": _safe_bool(payload.get("restrict_ui")),
        "die_on_unhandled_exception": _safe_bool(payload.get("die_on_unhandled_exception")),
        "max_processes": _safe_int(payload.get("max_processes")),
        "max_process_memory_mb": _safe_int(payload.get("max_process_memory_mb")),
    }


def collect_sandbox_diagnostics(
    *,
    agent: Any | None = None,
    sandbox_manager: Any | None = None,
    runtime_policy_engine: Any | None = None,
) -> dict[str, Any]:
    if agent is not None:
        runtime_services = get_agent_runtime_services(agent)
        sandbox_manager = sandbox_manager or runtime_services.sandbox_manager
        runtime_policy_engine = runtime_policy_engine or runtime_services.runtime_policy_engine

    selection = None
    if sandbox_manager is not None:
        try:
            selection = sandbox_manager.select_initial()
        except Exception:
            selection = None

    metadata = {}
    if selection is not None and isinstance(getattr(selection, "metadata", None), dict):
        metadata = dict(selection.metadata)

    policy = getattr(runtime_policy_engine, "policy", None)
    network_policy = getattr(sandbox_manager, "network_policy", None)
    allow_domains = tuple(getattr(network_policy, "allow_domains", ()) or ())
    block_domains = tuple(getattr(network_policy, "block_domains", ()) or ())

    payload = {
        "backend": _safe_text(
            metadata.get("backend")
            or getattr(selection, "backend", None)
            or "none"
        ),
        "reason": _safe_text(metadata.get("reason") or getattr(selection, "reason", None)) or None,
        "sandbox_mode": _safe_text(
            metadata.get("sandbox_mode")
            or getattr(policy, "sandbox_mode", None)
        ) or None,
        "approval_profile": _safe_text(getattr(policy, "approval_profile", None)) or None,
        "access_level": _safe_text(getattr(policy, "access_level", None)) or None,
        "workspace_root": _safe_text(metadata.get("workspace_root")) or None,
        "network_mode": _safe_text(
            metadata.get("network_mode")
            or getattr(getattr(network_policy, "mode", None), "value", None)
            or "allow_all"
        ),
        "network_allow_domains": list(allow_domains),
        "network_block_domains": list(block_domains),
        "restricted_token": metadata.get("restricted_token"),
        "low_integrity": metadata.get("low_integrity"),
        "mandatory_policy": metadata.get("mandatory_policy"),
        "disable_admin_groups": metadata.get("disable_admin_groups"),
        "restrict_ui": metadata.get("restrict_ui"),
        "die_on_unhandled_exception": metadata.get("die_on_unhandled_exception"),
        "max_processes": metadata.get("max_processes"),
        "max_process_memory_mb": metadata.get("max_process_memory_mb"),
    }
    return normalize_sandbox_diagnostics(payload)


def compact_sandbox_summary(value: Any) -> str:
    diagnostics = normalize_sandbox_diagnostics(value)
    backend = diagnostics["backend"]
    sandbox_mode = diagnostics["sandbox_mode"] or "workspace"

    if backend == "windows_restricted_token":
        parts = ["win-token"]
        if diagnostics["low_integrity"]:
            parts.append("low")
        mandatory_policy = diagnostics["mandatory_policy"]
        if mandatory_policy > 0:
            parts.append(f"mp={mandatory_policy}")
        return " / ".join(parts)

    if backend == "none" and sandbox_mode == "unrestricted":
        return "none / unrestricted"
    if backend == "none":
        return "none / passthrough"
    return backend


def sandbox_policy_summary(value: Any) -> str:
    diagnostics = normalize_sandbox_diagnostics(value)
    approval_profile = diagnostics["approval_profile"] or "build"
    access_level = diagnostics["access_level"] or "default"
    return f"{approval_profile} / {access_level}"


def sandbox_guardrail_summary(value: Any) -> str:
    diagnostics = normalize_sandbox_diagnostics(value)
    items: list[str] = []
    if diagnostics["restricted_token"]:
        items.append("rtok")
    if diagnostics["disable_admin_groups"]:
        items.append("admin off")
    if diagnostics["restrict_ui"]:
        items.append("ui locked")
    if diagnostics["die_on_unhandled_exception"]:
        items.append("die-on-crash")
    return " | ".join(items) if items else "baseline"


def sandbox_network_summary(value: Any) -> str:
    diagnostics = normalize_sandbox_diagnostics(value)
    mode = diagnostics["network_mode"] or "allow_all"
    allow_count = len(diagnostics["network_allow_domains"])
    block_count = len(diagnostics["network_block_domains"])
    suffixes: list[str] = []
    if allow_count > 0:
        suffixes.append(f"allow={allow_count}")
    if block_count > 0:
        suffixes.append(f"block={block_count}")
    return f"{mode} | {' | '.join(suffixes)}" if suffixes else mode


def format_sandbox_status(value: Any) -> str:
    diagnostics = normalize_sandbox_diagnostics(value)
    policy_bits = diagnostics["mandatory_policy"]
    lines = [
        "Sandbox Status",
        f"- backend: {diagnostics['backend']}",
        f"- mode: {diagnostics['sandbox_mode'] or 'workspace'}",
        f"- execution: {diagnostics['approval_profile'] or 'build'}",
        f"- access: {diagnostics['access_level'] or 'default'}",
        f"- integrity: {'low' if diagnostics['low_integrity'] else 'default'}",
        f"- mandatory policy: {policy_bits if policy_bits > 0 else 'n/a'}",
        f"- restricted token: {'on' if diagnostics['restricted_token'] else 'off'}",
        f"- admin groups disabled: {'yes' if diagnostics['disable_admin_groups'] else 'no'}",
        f"- ui restrictions: {'on' if diagnostics['restrict_ui'] else 'off'}",
        f"- die on crash: {'on' if diagnostics['die_on_unhandled_exception'] else 'off'}",
        f"- max processes: {diagnostics['max_processes'] if diagnostics['max_processes'] > 0 else 'n/a'}",
        (
            f"- max process memory: {diagnostics['max_process_memory_mb']} MB"
            if diagnostics["max_process_memory_mb"] > 0
            else "- max process memory: n/a"
        ),
        f"- network: {sandbox_network_summary(diagnostics)}",
    ]
    return "\n".join(lines)


__all__ = [
    "collect_sandbox_diagnostics",
    "compact_sandbox_summary",
    "format_sandbox_status",
    "normalize_sandbox_diagnostics",
    "sandbox_guardrail_summary",
    "sandbox_network_summary",
    "sandbox_policy_summary",
]
