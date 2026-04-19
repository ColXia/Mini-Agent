"""DesktopUI shell and formatting helpers."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
import html
import json
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlsplit

from mini_agent.desktop.gateway_transport_binding import DesktopGatewayTransportBinding
from mini_agent.desktop.gateway_supervisor import DesktopGatewayConnection, DesktopGatewaySupervisor
from mini_agent.desktop.session_actions import (
    DesktopSessionActionFeedback,
    desktop_error_detail,
    desktop_run_can_cancel,
    desktop_run_can_interrupt,
    desktop_run_can_resume,
    format_desktop_approval_failure,
    perform_desktop_pending_approval_resolution,
    perform_desktop_run_cancel,
    perform_desktop_run_interrupt,
    perform_desktop_run_resume,
    perform_desktop_session_compact,
    perform_desktop_session_creation,
    perform_desktop_session_fork,
    perform_desktop_session_rename,
    perform_desktop_share_toggle,
)
from mini_agent.interfaces.agent import (
    MainAgentChatRequest,
    MainAgentDefaultSessionRequest,
)
from mini_agent.interfaces.model import MainAgentModelBindingRequest
from mini_agent.interfaces.ops import (
    StudioFeatureModelBindingRequest,
    StudioModelCapabilityProbeRequest,
    StudioModelRoleRequest,
    StudioProviderModelDiscoveryRequest,
    StudioProviderUpsertRequest,
    StudioProviderValidationRequest,
)
from mini_agent.interfaces.surface_payload_adapter import (
    surface_payload_from_dto,
    surface_payload_list_from_dtos,
)
from mini_agent.runtime.read_models.session_payload_codec import RuntimeSessionPayloadCodec
from mini_agent.runtime.live_control.run_control_store import RuntimeSessionRunControlStore
from mini_agent.transport.gateway_error import extract_gateway_error_info
from mini_agent.transport.remote_chat_service_port import RemoteChatServicePort
from mini_agent.transport.remote_stream_error_service import RemoteStreamErrorService


DESKTOP_PAGE_SPECS: tuple[dict[str, str], ...] = (
    {
        "id": "chat",
        "label": "Chat",
        "description": "Focused conversation workspace with recent chats and on-demand runtime context.",
    },
    {
        "id": "models",
        "label": "Models",
        "description": "Model inventory, capability facts, role assignment, and feature binding workflows.",
    },
    {
        "id": "providers",
        "label": "Providers",
        "description": "Provider configuration, connection health, and supplier setup flows.",
    },
    {
        "id": "settings",
        "label": "Settings",
        "description": "Desktop preferences, workspace controls, and current runtime overview.",
    },
    {
        "id": "sessions",
        "label": "Sessions",
        "description": "Session history workspace and current session diagnostics.",
    },
    {
        "id": "memory",
        "label": "Memory",
        "description": "Durable note memory and memory-file editing follow-up workspace.",
    },
)

DESKTOP_MODEL_ROLE_OPTIONS: tuple[str, ...] = ("chat", "embedding", "ocr", "unclassified")
DESKTOP_FEATURE_ROLE_OPTIONS: tuple[str, ...] = ("embedding", "ocr")
DESKTOP_PROVIDER_PRESET_SPECS: tuple[dict[str, str], ...] = (
    {
        "id": "openai_official",
        "label": "OpenAI",
        "api_type": "openai",
        "provider_id": "openai-official",
        "provider_name": "OpenAI Official",
        "api_base": "https://api.openai.com/v1",
        "base_placeholder": "Official OpenAI or any OpenAI-compatible endpoint",
        "api_key_placeholder": "Paste OpenAI API key",
        "model_placeholder": "One model id per line, for example gpt-*",
        "default_model_placeholder": "Optional default model id",
        "note": "Official OpenAI quick-fill. You can also reuse it for OpenAI-compatible MaaS by replacing the Base URL.",
    },
    {
        "id": "anthropic_official",
        "label": "Anthropic",
        "api_type": "anthropic",
        "provider_id": "anthropic-official",
        "provider_name": "Anthropic Official",
        "api_base": "https://api.anthropic.com",
        "base_placeholder": "Official Anthropic endpoint",
        "api_key_placeholder": "Paste Anthropic API key",
        "model_placeholder": "One model id per line, for example claude-*",
        "default_model_placeholder": "Optional default model id",
        "note": "Official Anthropic quick-fill for direct API access.",
    },
    {
        "id": "minimax_anthropic",
        "label": "MiniMax",
        "api_type": "anthropic",
        "provider_id": "minimax-m2-7",
        "provider_name": "MiniMax M2.7",
        "api_base": "",
        "base_placeholder": "Paste MiniMax Anthropic-compatible endpoint",
        "api_key_placeholder": "Paste MiniMax-compatible API key",
        "model_placeholder": "One model id per line, for example MiniMax-M2.7",
        "default_model_placeholder": "Optional default model id",
        "note": "Anthropic-family sub-preset for MiniMax. Fill the Anthropic-compatible relay URL from your deployment.",
    },
    {
        "id": "ollama_local",
        "label": "Ollama",
        "api_type": "ollama",
        "provider_id": "ollama-local",
        "provider_name": "Ollama Local",
        "api_base": "http://127.0.0.1:11434/v1",
        "base_placeholder": "Local Ollama daemon URL",
        "api_key_placeholder": "Usually not required for local Ollama",
        "model_placeholder": "One model id per line, for example qwen3.5:9b",
        "default_model_placeholder": "Optional default model id",
        "note": "Local Ollama quick-fill. Discover models after the daemon is running.",
    },
)

DESKTOP_OLLAMA_SENTINEL_API_KEY = "ollama"


@dataclass(frozen=True, slots=True)
class DesktopTurnFeedback:
    """Normalized feedback for desktop prompt submission and stream outcomes."""

    status_text: str
    activity_message: str
    activity_kind: str = "status"
    activity_detail: str | None = None


def _compact_text(value: Any) -> str:
    return " ".join(str(value or "").split())


def _truncate_text(value: Any, *, limit: int = 88) -> str:
    text = str(value or "")
    if len(text) <= limit:
        return text
    if limit <= 1:
        return text[:limit]
    return f"{text[: limit - 1]}…"


def _normalize_chat_content(value: Any) -> str:
    text = str(value or "")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return text.expandtabs(4)


def _safe_nonnegative_int(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except Exception:
        return 0


def _format_token_compact(value: Any) -> str:
    amount = _safe_nonnegative_int(value)
    if amount < 1000:
        return str(amount)
    if amount < 1_000_000:
        scaled = amount / 1000.0
        suffix = "k"
    elif amount < 1_000_000_000:
        scaled = amount / 1_000_000.0
        suffix = "M"
    else:
        scaled = amount / 1_000_000_000.0
        suffix = "B"
    return f"{scaled:.1f}".rstrip("0").rstrip(".") + suffix


def resolve_desktop_context_usage_stats(
    detail: dict[str, Any] | None,
    selected_model_option: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Resolve compact context-usage stats for the desktop composer."""
    payload = detail if isinstance(detail, dict) else {}
    option = selected_model_option if isinstance(selected_model_option, dict) else {}

    usage = _safe_nonnegative_int(payload.get("token_usage"))
    usage_source = "reported"
    if usage <= 0:
        recent_messages = payload.get("recent_messages")
        if isinstance(recent_messages, list):
            usage = RuntimeSessionPayloadCodec.estimate_raw_message_tokens(recent_messages)
            if usage > 0:
                usage_source = "estimated"

    limit = 0
    limit_source = "unknown"
    for source, candidate in (
        ("token_limit", payload.get("token_limit")),
        ("selected_token_limit", payload.get("selected_token_limit")),
        ("selected_learned_token_limit", payload.get("selected_learned_token_limit")),
        ("selected_context_window", payload.get("selected_context_window")),
        ("model_token_limit", option.get("token_limit")),
        ("model_learned_token_limit", option.get("learned_token_limit")),
        ("model_context_window", option.get("context_window")),
    ):
        parsed = _safe_nonnegative_int(candidate)
        if parsed > 0:
            limit = parsed
            limit_source = source
            break

    raw_ratio = (float(usage) / float(limit)) if limit > 0 else 0.0
    ratio = max(0.0, min(1.0, raw_ratio))
    percent = min(999, int(round(raw_ratio * 100))) if limit > 0 else 0

    if limit <= 0:
        tone = "muted"
    elif raw_ratio >= 0.85:
        tone = "high"
    elif raw_ratio >= 0.6:
        tone = "medium"
    else:
        tone = "low"

    return {
        "usage": usage,
        "limit": limit,
        "ratio": ratio,
        "percent": percent,
        "tone": tone,
        "usage_source": usage_source,
        "limit_source": limit_source,
        "budget_text": f"{usage:,} / {limit:,}" if limit > 0 else f"{usage:,} / --",
        "compact_usage": _format_token_compact(usage),
        "compact_limit": _format_token_compact(limit) if limit > 0 else "--",
        "percent_text": f"{percent}%" if limit > 0 else "--",
        "ring_text": "--" if limit <= 0 else ("99+" if percent > 99 else str(percent)),
    }


def _source_badge(source: str | None) -> str:
    normalized = _compact_text(source).lower()
    if normalized == "custom":
        return "C"
    if normalized == "preset":
        return "P"
    if normalized == "builtin":
        return "B"
    return normalized[:1].upper() or "?"


def _looks_like_ollama_endpoint(api_base: Any) -> bool:
    normalized = _compact_text(api_base)
    if not normalized:
        return False
    try:
        parsed = urlsplit(normalized)
    except Exception:
        return "11434" in normalized
    host = str(parsed.hostname or "").strip().lower()
    if host in {"localhost", "127.0.0.1", "::1"} and parsed.port == 11434:
        return True
    return "11434" in normalized


def _desktop_provider_api_type(api_type: Any, api_base: Any) -> str:
    normalized = _compact_text(api_type).lower()
    if normalized == "ollama":
        return "ollama"
    if normalized == "openai" and _looks_like_ollama_endpoint(api_base):
        return "ollama"
    return normalized or "openai"


def _normalize_desktop_provider_api_base(*, api_type: Any, api_base: Any) -> str:
    normalized = _compact_text(api_base).rstrip("/")
    if not normalized:
        return ""
    if _desktop_provider_api_type(api_type, normalized) != "ollama":
        return normalized
    if normalized.endswith("/v1/models"):
        return normalized[: -len("/models")]
    if normalized.endswith("/v1"):
        return normalized
    return f"{normalized}/v1"


def _resolve_desktop_provider_api_key(*, api_type: Any, api_base: Any, api_key: Any) -> str:
    normalized_key = _compact_text(api_key)
    if normalized_key:
        return normalized_key
    if _desktop_provider_api_type(api_type, api_base) == "ollama":
        return DESKTOP_OLLAMA_SENTINEL_API_KEY
    return ""


def format_session_row(session: dict[str, Any]) -> str:
    """Render one compact session row for the left rail."""
    title = _compact_text(session.get("title")) or _compact_text(session.get("session_id")) or "Untitled"
    labels: list[str] = [title]
    pending = list(session.get("pending_approvals") or [])
    running_state = _compact_text(session.get("running_state")).lower()
    recovery = session.get("recovery") if isinstance(session.get("recovery"), dict) else {}
    if pending:
        labels.append("Waiting")
    elif running_state == "cancellation requested":
        labels.append("Cancelling")
    elif running_state == "interrupt requested":
        labels.append("Interrupting")
    elif recovery:
        labels.append("Interrupted")
    elif bool(session.get("busy")):
        labels.append("Busy")
    if bool(session.get("shared")):
        labels.append("Shared")
    return " | ".join(labels)


def format_session_context_text(
    detail: dict[str, Any],
    run_summary: dict[str, Any] | None = None,
) -> str:
    """Render concise session metadata and diagnostics for the right rail."""
    diagnostics = {
        "pending_approvals": detail.get("pending_approvals") or [],
        "memory_diagnostics": detail.get("memory_diagnostics") or {},
        "sandbox_diagnostics": detail.get("sandbox_diagnostics") or {},
    }
    lines = [
        f"Title: {_compact_text(detail.get('title')) or '-'}",
        f"Session ID: {_compact_text(detail.get('session_id')) or '-'}",
        f"Workspace: {_compact_text(detail.get('workspace_dir')) or '-'}",
        f"Surface: {_compact_text(detail.get('active_surface') or detail.get('origin_surface')) or '-'}",
        f"Shared: {bool(detail.get('shared'))}",
        f"Busy: {bool(detail.get('busy'))}",
        f"Running: {_compact_text(detail.get('running_state')) or '-'}",
        f"Model: {_compact_text(detail.get('selected_provider_id')) or '-'} / {_compact_text(detail.get('selected_model_id')) or '-'}",
        f"Updated: {_compact_text(detail.get('updated_at')) or '-'}",
        "",
        format_desktop_run_summary_text(run_summary),
        "",
        "Diagnostics:",
        json.dumps(diagnostics, ensure_ascii=False, indent=2),
    ]
    return "\n".join(lines)


def format_model_catalog_text(
    catalog: dict[str, Any] | None,
    current_detail: dict[str, Any] | None = None,
) -> str:
    """Render provider/model catalog for the right rail."""
    items = list((catalog or {}).get("items") or [])
    if not items:
        return "No model catalog available."

    selected_provider = _compact_text((current_detail or {}).get("selected_provider_id"))
    selected_model = _compact_text((current_detail or {}).get("selected_model_id"))
    lines: list[str] = []
    for provider in items:
        provider_name = _compact_text(provider.get("provider_name")) or _compact_text(provider.get("provider_id")) or "Provider"
        badge = _source_badge(provider.get("source"))
        default_model = _compact_text(provider.get("default_model_id")) or "-"
        lines.append(f"{provider_name} [{badge}] | default {default_model}")
        for model in list(provider.get("models") or []):
            model_id = _compact_text(model.get("model_id")) or "-"
            display_name = _compact_text(model.get("display_name"))
            suffix = ""
            if (
                _compact_text(provider.get("provider_id")) == selected_provider
                and model_id == selected_model
            ):
                suffix = " [session]"
            elif bool(model.get("is_default")):
                suffix = " [default]"
            if display_name and display_name != model_id:
                lines.append(f"  {model_id} ({display_name}){suffix}")
            else:
                lines.append(f"  {model_id}{suffix}")
        lines.append("")
    return "\n".join(lines).rstrip()


def collect_model_options(catalog: dict[str, Any] | None) -> list[dict[str, str]]:
    """Flatten provider/model catalog into combobox-friendly options."""
    options: list[dict[str, str]] = []
    for provider in list((catalog or {}).get("items") or []):
        provider_source = _compact_text(provider.get("source"))
        provider_id = _compact_text(provider.get("provider_id"))
        provider_name = _compact_text(provider.get("provider_name")) or provider_id or "Provider"
        for model in list(provider.get("models") or []):
            model_id = _compact_text(model.get("model_id"))
            if not provider_id or not model_id:
                continue
            display_name = _compact_text(model.get("display_name"))
            label = f"{provider_name} [{_source_badge(provider_source)}] | {model_id}"
            if display_name and display_name != model_id:
                label = f"{label} ({display_name})"
            options.append(
                {
                    "label": label,
                    "combo_label": display_name or model_id,
                    "display_name": display_name or model_id,
                    "provider_name": provider_name,
                    "provider_source": provider_source,
                    "provider_id": provider_id,
                    "model_id": model_id,
                    "context_window": str(model.get("context_window") or ""),
                    "learned_token_limit": str(model.get("learned_token_limit") or ""),
                    "token_limit": str(model.get("token_limit") or ""),
                }
            )
    return options


def first_pending_approval(
    detail: dict[str, Any] | None,
    run_summary: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Return the first pending approval item from session detail."""
    run_wait = (run_summary or {}).get("approval_wait") if isinstance(run_summary, dict) else None
    if isinstance(run_wait, dict):
        token = _compact_text(run_wait.get("approval_token"))
        tool_name = _compact_text(run_wait.get("tool_name"))
        if token or tool_name:
            return {
                "token": token or None,
                "tool_name": tool_name or "tool",
                "arguments": (
                    dict(run_wait.get("tool_arguments_summary") or {})
                    if isinstance(run_wait.get("tool_arguments_summary"), dict)
                    else {}
                ),
                "kind": _compact_text(run_wait.get("approval_kind")) or None,
                "reason": _compact_text(run_wait.get("policy_reason")) or None,
                "cache_key": _compact_text(run_wait.get("cache_key")) or None,
                "can_escalate": bool(run_wait.get("can_escalate")),
                "wait_id": _compact_text(run_wait.get("wait_id")) or None,
            }
    items = list((detail or {}).get("pending_approvals") or [])
    if not items:
        return None
    item = items[0]
    return item if isinstance(item, dict) else None


def count_desktop_pending_approvals(
    detail: dict[str, Any] | None,
    run_summary: dict[str, Any] | None = None,
) -> int:
    """Count visible pending approvals, preferring run-level truth when present."""
    run_wait = (run_summary or {}).get("approval_wait") if isinstance(run_summary, dict) else None
    if isinstance(run_wait, dict):
        token = _compact_text(run_wait.get("approval_token"))
        tool_name = _compact_text(run_wait.get("tool_name"))
        if token or tool_name:
            return 1
    items = [item for item in list((detail or {}).get("pending_approvals") or []) if isinstance(item, dict)]
    return len(items)


def resolve_desktop_approval_button_text(
    detail: dict[str, Any] | None,
    run_summary: dict[str, Any] | None = None,
) -> str:
    """Resolve the DesktopUI approvals button label."""
    count = count_desktop_pending_approvals(detail, run_summary)
    return "Approvals" if count <= 0 else f"Approvals ({count})"


def desktop_stream_activity_payload(
    event_type: Any,
    payload: object,
    *,
    thinking_text: str | None = None,
) -> dict[str, str] | None:
    """Normalize one remote stream event into one desktop activity card payload."""
    event = _compact_text(event_type).lower() or "message"
    data = payload if isinstance(payload, dict) else {}

    if event == "activity":
        label = _compact_text(data.get("label")) or "activity"
        detail = _compact_text(data.get("detail")) or "running"
        preview = _compact_text(data.get("preview"))
        return {
            "kind": label,
            "title": detail,
            "detail": _compact_text(data.get("output_text")),
            "preview": preview,
            "activity_id": _compact_text(data.get("activity_id") or data.get("id")),
        }
    if event == "status":
        stage = _compact_text(data.get("stage")) or "running"
        return {"kind": "status", "title": stage}
    if event == "approval_requested":
        tool_name = _compact_text(data.get("tool_name")) or "tool"
        return {
            "kind": "approval",
            "title": f"{tool_name} needs approval",
            "detail": _compact_text(data.get("reason")),
            "activity_id": f"approval:{_compact_text(data.get('token')) or tool_name}",
        }
    if event == "approval_resolved":
        return {"kind": "approval", "title": "Approval resolved"}
    if event.startswith("delegation."):
        detail = event.split(".", 1)[-1] or "delegation"
        owner = _compact_text(data.get("worker_id") or data.get("owner"))
        return {
            "kind": "delegation",
            "title": detail,
            "preview": owner,
            "activity_id": _compact_text(data.get("task_id")) or event,
        }
    if event == "thinking_delta":
        text = _normalize_chat_content(thinking_text or data.get("chunk")).strip()
        if not text:
            return None
        return {
            "kind": "thinking",
            "title": "Thinking",
            "detail": text,
            "activity_id": "remote-thinking",
        }
    if event == "error":
        detail = RemoteStreamErrorService.payload_detail(data)
        return {
            "kind": "error",
            "title": detail,
        }
    return None


def build_desktop_chat_request(
    *,
    session_id: str,
    message: str,
    workspace_dir: str | None,
) -> MainAgentChatRequest:
    """Build the canonical DesktopUI chat submission request."""
    resolved_workspace = str(workspace_dir or "").strip() or None
    return MainAgentChatRequest(
        session_id=_compact_text(session_id),
        message=str(message or "").strip(),
        workspace_dir=resolved_workspace,
        surface="desktop",
    )


def record_desktop_prompt_submission(
    conversation_messages: list[dict[str, Any]],
    *,
    session_id: str,
    message: str,
) -> DesktopTurnFeedback:
    """Append the outgoing user prompt to the desktop transcript."""
    conversation_messages.append(
        {
            "role": "user",
            "content": str(message or ""),
            "surface": "desktop",
        }
    )
    status_text = f"Prompt submitted to {session_id}."
    return DesktopTurnFeedback(
        status_text=status_text,
        activity_message=status_text,
        activity_kind="session",
    )


def append_desktop_assistant_stream_chunk(
    conversation_messages: list[dict[str, Any]],
    chunk: str,
) -> None:
    """Append one assistant streaming chunk into the desktop transcript."""
    if (
        conversation_messages
        and conversation_messages[-1].get("role") == "assistant"
        and conversation_messages[-1].get("surface") == "desktop"
        and bool(conversation_messages[-1].get("streaming"))
    ):
        conversation_messages[-1]["content"] = (
            f"{conversation_messages[-1].get('content') or ''}{chunk}"
        )
        return
    conversation_messages.append(
        {
            "role": "assistant",
            "content": chunk,
            "surface": "desktop",
            "streaming": True,
        }
    )


def finalize_desktop_stream_completion(
    conversation_messages: list[dict[str, Any]],
    payload: object,
) -> DesktopTurnFeedback:
    """Apply a finished desktop stream payload to the transcript."""
    response = surface_payload_from_dto(payload)
    reply = str(response.get("reply") or "")
    last_message = conversation_messages[-1] if conversation_messages else None
    last_is_desktop_assistant = bool(
        isinstance(last_message, dict)
        and last_message.get("role") == "assistant"
        and last_message.get("surface") == "desktop"
    )
    if last_is_desktop_assistant:
        current_content = str(last_message.get("content") or "")
        if reply and not current_content.strip():
            last_message["content"] = reply
        last_message.pop("streaming", None)
    elif reply:
        conversation_messages.append(
            {
                "role": "assistant",
                "content": reply,
                "surface": "desktop",
            }
        )

    token_usage = response.get("token_usage")
    return DesktopTurnFeedback(
        status_text="Turn completed",
        activity_message="Turn completed",
        activity_kind="status",
        activity_detail=(f"token_usage={token_usage}" if token_usage is not None else None),
    )


def finalize_desktop_stream_error(
    conversation_messages: list[dict[str, Any]],
    message: str,
) -> DesktopTurnFeedback:
    """Apply a failed desktop stream outcome to the transcript."""
    error_text = str(message or "").strip() or "Desktop turn failed."
    if (
        conversation_messages
        and conversation_messages[-1].get("role") == "assistant"
        and conversation_messages[-1].get("surface") == "desktop"
    ):
        conversation_messages[-1].pop("streaming", None)
    status_text = f"Turn failed: {error_text}"
    conversation_messages.append(
        {
            "role": "system",
            "content": f"Desktop turn failed: {error_text}",
            "surface": "desktop",
        }
    )
    return DesktopTurnFeedback(
        status_text=status_text,
        activity_message=status_text,
        activity_kind="error",
    )


def resolve_desktop_run_state_badge(
    detail: dict[str, Any] | None,
    run_summary: dict[str, Any] | None,
    *,
    send_busy: bool = False,
) -> dict[str, str]:
    """Resolve the compact chat-header run state badge from run truth."""
    summary = run_summary if isinstance(run_summary, dict) else {}
    payload = detail if isinstance(detail, dict) else {}
    if bool(summary.get("cancel_requested")):
        return {"text": "Cancelling", "tone": "warning"}
    if bool(summary.get("interrupt_requested")):
        return {"text": "Interrupting", "tone": "warning"}
    if bool(summary.get("waiting_on_approval")):
        return {"text": "Waiting", "tone": "accent"}
    if send_busy or bool(summary.get("busy")) or bool(payload.get("busy")):
        return {"text": "Busy", "tone": "warning"}
    recovery = payload.get("recovery") if isinstance(payload.get("recovery"), dict) else {}
    if recovery:
        return {"text": "Interrupted", "tone": "muted"}
    return {"text": "Ready", "tone": "success"}


def append_desktop_activity_entry(
    entries: list[dict[str, Any]],
    message: str,
    *,
    kind: str = "activity",
    detail: str | None = None,
    preview: str | None = None,
    activity_id: str | None = None,
    timestamp: str | None = None,
    limit: int = 120,
) -> list[dict[str, Any]]:
    """Append or update one desktop activity entry in-place."""
    normalized_message = str(message or "").strip() or "activity"
    normalized_detail = str(detail or "")
    if not normalized_detail and "\n" in normalized_message:
        first_line, remainder = normalized_message.split("\n", 1)
        normalized_message = first_line.strip() or "activity"
        normalized_detail = remainder.strip()

    normalized_id = _compact_text(activity_id)
    normalized_timestamp = _compact_text(timestamp) or datetime.now().strftime("%H:%M:%S")
    target: dict[str, Any] | None = None
    if normalized_id:
        for item in entries:
            if _compact_text(item.get("activity_id")) == normalized_id:
                target = item
                break

    if target is None:
        entries.append(
            {
                "timestamp": normalized_timestamp,
                "kind": _compact_text(kind).lower() or "activity",
                "title": normalized_message,
                "detail": normalized_detail,
                "preview": _compact_text(preview),
                "activity_id": normalized_id,
            }
        )
    else:
        target["timestamp"] = normalized_timestamp
        target["kind"] = _compact_text(kind).lower() or "activity"
        target["title"] = normalized_message
        target["detail"] = normalized_detail
        if preview is not None:
            target["preview"] = _compact_text(preview)
        target["activity_id"] = normalized_id

    if len(entries) > max(1, int(limit or 120)):
        del entries[:-max(1, int(limit or 120))]
    return entries


def format_desktop_run_summary_text(run_summary: dict[str, Any] | None) -> str:
    """Render a compact run-level summary for the desktop chat side panel."""
    summary = run_summary if isinstance(run_summary, dict) else {}
    if not summary:
        return "Run: unavailable"
    status = _compact_text(summary.get("status")) or "-"
    phase = _compact_text(summary.get("phase")) or "-"
    control_mode = _compact_text(summary.get("control_mode")) or "-"
    running_state = _compact_text(summary.get("running_state")) or "-"
    lines = [
        f"Run Status: {status}",
        f"Run Phase: {phase}",
        f"Control: {control_mode}",
        f"Running: {running_state}",
    ]
    approval_wait = summary.get("approval_wait") if isinstance(summary.get("approval_wait"), dict) else {}
    if approval_wait:
        tool_name = _compact_text(approval_wait.get("tool_name")) or "tool"
        token = _compact_text(approval_wait.get("approval_token")) or "-"
        lines.append(f"Approval Wait: {tool_name} ({token})")
    checkpoint = summary.get("checkpoint") if isinstance(summary.get("checkpoint"), dict) else {}
    if checkpoint:
        checkpoint_id = _compact_text(checkpoint.get("checkpoint_id")) or "-"
        mutation_count = int(checkpoint.get("mutation_count") or 0)
        lines.append(f"Checkpoint: {checkpoint_id} | mutations={mutation_count}")
    return "\n".join(lines)


def format_chat_context_text(
    detail: dict[str, Any] | None,
    run_summary: dict[str, Any] | None = None,
) -> str:
    """Render a compact session+run summary for the desktop chat side panel."""
    payload = detail or {}
    if not payload:
        return "No session selected."
    provider_id = _compact_text(payload.get("selected_provider_id")) or "-"
    model_id = _compact_text(payload.get("selected_model_id")) or "-"
    updated = _compact_text(payload.get("updated_at")) or "-"
    pending_approvals = len(list(payload.get("pending_approvals") or []))
    lines = [
        f"State: {'busy' if bool(payload.get('busy')) else 'ready'}",
        f"Access: {'shared' if bool(payload.get('shared')) else 'private'}",
        f"Model: {provider_id} / {model_id}",
        f"Updated: {updated}",
        f"Approvals: {pending_approvals}",
        "",
        format_desktop_run_summary_text(run_summary),
    ]
    return "\n".join(lines)


def format_chat_runtime_text(
    catalog: dict[str, Any] | None,
    current_detail: dict[str, Any] | None = None,
    run_summary: dict[str, Any] | None = None,
) -> str:
    """Render a compact runtime note for the desktop chat workspace."""
    items = list((catalog or {}).get("items") or [])
    detail = current_detail if isinstance(current_detail, dict) else {}
    selected_provider = _compact_text(detail.get("selected_provider_id")) or "-"
    selected_model = _compact_text(detail.get("selected_model_id")) or "-"
    provider_count = len(items)
    model_count = sum(len(list(provider.get("models") or [])) for provider in items)
    lines = [
        f"Session: {_compact_text(detail.get('session_id')) or 'none'}",
        f"Selected: {selected_provider} / {selected_model}",
        f"Providers: {provider_count}",
        f"Models: {model_count}",
        "",
        format_desktop_run_summary_text(run_summary),
    ]
    return "\n".join(lines)


def render_conversation_html(messages: list[dict[str, Any]]) -> str:
    """Render transcript entries as lightweight HTML blocks."""
    if not messages:
        return (
            "<html><body style='font-family: \"Segoe UI Variable\", \"SF Pro Text\", \"Microsoft YaHei UI\"; "
            "color: #67778b; background: transparent;'>"
            "<div style='padding: 10px 2px; opacity: 0.82;'>No transcript entries yet.</div>"
            "</body></html>"
        )

    role_styles = {
        "user": ("#14243a", "#eef5ff", "#d9e7fb", "#5e8fda"),
        "assistant": ("#1b2838", "#ffffff", "#e2e8f0", "#b4c2d4"),
        "system": ("#342046", "#f6efff", "#e8dcff", "#b388ee"),
        "tool": ("#123126", "#edf9f2", "#d7efe2", "#67c28b"),
    }
    parts = [
        "<html><body style='font-family: \"Segoe UI Variable\", \"SF Pro Text\", \"Microsoft YaHei UI\"; "
        "background: transparent; margin: 0;'>"
    ]
    for message in messages:
        role = _compact_text(message.get("role")).lower() or "assistant"
        surface = _compact_text(message.get("surface")) or "-"
        content = html.escape(str(message.get("content") or "")).replace("\n", "<br>")
        fg, bg, border, accent = role_styles.get(role, ("#1b2838", "#ffffff", "#e2e8f0", "#9eb0c8"))
        parts.append(
            "<div style='margin: 0 0 12px 0; padding: 14px 16px; "
            f"border: 1px solid {border}; background: {bg}; color: {fg}; border-radius: 16px;'>"
            f"<div style='display: inline-block; margin-bottom: 8px; padding: 3px 9px; "
            f"border-radius: 999px; background: {accent}; color: #ffffff; font-size: 11px; font-weight: 600;'>"
            f"{html.escape(role)} | {html.escape(surface)}</div>"
            f"<div style='font-size: 13px; line-height: 1.58;'>{content or '&nbsp;'}</div>"
            "</div>"
        )
    parts.append("</body></html>")
    return "".join(parts)


def render_activity_html(entries: list[dict[str, Any]]) -> str:
    """Render structured activity entries as compact operator cards."""
    if not entries:
        return (
            "<html><body style='font-family: \"Segoe UI Variable\", \"SF Pro Text\", \"Microsoft YaHei UI\"; "
            "color: #67778b; background: transparent;'>"
            "<div style='padding: 10px 2px; opacity: 0.82;'>No activity yet.</div>"
            "</body></html>"
        )

    palette = {
        "activity": ("#18304c", "#f3f7fd", "#dbe6f3", "#7ea5db"),
        "approval": ("#4a3411", "#fff8eb", "#f5e4b8", "#e0b251"),
        "delegation": ("#113223", "#eef9f3", "#d7ecdf", "#68bd8f"),
        "error": ("#4c1f1f", "#fff2f2", "#f0d2d2", "#d98282"),
        "gateway": ("#35224a", "#f7f1ff", "#eadfff", "#af8ae2"),
        "health": ("#123326", "#eefaf3", "#d7ecdf", "#63bb88"),
        "model": ("#1d2850", "#f3f4ff", "#dfe3ff", "#7d8fe6"),
        "session": ("#163845", "#eef9fc", "#d6eaf0", "#67bdd5"),
        "status": ("#1a3046", "#f1f7fc", "#dce8f3", "#7fb2da"),
        "thinking": ("#35224a", "#f8f4ff", "#eadfff", "#ab84eb"),
    }
    parts = [
        "<html><body style='font-family: \"Segoe UI Variable\", \"SF Pro Text\", \"Microsoft YaHei UI\"; "
        "background: transparent; margin: 0;'>"
    ]
    for entry in entries:
        kind = _compact_text(entry.get("kind")).lower() or "activity"
        timestamp = _compact_text(entry.get("timestamp")) or "--:--:--"
        title = html.escape(_compact_text(entry.get("title")) or "activity")
        detail = str(entry.get("detail") or "")
        preview = _compact_text(entry.get("preview"))
        fg, bg, border, accent = palette.get(kind, ("#1b2838", "#ffffff", "#e2e8f0", "#9eb0c8"))
        parts.append(
            "<div style='margin: 0 0 10px 0; padding: 12px 14px; "
            f"border: 1px solid {border}; background: {bg}; color: {fg}; border-radius: 14px;'>"
            f"<div style='display: inline-block; margin-bottom: 8px; padding: 3px 9px; "
            f"border-radius: 999px; background: {accent}; color: #ffffff; font-size: 11px; font-weight: 600;'>"
            f"{html.escape(kind)}</div>"
            f"<div style='font-size: 11px; opacity: 0.72; margin-bottom: 5px;'>"
            f"{html.escape(timestamp)} | {html.escape(kind)}</div>"
            f"<div style='font-size: 13px; font-weight: 600; margin-bottom: 4px;'>{title}</div>"
        )
        if preview:
            parts.append(
                "<div style='font-size: 11px; opacity: 0.76; margin-bottom: 4px;'>"
                f"{html.escape(preview)}</div>"
            )
        if detail:
            parts.append(
                "<div style='font-size: 12px; line-height: 1.4; white-space: pre-wrap;'>"
                f"{html.escape(detail)}</div>"
            )
        parts.append("</div>")
    parts.append("</body></html>")
    return "".join(parts)


def desktop_page_specs() -> list[dict[str, str]]:
    """Return immutable desktop page metadata as a mutable list for UI consumers."""
    return [dict(item) for item in DESKTOP_PAGE_SPECS]


def desktop_provider_preset_specs() -> list[dict[str, str]]:
    """Return provider preset metadata for desktop quick-fill flows."""
    return [dict(item) for item in DESKTOP_PROVIDER_PRESET_SPECS]


def collect_provider_entries(payload: dict[str, Any] | None) -> list[dict[str, str]]:
    """Flatten provider summaries for list-driven desktop pages."""
    entries: list[dict[str, str]] = []
    for item in list((payload or {}).get("items") or []):
        provider_id = _compact_text(item.get("id"))
        if not provider_id:
            continue
        name = _compact_text(item.get("name")) or provider_id
        api_base = _compact_text(item.get("api_base"))
        api_type = _desktop_provider_api_type(item.get("api_type"), api_base) or "-"
        health_status = _compact_text(item.get("health_status")) or "-"
        models = list(item.get("models") or [])
        label = name
        if health_status not in {"", "-", "healthy"}:
            label = f"{name} | {health_status}"
        entries.append(
            {
                "label": label,
                "detail": "\n".join(
                    [
                        f"Name: {name}",
                        f"Type: {api_type}",
                        f"Health: {health_status}",
                        f"Models: {len(models)}",
                        f"Base URL: {api_base or '-'}",
                    ]
                ),
                "provider_id": provider_id,
                "provider_name": name,
                "api_type": api_type,
                "api_base": api_base,
                "health_status": health_status,
            }
        )
    return entries


def collect_registry_model_entries(
    payload: dict[str, Any] | None,
    *,
    filter_text: str = "",
) -> list[dict[str, str]]:
    """Flatten ops model registry payload into list-friendly desktop items."""
    needle = _compact_text(filter_text).lower()
    entries: list[dict[str, str]] = []
    for provider in list((payload or {}).get("items") or []):
        source = _compact_text(provider.get("source"))
        provider_id = _compact_text(provider.get("provider_id"))
        provider_name = _compact_text(provider.get("provider_name")) or provider_id or "Provider"
        for model in list(provider.get("models") or []):
            model_id = _compact_text(model.get("model_id"))
            if not provider_id or not model_id:
                continue
            role = _compact_text(model.get("model_role")) or "unclassified"
            tools = _compact_text(model.get("supports_tools_truth")) or "--"
            thinking = _compact_text(model.get("supports_thinking_truth")) or "--"
            display_name = _compact_text(model.get("display_name"))
            label_parts = [display_name or model_id, provider_name]
            if role != "unclassified":
                label_parts.append(role)
            if bool(model.get("is_default")):
                label_parts.append("default")
            label = " | ".join(label_parts)
            entry = {
                "label": label,
                "detail": "\n".join(
                    [
                        f"Provider: {provider_name} [{_source_badge(source)}]",
                        f"Model: {model_id}",
                        f"Display: {display_name or model_id}",
                        f"Role: {role}",
                        f"Tools: {tools}",
                        f"Thinking: {thinking}",
                    ]
                ),
                "source": source,
                "provider_id": provider_id,
                "provider_name": provider_name,
                "provider_family": _compact_text(provider.get("provider_family")),
                "provider_variant": _compact_text(provider.get("provider_variant")),
                "api_type": _compact_text(provider.get("api_type")),
                "api_base": _compact_text(provider.get("api_base")),
                "model_id": model_id,
                "display_name": display_name or model_id,
                "model_role": role,
                "supports_tools_truth": tools,
                "supports_thinking_truth": thinking,
                "context_window": str(model.get("context_window") or ""),
                "learned_token_limit": str(model.get("learned_token_limit") or ""),
            }
            haystack = " ".join(
                [
                    entry["provider_name"],
                    entry["provider_id"],
                    entry["model_id"],
                    entry["display_name"],
                    entry["model_role"],
                    entry["supports_tools_truth"],
                    entry["supports_thinking_truth"],
                ]
            ).lower()
            if needle and needle not in haystack:
                continue
            entries.append(entry)
    return entries


def collect_provider_draft_model_entries(
    *,
    provider_id: str | None,
    model_ids: list[str] | None,
    default_model_id: str | None = None,
    registry_payload: dict[str, Any] | None = None,
    feature_bindings: dict[str, Any] | None = None,
) -> list[dict[str, str]]:
    """Project current provider-draft models into shortcut-friendly entries."""
    normalized_provider_id = _compact_text(provider_id)
    normalized_default_model_id = _compact_text(default_model_id)
    registry_models: dict[str, dict[str, Any]] = {}
    for provider in list((registry_payload or {}).get("items") or []):
        if _compact_text(provider.get("source")).lower() != "custom":
            continue
        if _compact_text(provider.get("provider_id")) != normalized_provider_id:
            continue
        for model in list(provider.get("models") or []):
            model_id = _compact_text(model.get("model_id"))
            if model_id:
                registry_models[model_id] = model if isinstance(model, dict) else {}

    feature_roles_by_model: dict[str, list[str]] = {}
    for item in list((feature_bindings or {}).get("items") or []):
        if _compact_text(item.get("provider_id")) != normalized_provider_id:
            continue
        model_id = _compact_text(item.get("model_id"))
        feature_role = _compact_text(item.get("feature_role"))
        if not model_id or not feature_role:
            continue
        feature_roles_by_model.setdefault(model_id, [])
        if feature_role not in feature_roles_by_model[model_id]:
            feature_roles_by_model[model_id].append(feature_role)

    entries: list[dict[str, str]] = []
    seen: set[str] = set()
    for raw_model_id in list(model_ids or []):
        model_id = _compact_text(raw_model_id)
        if not model_id:
            continue
        lowered = model_id.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        registry_model = registry_models.get(model_id, {})
        status = "saved" if registry_model else "draft"
        model_role = _compact_text(registry_model.get("model_role")) or "unclassified"
        tools = _compact_text(registry_model.get("supports_tools_truth")) or "--"
        thinking = _compact_text(registry_model.get("supports_thinking_truth")) or "--"
        feature_roles = ",".join(feature_roles_by_model.get(model_id) or [])
        default_suffix = " | default" if model_id == normalized_default_model_id else ""
        feature_suffix = f" | feature={feature_roles}" if feature_roles else ""
        entries.append(
            {
                "label": (
                    f"{model_id} | {status} | role={model_role} | "
                    f"tools={tools} | thinking={thinking}{feature_suffix}{default_suffix}"
                ),
                "model_id": model_id,
                "status": status,
                "model_role": model_role,
                "supports_tools_truth": tools,
                "supports_thinking_truth": thinking,
                "feature_roles": feature_roles,
                "is_default": "true" if model_id == normalized_default_model_id else "false",
            }
        )
    return entries


def format_feature_bindings_text(payload: dict[str, Any] | None) -> str:
    """Render feature-model bindings as concise desktop-readable text."""
    items = list((payload or {}).get("items") or [])
    if not items:
        return "No feature-model bindings configured."
    lines = ["Feature Bindings:"]
    for item in items:
        feature_role = _compact_text(item.get("feature_role")) or "-"
        provider = _compact_text(item.get("provider_name") or item.get("provider_id")) or "-"
        model_id = _compact_text(item.get("model_id")) or "-"
        resolved = "resolved" if bool(item.get("resolved", True)) else "stale"
        lines.append(f"- {feature_role}: {provider} / {model_id} ({resolved})")
    return "\n".join(lines)


def format_provider_detail_text(
    provider: dict[str, Any] | None,
    *,
    health: dict[str, Any] | None = None,
) -> str:
    """Render one provider summary for the Providers page inspector."""
    if not isinstance(provider, dict) or not provider:
        return "Select a provider to inspect configuration and health."
    lines = [
        f"Name: {_compact_text(provider.get('name')) or '-'}",
        f"Provider ID: {_compact_text(provider.get('id')) or '-'}",
        f"Type: {_desktop_provider_api_type(provider.get('api_type'), provider.get('api_base')) or '-'}",
        f"Base URL: {_compact_text(provider.get('api_base')) or '-'}",
        f"Enabled: {bool(provider.get('enabled'))}",
        f"Priority: {provider.get('priority') if provider.get('priority') is not None else '-'}",
        f"Timeout: {provider.get('timeout') if provider.get('timeout') is not None else '-'}",
        f"Health: {_compact_text(provider.get('health_status')) or '-'}",
        f"Breaker: {_compact_text(provider.get('breaker_state')) or '-'}",
        f"Models: {len(list(provider.get('models') or []))}",
    ]
    if isinstance(health, dict) and health:
        lines.extend(
            [
                "",
                "Health Snapshot:",
                f"- status: {_compact_text(health.get('status')) or '-'}",
                f"- breaker: {_compact_text(health.get('breaker_state')) or '-'}",
                f"- selected_count: {health.get('selected_count') if health.get('selected_count') is not None else '-'}",
                f"- consecutive_failures: {health.get('consecutive_failures') if health.get('consecutive_failures') is not None else '-'}",
                f"- error_rate: {health.get('error_rate') if health.get('error_rate') is not None else '-'}",
                f"- last_failure_reason: {_compact_text(health.get('last_failure_reason')) or '-'}",
            ]
        )
    headers = provider.get("headers")
    if isinstance(headers, dict) and headers:
        lines.extend(["", "Headers:", json.dumps(headers, ensure_ascii=False, indent=2)])
    models = list(provider.get("models") or [])
    if models:
        lines.extend(["", "Models:"])
        for model_id in models:
            lines.append(f"- {_compact_text(model_id) or '-'}")
    return "\n".join(lines)


def format_provider_validation_text(payload: dict[str, Any] | None) -> str:
    """Render compact provider connection feedback for the draft form."""
    if not isinstance(payload, dict) or not payload:
        return "Connection not tested for current draft."

    status = _compact_text(payload.get("status")) or "unknown"
    model_count = int(payload.get("model_count") or len(list(payload.get("models") or [])))
    latest_model_id = _compact_text(payload.get("latest_model_id")) or "-"
    message = _compact_text(payload.get("message")) or "Connection feedback unavailable."
    if status == "reachable":
        return (
            f"Connection OK. {model_count} model(s) reachable. "
            f"Latest: {latest_model_id}. {message}"
        )
    if status == "reachable_no_models":
        return f"Connection OK, but no models were listed. {message}"
    return message


def format_registry_model_detail_text(
    entry: dict[str, Any] | None,
    *,
    feature_bindings: dict[str, Any] | None = None,
) -> str:
    """Render one flattened registry model entry for the Models page inspector."""
    if not isinstance(entry, dict) or not entry:
        return "Select a model to inspect role, capability facts, and feature bindings."
    lines = [
        f"Provider: {_compact_text(entry.get('provider_name')) or '-'}",
        f"Provider ID: {_compact_text(entry.get('provider_id')) or '-'}",
        f"Source: {_compact_text(entry.get('source')) or '-'}",
        f"Family: {_compact_text(entry.get('provider_family')) or '-'}",
        f"Variant: {_compact_text(entry.get('provider_variant')) or '-'}",
        f"API Type: {_compact_text(entry.get('api_type')) or '-'}",
        f"Base URL: {_compact_text(entry.get('api_base')) or '-'}",
        f"Model: {_compact_text(entry.get('model_id')) or '-'}",
        f"Display: {_compact_text(entry.get('display_name')) or '-'}",
        f"Role: {_compact_text(entry.get('model_role')) or '-'}",
        f"Context Window: {_compact_text(entry.get('context_window')) or '--'}",
        f"Learned Token Limit: {_compact_text(entry.get('learned_token_limit')) or '--'}",
        f"Supports Tools: {_compact_text(entry.get('supports_tools_truth')) or '--'}",
        f"Supports Thinking: {_compact_text(entry.get('supports_thinking_truth')) or '--'}",
    ]
    bindings_text = format_feature_bindings_text(feature_bindings)
    if bindings_text:
        lines.extend(["", bindings_text])
    return "\n".join(lines)


def format_settings_summary_text(
    *,
    connection: Any,
    selected_session_detail: dict[str, Any] | None = None,
    workspace_summary: dict[str, Any] | None = None,
    active_workspace: dict[str, Any] | None = None,
    workspace_runtime_summary: dict[str, Any] | None = None,
    workspace_list: list[dict[str, Any]] | None = None,
    model_catalog: dict[str, Any] | None = None,
    registry_payload: dict[str, Any] | None = None,
    provider_payload: dict[str, Any] | None = None,
    feature_bindings: dict[str, Any] | None = None,
    refresh_interval_ms: int | None = None,
    auto_refresh_enabled: bool | None = None,
) -> str:
    """Render a lightweight settings/overview page from current desktop state."""
    session = selected_session_detail or {}
    provider_count = len(list((provider_payload or {}).get("items") or []))
    registry_provider_count = len(list((registry_payload or {}).get("items") or []))
    catalog_items = len(list((model_catalog or {}).get("items") or []))
    workspace = str(getattr(connection, "workspace", "") or "")
    requested_workspace = workspace_summary or {}
    resolved_active_workspace = active_workspace or {}
    runtime_summary = workspace_runtime_summary or {}
    runtime_policy = runtime_summary.get("runtime_policy") if isinstance(runtime_summary, dict) else {}
    runtime_details = runtime_summary.get("runtime") if isinstance(runtime_summary, dict) else {}
    lines = [
        "Desktop Overview:",
        f"- gateway: {_compact_text(getattr(connection, 'base_url', None)) or '-'}",
        f"- workspace: {_compact_text(workspace) or '-'}",
        f"- mode: {'managed' if bool(getattr(connection, 'managed', False)) else 'external'}",
        f"- auto_refresh: {'enabled' if bool(auto_refresh_enabled if auto_refresh_enabled is not None else True) else 'paused'}",
        f"- refresh_interval_ms: {int(refresh_interval_ms or 0)}",
        "",
        "Current Session:",
        f"- title: {_compact_text(session.get('title')) or '-'}",
        f"- session_id: {_compact_text(session.get('session_id')) or '-'}",
        f"- selected_provider: {_compact_text(session.get('selected_provider_id')) or '-'}",
        f"- selected_model: {_compact_text(session.get('selected_model_id')) or '-'}",
        f"- pending_approvals: {len(list(session.get('pending_approvals') or []))}",
        "",
        "Workspace:",
        f"- active_title: {_compact_text(resolved_active_workspace.get('title')) or '-'}",
        f"- active_workspace: {_compact_text(resolved_active_workspace.get('workspace_dir')) or '-'}",
        f"- requested_workspace: {_compact_text(requested_workspace.get('workspace_dir')) or _compact_text(workspace) or '-'}",
        f"- known_workspaces: {len(list(workspace_list or []))}",
        f"- workspace_sessions: {requested_workspace.get('session_count') if requested_workspace.get('session_count') is not None else '-'}",
        f"- shared_workspace_sessions: {requested_workspace.get('shared_session_count') if requested_workspace.get('shared_session_count') is not None else '-'}",
        f"- runtime_mode: {_compact_text(runtime_policy.get('mode')) or _compact_text(runtime_details.get('mode')) or '-'}",
        f"- runtime_scope: {_compact_text(runtime_details.get('scope')) or '-'}",
        "",
        "Model Supply:",
        f"- runtime_catalog_items: {catalog_items}",
        f"- provider_count: {provider_count}",
        f"- registry_provider_count: {registry_provider_count}",
        f"- feature_bindings: {len(list((feature_bindings or {}).get('items') or []))}",
        "",
        format_feature_bindings_text(feature_bindings),
    ]
    return "\n".join(lines)


def collect_memory_file_entries(
    summary: dict[str, Any] | None,
    *,
    workspace_dir: str | None = None,
) -> list[dict[str, str]]:
    """Flatten memory summary into editor-friendly file entries."""
    entries: list[dict[str, str]] = []
    long_term_file = _compact_text((summary or {}).get("long_term_file"))
    if long_term_file:
        entries.append(
            {
                "label": f"Long-Term | {Path(long_term_file).name}",
                "path": long_term_file,
                "kind": "long_term",
            }
        )

    daily_dir = Path(
        _compact_text((summary or {}).get("daily_dir"))
        or str(Path(workspace_dir or ".") / "memory")
    )
    for filename in list((summary or {}).get("daily_files") or []):
        normalized = _compact_text(filename)
        if not normalized:
            continue
        entries.append(
            {
                "label": f"Daily | {normalized}",
                "path": str((daily_dir / normalized).resolve()),
                "kind": "daily",
            }
        )
    return entries


def format_memory_summary_text(
    summary: dict[str, Any] | None,
    *,
    search_payload: dict[str, Any] | None = None,
    selected_path: str | None = None,
) -> str:
    """Render workspace memory overview for the Memory page."""
    payload = summary or {}
    categories = ", ".join(str(item) for item in list(payload.get("categories") or [])) or "-"
    search = search_payload or {}
    lines = [
        "Memory Overview:",
        f"- workspace: {_compact_text(payload.get('workspace_dir')) or '-'}",
        f"- memory_root: {_compact_text(payload.get('memory_root')) or '-'}",
        f"- long_term_file: {_compact_text(payload.get('long_term_file')) or '-'}",
        f"- daily_dir: {_compact_text(payload.get('daily_dir')) or '-'}",
        f"- daily_files: {len(list(payload.get('daily_files') or []))}",
        f"- notes_count: {payload.get('notes_count') if payload.get('notes_count') is not None else '-'}",
        f"- categories: {categories}",
    ]
    if search:
        lines.extend(
            [
                "",
                "Search:",
                f"- query: {_compact_text(search.get('query')) or '-'}",
                f"- total: {search.get('total') if search.get('total') is not None else 0}",
            ]
        )
    if _compact_text(selected_path):
        lines.extend(["", f"Selected File: {_compact_text(selected_path)}"])
    return "\n".join(lines)


def create_desktop_main_window(
    *,
    qtwidgets: Any,
    qtcore: Any,
    transport_binding: DesktopGatewayTransportBinding,
    supervisor: DesktopGatewaySupervisor,
    connection: DesktopGatewayConnection,
    reconnect_handler: Callable[[], DesktopGatewayConnection],
) -> Any:
    """Build the DesktopUI main window without importing Qt at module import time."""

    from PySide6 import QtGui as qtgui

    class ContextUsageRing(qtwidgets.QWidget):
        """Compact ring indicator for composer context usage."""

        def __init__(self) -> None:
            super().__init__()
            self._ratio = 0.0
            self._text = "--"
            self._tone = "muted"
            self.setFixedSize(36, 36)
            self.setToolTip("Context usage unavailable.")

        def set_metrics(
            self,
            *,
            ratio: float,
            text: str,
            tone: str,
            tooltip: str,
        ) -> None:
            self._ratio = max(0.0, min(1.0, float(ratio)))
            self._text = _compact_text(text) or "--"
            self._tone = _compact_text(tone).lower() or "muted"
            self.setToolTip(_compact_text(tooltip) or "Context usage unavailable.")
            self.update()

        def _colors(self) -> tuple[Any, Any, Any]:
            track = qtgui.QColor("#d8e0ea")
            text = qtgui.QColor("#5e6d81")
            palette = {
                "low": qtgui.QColor("#2f6ecb"),
                "medium": qtgui.QColor("#c9831d"),
                "high": qtgui.QColor("#c34f4f"),
                "muted": qtgui.QColor("#aab6c5"),
            }
            return track, palette.get(self._tone, palette["muted"]), text

        def paintEvent(self, event: Any) -> None:
            _ = event
            painter = qtgui.QPainter(self)
            painter.setRenderHint(qtgui.QPainter.RenderHint.Antialiasing, True)

            track_color, fill_color, text_color = self._colors()
            ring_rect = self.rect().adjusted(4, 4, -4, -4)

            track_pen = qtgui.QPen(track_color, 3.25)
            track_pen.setCapStyle(qtcore.Qt.PenCapStyle.RoundCap)
            painter.setPen(track_pen)
            painter.setBrush(qtcore.Qt.BrushStyle.NoBrush)
            painter.drawEllipse(ring_rect)

            if self._ratio > 0.0:
                fill_pen = qtgui.QPen(fill_color, 3.25)
                fill_pen.setCapStyle(qtcore.Qt.PenCapStyle.RoundCap)
                painter.setPen(fill_pen)
                painter.drawArc(ring_rect, 90 * 16, int(-360 * 16 * self._ratio))

            font = painter.font()
            font.setPointSize(8)
            font.setBold(True)
            painter.setFont(font)
            painter.setPen(text_color)
            painter.drawText(
                self.rect(),
                int(qtcore.Qt.AlignmentFlag.AlignCenter),
                self._text,
            )

    class ChatStreamWorker(qtcore.QObject):
        chunk_received = qtcore.Signal(str)
        activity_received = qtcore.Signal(object)
        approval_requested = qtcore.Signal(object)
        approval_resolved = qtcore.Signal()
        done_received = qtcore.Signal(object)
        error_received = qtcore.Signal(str)
        finished = qtcore.Signal()

        def __init__(
            self,
            *,
            chat_client: RemoteChatServicePort,
            request: MainAgentChatRequest,
        ) -> None:
            super().__init__()
            self._chat_client = chat_client
            self._request = request

        @qtcore.Slot()
        def run(self) -> None:
            try:
                asyncio.run(self._consume())
            except Exception as exc:
                self.error_received.emit(RemoteStreamErrorService.exception_detail(exc))
            finally:
                self.finished.emit()

        async def _consume(self) -> None:
            remote_thinking_text = ""
            remote_thinking_dirty = False

            def _flush_remote_thinking() -> None:
                nonlocal remote_thinking_dirty
                if not remote_thinking_dirty:
                    return
                activity = desktop_stream_activity_payload(
                    "thinking_delta",
                    {},
                    thinking_text=remote_thinking_text,
                )
                if activity is not None:
                    self.activity_received.emit(activity)
                remote_thinking_dirty = False

            async for event_type, payload in self._chat_client.stream_chat_events(self._request):
                event = _compact_text(event_type).lower() or "message"
                data = payload if isinstance(payload, dict) else {}
                if event == "thinking_delta":
                    chunk = str(data.get("chunk") or "")
                    if chunk:
                        remote_thinking_text += chunk
                        remote_thinking_dirty = True
                    continue
                if remote_thinking_dirty:
                    _flush_remote_thinking()
                if event == "delta":
                    chunk = str(data.get("chunk") or "")
                    if chunk:
                        self.chunk_received.emit(chunk)
                    continue
                activity = desktop_stream_activity_payload(event, data)
                if activity is not None:
                    self.activity_received.emit(activity)
                if event == "approval_requested":
                    self.approval_requested.emit(data)
                    continue
                if event == "approval_resolved":
                    self.approval_resolved.emit()
                    continue
                if event in {"activity", "status"} or event.startswith("delegation."):
                    continue
                if event == "error":
                    detail = RemoteStreamErrorService.payload_detail(data)
                    raise RuntimeError(detail)
                if event == "done":
                    self.done_received.emit(data)
                    return

    class DesktopMainWindow(qtwidgets.QMainWindow):
        REFRESH_INTERVAL_MS = 5000

        def __init__(self) -> None:
            super().__init__()
            self._transport_binding = transport_binding
            self._chat_client = transport_binding.chat_client
            self._run_client = transport_binding.run_client
            self._session_client = transport_binding.session_client
            self._system_client = transport_binding.system_client
            self._memory_client = transport_binding.memory_client
            self._model_client = transport_binding.model_client
            self._provider_client = transport_binding.provider_client
            self._workspace_client = transport_binding.workspace_client
            self._supervisor = supervisor
            self._connection = connection
            self._reconnect_handler = reconnect_handler
            self._session_ids_by_row: list[str] = []
            self._workspace_summary_payload: dict[str, Any] = {}
            self._active_workspace_summary_payload: dict[str, Any] = {}
            self._workspace_runtime_payload: dict[str, Any] = {}
            self._workspace_list_payload: list[dict[str, Any]] = []
            self._model_catalog: dict[str, Any] = {}
            self._selected_session_detail: dict[str, Any] = {}
            self._selected_run_summary: dict[str, Any] = {}
            self._conversation_messages: list[dict[str, Any]] = []
            self._activity_entries: list[dict[str, Any]] = []
            self._send_thread: Any = None
            self._send_worker: Any = None
            self._send_busy = False
            self._stream_target_session_id: str | None = None
            self._model_options: list[dict[str, str]] = []
            self._approval_dialog_token: str | None = None
            self._page_specs = desktop_page_specs()
            self._page_index_by_id: dict[str, int] = {}
            self._ops_registry_payload: dict[str, Any] = {}
            self._ops_provider_payload: dict[str, Any] = {}
            self._feature_bindings: dict[str, Any] = {}
            self._registry_model_entries: list[dict[str, str]] = []
            self._registry_model_keys_by_row: list[str] = []
            self._provider_entries: list[dict[str, str]] = []
            self._provider_ids_by_row: list[str] = []
            self._provider_draft_model_entries: list[dict[str, str]] = []
            self._provider_draft_model_ids_by_row: list[str] = []
            self._provider_health_cache: dict[str, dict[str, Any]] = {}
            self._provider_form_existing_id: str | None = None
            self._provider_form_loading = False
            self._provider_form_dirty = False
            self._provider_active_preset_id: str | None = None
            self._provider_validation_payload: dict[str, Any] = {}
            self._memory_summary_payload: dict[str, Any] = {}
            self._memory_search_payload: dict[str, Any] = {}
            self._memory_file_entries: list[dict[str, str]] = []
            self._memory_file_paths_by_row: list[str] = []
            self._memory_search_paths_by_row: list[str] = []
            self._selected_memory_file_path: str | None = None
            self._memory_editor_loading = False
            self._refresh_interval_ms = self.REFRESH_INTERVAL_MS
            self._auto_refresh_enabled = True
            self._shell_outer_margin = 0
            self._window_resize_margin = 8
            self._desktop_central: Any = None
            self._root_layout: Any = None
            self._window_surface: Any = None
            self._top_bar: Any = None
            self._title_drag_bar: Any = None
            self._nav_frame: Any = None
            self._page_nav_buttons: dict[str, Any] = {}
            self._window_minimize_button: Any = None
            self._window_maximize_button: Any = None
            self._window_close_button: Any = None
            self._composer: Any = None
            self._context_usage_ring: Any = None
            self._interrupt_turn_button: Any = None
            self._resume_turn_button: Any = None
            self._stop_turn_button: Any = None
            self._runtime_stat_cards: list[Any] = []
            self._top_action_buttons: list[Any] = []
            self._runtime_stats_panel: Any = None
            self._runtime_stats_layout: Any = None
            self._top_actions_panel: Any = None
            self._top_actions_layout: Any = None
            self._initial_geometry_applied = False
            self._title_drag_pending = False
            self._title_drag_press_global: Any = None
            self._desktop_status_bar = qtwidgets.QStatusBar()
            self._desktop_status_bar.setObjectName("desktopStatusBar")
            self._desktop_status_bar.setSizeGripEnabled(False)

            self.setWindowTitle("Mini-Agent DesktopUI")
            self.setWindowFlags(self.windowFlags() | qtcore.Qt.WindowType.FramelessWindowHint)
            self.setAttribute(qtcore.Qt.WidgetAttribute.WA_TranslucentBackground, True)
            self.setMinimumSize(720, 520)
            self.resize(1560, 940)
            self._apply_chrome_style()

            central = qtwidgets.QWidget()
            central.setObjectName("desktopCentral")
            central.setMouseTracking(True)
            root_layout = qtwidgets.QVBoxLayout(central)
            root_layout.setContentsMargins(
                self._shell_outer_margin,
                self._shell_outer_margin,
                self._shell_outer_margin,
                self._shell_outer_margin,
            )
            root_layout.setSpacing(0)
            root_layout.addWidget(self._build_unified_window_surface(), 1)
            self._desktop_central = central
            self._root_layout = root_layout

            self.setCentralWidget(central)
            self._desktop_central.installEventFilter(self)
            self.statusBar().showMessage("DesktopUI attached.")

            self._render_conversation()
            self._render_activity()
            self._models_view.setPlainText("Loading model catalog...")
            self._context_view.setPlainText("No session selected.")
            self._refresh_chat_workspace_summary()
            self._model_registry_detail_view.setPlainText(
                "Select a model to inspect role, capability facts, and feature bindings."
            )
            self._feature_bindings_view.setPlainText("Loading feature bindings...")
            self._provider_detail_view.setPlainText(
                "Select a provider to inspect configuration and health."
            )
            self._settings_view.setPlainText("Loading desktop overview...")
            self._sessions_overview_detail_view.setPlainText("No session selected.")
            self._sessions_transcript_view.setHtml(render_conversation_html([]))
            self._memory_summary_view.setPlainText("Loading memory summary...")
            self._memory_editor.setPlainText("")
            self._memory_file_path_value.setText("No file selected")
            self._select_page_by_id("chat")
            self._append_activity(self._connection.note or "DesktopUI bootstrapped.", kind="status")
            self._append_managed_gateway_excerpt("Managed gateway log tail")
            self.refresh_snapshot()

            self._timer = qtcore.QTimer(self)
            self._timer.setInterval(self._refresh_interval_ms)
            self._timer.timeout.connect(self.refresh_snapshot)
            self._timer.start()
            self._refresh_session_action_state()
            self._refresh_run_action_state()
            self._refresh_registry_action_state()
            self._refresh_provider_action_state()
            self._sync_settings_controls()

            qtcore.QTimer.singleShot(0, self._apply_initial_shell_sizes)
            qtcore.QTimer.singleShot(0, self._sync_window_chrome)

        def _apply_chrome_style(self) -> None:
            self.setStyleSheet(
                """
                QMainWindow, QWidget {
                    background: transparent;
                    color: #182537;
                    font-family: "Segoe UI Variable", "SF Pro Text", "Microsoft YaHei UI";
                    font-size: 13px;
                }
                QWidget#desktopCentral {
                    background: qlineargradient(
                        x1: 0, y1: 0, x2: 1, y2: 1,
                        stop: 0 #edf1f6,
                        stop: 0.52 #e7ecf3,
                        stop: 1 #dde4ee
                    );
                }
                QFrame#desktopWindowSurface {
                    background: qlineargradient(
                        x1: 0, y1: 0, x2: 1, y2: 1,
                        stop: 0 #fbfcfe,
                        stop: 0.52 #f6f8fb,
                        stop: 1 #eef2f7
                    );
                    border: none;
                    border-radius: 24px;
                }
                QFrame#desktopWindowSurface[shellMaximized="true"] {
                    border-radius: 0;
                }
                QFrame#desktopTopBar {
                    background: rgba(248, 250, 252, 0.96);
                    border-bottom: 1px solid #dbe1e9;
                    border-top-left-radius: 24px;
                    border-top-right-radius: 24px;
                }
                QFrame#desktopTopBar[shellMaximized="true"] {
                    border-top-left-radius: 0;
                    border-top-right-radius: 0;
                }
                QWidget#desktopTitleDragBar {
                    background: transparent;
                }
                QWidget#desktopTopUtilityPanel {
                    background: transparent;
                }
                QWidget#desktopTopActionsPanel {
                    background: rgba(244, 247, 251, 0.96);
                    border: 1px solid #dde4ec;
                    border-radius: 16px;
                }
                QWidget#desktopTopPageNavPanel {
                    background: transparent;
                }
                QWidget#desktopTopMetaPanel {
                    background: transparent;
                }
                QSplitter#desktopBody {
                    background: transparent;
                    border: none;
                }
                QFrame#desktopWorkspaceShell {
                    background: transparent;
                    border: none;
                }
                QFrame#desktopPageHeader {
                    background: transparent;
                    border: none;
                    border-radius: 0;
                }
                QFrame#desktopWorkspaceCard {
                    background: rgba(255, 255, 255, 0.92);
                    border: 1px solid #dde4ec;
                    border-radius: 20px;
                }
                QFrame#desktopWorkspaceHero {
                    background: qlineargradient(
                        x1: 0, y1: 0, x2: 1, y2: 1,
                        stop: 0 rgba(255, 255, 255, 0.98),
                        stop: 1 rgba(241, 247, 255, 0.98)
                    );
                    border: 1px solid #d9e4f0;
                    border-radius: 22px;
                }
                QFrame#desktopSurfaceHeader {
                    background: transparent;
                    border: none;
                }
                QFrame#desktopStatCard {
                    background: rgba(255, 255, 255, 0.82);
                    border: 1px solid #d8e0ea;
                    border-radius: 13px;
                }
                QLabel#desktopStatLabel {
                    color: #728197;
                    font-size: 10px;
                    font-weight: 600;
                    text-transform: uppercase;
                }
                QLabel#desktopStatValue {
                    color: #17263a;
                    font-size: 13px;
                    font-weight: 600;
                }
                QLabel#desktopTopMetaLabel {
                    color: #7c8899;
                    font-size: 11px;
                    font-weight: 600;
                }
                QLabel#desktopTopMetaValue {
                    color: #17263a;
                    font-size: 12px;
                    font-weight: 600;
                }
                QLabel#desktopTopMetaValue[metaRole="workspace"] {
                    color: #304055;
                    font-weight: 500;
                }
                QLabel#desktopBrand {
                    font-size: 20px;
                    font-weight: 700;
                    color: #111c2b;
                }
                QLabel#desktopBrandSubtitle {
                    color: #6b7788;
                    font-size: 12px;
                }
                QLabel#desktopTopNote {
                    color: #5d6a7c;
                    font-size: 12px;
                }
                QLabel#desktopPageTitle {
                    font-size: 20px;
                    font-weight: 700;
                    color: #152233;
                }
                QLabel#desktopPageDescription {
                    color: #697788;
                    font-size: 12px;
                }
                QLabel#desktopSurfaceTitle {
                    color: #152336;
                    font-size: 15px;
                    font-weight: 700;
                }
                QLabel#desktopHeroEyebrow {
                    color: #7b8aa0;
                    font-size: 10px;
                    font-weight: 700;
                    letter-spacing: 0.12em;
                }
                QLabel#desktopHeroTitle {
                    color: #102033;
                    font-size: 24px;
                    font-weight: 700;
                }
                QLabel#desktopHeroMeta {
                    color: #607084;
                    font-size: 12px;
                }
                QLabel#desktopInfoBadge {
                    background: rgba(248, 251, 255, 0.96);
                    color: #506074;
                    border: 1px solid #d9e0e8;
                    border-radius: 12px;
                    min-height: 24px;
                    max-height: 24px;
                    padding: 2px 12px;
                    font-size: 11px;
                    font-weight: 600;
                }
                QLabel#desktopInfoBadge[badgeTone="accent"] {
                    background: rgba(232, 242, 255, 0.98);
                    color: #1f5bb4;
                    border-color: #cfe0fb;
                }
                QLabel#desktopInfoBadge[badgeTone="success"] {
                    background: rgba(235, 249, 241, 0.98);
                    color: #2d7a56;
                    border-color: #d4ebdd;
                }
                QLabel#desktopInfoBadge[badgeTone="warning"] {
                    background: rgba(255, 247, 232, 0.98);
                    color: #8a6131;
                    border-color: #f0dfbd;
                }
                QPushButton#desktopPagePill {
                    background: transparent;
                    color: #5c6b7d;
                    border: 1px solid transparent;
                    border-radius: 12px;
                    padding: 6px 11px;
                    font-weight: 600;
                }
                QPushButton#desktopPagePill:hover {
                    background: rgba(255, 255, 255, 0.76);
                    color: #1d2c40;
                }
                QPushButton#desktopPagePill[navActive="true"] {
                    background: rgba(255, 255, 255, 0.98);
                    color: #16253b;
                    border-color: #d8e0e9;
                }
                QGroupBox {
                    font-weight: 600;
                    border: 1px solid #d9e0e9;
                    border-radius: 16px;
                    margin-top: 10px;
                    padding-top: 10px;
                    background: rgba(255, 255, 255, 0.93);
                }
                QGroupBox::title {
                    subcontrol-origin: margin;
                    left: 12px;
                    padding: 0 6px;
                    color: #243247;
                }
                QGroupBox#desktopPanel {
                    margin-top: 12px;
                    padding-top: 12px;
                    border-radius: 18px;
                }
                QGroupBox#desktopPanel::title {
                    left: 14px;
                }
                QWidget#desktopPanelTools, QFrame#desktopPanelTools {
                    background: rgba(245, 248, 251, 0.96);
                    border: 1px solid #dde4ec;
                    border-radius: 14px;
                }
                QFrame#desktopRailHeaderBar {
                    background: rgba(247, 249, 252, 0.98);
                    border: 1px solid #e0e7ef;
                    border-radius: 15px;
                }
                QFrame#desktopComposerShell {
                    background: qlineargradient(
                        x1: 0, y1: 0, x2: 1, y2: 1,
                        stop: 0 rgba(252, 253, 255, 0.99),
                        stop: 1 rgba(245, 248, 252, 0.99)
                    );
                    border: 1px solid #dce4ed;
                    border-radius: 20px;
                }
                QFrame#desktopComposerControlsFrame {
                    background: rgba(255, 255, 255, 0.72);
                    border: 1px solid #e1e7ef;
                    border-radius: 14px;
                }
                QLabel#desktopInlineSectionLabel {
                    color: #738195;
                    font-size: 10px;
                    font-weight: 700;
                    text-transform: uppercase;
                }
                QPushButton {
                    background: rgba(246, 248, 251, 0.96);
                    color: #1a2738;
                    border: 1px solid #d7dfe8;
                    border-radius: 12px;
                    padding: 7px 14px;
                }
                QPushButton:hover {
                    background: #edf2f7;
                }
                QPushButton:pressed {
                    background: #e5ebf3;
                }
                QPushButton:disabled {
                    color: #8b98aa;
                    background: #f2f5f9;
                    border-color: #e0e5ec;
                }
                QPushButton#desktopTopAction {
                    background: transparent;
                    border: none;
                    border-radius: 12px;
                    padding: 6px 10px;
                    color: #566476;
                    font-size: 12px;
                    font-weight: 600;
                    text-align: left;
                }
                QPushButton#desktopTopAction:hover {
                    background: rgba(255, 255, 255, 0.78);
                    color: #1c2b3f;
                }
                QPushButton#desktopTopAction:pressed {
                    background: rgba(228, 234, 242, 0.92);
                }
                QPushButton[tone="ghost"] {
                    background: transparent;
                    border: none;
                    color: #5c6a7c;
                    border-radius: 10px;
                    padding: 7px 10px;
                    font-weight: 600;
                }
                QPushButton[tone="ghost"]:hover {
                    background: rgba(255, 255, 255, 0.86);
                    color: #1e2c40;
                }
                QPushButton[tone="ghost"]:pressed {
                    background: rgba(228, 234, 242, 0.92);
                }
                QPushButton[compactAction="true"] {
                    border-radius: 10px;
                    padding: 5px 10px;
                    font-size: 11px;
                }
                QPushButton[tone="primary"] {
                    background: #215db8;
                    color: #ffffff;
                    border: 1px solid #1f57a8;
                    border-radius: 11px;
                    padding: 7px 12px;
                    font-weight: 700;
                }
                QPushButton[tone="primary"]:hover {
                    background: #1f56aa;
                    border-color: #1b4e9a;
                }
                QPushButton[tone="primary"]:pressed {
                    background: #1a4a91;
                }
                QPushButton[tone="danger"] {
                    background: #fff4f4;
                    color: #a34a4a;
                    border: 1px solid #efcfcf;
                    border-radius: 11px;
                    padding: 7px 12px;
                    font-weight: 700;
                }
                QPushButton[tone="danger"]:hover {
                    background: #fdeaea;
                    border-color: #e8bcbc;
                }
                QToolButton#desktopWindowControlMinimize,
                QToolButton#desktopWindowControlMaximize,
                QToolButton#desktopWindowControlClose {
                    color: #4d5d70;
                    border: 1px solid #d5dce6;
                    border-radius: 12px;
                    padding: 0;
                    font-size: 13px;
                    font-weight: 700;
                    background: rgba(248, 250, 252, 0.94);
                }
                QToolButton#desktopWindowControlMinimize:hover,
                QToolButton#desktopWindowControlMaximize:hover,
                QToolButton#desktopWindowControlClose:hover {
                    border-color: #c3ccd8;
                    background: rgba(238, 242, 247, 0.98);
                }
                QToolButton#desktopWindowControlMinimize {
                    background: rgba(248, 250, 252, 0.94);
                }
                QToolButton#desktopWindowControlMaximize {
                    background: rgba(248, 250, 252, 0.94);
                }
                QToolButton#desktopWindowControlClose {
                    background: rgba(248, 250, 252, 0.94);
                }
                QToolButton#desktopWindowControlClose:hover {
                    background: rgba(253, 235, 235, 0.98);
                    border-color: #e7c7c7;
                    color: #a94442;
                }
                QListWidget, QTextBrowser, QPlainTextEdit, QLineEdit, QComboBox, QSpinBox {
                    background: rgba(253, 254, 255, 0.96);
                    border: 1px solid #d8e0e9;
                    border-radius: 12px;
                    padding: 6px 8px;
                    selection-background-color: #dfe8f6;
                    selection-color: #152336;
                }
                QComboBox::drop-down {
                    border: none;
                    width: 24px;
                }
                QLineEdit[compactField="true"],
                QComboBox[compactField="true"],
                QSpinBox[compactField="true"] {
                    background: rgba(255, 255, 255, 0.78);
                    border: 1px solid #d7dfe8;
                    border-radius: 10px;
                    padding: 5px 8px;
                    min-height: 30px;
                }
                QListWidget#desktopListSurface {
                    background: rgba(250, 251, 253, 0.98);
                    border: 1px solid #d9e0e9;
                    border-radius: 14px;
                    padding: 5px;
                }
                QListWidget#desktopListSurface::item {
                    border: 1px solid transparent;
                    border-radius: 11px;
                    padding: 7px 9px;
                    margin: 2px 0;
                }
                QListWidget#desktopListSurface[denseList="true"]::item {
                    padding: 5px 7px;
                    margin: 1px 0;
                }
                QListWidget#desktopListSurface::item:hover {
                    background: rgba(255, 255, 255, 0.86);
                }
                QListWidget#desktopListSurface::item:selected {
                    background: rgba(234, 240, 248, 0.98);
                    border-color: #d2dae5;
                    color: #182538;
                }
                QPlainTextEdit#desktopReadSurface,
                QTextBrowser#desktopReadSurface {
                    background: rgba(252, 253, 255, 0.99);
                    border: 1px solid #dfe5ed;
                    border-radius: 16px;
                    padding: 12px 14px;
                }
                QPlainTextEdit#desktopComposeSurface {
                    background: transparent;
                    border: none;
                    padding: 2px 0;
                }
                QTabWidget#desktopAuxTabs::pane {
                    background: rgba(255, 255, 255, 0.95);
                    border: 1px solid #dde4ec;
                    border-radius: 16px;
                    top: -1px;
                }
                QTabWidget#desktopAuxTabs QTabBar::tab {
                    background: transparent;
                    color: #6a788b;
                    border: 1px solid transparent;
                    border-radius: 10px;
                    padding: 5px 9px;
                    margin-right: 3px;
                    font-weight: 600;
                }
                QTabWidget#desktopAuxTabs QTabBar::tab:selected {
                    background: rgba(255, 255, 255, 0.98);
                    color: #1a2940;
                    border-color: #d8e0e9;
                }
                QTabWidget#desktopAuxTabs QTabBar::tab:hover {
                    background: rgba(244, 247, 251, 0.98);
                    color: #233349;
                }
                QSplitter::handle {
                    background: rgba(212, 220, 230, 0.95);
                    width: 6px;
                    height: 6px;
                    margin: 4px;
                    border-radius: 3px;
                }
                QStatusBar#desktopStatusBar {
                    background: rgba(248, 249, 251, 0.94);
                    color: #5c6b7d;
                    border-top: 1px solid #d9dfe7;
                    border-bottom-left-radius: 24px;
                    border-bottom-right-radius: 24px;
                }
                QStatusBar#desktopStatusBar[shellMaximized="true"] {
                    border-bottom-left-radius: 0;
                    border-bottom-right-radius: 0;
                }
                """
            )

        def _build_top_page_nav(self) -> Any:
            panel = qtwidgets.QWidget()
            panel.setObjectName("desktopTopPageNavPanel")
            layout = qtwidgets.QHBoxLayout(panel)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(6)
            self._page_nav_buttons = {}
            for page in self._page_specs:
                button = qtwidgets.QPushButton(page["label"])
                button.setObjectName("desktopPagePill")
                button.setProperty("navActive", False)
                button.setCursor(qtcore.Qt.CursorShape.PointingHandCursor)
                button.setToolTip(page["description"])
                button.clicked.connect(
                    lambda checked=False, page_id=page["id"]: self._select_page_by_id(page_id)
                )
                layout.addWidget(button, 0)
                self._page_nav_buttons[page["id"]] = button
            return panel

        def _build_runtime_stat_card(self, title: str, value_label: Any) -> Any:
            card = qtwidgets.QFrame()
            card.setObjectName("desktopStatCard")
            card.setSizePolicy(
                qtwidgets.QSizePolicy.Policy.Expanding,
                qtwidgets.QSizePolicy.Policy.Preferred,
            )
            layout = qtwidgets.QHBoxLayout(card)
            layout.setContentsMargins(12, 8, 12, 8)
            layout.setSpacing(8)
            label = qtwidgets.QLabel(title)
            label.setObjectName("desktopStatLabel")
            value_label.setObjectName("desktopStatValue")
            value_label.setWordWrap(False)
            value_label.setMinimumWidth(0)
            value_label.setSizePolicy(
                qtwidgets.QSizePolicy.Policy.Ignored,
                qtwidgets.QSizePolicy.Policy.Preferred,
            )
            layout.addWidget(label)
            layout.addSpacing(2)
            layout.addWidget(value_label)
            return card

        def _build_top_meta_item(self, label_text: str, value_label: Any) -> Any:
            container = qtwidgets.QWidget()
            layout = qtwidgets.QHBoxLayout(container)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(6)
            label = qtwidgets.QLabel(label_text)
            label.setObjectName("desktopTopMetaLabel")
            value_label.setObjectName("desktopTopMetaValue")
            layout.addWidget(label, 0)
            layout.addWidget(value_label, 0)
            return container

        def _build_window_control_button(
            self,
            *,
            object_name: str,
            text: str,
            tooltip: str,
            handler: Callable[[], None],
        ) -> Any:
            button = qtwidgets.QToolButton()
            button.setObjectName(object_name)
            button.setText(text)
            button.setToolTip(tooltip)
            button.setCursor(qtcore.Qt.CursorShape.PointingHandCursor)
            button.setAutoRaise(True)
            button.setFixedSize(30, 30)
            button.clicked.connect(handler)
            return button

        def _build_panel_group(self, title: str) -> Any:
            group = qtwidgets.QGroupBox(title)
            group.setObjectName("desktopPanel")
            return group

        def _build_panel_tools_frame(self, *, spacing: int = 8) -> tuple[Any, Any]:
            frame = qtwidgets.QFrame()
            frame.setObjectName("desktopPanelTools")
            layout = qtwidgets.QHBoxLayout(frame)
            layout.setContentsMargins(8, 8, 8, 8)
            layout.setSpacing(spacing)
            return frame, layout

        def _build_section_label(self, text: str) -> Any:
            label = qtwidgets.QLabel(text)
            label.setObjectName("desktopInlineSectionLabel")
            return label

        def _build_workspace_card(
            self,
            *,
            object_name: str = "desktopWorkspaceCard",
            spacing: int = 12,
        ) -> tuple[Any, Any]:
            frame = qtwidgets.QFrame()
            frame.setObjectName(object_name)
            layout = qtwidgets.QVBoxLayout(frame)
            layout.setContentsMargins(16, 16, 16, 16)
            layout.setSpacing(spacing)
            return frame, layout

        def _build_surface_header(self, title: str, description: str = "") -> Any:
            frame = qtwidgets.QFrame()
            frame.setObjectName("desktopSurfaceHeader")
            layout = qtwidgets.QVBoxLayout(frame)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(0)
            title_label = qtwidgets.QLabel(title)
            title_label.setObjectName("desktopSurfaceTitle")
            layout.addWidget(title_label)
            return frame

        def _build_info_badge(self, text: str = "", *, tone: str = "muted") -> Any:
            label = qtwidgets.QLabel(text)
            label.setAlignment(qtcore.Qt.AlignmentFlag.AlignCenter)
            label.setWordWrap(False)
            label.setSizePolicy(
                qtwidgets.QSizePolicy.Policy.Maximum,
                qtwidgets.QSizePolicy.Policy.Fixed,
            )
            self._style_info_badge(label, tone=tone)
            return label

        def _style_action_button(self, button: Any, *, tone: str = "ghost", compact: bool = False) -> Any:
            button.setProperty("tone", tone)
            button.setProperty("compactAction", bool(compact))
            style = button.style()
            if style is not None:
                style.unpolish(button)
                style.polish(button)
            return button

        def _style_info_badge(self, label: Any, *, tone: str = "muted") -> Any:
            label.setObjectName("desktopInfoBadge")
            label.setProperty("badgeTone", tone)
            style = label.style()
            if style is not None:
                style.unpolish(label)
                style.polish(label)
            return label

        def _style_page_nav_button(self, button: Any, *, active: bool) -> Any:
            button.setProperty("navActive", bool(active))
            style = button.style()
            if style is not None:
                style.unpolish(button)
                style.polish(button)
            return button

        def _style_compact_field(self, widget: Any) -> Any:
            widget.setProperty("compactField", True)
            return widget

        def _style_list_surface(self, widget: Any, *, dense: bool = False) -> Any:
            widget.setObjectName("desktopListSurface")
            widget.setProperty("denseList", bool(dense))
            if hasattr(widget, "setHorizontalScrollBarPolicy"):
                widget.setHorizontalScrollBarPolicy(qtcore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            style = widget.style()
            if style is not None:
                style.unpolish(widget)
                style.polish(widget)
            return widget

        def _style_read_surface(self, widget: Any) -> Any:
            widget.setObjectName("desktopReadSurface")
            if hasattr(widget, "setHorizontalScrollBarPolicy"):
                widget.setHorizontalScrollBarPolicy(qtcore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            if isinstance(widget, qtwidgets.QPlainTextEdit):
                widget.setLineWrapMode(qtwidgets.QPlainTextEdit.LineWrapMode.WidgetWidth)
            elif isinstance(widget, qtwidgets.QTextBrowser):
                widget.setLineWrapMode(qtwidgets.QTextEdit.LineWrapMode.WidgetWidth)
            style = widget.style()
            if style is not None:
                style.unpolish(widget)
                style.polish(widget)
            return widget

        def _build_unified_window_surface(self) -> Any:
            surface = qtwidgets.QFrame()
            surface.setObjectName("desktopWindowSurface")
            self._window_surface = surface
            layout = qtwidgets.QVBoxLayout(surface)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(0)

            top_bar = qtwidgets.QFrame()
            top_bar.setObjectName("desktopTopBar")
            self._top_bar = top_bar
            top_layout = qtwidgets.QVBoxLayout(top_bar)
            top_layout.setContentsMargins(18, 14, 18, 16)
            top_layout.setSpacing(14)

            self._title_drag_bar = qtwidgets.QFrame()
            self._title_drag_bar.setObjectName("desktopTitleDragBar")
            self._title_drag_bar.setMouseTracking(True)
            self._title_drag_bar.setCursor(qtcore.Qt.CursorShape.OpenHandCursor)
            self._title_drag_bar.installEventFilter(self)
            title_layout = qtwidgets.QHBoxLayout(self._title_drag_bar)
            title_layout.setContentsMargins(0, 0, 0, 0)
            title_layout.setSpacing(12)

            brand = qtwidgets.QLabel("Mini-Agent")
            brand.setObjectName("desktopBrand")
            subtitle = qtwidgets.QLabel("Desktop workspace")
            subtitle.setObjectName("desktopBrandSubtitle")
            self._note_value = qtwidgets.QLabel(self._connection.note or "-")
            self._note_value.setObjectName("desktopTopNote")
            self._note_value.setWordWrap(False)
            for label in (brand, subtitle, self._note_value):
                label.setAttribute(qtcore.Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
            subtitle.hide()
            self._note_value.hide()
            title_layout.addWidget(brand, 0)
            title_layout.addSpacing(8)

            self._status_value = qtwidgets.QLabel("Connecting")
            self._gateway_value = qtwidgets.QLabel(self._connection.base_url)
            self._workspace_value = qtwidgets.QLabel(str(self._connection.workspace))
            self._sessions_value = qtwidgets.QLabel("0")
            self._mode_value = qtwidgets.QLabel(self._mode_text())
            self._set_runtime_note(self._connection.note or "-")
            self._refresh_runtime_identity()
            self._new_session_button = qtwidgets.QPushButton("New Session")
            self._new_session_button.setObjectName("desktopTopAction")
            self._new_session_button.clicked.connect(self._create_session)
            self._refresh_button = qtwidgets.QPushButton("Refresh")
            self._refresh_button.setObjectName("desktopTopAction")
            self._refresh_button.clicked.connect(self.refresh_snapshot)
            self._reconnect_button = qtwidgets.QPushButton("Reconnect")
            self._reconnect_button.setObjectName("desktopTopAction")
            self._reconnect_button.clicked.connect(self._reconnect_gateway)
            self._approvals_button = qtwidgets.QPushButton("Approvals")
            self._approvals_button.setObjectName("desktopTopAction")
            self._approvals_button.clicked.connect(self._open_pending_approval_dialog)
            self._command_button = qtwidgets.QPushButton("Commands")
            self._command_button.setObjectName("desktopTopAction")
            self._command_button.clicked.connect(self._open_command_palette)
            for button in (
                self._new_session_button,
                self._refresh_button,
                self._reconnect_button,
                self._approvals_button,
                self._command_button,
            ):
                button.setSizePolicy(
                    qtwidgets.QSizePolicy.Policy.Maximum,
                    qtwidgets.QSizePolicy.Policy.Fixed,
                )
                self._style_action_button(button, tone="ghost", compact=True)
            self._style_action_button(self._new_session_button, tone="primary", compact=True)
            title_layout.addWidget(self._new_session_button, 0)
            title_layout.addWidget(self._refresh_button, 0)
            title_layout.addWidget(self._approvals_button, 0)
            title_layout.addWidget(self._command_button, 0)
            title_layout.addStretch(1)
            title_layout.addWidget(self._build_top_page_nav(), 0)

            control_layout = qtwidgets.QHBoxLayout()
            control_layout.setContentsMargins(0, 0, 0, 0)
            control_layout.setSpacing(8)
            self._window_minimize_button = self._build_window_control_button(
                object_name="desktopWindowControlMinimize",
                text="–",
                tooltip="Minimize Window",
                handler=self.showMinimized,
            )
            self._window_maximize_button = self._build_window_control_button(
                object_name="desktopWindowControlMaximize",
                text="□",
                tooltip="Maximize Window",
                handler=self._toggle_window_maximize_restore,
            )
            self._window_close_button = self._build_window_control_button(
                object_name="desktopWindowControlClose",
                text="×",
                tooltip="Close Window",
                handler=self.close,
            )
            for button in (
                self._window_minimize_button,
                self._window_maximize_button,
                self._window_close_button,
            ):
                control_layout.addWidget(button)
            title_layout.addLayout(control_layout, 0)
            self._title_drag_bar.setMinimumHeight(38)
            top_layout.addWidget(self._title_drag_bar, 0)

            self._workspace_value.setProperty("metaRole", "workspace")
            self._workspace_value.setSizePolicy(
                qtwidgets.QSizePolicy.Policy.Expanding,
                qtwidgets.QSizePolicy.Policy.Preferred,
            )
            meta_panel = qtwidgets.QWidget()
            meta_panel.setObjectName("desktopTopMetaPanel")
            meta_layout = qtwidgets.QHBoxLayout(meta_panel)
            meta_layout.setContentsMargins(0, 0, 0, 0)
            meta_layout.setSpacing(16)
            meta_layout.addWidget(self._build_top_meta_item("Status", self._status_value), 0)
            meta_layout.addWidget(self._build_top_meta_item("Sessions", self._sessions_value), 0)
            meta_layout.addWidget(self._build_top_meta_item("Workspace", self._workspace_value), 1)
            top_layout.addWidget(meta_panel, 0)

            self._runtime_stat_cards = []
            self._top_action_buttons = []
            self._runtime_stats_panel = None
            self._runtime_stats_layout = None
            self._top_actions_panel = None
            self._top_actions_layout = None
            layout.addWidget(top_bar, 0)

            layout.addWidget(self._build_workspace_shell(), 1)
            layout.addWidget(self._desktop_status_bar, 0)
            return surface

        def _apply_initial_shell_sizes(self) -> None:
            return None

        def statusBar(self) -> Any:  # noqa: N802 - Qt naming
            return self._desktop_status_bar

        def _toggle_window_maximize_restore(self) -> None:
            if self.isMaximized():
                self.showNormal()
            else:
                self.showMaximized()
            qtcore.QTimer.singleShot(0, self._sync_window_chrome)

        def _current_available_geometry(self) -> Any:
            screen = self.screen()
            if screen is None:
                app = qtwidgets.QApplication.instance()
                screen = app.primaryScreen() if app is not None else None
            return screen.availableGeometry() if screen is not None else None

        def _clear_layout_widgets(self, layout: Any) -> None:
            if layout is None:
                return
            while layout.count():
                item = layout.takeAt(0)
                child_layout = item.layout()
                if child_layout is not None:
                    self._clear_layout_widgets(child_layout)

        def _relayout_top_panel(self) -> None:
            if self._runtime_stats_layout is None or self._top_actions_layout is None:
                return
            content_width = max(int(self.width() - (self._shell_outer_margin * 2)), 1)
            if content_width >= 1560:
                stat_columns = 5
                action_columns = 5
            elif content_width >= 1320:
                stat_columns = 4
                action_columns = 4
            elif content_width >= 1120:
                stat_columns = 3
                action_columns = 3
            elif content_width >= 920:
                stat_columns = 2
                action_columns = 2
            else:
                stat_columns = 2
                action_columns = 1
            self._clear_layout_widgets(self._runtime_stats_layout)
            self._clear_layout_widgets(self._top_actions_layout)
            for index, card in enumerate(self._runtime_stat_cards):
                row = index // stat_columns
                column = index % stat_columns
                self._runtime_stats_layout.addWidget(card, row, column)
            for column in range(stat_columns):
                self._runtime_stats_layout.setColumnStretch(column, 1)
            for index, button in enumerate(self._top_action_buttons):
                row = index // action_columns
                column = index % action_columns
                self._top_actions_layout.addWidget(button, row, column)
            for column in range(action_columns):
                self._top_actions_layout.setColumnStretch(column, 1)

        def _refresh_runtime_identity(self) -> None:
            gateway_text = self._connection.base_url
            workspace_text = self._effective_workspace_dir()
            mode_text = self._mode_text()
            self._gateway_value.setText(_truncate_text(gateway_text, limit=34))
            self._gateway_value.setToolTip(gateway_text)
            self._workspace_value.setText(workspace_text)
            workspace_tooltip_lines = [workspace_text]
            active_title = _compact_text(self._active_workspace_summary_payload.get("title"))
            if active_title:
                workspace_tooltip_lines.insert(0, active_title)
            runtime_mode = _compact_text(
                (self._workspace_runtime_payload.get("runtime_policy") or {}).get("mode")
            ) or _compact_text((self._workspace_runtime_payload.get("runtime") or {}).get("mode"))
            runtime_scope = _compact_text((self._workspace_runtime_payload.get("runtime") or {}).get("scope"))
            runtime_hint = " / ".join(part for part in (runtime_mode, runtime_scope) if part)
            if runtime_hint:
                workspace_tooltip_lines.append(runtime_hint)
            self._workspace_value.setToolTip("\n".join(line for line in workspace_tooltip_lines if line))
            self._mode_value.setText(_truncate_text(mode_text, limit=18))
            self._mode_value.setToolTip(mode_text)

        def _requested_workspace_id(self) -> str:
            return str(self._connection.workspace)

        def _effective_workspace_dir(self) -> str:
            for payload in (
                self._workspace_summary_payload,
                self._active_workspace_summary_payload,
                self._workspace_runtime_payload,
            ):
                raw_workspace = _compact_text(payload.get("workspace_dir"))
                if raw_workspace:
                    return raw_workspace
            return str(self._connection.workspace)

        def _refresh_workspace_snapshot(self) -> None:
            requested_workspace = self._requested_workspace_id()
            try:
                self._workspace_list_payload = surface_payload_list_from_dtos(
                    self._workspace_client.list_workspaces_sync()
                )
            except Exception:
                pass

            try:
                self._workspace_summary_payload = surface_payload_from_dto(
                    self._workspace_client.get_workspace_sync(requested_workspace)
                )
            except Exception:
                pass

            try:
                self._active_workspace_summary_payload = surface_payload_from_dto(
                    self._workspace_client.get_active_workspace_sync()
                )
            except Exception:
                pass

            runtime_workspace_id = (
                _compact_text(self._workspace_summary_payload.get("workspace_id"))
                or _compact_text(self._workspace_summary_payload.get("workspace_dir"))
                or _compact_text(self._active_workspace_summary_payload.get("workspace_id"))
                or _compact_text(self._active_workspace_summary_payload.get("workspace_dir"))
                or requested_workspace
            )
            try:
                self._workspace_runtime_payload = surface_payload_from_dto(
                    self._workspace_client.get_workspace_runtime_summary_sync(
                        workspace_id=runtime_workspace_id
                    )
                )
            except Exception:
                pass
            self._refresh_runtime_identity()

        def _refresh_chat_workspace_summary(self) -> None:
            if not hasattr(self, "_chat_session_title_label"):
                return
            detail = self._selected_session_detail or {}
            session_title = _compact_text(detail.get("title")) or "New chat"
            session_id = _compact_text(detail.get("session_id"))
            provider_id = _compact_text(detail.get("selected_provider_id"))
            model_id = _compact_text(detail.get("selected_model_id"))
            busy = self._send_busy or bool(detail.get("busy"))
            shared = bool(detail.get("shared"))

            self._chat_session_title_label.setText(session_title)
            self._chat_session_title_label.setToolTip(session_id or session_title)

            session_count = len(self._session_ids_by_row)
            self._chat_session_count_badge.setText(f"{session_count} chats")
            self._style_info_badge(self._chat_session_count_badge, tone="accent")

            selection_text = "Selected" if detail else "No selection"
            self._chat_selection_badge.setText(selection_text)
            self._style_info_badge(
                self._chat_selection_badge,
                tone="accent" if detail else "muted",
            )

            self._chat_visibility_badge.setText("Shared" if shared else "Private")
            self._style_info_badge(
                self._chat_visibility_badge,
                tone="accent" if shared else "muted",
            )

            state_badge = resolve_desktop_run_state_badge(
                detail,
                self._selected_run_summary,
                send_busy=self._send_busy,
            )
            self._chat_state_badge.setText(state_badge["text"])
            self._style_info_badge(
                self._chat_state_badge,
                tone=state_badge["tone"],
            )

            runtime_text = model_id or "Model not set"
            self._chat_model_badge.setText(runtime_text)
            self._chat_model_badge.setToolTip(
                f"{provider_id or 'provider?'} / {model_id or 'model?'}"
                if provider_id or model_id
                else runtime_text
            )
            self._style_info_badge(
                self._chat_model_badge,
                tone="accent" if model_id else "muted",
            )
            self._refresh_context_usage_indicator()

        def _selected_runtime_model_option(self) -> dict[str, str]:
            selected_provider = _compact_text(self._selected_session_detail.get("selected_provider_id"))
            selected_model = _compact_text(self._selected_session_detail.get("selected_model_id"))
            if not selected_provider or not selected_model:
                return {}
            for option in self._model_options:
                if (
                    _compact_text(option.get("provider_id")) == selected_provider
                    and _compact_text(option.get("model_id")) == selected_model
                ):
                    return option
            return {}

        def _refresh_context_usage_indicator(self) -> None:
            if self._context_usage_ring is None:
                return
            detail = self._selected_session_detail or {}
            stats = resolve_desktop_context_usage_stats(detail, self._selected_runtime_model_option())
            if not detail:
                tooltip = "Context usage unavailable. Select a chat to view the active session budget."
            else:
                usage_source_text = "reported tokens" if stats["usage_source"] == "reported" else "estimated from transcript"
                limit_source_text = {
                    "token_limit": "runtime token limit",
                    "selected_token_limit": "selected model token limit",
                    "selected_learned_token_limit": "selected learned token limit",
                    "selected_context_window": "selected context window",
                    "model_token_limit": "catalog token limit",
                    "model_learned_token_limit": "catalog learned token limit",
                    "model_context_window": "catalog context window",
                    "unknown": "limit unavailable",
                }.get(stats["limit_source"], "limit unavailable")
                tooltip = "\n".join(
                    [
                        f"Context usage: {stats['budget_text']}",
                        f"Percent: {stats['percent_text']}",
                        f"Usage source: {usage_source_text}",
                        f"Limit source: {limit_source_text}",
                    ]
                )
            self._context_usage_ring.set_metrics(
                ratio=stats["ratio"],
                text=stats["ring_text"],
                tone=stats["tone"],
                tooltip=tooltip,
            )

        def _adjust_composer_height(self) -> None:
            if self._composer is None:
                return
            document_layout = self._composer.document().documentLayout()
            document_height = int(document_layout.documentSize().height()) if document_layout is not None else 0
            target_height = max(56, min(164, document_height + 18))
            self._composer.setFixedHeight(target_height)

        def _apply_initial_window_geometry(self) -> None:
            if self._initial_geometry_applied:
                return
            available = self._current_available_geometry()
            if available is None:
                self._initial_geometry_applied = True
                return
            preferred_width = min(1560, max(720, int(available.width() * 0.88)))
            preferred_height = min(940, max(520, int(available.height() * 0.9)))
            width = min(preferred_width, max(available.width() - 24, 640))
            height = min(preferred_height, max(available.height() - 24, 480))
            width = max(width, min(self.minimumWidth(), available.width()))
            height = max(height, min(self.minimumHeight(), available.height()))
            self.resize(width, height)
            frame = self.frameGeometry()
            frame.moveCenter(available.center())
            top_left = frame.topLeft()
            min_x = available.left()
            max_x = available.right() - frame.width() + 1
            min_y = available.top()
            max_y = available.bottom() - frame.height() + 1
            top_left.setX(max(min_x, min(top_left.x(), max_x)))
            top_left.setY(max(min_y, min(top_left.y(), max_y)))
            self.move(top_left)
            self._initial_geometry_applied = True

        def _ensure_window_within_available_geometry(self) -> None:
            if self.isMaximized() or self.isFullScreen():
                return
            available = self._current_available_geometry()
            if available is None:
                return
            frame = self.frameGeometry()
            moved = False
            if frame.width() > available.width():
                self.resize(available.width(), self.height())
                frame = self.frameGeometry()
            if frame.height() > available.height():
                self.resize(self.width(), available.height())
                frame = self.frameGeometry()
            if frame.left() < available.left():
                frame.moveLeft(available.left())
                moved = True
            if frame.top() < available.top():
                frame.moveTop(available.top())
                moved = True
            if frame.right() > available.right():
                frame.moveLeft(max(available.left(), available.right() - frame.width() + 1))
                moved = True
            if frame.bottom() > available.bottom():
                frame.moveTop(max(available.top(), available.bottom() - frame.height() + 1))
                moved = True
            if moved:
                self.move(frame.topLeft())

        def _sync_window_chrome(self) -> None:
            maximized = bool(self.isMaximized() or self.isFullScreen())
            margin = 0 if maximized else self._shell_outer_margin
            if self._root_layout is not None:
                self._root_layout.setContentsMargins(margin, margin, margin, margin)
            for widget in (
                self._window_surface,
                self._top_bar,
                self._nav_frame,
                self._desktop_status_bar,
            ):
                if widget is None:
                    continue
                widget.setProperty("shellMaximized", maximized)
                style = widget.style()
                if style is not None:
                    style.unpolish(widget)
                    style.polish(widget)
                widget.update()
            if self._window_maximize_button is not None:
                self._window_maximize_button.setText("❐" if maximized else "□")
                self._window_maximize_button.setToolTip(
                    "Restore Window" if maximized else "Maximize Window"
                )
            self._relayout_top_panel()
            if not maximized:
                self._ensure_window_within_available_geometry()
            self.update()

        def _event_global_point(self, event: Any) -> Any:
            global_position = getattr(event, "globalPosition", None)
            if callable(global_position):
                point = global_position()
                return point.toPoint() if hasattr(point, "toPoint") else point
            global_pos = getattr(event, "globalPos", None)
            if callable(global_pos):
                return global_pos()
            return None

        def _resize_edges_for_point(self, point: Any) -> Any:
            if point is None or self.isMaximized() or self.isFullScreen():
                return qtcore.Qt.Edge(0)
            rect = self.rect()
            margin = self._window_resize_margin
            x = int(point.x())
            y = int(point.y())
            left = x <= margin
            right = x >= rect.width() - margin
            top = y <= margin
            bottom = y >= rect.height() - margin
            edges = qtcore.Qt.Edge(0)
            if left:
                edges |= qtcore.Qt.Edge.LeftEdge
            if right:
                edges |= qtcore.Qt.Edge.RightEdge
            if top:
                edges |= qtcore.Qt.Edge.TopEdge
            if bottom:
                edges |= qtcore.Qt.Edge.BottomEdge
            return edges

        def _cursor_for_resize_edges(self, edges: Any) -> Any:
            if not int(edges):
                return None
            if edges in {qtcore.Qt.Edge.LeftEdge, qtcore.Qt.Edge.RightEdge}:
                return qtcore.Qt.CursorShape.SizeHorCursor
            if edges in {qtcore.Qt.Edge.TopEdge, qtcore.Qt.Edge.BottomEdge}:
                return qtcore.Qt.CursorShape.SizeVerCursor
            if edges in {
                qtcore.Qt.Edge.LeftEdge | qtcore.Qt.Edge.TopEdge,
                qtcore.Qt.Edge.RightEdge | qtcore.Qt.Edge.BottomEdge,
            }:
                return qtcore.Qt.CursorShape.SizeFDiagCursor
            return qtcore.Qt.CursorShape.SizeBDiagCursor

        def _update_resize_cursor(self, global_point: Any) -> None:
            local_point = self.mapFromGlobal(global_point) if global_point is not None else None
            cursor_shape = self._cursor_for_resize_edges(self._resize_edges_for_point(local_point))
            if cursor_shape is None:
                self.unsetCursor()
                if self._desktop_central is not None:
                    self._desktop_central.unsetCursor()
                return
            self.setCursor(cursor_shape)
            if self._desktop_central is not None:
                self._desktop_central.setCursor(cursor_shape)

        def _start_window_resize(self, global_point: Any) -> bool:
            local_point = self.mapFromGlobal(global_point) if global_point is not None else None
            edges = self._resize_edges_for_point(local_point)
            if not int(edges):
                return False
            handle = self.windowHandle()
            if handle is None:
                return False
            result = handle.startSystemResize(edges)
            return True if result is None else bool(result)

        def _start_window_move(self) -> bool:
            if self.isMaximized() or self.isFullScreen():
                return False
            handle = self.windowHandle()
            if handle is None:
                return False
            result = handle.startSystemMove()
            return True if result is None else bool(result)

        def showEvent(self, event: Any) -> None:  # noqa: N802 - Qt naming
            super().showEvent(event)
            self._apply_initial_window_geometry()
            self._apply_initial_shell_sizes()
            self._relayout_top_panel()
            self._sync_window_chrome()

        def changeEvent(self, event: Any) -> None:  # noqa: N802 - Qt naming
            super().changeEvent(event)
            if event.type() == qtcore.QEvent.Type.WindowStateChange:
                qtcore.QTimer.singleShot(0, self._sync_window_chrome)

        def resizeEvent(self, event: Any) -> None:  # noqa: N802 - Qt naming
            super().resizeEvent(event)
            self._relayout_top_panel()

        def _build_workspace_shell(self) -> Any:
            shell_frame = qtwidgets.QFrame()
            shell_frame.setObjectName("desktopWorkspaceShell")
            shell_layout = qtwidgets.QVBoxLayout(shell_frame)
            shell_layout.setContentsMargins(18, 14, 18, 14)
            shell_layout.setSpacing(10)

            header = qtwidgets.QFrame()
            header.setObjectName("desktopPageHeader")
            header_layout = qtwidgets.QHBoxLayout(header)
            header_layout.setContentsMargins(4, 0, 4, 0)
            header_layout.setSpacing(0)
            self._page_title = qtwidgets.QLabel("Chat")
            self._page_title.setObjectName("desktopPageTitle")
            header_layout.addWidget(self._page_title)
            header_layout.addStretch(1)
            shell_layout.addWidget(header)

            self._page_stack = qtwidgets.QStackedWidget()
            self._page_stack.setSizePolicy(
                qtwidgets.QSizePolicy.Policy.Expanding,
                qtwidgets.QSizePolicy.Policy.Expanding,
            )
            for page in self._page_specs:
                builder = getattr(self, f"_build_{page['id']}_page")
                self._page_index_by_id[page["id"]] = self._page_stack.addWidget(builder())
            shell_layout.addWidget(self._page_stack, 1)
            return shell_frame

        def _build_chat_page(self) -> Any:
            page = qtwidgets.QWidget()
            layout = qtwidgets.QVBoxLayout(page)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(0)

            body_splitter = qtwidgets.QSplitter(qtcore.Qt.Horizontal)
            body_splitter.setObjectName("desktopContentSplit")
            body_splitter.setChildrenCollapsible(False)
            body_splitter.setHandleWidth(10)

            session_card, session_layout = self._build_workspace_card()
            session_card.setMinimumWidth(208)
            session_card.setMaximumWidth(268)
            rail_primary_frame = qtwidgets.QFrame()
            rail_primary_frame.setObjectName("desktopRailHeaderBar")
            rail_primary_row = qtwidgets.QHBoxLayout(rail_primary_frame)
            rail_primary_row.setContentsMargins(8, 6, 8, 6)
            rail_primary_row.setSpacing(6)
            chats_title = qtwidgets.QLabel("Chats")
            chats_title.setObjectName("desktopSurfaceTitle")
            self._chat_session_count_badge = self._build_info_badge("0 chats", tone="accent")
            self._chat_session_count_badge.setMinimumWidth(80)
            self._chat_selection_badge = self._build_info_badge("No selection")
            self._chat_selection_badge.hide()
            self._chat_create_session_button = qtwidgets.QPushButton("New Chat")
            self._chat_create_session_button.clicked.connect(self._create_session)
            self._style_action_button(self._chat_create_session_button, tone="primary", compact=True)
            self._chat_create_session_button.setMinimumWidth(94)
            self._chat_create_session_button.setSizePolicy(
                qtwidgets.QSizePolicy.Policy.Maximum,
                qtwidgets.QSizePolicy.Policy.Fixed,
            )
            rail_primary_row.addWidget(chats_title, 0)
            rail_primary_row.addWidget(self._chat_session_count_badge, 0)
            rail_primary_row.addStretch(1)
            rail_primary_row.addWidget(self._chat_create_session_button, 0)
            session_layout.addWidget(rail_primary_frame)

            self._session_list = qtwidgets.QListWidget()
            self._style_list_surface(self._session_list, dense=True)
            self._session_list.currentRowChanged.connect(self._on_session_selected)
            session_layout.addWidget(self._session_list)

            session_actions_frame = qtwidgets.QFrame()
            session_actions_frame.setObjectName("desktopPanelTools")
            session_actions = qtwidgets.QGridLayout(session_actions_frame)
            session_actions.setContentsMargins(5, 5, 5, 5)
            session_actions.setHorizontalSpacing(3)
            session_actions.setVerticalSpacing(3)
            self._rename_session_button = qtwidgets.QPushButton("Rename")
            self._rename_session_button.clicked.connect(self._rename_current_session)
            self._share_session_button = qtwidgets.QPushButton("Share")
            self._share_session_button.clicked.connect(self._toggle_share_current_session)
            self._fork_session_button = qtwidgets.QPushButton("Fork")
            self._fork_session_button.clicked.connect(self._fork_current_session)
            self._compact_session_button = qtwidgets.QPushButton("Compact")
            self._compact_session_button.clicked.connect(self._compact_current_session)
            for button in (
                self._rename_session_button,
                self._share_session_button,
                self._fork_session_button,
                self._compact_session_button,
            ):
                self._style_action_button(button, tone="ghost", compact=True)
            session_actions.addWidget(self._rename_session_button, 0, 0)
            session_actions.addWidget(self._share_session_button, 0, 1)
            session_actions.addWidget(self._fork_session_button, 1, 0)
            session_actions.addWidget(self._compact_session_button, 1, 1)
            session_layout.addWidget(session_actions_frame)
            body_splitter.addWidget(session_card)

            conversation_stage = qtwidgets.QWidget()
            conversation_layout = qtwidgets.QVBoxLayout(conversation_stage)
            conversation_layout.setContentsMargins(0, 0, 0, 0)
            conversation_layout.setSpacing(6)

            self._chat_session_title_label = qtwidgets.QLabel("New chat")
            self._chat_session_title_label.setObjectName("desktopHeroTitle")
            self._chat_session_title_label.setWordWrap(True)
            self._chat_session_title_label.hide()
            self._chat_session_meta_label = qtwidgets.QLabel("Start a conversation.")
            self._chat_session_meta_label.setObjectName("desktopHeroMeta")
            self._chat_session_meta_label.setWordWrap(True)
            self._chat_session_meta_label.hide()

            self._chat_visibility_badge = self._build_info_badge("Private")
            self._chat_visibility_badge.hide()
            self._chat_state_badge = self._build_info_badge("Ready", tone="success")
            self._chat_state_badge.hide()
            self._chat_model_badge = self._build_info_badge("Provider / model not set", tone="accent")
            self._chat_model_badge.hide()

            transcript_card, transcript_layout = self._build_workspace_card()
            self._conversation_view = qtwidgets.QTextBrowser()
            self._conversation_view.setOpenExternalLinks(False)
            self._style_read_surface(self._conversation_view)
            transcript_layout.addWidget(self._conversation_view, 1)
            conversation_layout.addWidget(transcript_card, 1)

            composer_shell = qtwidgets.QFrame()
            composer_shell.setObjectName("desktopComposerShell")
            composer_shell_layout = qtwidgets.QVBoxLayout(composer_shell)
            composer_shell_layout.setContentsMargins(9, 9, 9, 9)
            composer_shell_layout.setSpacing(5)

            composer_meta_row = qtwidgets.QHBoxLayout()
            composer_meta_row.setContentsMargins(0, 0, 0, 0)
            composer_meta_row.setSpacing(6)
            composer_meta_row.addStretch(1)
            self._context_usage_ring = ContextUsageRing()
            composer_meta_row.addWidget(
                self._context_usage_ring,
                0,
                qtcore.Qt.AlignmentFlag.AlignRight,
            )
            composer_shell_layout.addLayout(composer_meta_row)

            self._composer = qtwidgets.QPlainTextEdit()
            self._composer.setObjectName("desktopComposeSurface")
            self._composer.setPlaceholderText("Type a prompt for the selected session. Ctrl+Enter to send.")
            self._composer.setMinimumHeight(56)
            self._composer.setMaximumHeight(164)
            self._composer.setVerticalScrollBarPolicy(qtcore.Qt.ScrollBarPolicy.ScrollBarAsNeeded)
            self._composer.installEventFilter(self)
            self._composer.textChanged.connect(self._adjust_composer_height)
            composer_shell_layout.addWidget(self._composer)

            composer_controls_frame = qtwidgets.QFrame()
            composer_controls_frame.setObjectName("desktopComposerControlsFrame")
            composer_actions = qtwidgets.QHBoxLayout(composer_controls_frame)
            composer_actions.setContentsMargins(8, 5, 8, 5)
            composer_actions.setSpacing(8)
            self._model_combo = qtwidgets.QComboBox()
            self._style_compact_field(self._model_combo)
            self._model_combo.setMinimumWidth(118)
            self._model_combo.setMaximumWidth(156)
            self._model_combo.setMinimumContentsLength(9)
            self._model_combo.setSizeAdjustPolicy(
                qtwidgets.QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
            )
            self._model_combo.currentIndexChanged.connect(self._refresh_model_combo_tooltip)
            self._apply_model_button = qtwidgets.QPushButton("Apply")
            self._apply_model_button.clicked.connect(self._apply_selected_model)
            self._style_action_button(self._apply_model_button, tone="ghost", compact=True)
            self._apply_model_button.setMinimumWidth(56)
            self._send_button = qtwidgets.QPushButton("Send")
            self._send_button.clicked.connect(self._send_current_prompt)
            self._send_button.setDefault(True)
            self._send_button.setMinimumWidth(72)
            self._interrupt_turn_button = qtwidgets.QPushButton("Pause")
            self._interrupt_turn_button.clicked.connect(self._interrupt_current_run)
            self._interrupt_turn_button.setMinimumWidth(62)
            self._resume_turn_button = qtwidgets.QPushButton("Resume")
            self._resume_turn_button.clicked.connect(self._resume_current_run)
            self._resume_turn_button.setMinimumWidth(68)
            self._stop_turn_button = qtwidgets.QPushButton("Stop")
            self._stop_turn_button.clicked.connect(self._cancel_current_run)
            self._stop_turn_button.setMinimumWidth(62)
            self._clear_button = qtwidgets.QPushButton("Clear")
            self._clear_button.clicked.connect(self._composer.clear)
            self._clear_button.setMinimumWidth(56)
            self._style_action_button(self._clear_button, tone="ghost", compact=True)
            self._style_action_button(self._interrupt_turn_button, tone="ghost", compact=True)
            self._style_action_button(self._resume_turn_button, tone="ghost", compact=True)
            self._style_action_button(self._stop_turn_button, tone="danger", compact=True)
            self._style_action_button(self._send_button, tone="primary", compact=True)
            composer_actions.addWidget(self._model_combo, 1)
            composer_actions.addWidget(self._apply_model_button, 0)
            composer_actions.addStretch(1)
            composer_actions.addWidget(self._clear_button)
            composer_actions.addWidget(self._interrupt_turn_button)
            composer_actions.addWidget(self._resume_turn_button)
            composer_actions.addWidget(self._stop_turn_button)
            composer_actions.addWidget(self._send_button)
            composer_shell_layout.addWidget(composer_controls_frame)
            conversation_layout.addWidget(composer_shell)
            body_splitter.addWidget(conversation_stage)

            workspace_card, workspace_layout = self._build_workspace_card()
            workspace_card.setMinimumWidth(248)
            workspace_card.setMaximumWidth(320)
            workspace_layout.addWidget(self._build_surface_header("Workspace"))
            self._chat_aux_tabs = qtwidgets.QTabWidget()
            self._chat_aux_tabs.setObjectName("desktopAuxTabs")
            self._chat_aux_tabs.setDocumentMode(True)

            context_page = qtwidgets.QWidget()
            context_layout = qtwidgets.QVBoxLayout(context_page)
            context_layout.setContentsMargins(10, 10, 10, 10)
            context_layout.setSpacing(8)
            self._context_view = qtwidgets.QPlainTextEdit()
            self._context_view.setReadOnly(True)
            self._style_read_surface(self._context_view)
            context_layout.addWidget(self._context_view)
            self._chat_aux_tabs.addTab(context_page, "Context")

            self._models_view = qtwidgets.QPlainTextEdit()
            self._models_view.setReadOnly(True)
            self._style_read_surface(self._models_view)
            self._chat_aux_tabs.addTab(self._models_view, "Runtime")

            activity_page = qtwidgets.QWidget()
            activity_layout = qtwidgets.QVBoxLayout(activity_page)
            activity_layout.setContentsMargins(10, 10, 10, 10)
            activity_layout.setSpacing(8)
            self._activity_view = qtwidgets.QTextBrowser()
            self._activity_view.setOpenExternalLinks(False)
            self._style_read_surface(self._activity_view)
            activity_layout.addWidget(self._activity_view)
            self._chat_aux_tabs.addTab(activity_page, "Activity")
            workspace_layout.addWidget(self._chat_aux_tabs, 1)
            body_splitter.addWidget(workspace_card)

            body_splitter.setStretchFactor(0, 2)
            body_splitter.setStretchFactor(1, 13)
            body_splitter.setStretchFactor(2, 2)
            layout.addWidget(body_splitter, 1)
            qtcore.QTimer.singleShot(0, lambda: body_splitter.setSizes([240, 1020, 276]))
            qtcore.QTimer.singleShot(0, self._adjust_composer_height)
            return page

        def _build_models_page(self) -> Any:
            page = qtwidgets.QWidget()
            layout = qtwidgets.QVBoxLayout(page)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(12)

            splitter = qtwidgets.QSplitter(qtcore.Qt.Horizontal)
            splitter.setObjectName("desktopContentSplit")
            splitter.setChildrenCollapsible(False)
            splitter.setHandleWidth(10)

            list_card, list_layout = self._build_workspace_card()
            list_layout.addWidget(
                self._build_surface_header(
                    "Registry",
                    "Browse the resolved model inventory, then filter, classify, or inspect capability facts.",
                )
            )
            filter_bar, filter_row = self._build_panel_tools_frame()
            filter_row.addWidget(self._build_section_label("Search"), 0)
            self._model_registry_search = qtwidgets.QLineEdit()
            self._style_compact_field(self._model_registry_search)
            self._model_registry_search.setPlaceholderText("Filter by provider, model, role, or capability")
            self._model_registry_search.textChanged.connect(self._refresh_registry_model_list)
            self._refresh_registry_button = qtwidgets.QPushButton("Refresh Registry")
            self._refresh_registry_button.clicked.connect(self._refresh_ops_registry_snapshot)
            self._style_action_button(self._refresh_registry_button, tone="ghost")
            filter_row.addWidget(self._model_registry_search, 1)
            filter_row.addWidget(self._refresh_registry_button)
            list_layout.addWidget(filter_bar)
            self._model_registry_list = qtwidgets.QListWidget()
            self._style_list_surface(self._model_registry_list)
            self._model_registry_list.currentRowChanged.connect(self._on_registry_model_selected)
            list_layout.addWidget(self._model_registry_list, 1)
            splitter.addWidget(list_card)

            inspector_card, inspector_layout = self._build_workspace_card()
            inspector_layout.addWidget(
                self._build_surface_header(
                    "Inspector",
                    "Confirm roles, probe capabilities, and keep feature bindings explicit and easy to audit.",
                )
            )
            self._models_aux_tabs = qtwidgets.QTabWidget()
            self._models_aux_tabs.setObjectName("desktopAuxTabs")
            self._models_aux_tabs.setDocumentMode(True)

            detail_page = qtwidgets.QWidget()
            detail_layout = qtwidgets.QVBoxLayout(detail_page)
            detail_layout.setContentsMargins(12, 12, 12, 12)
            detail_layout.setSpacing(10)
            role_frame, role_row = self._build_panel_tools_frame()
            role_row.addWidget(self._build_section_label("Role"), 0)
            self._registry_model_role_combo = qtwidgets.QComboBox()
            self._style_compact_field(self._registry_model_role_combo)
            self._registry_model_role_combo.addItems(list(DESKTOP_MODEL_ROLE_OPTIONS))
            self._registry_set_role_button = qtwidgets.QPushButton("Set Role")
            self._registry_set_role_button.clicked.connect(self._set_selected_registry_model_role)
            self._registry_probe_button = qtwidgets.QPushButton("Probe Capabilities")
            self._registry_probe_button.clicked.connect(self._probe_selected_registry_model)
            self._style_action_button(self._registry_set_role_button, tone="primary")
            self._style_action_button(self._registry_probe_button, tone="ghost")
            role_row.addWidget(self._registry_model_role_combo)
            role_row.addWidget(self._registry_set_role_button)
            role_row.addWidget(self._registry_probe_button)
            detail_layout.addWidget(role_frame)
            detail_layout.addWidget(
                self._build_surface_header(
                    "Capability Detail",
                    "Review provider family, context window, and model capability truth before promoting the model.",
                )
            )
            self._model_registry_detail_view = qtwidgets.QPlainTextEdit()
            self._model_registry_detail_view.setReadOnly(True)
            self._style_read_surface(self._model_registry_detail_view)
            detail_layout.addWidget(self._model_registry_detail_view, 1)
            self._models_aux_tabs.addTab(detail_page, "Detail")

            bindings_page = qtwidgets.QWidget()
            bindings_layout = qtwidgets.QVBoxLayout(bindings_page)
            bindings_layout.setContentsMargins(12, 12, 12, 12)
            bindings_layout.setSpacing(10)
            binding_frame, binding_row = self._build_panel_tools_frame()
            binding_row.addWidget(self._build_section_label("Feature"), 0)
            self._feature_binding_role_combo = qtwidgets.QComboBox()
            self._style_compact_field(self._feature_binding_role_combo)
            self._feature_binding_role_combo.addItems(list(DESKTOP_FEATURE_ROLE_OPTIONS))
            self._registry_bind_feature_button = qtwidgets.QPushButton("Bind Feature")
            self._registry_bind_feature_button.clicked.connect(self._bind_selected_registry_feature_model)
            self._registry_clear_feature_button = qtwidgets.QPushButton("Clear Binding")
            self._registry_clear_feature_button.clicked.connect(self._clear_selected_feature_binding)
            self._style_action_button(self._registry_bind_feature_button, tone="primary")
            self._style_action_button(self._registry_clear_feature_button, tone="danger")
            binding_row.addWidget(self._feature_binding_role_combo)
            binding_row.addWidget(self._registry_bind_feature_button)
            binding_row.addWidget(self._registry_clear_feature_button)
            bindings_layout.addWidget(binding_frame)
            bindings_layout.addWidget(
                self._build_surface_header(
                    "Feature Bindings",
                    "Bind the runtime embedding or OCR slot explicitly so higher-level features stay predictable.",
                )
            )
            self._feature_bindings_view = qtwidgets.QPlainTextEdit()
            self._feature_bindings_view.setReadOnly(True)
            self._style_read_surface(self._feature_bindings_view)
            bindings_layout.addWidget(self._feature_bindings_view, 1)
            self._models_aux_tabs.addTab(bindings_page, "Bindings")

            inspector_layout.addWidget(self._models_aux_tabs, 1)
            splitter.addWidget(inspector_card)

            splitter.setStretchFactor(0, 4)
            splitter.setStretchFactor(1, 6)
            layout.addWidget(splitter, 1)
            return page

        def _build_providers_page(self) -> Any:
            page = qtwidgets.QWidget()
            layout = qtwidgets.QVBoxLayout(page)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(12)

            splitter = qtwidgets.QSplitter(qtcore.Qt.Horizontal)
            splitter.setObjectName("desktopContentSplit")
            splitter.setChildrenCollapsible(False)
            splitter.setHandleWidth(10)

            list_card, list_layout = self._build_workspace_card()
            list_layout.addWidget(
                self._build_surface_header(
                    "Providers",
                    "Manage cloud suppliers, local runtimes, and connection presets without mixing them into the chat stage.",
                )
            )
            provider_actions_frame, provider_actions = self._build_panel_tools_frame()
            provider_actions.addWidget(self._build_section_label("Catalog"), 0)
            self._provider_refresh_button = qtwidgets.QPushButton("Refresh")
            self._provider_refresh_button.clicked.connect(self._refresh_ops_providers_snapshot)
            self._provider_new_button = qtwidgets.QPushButton("New Draft")
            self._provider_new_button.clicked.connect(self._reset_provider_draft)
            self._style_action_button(self._provider_refresh_button, tone="ghost")
            self._style_action_button(self._provider_new_button, tone="primary")
            provider_actions.addWidget(self._provider_refresh_button)
            provider_actions.addWidget(self._provider_new_button)
            provider_actions.addStretch(1)
            list_layout.addWidget(provider_actions_frame)
            self._provider_list = qtwidgets.QListWidget()
            self._style_list_surface(self._provider_list)
            self._provider_list.currentRowChanged.connect(self._on_provider_selected)
            list_layout.addWidget(self._provider_list, 1)
            splitter.addWidget(list_card)

            editor_shell = qtwidgets.QWidget()
            editor_shell_layout = qtwidgets.QVBoxLayout(editor_shell)
            editor_shell_layout.setContentsMargins(0, 0, 0, 0)
            editor_shell_layout.setSpacing(12)

            detail_card, detail_layout = self._build_workspace_card()
            detail_layout.addWidget(
                self._build_surface_header(
                    "Provider Detail",
                    "Inspect health, breaker state, and saved connection details for the current supplier.",
                )
            )
            detail_tools_frame, detail_button_row = self._build_panel_tools_frame()
            detail_button_row.addWidget(self._build_section_label("Selected Provider"), 0)
            self._provider_health_button = qtwidgets.QPushButton("Refresh Health")
            self._provider_health_button.clicked.connect(self._refresh_selected_provider_health)
            self._provider_delete_button = qtwidgets.QPushButton("Delete Provider")
            self._provider_delete_button.clicked.connect(self._delete_selected_provider)
            self._style_action_button(self._provider_health_button, tone="ghost")
            self._style_action_button(self._provider_delete_button, tone="danger")
            detail_button_row.addWidget(self._provider_health_button)
            detail_button_row.addWidget(self._provider_delete_button)
            detail_button_row.addStretch(1)
            detail_layout.addWidget(detail_tools_frame)
            self._provider_detail_view = qtwidgets.QPlainTextEdit()
            self._provider_detail_view.setReadOnly(True)
            self._style_read_surface(self._provider_detail_view)
            detail_layout.addWidget(self._provider_detail_view, 1)
            editor_shell_layout.addWidget(detail_card, 2)

            editor_card, editor_layout = self._build_workspace_card()
            editor_layout.addWidget(
                self._build_surface_header(
                    "Provider Editor",
                    "Build a fast connection draft first, then classify discovered models once the provider is saved.",
                )
            )
            self._provider_editor_tabs = qtwidgets.QTabWidget()
            self._provider_editor_tabs.setObjectName("desktopAuxTabs")
            self._provider_editor_tabs.setDocumentMode(True)

            connection_page = qtwidgets.QWidget()
            form_layout = qtwidgets.QFormLayout(connection_page)
            form_layout.setContentsMargins(16, 18, 16, 16)
            form_layout.setSpacing(10)
            self._provider_preset_note = qtwidgets.QLabel(
                "Choose a preset to quick-fill the protocol family and endpoint, then adjust model ids and credentials."
            )
            self._provider_preset_note.setWordWrap(True)
            self._provider_preset_note.hide()
            self._provider_validation_note = qtwidgets.QLabel("Connection not tested for current draft.")
            self._provider_validation_note.setWordWrap(True)
            preset_bar = qtwidgets.QWidget()
            preset_bar.setObjectName("desktopPanelTools")
            preset_bar_layout = qtwidgets.QHBoxLayout(preset_bar)
            preset_bar_layout.setContentsMargins(8, 8, 8, 8)
            preset_bar_layout.setSpacing(8)
            for preset in desktop_provider_preset_specs():
                button = qtwidgets.QPushButton(preset["label"])
                self._style_action_button(button, tone="ghost")
                button.clicked.connect(
                    lambda checked=False, preset_id=preset["id"]: self._apply_provider_preset(
                        preset_id,
                        checked=checked,
                    )
                )
                preset_bar_layout.addWidget(button)
            preset_bar_layout.addStretch(1)
            self._provider_id_input = qtwidgets.QLineEdit()
            self._provider_name_input = qtwidgets.QLineEdit()
            self._provider_type_combo = qtwidgets.QComboBox()
            self._provider_type_combo.addItems(["openai", "anthropic", "ollama"])
            self._provider_base_input = qtwidgets.QLineEdit()
            self._provider_api_key_input = qtwidgets.QLineEdit()
            self._provider_api_key_input.setEchoMode(qtwidgets.QLineEdit.EchoMode.Password)
            self._provider_default_model_input = qtwidgets.QLineEdit()
            self._provider_models_edit = qtwidgets.QPlainTextEdit()
            self._provider_models_edit.setPlaceholderText("One model id per line, or comma-separated.")
            self._provider_models_edit.setMinimumHeight(88)
            self._provider_headers_edit = qtwidgets.QPlainTextEdit()
            self._provider_headers_edit.setPlaceholderText('Optional JSON headers, for example: {"x-tenant":"demo"}')
            self._provider_headers_edit.setMinimumHeight(72)
            self._provider_enabled_checkbox = qtwidgets.QCheckBox("Enabled")
            self._provider_priority_spin = qtwidgets.QSpinBox()
            self._provider_priority_spin.setRange(-1000, 1000)
            self._provider_timeout_spin = qtwidgets.QSpinBox()
            self._provider_timeout_spin.setRange(1, 600)
            self._provider_timeout_spin.setValue(60)
            for widget in (
                self._provider_id_input,
                self._provider_name_input,
                self._provider_type_combo,
                self._provider_base_input,
                self._provider_api_key_input,
                self._provider_default_model_input,
                self._provider_priority_spin,
                self._provider_timeout_spin,
            ):
                self._style_compact_field(widget)
            form_layout.addRow("Quick Presets", preset_bar)
            form_layout.addRow("", self._provider_preset_note)
            form_layout.addRow("", self._provider_validation_note)
            form_layout.addRow("Provider ID", self._provider_id_input)
            form_layout.addRow("Name", self._provider_name_input)
            form_layout.addRow("API Type", self._provider_type_combo)
            form_layout.addRow("Base URL", self._provider_base_input)
            form_layout.addRow("API Key", self._provider_api_key_input)
            form_layout.addRow("Default Model", self._provider_default_model_input)
            form_layout.addRow("Models", self._provider_models_edit)
            form_layout.addRow("Headers", self._provider_headers_edit)
            form_layout.addRow("Enabled", self._provider_enabled_checkbox)
            form_layout.addRow("Priority", self._provider_priority_spin)
            form_layout.addRow("Timeout", self._provider_timeout_spin)

            provider_form_actions = qtwidgets.QHBoxLayout()
            self._provider_validate_button = qtwidgets.QPushButton("Test Connection")
            self._provider_validate_button.clicked.connect(self._validate_provider_connection)
            self._provider_discover_button = qtwidgets.QPushButton("Discover Models")
            self._provider_discover_button.clicked.connect(self._discover_provider_models)
            self._provider_save_button = qtwidgets.QPushButton("Save Provider")
            self._provider_save_button.clicked.connect(self._save_provider_draft)
            self._style_action_button(self._provider_validate_button, tone="ghost")
            self._style_action_button(self._provider_discover_button, tone="ghost")
            self._style_action_button(self._provider_save_button, tone="primary")
            provider_form_actions.addWidget(self._provider_validate_button)
            provider_form_actions.addWidget(self._provider_discover_button)
            provider_form_actions.addStretch(1)
            provider_form_actions.addWidget(self._provider_save_button)
            form_layout.addRow("", provider_form_actions)
            self._provider_editor_tabs.addTab(connection_page, "Connection")

            shortcuts_panel = qtwidgets.QWidget()
            shortcuts_layout = qtwidgets.QVBoxLayout(shortcuts_panel)
            shortcuts_layout.setContentsMargins(0, 8, 0, 0)
            shortcuts_layout.setSpacing(8)
            self._provider_model_shortcuts_note = qtwidgets.QLabel(
                "Save the provider, then use these shortcuts to classify or bind the current draft models."
            )
            self._provider_model_shortcuts_note.setWordWrap(True)
            self._provider_model_shortcuts_note.hide()
            shortcuts_layout.addWidget(self._provider_model_shortcuts_note)
            self._provider_draft_model_list = qtwidgets.QListWidget()
            self._style_list_surface(self._provider_draft_model_list)
            self._provider_draft_model_list.currentRowChanged.connect(self._on_provider_draft_model_selected)
            self._provider_draft_model_list.setMinimumHeight(112)
            shortcuts_layout.addWidget(self._provider_draft_model_list)

            default_row = qtwidgets.QHBoxLayout()
            self._provider_draft_default_button = qtwidgets.QPushButton("Use As Default")
            self._provider_draft_default_button.clicked.connect(self._use_selected_provider_model_as_default)
            self._style_action_button(self._provider_draft_default_button, tone="ghost")
            default_row.addWidget(self._provider_draft_default_button)
            default_row.addStretch(1)
            shortcuts_layout.addLayout(default_row)

            role_row = qtwidgets.QHBoxLayout()
            self._provider_draft_model_role_combo = qtwidgets.QComboBox()
            self._style_compact_field(self._provider_draft_model_role_combo)
            self._provider_draft_model_role_combo.addItems(list(DESKTOP_MODEL_ROLE_OPTIONS))
            self._provider_draft_set_role_button = qtwidgets.QPushButton("Apply Role")
            self._provider_draft_set_role_button.clicked.connect(self._set_selected_provider_draft_model_role)
            self._style_action_button(self._provider_draft_set_role_button, tone="primary")
            role_row.addWidget(self._provider_draft_model_role_combo)
            role_row.addWidget(self._provider_draft_set_role_button)
            shortcuts_layout.addLayout(role_row)

            feature_row = qtwidgets.QHBoxLayout()
            self._provider_draft_feature_combo = qtwidgets.QComboBox()
            self._style_compact_field(self._provider_draft_feature_combo)
            self._provider_draft_feature_combo.addItems(list(DESKTOP_FEATURE_ROLE_OPTIONS))
            self._provider_draft_bind_feature_button = qtwidgets.QPushButton("Bind Feature")
            self._provider_draft_bind_feature_button.clicked.connect(self._bind_selected_provider_draft_feature_model)
            self._style_action_button(self._provider_draft_bind_feature_button, tone="primary")
            feature_row.addWidget(self._provider_draft_feature_combo)
            feature_row.addWidget(self._provider_draft_bind_feature_button)
            shortcuts_layout.addLayout(feature_row)
            self._provider_editor_tabs.addTab(shortcuts_panel, "Models")
            editor_layout.addWidget(self._provider_editor_tabs, 1)
            editor_shell_layout.addWidget(editor_card, 5)
            splitter.addWidget(editor_shell)

            splitter.setStretchFactor(0, 3)
            splitter.setStretchFactor(1, 5)
            layout.addWidget(splitter, 1)
            self._wire_provider_form_dirty_tracking()
            self._reset_provider_draft()
            return page

        def _build_settings_page(self) -> Any:
            page = qtwidgets.QWidget()
            layout = qtwidgets.QVBoxLayout(page)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(12)

            top_row = qtwidgets.QHBoxLayout()
            top_row.setContentsMargins(0, 0, 0, 0)
            top_row.setSpacing(12)

            controls_card, controls_layout = self._build_workspace_card()
            controls_layout.addWidget(
                self._build_surface_header(
                    "Desktop Preferences",
                    "Tune the refresh cadence and keep the desktop workspace stable while iterating on real features.",
                )
            )
            controls_grid = qtwidgets.QGridLayout()
            controls_grid.setContentsMargins(0, 0, 0, 0)
            controls_grid.setHorizontalSpacing(12)
            controls_grid.setVerticalSpacing(10)
            controls_layout.setContentsMargins(16, 18, 16, 16)
            self._settings_auto_refresh_checkbox = qtwidgets.QCheckBox("Enable auto refresh")
            self._settings_auto_refresh_checkbox.toggled.connect(self._set_auto_refresh_enabled)
            self._settings_refresh_interval_spin = qtwidgets.QSpinBox()
            self._settings_refresh_interval_spin.setRange(1000, 60000)
            self._settings_refresh_interval_spin.setSingleStep(500)
            self._settings_refresh_interval_spin.valueChanged.connect(self._set_refresh_interval_ms)
            self._settings_pref_status = qtwidgets.QLabel("")
            self._settings_pref_status.setWordWrap(True)
            self._settings_workspace_path = qtwidgets.QLineEdit()
            self._settings_workspace_path.setReadOnly(True)
            self._settings_gateway_path = qtwidgets.QLineEdit()
            self._settings_gateway_path.setReadOnly(True)
            self._style_compact_field(self._settings_refresh_interval_spin)
            self._style_compact_field(self._settings_workspace_path)
            self._style_compact_field(self._settings_gateway_path)
            controls_grid.addWidget(self._settings_auto_refresh_checkbox, 0, 0, 1, 2)
            controls_grid.addWidget(qtwidgets.QLabel("Refresh Interval (ms)"), 1, 0)
            controls_grid.addWidget(self._settings_refresh_interval_spin, 1, 1)
            controls_grid.addWidget(qtwidgets.QLabel("Workspace"), 2, 0)
            controls_grid.addWidget(self._settings_workspace_path, 2, 1)
            controls_grid.addWidget(qtwidgets.QLabel("Gateway"), 3, 0)
            controls_grid.addWidget(self._settings_gateway_path, 3, 1)
            controls_grid.addWidget(self._settings_pref_status, 4, 0, 1, 2)
            controls_layout.addLayout(controls_grid)

            quick_actions_card, quick_actions_layout = self._build_workspace_card()
            quick_actions_layout.addWidget(
                self._build_surface_header(
                    "Quick Actions",
                    "Jump back into the core workspaces or resync the runtime without leaving the desktop shell.",
                )
            )
            shortcuts_grid = qtwidgets.QGridLayout()
            shortcuts_grid.setContentsMargins(0, 0, 0, 0)
            shortcuts_grid.setHorizontalSpacing(8)
            shortcuts_grid.setVerticalSpacing(8)
            self._settings_refresh_now_button = qtwidgets.QPushButton("Refresh Now")
            self._settings_refresh_now_button.clicked.connect(self.refresh_snapshot)
            self._settings_reconnect_button = qtwidgets.QPushButton("Reconnect Gateway")
            self._settings_reconnect_button.clicked.connect(self._reconnect_gateway)
            self._settings_open_chat_button = qtwidgets.QPushButton("Open Chat")
            self._settings_open_chat_button.clicked.connect(
                lambda checked=False: self._select_page_by_id("chat")
            )
            self._settings_open_models_button = qtwidgets.QPushButton("Open Models")
            self._settings_open_models_button.clicked.connect(
                lambda checked=False: self._select_page_by_id("models")
            )
            self._settings_open_providers_button = qtwidgets.QPushButton("Open Providers")
            self._settings_open_providers_button.clicked.connect(
                lambda checked=False: self._select_page_by_id("providers")
            )
            self._settings_open_memory_button = qtwidgets.QPushButton("Open Memory")
            self._settings_open_memory_button.clicked.connect(
                lambda checked=False: self._select_page_by_id("memory")
            )
            for button in (
                self._settings_refresh_now_button,
                self._settings_reconnect_button,
                self._settings_open_chat_button,
                self._settings_open_models_button,
                self._settings_open_providers_button,
                self._settings_open_memory_button,
            ):
                self._style_action_button(button, tone="ghost")
            shortcuts_grid.addWidget(self._settings_refresh_now_button, 0, 0)
            shortcuts_grid.addWidget(self._settings_reconnect_button, 0, 1)
            shortcuts_grid.addWidget(self._settings_open_chat_button, 0, 2)
            shortcuts_grid.addWidget(self._settings_open_models_button, 1, 0)
            shortcuts_grid.addWidget(self._settings_open_providers_button, 1, 1)
            shortcuts_grid.addWidget(self._settings_open_memory_button, 1, 2)
            for column in range(3):
                shortcuts_grid.setColumnStretch(column, 1)
            quick_actions_layout.addLayout(shortcuts_grid)

            top_row.addWidget(controls_card, 1)
            top_row.addWidget(quick_actions_card, 1)
            layout.addLayout(top_row)

            settings_card, settings_layout = self._build_workspace_card()
            settings_layout.addWidget(
                self._build_surface_header(
                    "Desktop Overview",
                    "Track workspace state, supply-layer inventory, and the currently selected runtime session.",
                )
            )
            self._settings_view = qtwidgets.QPlainTextEdit()
            self._settings_view.setReadOnly(True)
            self._style_read_surface(self._settings_view)
            settings_layout.addWidget(self._settings_view, 1)
            layout.addWidget(settings_card, 1)
            return page

        def _build_sessions_page(self) -> Any:
            page = qtwidgets.QWidget()
            layout = qtwidgets.QVBoxLayout(page)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(12)
            splitter = qtwidgets.QSplitter(qtcore.Qt.Horizontal)

            list_group = qtwidgets.QGroupBox("Session Ledger")
            list_layout = qtwidgets.QVBoxLayout(list_group)
            session_actions = qtwidgets.QHBoxLayout()
            self._sessions_refresh_button = qtwidgets.QPushButton("Refresh")
            self._sessions_refresh_button.clicked.connect(self.refresh_snapshot)
            self._sessions_open_chat_button = qtwidgets.QPushButton("Open In Chat")
            self._sessions_open_chat_button.clicked.connect(self._open_selected_session_in_chat)
            session_actions.addWidget(self._sessions_refresh_button)
            session_actions.addWidget(self._sessions_open_chat_button)
            session_actions.addStretch(1)
            list_layout.addLayout(session_actions)
            self._sessions_overview_list = qtwidgets.QListWidget()
            self._sessions_overview_list.currentRowChanged.connect(self._on_sessions_overview_selected)
            list_layout.addWidget(self._sessions_overview_list)
            splitter.addWidget(list_group)

            right_splitter = qtwidgets.QSplitter(qtcore.Qt.Vertical)

            transcript_group = qtwidgets.QGroupBox("Transcript")
            transcript_layout = qtwidgets.QVBoxLayout(transcript_group)
            self._sessions_transcript_view = qtwidgets.QTextBrowser()
            self._sessions_transcript_view.setOpenExternalLinks(False)
            transcript_layout.addWidget(self._sessions_transcript_view)
            right_splitter.addWidget(transcript_group)

            detail_group = qtwidgets.QGroupBox("Session Detail")
            detail_layout = qtwidgets.QVBoxLayout(detail_group)
            self._sessions_overview_detail_view = qtwidgets.QPlainTextEdit()
            self._sessions_overview_detail_view.setReadOnly(True)
            detail_layout.addWidget(self._sessions_overview_detail_view)
            right_splitter.addWidget(detail_group)

            right_splitter.setStretchFactor(0, 4)
            right_splitter.setStretchFactor(1, 3)
            splitter.addWidget(right_splitter)

            splitter.setStretchFactor(0, 3)
            splitter.setStretchFactor(1, 5)
            layout.addWidget(splitter, 1)
            return page

        def _build_memory_page(self) -> Any:
            page = qtwidgets.QWidget()
            layout = qtwidgets.QVBoxLayout(page)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(12)

            splitter = qtwidgets.QSplitter(qtcore.Qt.Horizontal)

            explorer_group = qtwidgets.QGroupBox("Memory Explorer")
            explorer_layout = qtwidgets.QVBoxLayout(explorer_group)
            explorer_actions = qtwidgets.QHBoxLayout()
            self._memory_refresh_button = qtwidgets.QPushButton("Refresh")
            self._memory_refresh_button.clicked.connect(self._refresh_memory_page)
            self._memory_open_today_button = qtwidgets.QPushButton("Open Today")
            self._memory_open_today_button.clicked.connect(self._open_today_memory_file)
            explorer_actions.addWidget(self._memory_refresh_button)
            explorer_actions.addWidget(self._memory_open_today_button)
            explorer_actions.addStretch(1)
            explorer_layout.addLayout(explorer_actions)

            self._memory_summary_view = qtwidgets.QPlainTextEdit()
            self._memory_summary_view.setReadOnly(True)
            self._memory_summary_view.setMinimumHeight(108)
            explorer_layout.addWidget(self._memory_summary_view)

            explorer_layout.addWidget(qtwidgets.QLabel("Files"))
            self._memory_file_list = qtwidgets.QListWidget()
            self._memory_file_list.currentRowChanged.connect(self._on_memory_file_selected)
            explorer_layout.addWidget(self._memory_file_list, 1)

            search_row = qtwidgets.QHBoxLayout()
            self._memory_search_input = qtwidgets.QLineEdit()
            self._memory_search_input.setPlaceholderText("Search workspace memory notes")
            self._memory_search_button = qtwidgets.QPushButton("Search")
            self._memory_search_button.clicked.connect(self._search_memory_notes)
            search_row.addWidget(self._memory_search_input, 1)
            search_row.addWidget(self._memory_search_button)
            explorer_layout.addLayout(search_row)

            self._memory_search_results = qtwidgets.QListWidget()
            self._memory_search_results.currentRowChanged.connect(self._on_memory_search_selected)
            explorer_layout.addWidget(self._memory_search_results, 1)
            splitter.addWidget(explorer_group)

            editor_group = qtwidgets.QGroupBox("Memory Editor")
            editor_layout = qtwidgets.QVBoxLayout(editor_group)
            self._memory_file_path_value = qtwidgets.QLabel("No file selected")
            self._memory_file_path_value.setWordWrap(True)
            editor_layout.addWidget(self._memory_file_path_value)

            editor_actions = qtwidgets.QHBoxLayout()
            self._memory_reload_button = qtwidgets.QPushButton("Reload File")
            self._memory_reload_button.clicked.connect(self._reload_selected_memory_file)
            self._memory_save_button = qtwidgets.QPushButton("Save File")
            self._memory_save_button.clicked.connect(self._save_selected_memory_file)
            editor_actions.addWidget(self._memory_reload_button)
            editor_actions.addStretch(1)
            editor_actions.addWidget(self._memory_save_button)
            editor_layout.addLayout(editor_actions)

            self._memory_editor = qtwidgets.QPlainTextEdit()
            editor_layout.addWidget(self._memory_editor, 1)
            splitter.addWidget(editor_group)

            splitter.setStretchFactor(0, 3)
            splitter.setStretchFactor(1, 5)
            layout.addWidget(splitter, 1)
            return page

        def _wire_provider_form_dirty_tracking(self) -> None:
            widgets: list[Any] = [
                self._provider_id_input,
                self._provider_name_input,
                self._provider_base_input,
                self._provider_api_key_input,
                self._provider_default_model_input,
            ]
            for widget in widgets:
                widget.textChanged.connect(self._mark_provider_form_dirty)
            self._provider_type_combo.currentTextChanged.connect(self._mark_provider_form_dirty)
            self._provider_enabled_checkbox.toggled.connect(self._mark_provider_form_dirty)
            self._provider_priority_spin.valueChanged.connect(self._mark_provider_form_dirty)
            self._provider_timeout_spin.valueChanged.connect(self._mark_provider_form_dirty)
            self._provider_models_edit.textChanged.connect(self._mark_provider_form_dirty)
            self._provider_headers_edit.textChanged.connect(self._mark_provider_form_dirty)
            self._provider_type_combo.currentTextChanged.connect(self._on_provider_api_type_changed)
            self._provider_type_combo.currentTextChanged.connect(self._clear_provider_validation_state)
            self._provider_base_input.textChanged.connect(self._clear_provider_validation_state)
            self._provider_api_key_input.textChanged.connect(self._clear_provider_validation_state)
            self._provider_id_input.textChanged.connect(self._refresh_provider_model_shortcuts)
            self._provider_default_model_input.textChanged.connect(self._refresh_provider_model_shortcuts)
            self._provider_models_edit.textChanged.connect(self._refresh_provider_model_shortcuts)

        def _mark_provider_form_dirty(self, *_: Any) -> None:
            if not self._provider_form_loading:
                self._provider_form_dirty = True

        def _clear_provider_validation_state(self, *_: Any) -> None:
            if self._provider_form_loading:
                return
            self._provider_validation_payload = {}
            self._provider_validation_note.setText("Connection not tested for current draft.")

        def _provider_preset_spec(self, preset_id: str | None) -> dict[str, str] | None:
            target = _compact_text(preset_id).lower()
            for item in DESKTOP_PROVIDER_PRESET_SPECS:
                if _compact_text(item.get("id")).lower() == target:
                    return dict(item)
            return None

        def _apply_provider_input_placeholders(
            self,
            *,
            api_type: str,
            preset: dict[str, str] | None = None,
        ) -> None:
            preset_payload = preset or {}
            normalized_type = _compact_text(api_type).lower() or "openai"
            default_placeholders = {
                "openai": {
                    "base": "Official OpenAI or any OpenAI-compatible endpoint",
                    "key": "Paste API key",
                    "models": "One model id per line, for example gpt-*",
                    "default_model": "Optional default model id",
                    "note": "OpenAI-family providers can point at official OpenAI or compatible relays such as MaaS.",
                },
                "anthropic": {
                    "base": "Anthropic-family endpoint",
                    "key": "Paste API key",
                    "models": "One model id per line, for example claude-* or MiniMax-*",
                    "default_model": "Optional default model id",
                    "note": "Anthropic-family providers cover official Anthropic and compatible endpoints such as MiniMax relays.",
                },
                "ollama": {
                    "base": "Local Ollama daemon URL",
                    "key": "Usually not required for local Ollama",
                    "models": "One model id per line, for example qwen3.5:9b",
                    "default_model": "Optional default model id",
                    "note": "Ollama providers are local-first. Discover models after the daemon is running.",
                },
            }.get(normalized_type, {})
            self._provider_base_input.setPlaceholderText(
                _compact_text(preset_payload.get("base_placeholder")) or str(default_placeholders.get("base") or "")
            )
            self._provider_api_key_input.setPlaceholderText(
                _compact_text(preset_payload.get("api_key_placeholder")) or str(default_placeholders.get("key") or "")
            )
            self._provider_models_edit.setPlaceholderText(
                _compact_text(preset_payload.get("model_placeholder")) or str(default_placeholders.get("models") or "")
            )
            self._provider_default_model_input.setPlaceholderText(
                _compact_text(preset_payload.get("default_model_placeholder"))
                or str(default_placeholders.get("default_model") or "")
            )
            self._provider_preset_note.setText(
                _compact_text(preset_payload.get("note")) or str(default_placeholders.get("note") or "")
            )

        def _apply_provider_preset(self, preset_id: str, checked: bool = False) -> None:
            _ = checked
            preset = self._provider_preset_spec(preset_id)
            if preset is None:
                return
            self._provider_form_loading = True
            self._provider_active_preset_id = _compact_text(preset.get("id")) or None
            if not self._provider_form_existing_id:
                self._provider_id_input.setText(_compact_text(preset.get("provider_id")))
            self._provider_name_input.setText(_compact_text(preset.get("provider_name")))
            combo_index = self._provider_type_combo.findText(_compact_text(preset.get("api_type")) or "openai")
            if combo_index >= 0:
                self._provider_type_combo.setCurrentIndex(combo_index)
            self._provider_base_input.setText(_compact_text(preset.get("api_base")))
            if not self._provider_form_existing_id:
                self._provider_default_model_input.clear()
                self._provider_models_edit.setPlainText("")
                self._provider_headers_edit.setPlainText("")
            self._apply_provider_input_placeholders(
                api_type=_compact_text(preset.get("api_type")) or "openai",
                preset=preset,
            )
            if self._provider_form_existing_id and _compact_text(preset.get("api_type")).lower() != "ollama":
                self._provider_api_key_input.setPlaceholderText("Required to save changes.")
            self._provider_form_loading = False
            self._provider_form_dirty = True
            self._set_provider_validation_payload({})
            self.statusBar().showMessage(f"Applied provider preset: {_compact_text(preset.get('label'))}")

        def _on_provider_api_type_changed(self, value: str) -> None:
            if self._provider_form_loading:
                return
            self._provider_active_preset_id = None
            self._apply_provider_input_placeholders(api_type=value)

        def _current_provider_draft_api_type(self) -> str:
            return _compact_text(self._provider_type_combo.currentText()) or "openai"

        def _current_provider_draft_api_base(self) -> str:
            return _normalize_desktop_provider_api_base(
                api_type=self._current_provider_draft_api_type(),
                api_base=self._provider_base_input.text(),
            )

        def _current_provider_draft_api_key(self) -> str:
            return _resolve_desktop_provider_api_key(
                api_type=self._current_provider_draft_api_type(),
                api_base=self._current_provider_draft_api_base(),
                api_key=self._provider_api_key_input.text(),
            )

        def _set_provider_validation_payload(self, payload: dict[str, Any] | None) -> None:
            self._provider_validation_payload = dict(payload or {})
            self._provider_validation_note.setText(
                format_provider_validation_text(self._provider_validation_payload)
            )

        def _provider_draft_provider_id(self) -> str:
            return self._provider_form_existing_id or _compact_text(self._provider_id_input.text())

        def _provider_draft_model_ids(self) -> list[str]:
            return self._parse_provider_lines(self._provider_models_edit.toPlainText())

        def _current_provider_draft_model_entry(self) -> dict[str, str] | None:
            row = int(self._provider_draft_model_list.currentRow())
            if row < 0 or row >= len(self._provider_draft_model_entries):
                return None
            return self._provider_draft_model_entries[row]

        def _refresh_provider_model_shortcuts(self, *_: Any, preferred_model_id: str | None = None) -> None:
            current_entry = self._current_provider_draft_model_entry()
            target_model_id = _compact_text(preferred_model_id) or _compact_text(
                (current_entry or {}).get("model_id")
            )
            self._provider_draft_model_entries = collect_provider_draft_model_entries(
                provider_id=self._provider_draft_provider_id(),
                model_ids=self._provider_draft_model_ids(),
                default_model_id=self._provider_default_model_input.text(),
                registry_payload=self._ops_registry_payload,
                feature_bindings=self._feature_bindings,
            )
            self._provider_draft_model_ids_by_row = [
                str(entry.get("model_id") or "") for entry in self._provider_draft_model_entries
            ]
            self._provider_draft_model_list.blockSignals(True)
            self._provider_draft_model_list.clear()
            for entry in self._provider_draft_model_entries:
                self._provider_draft_model_list.addItem(entry["label"])
            if not self._provider_draft_model_entries:
                self._provider_draft_model_list.setCurrentRow(-1)
                self._provider_draft_model_list.blockSignals(False)
                self._provider_model_shortcuts_note.setText(
                    "Add or discover model ids in the draft to classify them here."
                )
                self._refresh_provider_action_state()
                return
            target_row = 0
            if target_model_id:
                try:
                    target_row = self._provider_draft_model_ids_by_row.index(target_model_id)
                except ValueError:
                    target_row = 0
            self._provider_draft_model_list.setCurrentRow(target_row)
            self._provider_draft_model_list.blockSignals(False)
            self._on_provider_draft_model_selected(target_row)

        def _on_provider_draft_model_selected(self, row: int) -> None:
            if row < 0 or row >= len(self._provider_draft_model_entries):
                self._provider_model_shortcuts_note.setText(
                    "Select one draft model to set it as default, classify it, or bind it to a feature role."
                )
                self._refresh_provider_action_state()
                return
            entry = self._provider_draft_model_entries[row]
            model_role = _compact_text(entry.get("model_role")) or "unclassified"
            combo_index = self._provider_draft_model_role_combo.findText(model_role)
            self._provider_draft_model_role_combo.setCurrentIndex(combo_index if combo_index >= 0 else 0)
            feature_roles = _compact_text(entry.get("feature_roles"))
            if feature_roles:
                first_feature_role = feature_roles.split(",", 1)[0]
                feature_index = self._provider_draft_feature_combo.findText(first_feature_role)
                if feature_index >= 0:
                    self._provider_draft_feature_combo.setCurrentIndex(feature_index)
            status = _compact_text(entry.get("status")) or "draft"
            self._provider_model_shortcuts_note.setText(
                f"Selected {entry.get('model_id')} ({status}). "
                "Use As Default only edits the draft. Role and feature actions write into the saved registry."
            )
            self._refresh_provider_action_state()

        def _use_selected_provider_model_as_default(self, checked: bool = False) -> None:
            _ = checked
            entry = self._current_provider_draft_model_entry()
            if not entry:
                self.statusBar().showMessage("Select a draft model first.")
                return
            model_id = _compact_text(entry.get("model_id"))
            if not model_id:
                self.statusBar().showMessage("Select a draft model first.")
                return
            self._provider_default_model_input.setText(model_id)
            self._provider_form_dirty = True
            self._refresh_provider_model_shortcuts(preferred_model_id=model_id)
            self.statusBar().showMessage(f"Default model set to {model_id}.")

        def _require_saved_provider_draft_model_target(self) -> tuple[str, dict[str, str]] | None:
            entry = self._current_provider_draft_model_entry()
            if not entry:
                self.statusBar().showMessage("Select a draft model first.")
                return None
            provider_id = self._provider_form_existing_id or ""
            if not provider_id:
                self.statusBar().showMessage("Save the provider first, then classify or bind its models.")
                return None
            if _compact_text(entry.get("status")) != "saved":
                self.statusBar().showMessage(
                    "Save the provider first so the current draft models enter the registry."
                )
                return None
            return provider_id, entry

        def _set_selected_provider_draft_model_role(self, checked: bool = False) -> None:
            _ = checked
            target = self._require_saved_provider_draft_model_target()
            if target is None:
                return
            provider_id, entry = target
            model_role = _compact_text(self._provider_draft_model_role_combo.currentText()) or "unclassified"
            try:
                self._model_client.set_model_role_sync(
                    StudioModelRoleRequest(
                        source="custom",
                        provider_id=provider_id,
                        model_id=str(entry.get("model_id") or ""),
                        model_role=model_role,
                    )
                )
            except Exception as exc:
                detail = desktop_error_detail(exc)
                self._append_activity(f"Provider draft role update failed: {detail}", kind="error")
                self.statusBar().showMessage("Provider model role update failed.")
                return
            self._append_activity(
                f"Set provider draft model role: {entry.get('model_id')} -> {model_role}",
                kind="model",
            )
            self.statusBar().showMessage("Provider model role updated.")
            self._refresh_ops_registry_snapshot()
            self._refresh_provider_model_shortcuts(preferred_model_id=str(entry.get("model_id") or ""))

        def _bind_selected_provider_draft_feature_model(self, checked: bool = False) -> None:
            _ = checked
            target = self._require_saved_provider_draft_model_target()
            if target is None:
                return
            provider_id, entry = target
            feature_role = _compact_text(self._provider_draft_feature_combo.currentText()) or "embedding"
            try:
                self._model_client.bind_feature_model_sync(
                    StudioFeatureModelBindingRequest(
                        feature_role=feature_role,
                        source="custom",
                        provider_id=provider_id,
                        model_id=str(entry.get("model_id") or ""),
                    )
                )
            except Exception as exc:
                detail = desktop_error_detail(exc)
                self._append_activity(f"Provider draft feature bind failed: {detail}", kind="error")
                self.statusBar().showMessage("Provider feature binding failed.")
                return
            self._append_activity(
                f"Bound provider draft model: {entry.get('model_id')} -> {feature_role}",
                kind="model",
            )
            self.statusBar().showMessage("Provider feature binding updated.")
            self._refresh_ops_registry_snapshot()
            self._refresh_provider_model_shortcuts(preferred_model_id=str(entry.get("model_id") or ""))

        def eventFilter(self, obj: Any, event: Any) -> bool:
            if (
                obj is self._composer
                and event.type() == qtcore.QEvent.Type.KeyPress
                and event.key() in {qtcore.Qt.Key.Key_Return, qtcore.Qt.Key.Key_Enter}
                and bool(event.modifiers() & qtcore.Qt.KeyboardModifier.ControlModifier)
            ):
                self._send_current_prompt()
                return True
            if obj is self._title_drag_bar:
                if (
                    event.type() == qtcore.QEvent.Type.MouseButtonDblClick
                    and event.button() == qtcore.Qt.MouseButton.LeftButton
                ):
                    self._title_drag_pending = False
                    self._title_drag_press_global = None
                    self._toggle_window_maximize_restore()
                    return True
                if (
                    event.type() == qtcore.QEvent.Type.MouseButtonPress
                    and event.button() == qtcore.Qt.MouseButton.LeftButton
                ):
                    self._title_drag_pending = True
                    self._title_drag_press_global = self._event_global_point(event)
                    self._title_drag_bar.setCursor(qtcore.Qt.CursorShape.ClosedHandCursor)
                    return False
                if (
                    event.type() == qtcore.QEvent.Type.MouseMove
                    and self._title_drag_pending
                    and bool(event.buttons() & qtcore.Qt.MouseButton.LeftButton)
                ):
                    global_point = self._event_global_point(event)
                    if (
                        global_point is not None
                        and self._title_drag_press_global is not None
                        and (
                            global_point - self._title_drag_press_global
                        ).manhattanLength()
                        >= qtwidgets.QApplication.startDragDistance()
                    ):
                        self._title_drag_pending = False
                        self._title_drag_press_global = None
                        self._title_drag_bar.setCursor(qtcore.Qt.CursorShape.OpenHandCursor)
                        if self._start_window_move():
                            return True
                if (
                    event.type() == qtcore.QEvent.Type.MouseButtonRelease
                    and event.button() == qtcore.Qt.MouseButton.LeftButton
                ):
                    self._title_drag_pending = False
                    self._title_drag_press_global = None
                    self._title_drag_bar.setCursor(qtcore.Qt.CursorShape.OpenHandCursor)
                    return False
            if obj is self._desktop_central:
                if event.type() == qtcore.QEvent.Type.MouseMove:
                    self._update_resize_cursor(self._event_global_point(event))
                elif (
                    event.type() == qtcore.QEvent.Type.MouseButtonPress
                    and event.button() == qtcore.Qt.MouseButton.LeftButton
                    and self._start_window_resize(self._event_global_point(event))
                ):
                    return True
                elif event.type() == qtcore.QEvent.Type.Leave:
                    self.unsetCursor()
                    self._desktop_central.unsetCursor()
            return super().eventFilter(obj, event)

        def keyPressEvent(self, event: Any) -> None:  # noqa: N802 - Qt naming
            if (
                event.key() == qtcore.Qt.Key.Key_K
                and bool(event.modifiers() & qtcore.Qt.KeyboardModifier.ControlModifier)
            ):
                self._open_command_palette()
                return
            super().keyPressEvent(event)

        def _on_page_nav_changed(self, row: int) -> None:
            if not hasattr(self, "_page_nav_list"):
                return
            if row < 0 or row >= self._page_nav_list.count():
                return
            item = self._page_nav_list.item(row)
            page_id = _compact_text(item.data(qtcore.Qt.ItemDataRole.UserRole)) if item is not None else ""
            self._switch_to_page(page_id or "chat")

        def _switch_to_page(self, page_id: str) -> None:
            normalized = _compact_text(page_id).lower() or "chat"
            index = self._page_index_by_id.get(normalized)
            if index is None:
                return
            self._page_stack.setCurrentIndex(index)
            spec = next((item for item in self._page_specs if item.get("id") == normalized), None) or {}
            self._page_title.setText(_compact_text(spec.get("label")) or normalized.title())
            for target_id, button in self._page_nav_buttons.items():
                self._style_page_nav_button(button, active=target_id == normalized)

        def _select_page_by_id(self, page_id: str) -> None:
            normalized = _compact_text(page_id).lower()
            self._switch_to_page(normalized)

        def _sync_settings_controls(self) -> None:
            self._settings_auto_refresh_checkbox.blockSignals(True)
            self._settings_auto_refresh_checkbox.setChecked(self._auto_refresh_enabled)
            self._settings_auto_refresh_checkbox.blockSignals(False)
            self._settings_refresh_interval_spin.blockSignals(True)
            self._settings_refresh_interval_spin.setValue(int(self._refresh_interval_ms))
            self._settings_refresh_interval_spin.blockSignals(False)
            self._settings_workspace_path.setText(self._effective_workspace_dir())
            self._settings_gateway_path.setText(self._connection.base_url)
            status = "Auto refresh active." if self._auto_refresh_enabled else "Auto refresh paused."
            self._settings_pref_status.setText(
                f"{status} The desktop snapshot cadence is {int(self._refresh_interval_ms)} ms."
            )

        def _set_auto_refresh_enabled(self, enabled: bool) -> None:
            self._auto_refresh_enabled = bool(enabled)
            if not hasattr(self, "_timer"):
                return
            if self._auto_refresh_enabled:
                self._timer.start()
            else:
                self._timer.stop()
            self._sync_settings_controls()
            self._refresh_settings_page()

        def _set_refresh_interval_ms(self, value: int) -> None:
            self._refresh_interval_ms = max(1000, int(value))
            if hasattr(self, "_timer"):
                self._timer.setInterval(self._refresh_interval_ms)
            self._sync_settings_controls()
            self._refresh_settings_page()

        def refresh_snapshot(self, checked: bool = False) -> None:
            _ = checked
            self._refresh_workspace_snapshot()
            self._refresh_health()
            self._refresh_models()
            self._refresh_ops_registry_snapshot()
            self._refresh_ops_providers_snapshot()
            if not self._send_busy:
                self._refresh_sessions()
            self._refresh_settings_page()
            self._refresh_memory_page()

        @staticmethod
        def _registry_model_ref(entry: dict[str, str] | None) -> str:
            if not isinstance(entry, dict):
                return ""
            return "|".join(
                [
                    _compact_text(entry.get("source")),
                    _compact_text(entry.get("provider_id")),
                    _compact_text(entry.get("model_id")),
                ]
            )

        def _current_registry_model_entry(self) -> dict[str, str] | None:
            row = int(self._model_registry_list.currentRow())
            if row < 0 or row >= len(self._registry_model_entries):
                return None
            return self._registry_model_entries[row]

        def _current_provider_id(self) -> str | None:
            row = int(self._provider_list.currentRow())
            if row < 0 or row >= len(self._provider_ids_by_row):
                return None
            return self._provider_ids_by_row[row]

        def _selected_provider_payload(self) -> dict[str, Any] | None:
            provider_id = self._current_provider_id()
            if not provider_id:
                return None
            for item in list((self._ops_provider_payload or {}).get("items") or []):
                if _compact_text(item.get("id")) == provider_id:
                    return item if isinstance(item, dict) else None
            return None

        def _refresh_ops_registry_snapshot(self, checked: bool = False) -> None:
            _ = checked
            selected_ref = self._registry_model_ref(self._current_registry_model_entry())
            try:
                self._ops_registry_payload = surface_payload_from_dto(
                    self._model_client.list_registry_models_sync()
                )
                self._feature_bindings = surface_payload_from_dto(
                    self._model_client.list_feature_model_bindings_sync()
                )
                self._feature_bindings_view.setPlainText(format_feature_bindings_text(self._feature_bindings))
                self._refresh_registry_model_list(preferred_ref=selected_ref)
                self._refresh_provider_model_shortcuts()
            except Exception as exc:
                detail = desktop_error_detail(exc)
                self._model_registry_detail_view.setPlainText(f"Failed to load model registry.\n{detail}")
                self._feature_bindings_view.setPlainText(f"Failed to load feature bindings.\n{detail}")
                self._append_activity(f"Model registry refresh failed: {detail}", kind="error")
                self._registry_model_entries = []
                self._registry_model_keys_by_row = []
                self._refresh_provider_model_shortcuts()
                self._refresh_registry_action_state()

        def _refresh_registry_model_list(
            self,
            *_: Any,
            preferred_ref: str | None = None,
        ) -> None:
            filter_text = self._model_registry_search.text() if hasattr(self, "_model_registry_search") else ""
            self._registry_model_entries = collect_registry_model_entries(
                self._ops_registry_payload,
                filter_text=filter_text,
            )
            self._registry_model_keys_by_row = [
                self._registry_model_ref(entry) for entry in self._registry_model_entries
            ]
            target_ref = preferred_ref or self._registry_model_ref(self._current_registry_model_entry())

            self._model_registry_list.blockSignals(True)
            self._model_registry_list.clear()
            for entry in self._registry_model_entries:
                item = qtwidgets.QListWidgetItem(entry["label"])
                item.setToolTip(str(entry.get("detail") or entry["label"]))
                self._model_registry_list.addItem(item)
            if not self._registry_model_entries:
                self._model_registry_list.blockSignals(False)
                self._model_registry_detail_view.setPlainText(
                    "No registry models match the current filter."
                )
                self._refresh_registry_action_state()
                return
            target_row = 0
            if target_ref:
                try:
                    target_row = self._registry_model_keys_by_row.index(target_ref)
                except ValueError:
                    target_row = 0
            self._model_registry_list.setCurrentRow(target_row)
            self._model_registry_list.blockSignals(False)
            self._on_registry_model_selected(target_row)

        def _on_registry_model_selected(self, row: int) -> None:
            if row < 0 or row >= len(self._registry_model_entries):
                self._model_registry_detail_view.setPlainText(
                    "Select a model to inspect role, capability facts, and feature bindings."
                )
                self._refresh_registry_action_state()
                return
            entry = self._registry_model_entries[row]
            self._registry_model_role_combo.setCurrentText(
                _compact_text(entry.get("model_role")) or "unclassified"
            )
            self._model_registry_detail_view.setPlainText(
                format_registry_model_detail_text(entry, feature_bindings=self._feature_bindings)
            )
            self._refresh_registry_action_state()

        def _refresh_registry_action_state(self) -> None:
            has_selection = self._current_registry_model_entry() is not None
            self._registry_set_role_button.setDisabled(self._send_busy or not has_selection)
            self._registry_probe_button.setDisabled(self._send_busy or not has_selection)
            self._registry_bind_feature_button.setDisabled(self._send_busy or not has_selection)
            self._registry_clear_feature_button.setDisabled(self._send_busy)

        def _set_selected_registry_model_role(self, checked: bool = False) -> None:
            _ = checked
            entry = self._current_registry_model_entry()
            if not entry:
                self.statusBar().showMessage("Select a registry model first.")
                return
            model_role = _compact_text(self._registry_model_role_combo.currentText()) or "unclassified"
            try:
                self._model_client.set_model_role_sync(
                    StudioModelRoleRequest(
                        source=str(entry.get("source") or ""),
                        provider_id=str(entry.get("provider_id") or ""),
                        model_id=str(entry.get("model_id") or ""),
                        model_role=model_role,
                    )
                )
            except Exception as exc:
                detail = desktop_error_detail(exc)
                self._append_activity(f"Set model role failed: {detail}", kind="error")
                self.statusBar().showMessage("Model role update failed.")
                return
            self._append_activity(
                f"Set role {model_role} for {entry.get('provider_id')}/{entry.get('model_id')}",
                kind="model",
            )
            self.statusBar().showMessage("Model role updated.")
            self._refresh_ops_registry_snapshot()

        def _probe_selected_registry_model(self, checked: bool = False) -> None:
            _ = checked
            entry = self._current_registry_model_entry()
            if not entry:
                self.statusBar().showMessage("Select a registry model first.")
                return
            try:
                payload = surface_payload_from_dto(
                    self._model_client.probe_model_capabilities_sync(
                        StudioModelCapabilityProbeRequest(
                            source=str(entry.get("source") or ""),
                            provider_id=str(entry.get("provider_id") or ""),
                            model_id=str(entry.get("model_id") or ""),
                        )
                    )
                )
                notes = ", ".join(str(item) for item in list(payload.get("notes") or [])[:3])
                updated_fields = ", ".join(str(item) for item in list(payload.get("updated_fields") or []))
            except Exception as exc:
                detail = desktop_error_detail(exc)
                self._append_activity(f"Capability probe failed: {detail}", kind="error")
                self.statusBar().showMessage("Capability probe failed.")
                return
            detail = "\n".join(part for part in [updated_fields, notes] if part)
            self._append_activity(
                f"Capability probe completed for {entry.get('model_id')}",
                kind="model",
                detail=detail or None,
            )
            self.statusBar().showMessage("Capability probe completed.")
            self._refresh_ops_registry_snapshot()

        def _bind_selected_registry_feature_model(self, checked: bool = False) -> None:
            _ = checked
            entry = self._current_registry_model_entry()
            if not entry:
                self.statusBar().showMessage("Select a registry model first.")
                return
            feature_role = _compact_text(self._feature_binding_role_combo.currentText()) or "embedding"
            try:
                self._model_client.bind_feature_model_sync(
                    StudioFeatureModelBindingRequest(
                        feature_role=feature_role,
                        source=str(entry.get("source") or ""),
                        provider_id=str(entry.get("provider_id") or ""),
                        model_id=str(entry.get("model_id") or ""),
                    )
                )
            except Exception as exc:
                detail = desktop_error_detail(exc)
                self._append_activity(f"Feature binding failed: {detail}", kind="error")
                self.statusBar().showMessage("Feature binding failed.")
                return
            self._append_activity(
                f"Bound {feature_role} to {entry.get('provider_id')}/{entry.get('model_id')}",
                kind="model",
            )
            self.statusBar().showMessage("Feature binding updated.")
            self._refresh_ops_registry_snapshot()

        def _clear_selected_feature_binding(self, checked: bool = False) -> None:
            _ = checked
            feature_role = _compact_text(self._feature_binding_role_combo.currentText()) or "embedding"
            try:
                self._model_client.clear_feature_model_binding_sync(feature_role=feature_role)
            except Exception as exc:
                detail = desktop_error_detail(exc)
                self._append_activity(f"Clear feature binding failed: {detail}", kind="error")
                self.statusBar().showMessage("Feature binding clear failed.")
                return
            self._append_activity(f"Cleared {feature_role} feature binding", kind="model")
            self.statusBar().showMessage("Feature binding cleared.")
            self._refresh_ops_registry_snapshot()

        def _refresh_ops_providers_snapshot(self, checked: bool = False) -> None:
            _ = checked
            selected_provider_id = self._current_provider_id() or self._provider_form_existing_id
            try:
                self._ops_provider_payload = surface_payload_from_dto(
                    self._provider_client.list_providers_sync()
                )
            except Exception as exc:
                detail = desktop_error_detail(exc)
                self._provider_detail_view.setPlainText(f"Failed to load providers.\n{detail}")
                self._append_activity(f"Provider refresh failed: {detail}", kind="error")
                self._provider_entries = []
                self._provider_ids_by_row = []
                self._provider_list.clear()
                self._refresh_provider_action_state()
                return

            self._provider_entries = collect_provider_entries(self._ops_provider_payload)
            self._provider_ids_by_row = [str(entry.get("provider_id") or "") for entry in self._provider_entries]
            self._provider_list.blockSignals(True)
            self._provider_list.clear()
            for entry in self._provider_entries:
                item = qtwidgets.QListWidgetItem(entry["label"])
                item.setToolTip(str(entry.get("detail") or entry["label"]))
                self._provider_list.addItem(item)
            if not self._provider_entries:
                self._provider_list.blockSignals(False)
                self._provider_detail_view.setPlainText(
                    "No providers are configured yet. Create a draft to add one."
                )
                if not self._provider_form_dirty:
                    self._reset_provider_draft()
                self._refresh_provider_action_state()
                return

            if not selected_provider_id and self._provider_form_existing_id is None:
                self._provider_list.setCurrentRow(-1)
                self._provider_list.blockSignals(False)
                self._refresh_provider_action_state()
                return

            target_row = 0
            if selected_provider_id:
                try:
                    target_row = self._provider_ids_by_row.index(selected_provider_id)
                except ValueError:
                    target_row = 0
            self._provider_list.setCurrentRow(target_row)
            self._provider_list.blockSignals(False)
            self._on_provider_selected(target_row)

        def _on_provider_selected(self, row: int) -> None:
            if row < 0 or row >= len(self._provider_ids_by_row):
                self._provider_detail_view.setPlainText(
                    "Select a provider to inspect configuration and health."
                )
                self._refresh_provider_action_state()
                return
            provider = self._selected_provider_payload()
            if provider is None:
                self._refresh_provider_action_state()
                return
            if not self._provider_form_dirty or self._provider_form_existing_id != _compact_text(provider.get("id")):
                self._populate_provider_form(provider)
            self._refresh_provider_detail()
            self._refresh_provider_action_state()

        def _populate_provider_form(self, provider: dict[str, Any] | None = None) -> None:
            payload = provider if isinstance(provider, dict) else {}
            provider_id = _compact_text(payload.get("id"))
            headers = payload.get("headers") if isinstance(payload.get("headers"), dict) else {}
            models = "\n".join(_compact_text(item) for item in list(payload.get("models") or []) if _compact_text(item))
            self._provider_form_loading = True
            self._provider_active_preset_id = None
            self._provider_form_existing_id = provider_id or None
            self._provider_id_input.setText(provider_id)
            self._provider_id_input.setDisabled(bool(provider_id))
            self._provider_name_input.setText(_compact_text(payload.get("name")))
            api_base = _normalize_desktop_provider_api_base(
                api_type=payload.get("api_type"),
                api_base=payload.get("api_base"),
            )
            api_type = _desktop_provider_api_type(payload.get("api_type"), api_base) or "openai"
            index = self._provider_type_combo.findText(api_type)
            if index >= 0:
                self._provider_type_combo.setCurrentIndex(index)
            else:
                self._provider_type_combo.setCurrentIndex(0)
            self._provider_base_input.setText(api_base)
            self._provider_api_key_input.clear()
            self._provider_api_key_input.setPlaceholderText(
                "Required to save changes."
                if provider_id and api_type != "ollama"
                else "Leave blank for local Ollama."
            )
            self._provider_default_model_input.setText(_compact_text(payload.get("selected_model_id")))
            self._provider_models_edit.setPlainText(models)
            self._provider_headers_edit.setPlainText(
                json.dumps(headers, ensure_ascii=False, indent=2) if headers else ""
            )
            self._provider_enabled_checkbox.setChecked(bool(payload.get("enabled", True)))
            self._provider_priority_spin.setValue(int(payload.get("priority") or 0))
            self._provider_timeout_spin.setValue(int(payload.get("timeout") or 60))
            self._apply_provider_input_placeholders(api_type=api_type)
            if provider_id and api_type != "ollama":
                self._provider_api_key_input.setPlaceholderText("Required to save changes.")
            self._provider_form_loading = False
            self._provider_form_dirty = False
            self._set_provider_validation_payload({})
            self._refresh_provider_model_shortcuts()

        def _reset_provider_draft(self, checked: bool = False) -> None:
            _ = checked
            self._provider_list.blockSignals(True)
            self._provider_list.clearSelection()
            self._provider_list.setCurrentRow(-1)
            self._provider_list.blockSignals(False)
            self._populate_provider_form(None)
            self._provider_id_input.setDisabled(False)
            self._provider_detail_view.setPlainText(
                "Draft a provider configuration, discover models, then save it into the provider catalog."
            )
            self._apply_provider_input_placeholders(api_type=_compact_text(self._provider_type_combo.currentText()) or "openai")
            self._set_provider_validation_payload({})
            self._refresh_provider_model_shortcuts()
            self._refresh_provider_action_state()

        @staticmethod
        def _parse_provider_lines(text: str) -> list[str]:
            values: list[str] = []
            for raw_line in str(text or "").replace(",", "\n").splitlines():
                normalized = _compact_text(raw_line)
                if normalized:
                    values.append(normalized)
            return values

        def _collect_provider_form_payload(self) -> dict[str, Any]:
            provider_id = _compact_text(self._provider_id_input.text())
            if not provider_id:
                raise ValueError("provider id is required")
            name = _compact_text(self._provider_name_input.text()) or provider_id
            api_type = self._current_provider_draft_api_type()
            display_api_type = _desktop_provider_api_type(api_type, self._provider_base_input.text())
            api_base = self._current_provider_draft_api_base()
            if not api_base:
                raise ValueError("base URL is required")
            api_key = self._current_provider_draft_api_key()
            if not api_key:
                raise ValueError(
                    "API key is required to save remote OpenAI/Anthropic providers"
                )
            headers_text = self._provider_headers_edit.toPlainText().strip()
            headers: dict[str, str] = {}
            if headers_text:
                parsed_headers = json.loads(headers_text)
                if not isinstance(parsed_headers, dict):
                    raise ValueError("headers must be a JSON object")
                headers = {str(key): str(value) for key, value in parsed_headers.items()}
            models = self._parse_provider_lines(self._provider_models_edit.toPlainText())
            if not models:
                hint = (
                    "Discover models or enter at least one local model id before saving."
                    if display_api_type == "ollama"
                    else "Discover models or enter at least one model id before saving."
                )
                raise ValueError(hint)
            selected_model_id = _compact_text(self._provider_default_model_input.text())
            if not selected_model_id and models:
                selected_model_id = models[0]
            return {
                "id": provider_id,
                "name": name,
                "api_type": api_type,
                "api_base": api_base,
                "api_key": api_key,
                "models": models,
                "selected_model_id": selected_model_id or None,
                "enabled": bool(self._provider_enabled_checkbox.isChecked()),
                "priority": int(self._provider_priority_spin.value()),
                "timeout": int(self._provider_timeout_spin.value()),
                "headers": headers,
            }

        def _validate_provider_connection(self, checked: bool = False) -> None:
            _ = checked
            api_type = self._current_provider_draft_api_type()
            api_base = self._current_provider_draft_api_base()
            if not api_base:
                self._clear_provider_validation_state()
                self._provider_validation_note.setText("Base URL is required before testing the connection.")
                self.statusBar().showMessage("Base URL is required before testing the connection.")
                return
            api_key = self._current_provider_draft_api_key()
            if not api_key and _desktop_provider_api_type(api_type, api_base) != "ollama":
                self._clear_provider_validation_state()
                self._provider_validation_note.setText(
                    "API key is required before testing a remote OpenAI/Anthropic provider."
                )
                self.statusBar().showMessage("API key is required before testing the connection.")
                return
            try:
                payload = surface_payload_from_dto(
                    self._provider_client.validate_provider_connection_sync(
                        StudioProviderValidationRequest(
                            api_type=api_type,
                            api_base=api_base,
                            api_key=api_key or None,
                        )
                    )
                )
            except Exception as exc:
                detail = desktop_error_detail(exc)
                self._clear_provider_validation_state()
                self._provider_validation_note.setText(f"Connection test failed: {detail}")
                self._append_activity(f"Provider connection test failed: {detail}", kind="error")
                self.statusBar().showMessage("Provider connection test failed.")
                return
            self._set_provider_validation_payload(payload)
            self._append_activity(
                "Provider connection validated",
                kind="health",
                detail=_compact_text(payload.get("message")) or None,
            )
            self.statusBar().showMessage("Provider connection validated.")

        def _refresh_selected_provider_health(self, checked: bool = False) -> None:
            _ = checked
            provider = self._selected_provider_payload()
            provider_id = _compact_text((provider or {}).get("id"))
            if not provider_id:
                self.statusBar().showMessage("Select a provider first.")
                return
            try:
                health = surface_payload_from_dto(
                    self._provider_client.get_provider_health_sync(provider_id)
                )
            except Exception as exc:
                detail = desktop_error_detail(exc)
                self._append_activity(f"Provider health refresh failed: {detail}", kind="error")
                self.statusBar().showMessage("Provider health refresh failed.")
                return
            self._provider_health_cache[provider_id] = health
            self._refresh_provider_detail()
            self.statusBar().showMessage("Provider health refreshed.")

        def _refresh_provider_detail(self) -> None:
            provider = self._selected_provider_payload()
            provider_id = _compact_text((provider or {}).get("id"))
            health = self._provider_health_cache.get(provider_id, {}) if provider_id else {}
            self._provider_detail_view.setPlainText(
                format_provider_detail_text(provider, health=health)
            )

        def _refresh_provider_action_state(self) -> None:
            has_provider = bool(self._selected_provider_payload())
            current_draft_model = self._current_provider_draft_model_entry()
            has_draft_model = current_draft_model is not None
            can_write_registry_model = bool(
                self._provider_form_existing_id
                and has_draft_model
                and _compact_text((current_draft_model or {}).get("status")) == "saved"
            )
            self._provider_health_button.setDisabled(not has_provider)
            self._provider_delete_button.setDisabled(self._send_busy or not has_provider)
            self._provider_validate_button.setDisabled(self._send_busy)
            self._provider_save_button.setDisabled(self._send_busy)
            self._provider_discover_button.setDisabled(self._send_busy)
            self._provider_draft_default_button.setDisabled(self._send_busy or not has_draft_model)
            self._provider_draft_model_role_combo.setDisabled(not has_draft_model)
            self._provider_draft_set_role_button.setDisabled(self._send_busy or not can_write_registry_model)
            self._provider_draft_feature_combo.setDisabled(not has_draft_model)
            self._provider_draft_bind_feature_button.setDisabled(self._send_busy or not can_write_registry_model)

        def _save_provider_draft(self, checked: bool = False) -> None:
            _ = checked
            try:
                payload = self._collect_provider_form_payload()
            except Exception as exc:
                self.statusBar().showMessage(str(exc))
                return

            try:
                if self._provider_form_existing_id:
                    saved = self._provider_client.update_provider_sync(
                        self._provider_form_existing_id,
                        StudioProviderUpsertRequest.model_validate(payload),
                    )
                else:
                    saved = self._provider_client.create_provider_sync(
                        StudioProviderUpsertRequest.model_validate(payload)
                    )
            except Exception as exc:
                detail = desktop_error_detail(exc)
                self._append_activity(f"Provider save failed: {detail}", kind="error")
                self.statusBar().showMessage("Provider save failed.")
                return

            saved_payload = surface_payload_from_dto(saved)
            saved_id = _compact_text(saved_payload.get("id")) or payload["id"]
            self._append_activity(f"Provider saved: {saved_id}", kind="health")
            self.statusBar().showMessage(f"Provider saved: {saved_id}")
            self._provider_form_existing_id = saved_id
            self._provider_form_dirty = False
            self._refresh_ops_providers_snapshot()
            self._refresh_ops_registry_snapshot()
            self._refresh_models()
            self._refresh_provider_model_shortcuts(
                preferred_model_id=_compact_text(self._provider_default_model_input.text())
            )

        def _delete_selected_provider(self, checked: bool = False) -> None:
            _ = checked
            provider = self._selected_provider_payload()
            provider_id = _compact_text((provider or {}).get("id"))
            if not provider_id:
                self.statusBar().showMessage("Select a provider first.")
                return
            answer = qtwidgets.QMessageBox.question(
                self,
                "Delete Provider",
                f"Delete provider '{provider_id}' from the catalog?",
            )
            if answer != qtwidgets.QMessageBox.StandardButton.Yes:
                return
            try:
                self._provider_client.delete_provider_sync(provider_id)
            except Exception as exc:
                detail = desktop_error_detail(exc)
                self._append_activity(f"Provider delete failed: {detail}", kind="error")
                self.statusBar().showMessage("Provider delete failed.")
                return
            self._provider_health_cache.pop(provider_id, None)
            self._append_activity(f"Provider deleted: {provider_id}", kind="health")
            self.statusBar().showMessage(f"Provider deleted: {provider_id}")
            self._reset_provider_draft()
            self._refresh_ops_providers_snapshot()
            self._refresh_ops_registry_snapshot()
            self._refresh_models()

        def _discover_provider_models(self, checked: bool = False) -> None:
            _ = checked
            api_type = self._current_provider_draft_api_type()
            api_base = self._current_provider_draft_api_base()
            api_key = self._current_provider_draft_api_key()
            if not api_base:
                self.statusBar().showMessage("Base URL is required for discovery.")
                return
            if not api_key and _desktop_provider_api_type(api_type, api_base) != "ollama":
                self.statusBar().showMessage("API key is required for discovery.")
                return
            try:
                payload = surface_payload_from_dto(
                    self._provider_client.discover_provider_models_sync(
                        StudioProviderModelDiscoveryRequest(
                            api_type=api_type,
                            api_base=api_base,
                            api_key=api_key,
                        )
                    )
                )
            except Exception as exc:
                detail = desktop_error_detail(exc)
                self._clear_provider_validation_state()
                self._provider_validation_note.setText(f"Discovery failed: {detail}")
                self._append_activity(f"Provider discovery failed: {detail}", kind="error")
                self.statusBar().showMessage("Provider discovery failed.")
                return
            models = list(payload.get("models") or [])
            model_ids = [
                _compact_text(item.get("model_id") if isinstance(item, dict) else item)
                for item in models
            ]
            model_ids = [item for item in model_ids if item]
            latest_model_id = _compact_text(payload.get("latest_model_id"))
            self._provider_form_loading = True
            self._provider_models_edit.setPlainText("\n".join(model_ids))
            if latest_model_id:
                self._provider_default_model_input.setText(latest_model_id)
            self._provider_form_loading = False
            self._provider_form_dirty = True
            self._set_provider_validation_payload(
                {
                    "status": "reachable" if model_ids else "reachable_no_models",
                    "model_count": len(model_ids),
                    "latest_model_id": latest_model_id or None,
                    "message": (
                        "Discovery completed. Review the imported model ids before saving."
                        if model_ids
                        else "Discovery completed, but no models were listed by the provider."
                    ),
                    "models": models,
                }
            )
            self._refresh_provider_model_shortcuts(preferred_model_id=latest_model_id or None)
            self._append_activity(
                f"Discovered {len(model_ids)} provider models",
                kind="health",
                detail=f"latest={latest_model_id or '-'}",
            )
            self.statusBar().showMessage("Provider models discovered.")

        def _refresh_settings_page(self) -> None:
            self._sync_settings_controls()
            self._settings_view.setPlainText(
                format_settings_summary_text(
                    connection=self._connection,
                    selected_session_detail=self._selected_session_detail,
                    workspace_summary=self._workspace_summary_payload,
                    active_workspace=self._active_workspace_summary_payload,
                    workspace_runtime_summary=self._workspace_runtime_payload,
                    workspace_list=self._workspace_list_payload,
                    model_catalog=self._model_catalog,
                    registry_payload=self._ops_registry_payload,
                    provider_payload=self._ops_provider_payload,
                    feature_bindings=self._feature_bindings,
                    refresh_interval_ms=self._refresh_interval_ms,
                    auto_refresh_enabled=self._auto_refresh_enabled,
                )
            )

        def _refresh_sessions_overview(self) -> None:
            selected_session_id = self._current_session_id()
            self._sessions_overview_list.blockSignals(True)
            self._sessions_overview_list.clear()
            for row in range(self._session_list.count()):
                item = self._session_list.item(row)
                self._sessions_overview_list.addItem(item.text() if item is not None else "-")
            target_row = -1
            if selected_session_id and selected_session_id in self._session_ids_by_row:
                target_row = self._session_ids_by_row.index(selected_session_id)
            self._sessions_overview_list.setCurrentRow(target_row)
            self._sessions_overview_list.blockSignals(False)
            self._sessions_transcript_view.setHtml(render_conversation_html(self._conversation_messages))
            self._sessions_overview_detail_view.setPlainText(
                format_session_context_text(self._selected_session_detail, self._selected_run_summary)
                if self._selected_session_detail
                else "No session selected."
            )
            self._sessions_open_chat_button.setDisabled(target_row < 0)

        def _on_sessions_overview_selected(self, row: int) -> None:
            if row < 0 or row >= len(self._session_ids_by_row):
                return
            self._force_select_session(self._session_ids_by_row[row])

        def _open_selected_session_in_chat(self, checked: bool = False) -> None:
            _ = checked
            row = int(self._sessions_overview_list.currentRow())
            if row < 0 or row >= len(self._session_ids_by_row):
                self.statusBar().showMessage("Select a session first.")
                return
            self._force_select_session(self._session_ids_by_row[row])
            self._select_page_by_id("chat")

        def _memory_workspace_dir(self) -> str:
            return self._effective_workspace_dir()

        def _refresh_memory_page(self, checked: bool = False) -> None:
            _ = checked
            selected_path = self._selected_memory_file_path
            workspace_dir = self._memory_workspace_dir()
            try:
                self._memory_summary_payload = surface_payload_from_dto(
                    self._memory_client.get_ops_memory_summary_sync(
                        workspace_dir=workspace_dir
                    )
                )
            except Exception as exc:
                self._memory_summary_view.setPlainText(
                    f"Failed to load memory summary.\n{desktop_error_detail(exc)}"
                )
                return

            self._memory_file_entries = collect_memory_file_entries(
                self._memory_summary_payload,
                workspace_dir=workspace_dir,
            )
            self._memory_file_paths_by_row = [entry["path"] for entry in self._memory_file_entries]
            self._memory_summary_view.setPlainText(
                format_memory_summary_text(
                    self._memory_summary_payload,
                    search_payload=self._memory_search_payload,
                    selected_path=selected_path,
                )
            )

            self._memory_file_list.blockSignals(True)
            self._memory_file_list.clear()
            for entry in self._memory_file_entries:
                self._memory_file_list.addItem(entry["label"])
            target_row = -1
            if selected_path and selected_path in self._memory_file_paths_by_row:
                target_row = self._memory_file_paths_by_row.index(selected_path)
            elif self._memory_file_paths_by_row:
                target_row = 0
            self._memory_file_list.setCurrentRow(target_row)
            self._memory_file_list.blockSignals(False)
            if target_row >= 0:
                self._on_memory_file_selected(target_row)
            else:
                self._selected_memory_file_path = None
                self._memory_file_path_value.setText("No file selected")
                self._memory_editor.setPlainText("")

        def _on_memory_file_selected(self, row: int) -> None:
            if row < 0 or row >= len(self._memory_file_paths_by_row):
                return
            self._load_memory_file(self._memory_file_paths_by_row[row])

        def _search_memory_notes(self, checked: bool = False) -> None:
            _ = checked
            workspace_dir = self._memory_workspace_dir()
            query = self._memory_search_input.text()
            try:
                self._memory_search_payload = surface_payload_from_dto(
                    self._memory_client.search_ops_memory_sync(
                        query=query,
                        limit=50,
                        workspace_dir=workspace_dir,
                    )
                )
            except Exception as exc:
                self._append_activity(f"Memory search failed: {desktop_error_detail(exc)}", kind="error")
                self.statusBar().showMessage("Memory search failed.")
                return

            self._memory_search_paths_by_row = []
            self._memory_search_results.blockSignals(True)
            self._memory_search_results.clear()
            for item in list(self._memory_search_payload.get("items") or []):
                if not isinstance(item, dict):
                    continue
                relative_path = _compact_text(item.get("path"))
                label = (
                    f"{_compact_text(item.get('category')) or '-'} | "
                    f"{_compact_text(item.get('timestamp')) or '-'} | "
                    f"{_truncate_text(item.get('content') or '', limit=72)}"
                )
                self._memory_search_results.addItem(label)
                self._memory_search_paths_by_row.append(relative_path)
            self._memory_search_results.blockSignals(False)
            self._memory_summary_view.setPlainText(
                format_memory_summary_text(
                    self._memory_summary_payload,
                    search_payload=self._memory_search_payload,
                    selected_path=self._selected_memory_file_path,
                )
            )
            self.statusBar().showMessage(
                f"Memory search completed: {int(self._memory_search_payload.get('total') or 0)} hits."
            )

        def _on_memory_search_selected(self, row: int) -> None:
            if row < 0 or row >= len(self._memory_search_paths_by_row):
                return
            relative_path = self._memory_search_paths_by_row[row]
            anchor = Path(_compact_text(self._memory_summary_payload.get("memory_root")) or self._memory_workspace_dir())
            target = (anchor / relative_path).resolve()
            self._load_memory_file(str(target))

        def _load_memory_file(self, path: str) -> None:
            target = Path(path).expanduser().resolve()
            try:
                if not target.exists():
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_text("", encoding="utf-8")
                content = target.read_text(encoding="utf-8")
            except Exception as exc:
                self._append_activity(f"Memory file load failed: {desktop_error_detail(exc)}", kind="error")
                self.statusBar().showMessage("Memory file load failed.")
                return

            self._selected_memory_file_path = str(target)
            self._memory_editor_loading = True
            self._memory_editor.setPlainText(content)
            self._memory_editor_loading = False
            self._memory_file_path_value.setText(str(target))
            self._memory_summary_view.setPlainText(
                format_memory_summary_text(
                    self._memory_summary_payload,
                    search_payload=self._memory_search_payload,
                    selected_path=self._selected_memory_file_path,
                )
            )

        def _reload_selected_memory_file(self, checked: bool = False) -> None:
            _ = checked
            if not self._selected_memory_file_path:
                self.statusBar().showMessage("Select a memory file first.")
                return
            self._load_memory_file(self._selected_memory_file_path)
            self.statusBar().showMessage("Memory file reloaded.")

        def _save_selected_memory_file(self, checked: bool = False) -> None:
            _ = checked
            if not self._selected_memory_file_path:
                self.statusBar().showMessage("Select a memory file first.")
                return
            target = Path(self._selected_memory_file_path).expanduser().resolve()
            try:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(self._memory_editor.toPlainText(), encoding="utf-8")
            except Exception as exc:
                self._append_activity(f"Memory file save failed: {desktop_error_detail(exc)}", kind="error")
                self.statusBar().showMessage("Memory file save failed.")
                return
            self._append_activity(f"Saved memory file: {target.name}", kind="status")
            self.statusBar().showMessage(f"Saved {target.name}")
            self._refresh_memory_page()

        def _open_today_memory_file(self, checked: bool = False) -> None:
            _ = checked
            workspace_dir = self._memory_workspace_dir()
            try:
                day_payload = surface_payload_from_dto(
                    self._memory_client.get_ops_memory_daily_sync(
                        day=datetime.now().date().isoformat(),
                        workspace_dir=workspace_dir,
                    )
                )
                target_path = _compact_text(day_payload.get("path"))
            except Exception:
                target_path = ""
            if not target_path:
                summary_daily_dir = _compact_text(self._memory_summary_payload.get("daily_dir"))
                base_dir = Path(summary_daily_dir or (Path(workspace_dir) / "memory")).resolve()
                target_path = str((base_dir / f"{datetime.now().date().isoformat()}.md").resolve())
            self._load_memory_file(target_path)

        def _refresh_health(self) -> None:
            try:
                payload = surface_payload_from_dto(self._system_client.get_system_health_sync())
                runtime = payload.get("runtime") if isinstance(payload, dict) else {}
                active_sessions = int((runtime or {}).get("active_sessions", 0))
                max_sessions = int((runtime or {}).get("max_active_sessions", 0))
                status = str(payload.get("status") or "unknown") if isinstance(payload, dict) else "unknown"
                status_text = status.title()
                self._status_value.setText(status_text)
                self._status_value.setToolTip(f"{status_text} | runtime {active_sessions}/{max_sessions}")
                self.statusBar().showMessage(f"Gateway healthy: {self._connection.base_url}")
            except Exception as exc:
                detail = desktop_error_detail(exc)
                status_text = "Offline"
                self._status_value.setText(status_text)
                self._status_value.setToolTip(f"{status_text} | {detail}")
                self.statusBar().showMessage("Gateway unreachable.")
                self._append_activity(f"Health check failed: {detail}", kind="error")
                self._append_managed_gateway_excerpt("Gateway health diagnostics")

        def _refresh_models(self) -> None:
            try:
                self._model_catalog = surface_payload_from_dto(
                    self._model_client.list_agent_model_candidates_sync()
                )
                self._model_options = collect_model_options(self._model_catalog)
                self._rebuild_model_combo()
                self._models_view.setPlainText(
                    format_chat_runtime_text(
                        self._model_catalog,
                        self._selected_session_detail,
                        self._selected_run_summary,
                    )
                )
                self._refresh_chat_workspace_summary()
            except Exception as exc:
                detail = desktop_error_detail(exc)
                self._models_view.setPlainText(f"Failed to load model catalog.\n{detail}")
                self._append_activity(f"Model catalog refresh failed: {detail}", kind="error")

        def _rebuild_model_combo(self) -> None:
            self._model_combo.blockSignals(True)
            self._model_combo.clear()
            for option in self._model_options:
                index = self._model_combo.count()
                self._model_combo.addItem(option.get("combo_label") or option["label"], option)
                self._model_combo.setItemData(
                    index,
                    option["label"],
                    qtcore.Qt.ItemDataRole.ToolTipRole,
                )
            self._sync_model_combo_selection()
            self._model_combo.blockSignals(False)
            self._refresh_model_combo_tooltip()
            self._refresh_session_action_state()

        def _sync_model_combo_selection(self) -> None:
            selected_provider = _compact_text(self._selected_session_detail.get("selected_provider_id"))
            selected_model = _compact_text(self._selected_session_detail.get("selected_model_id"))
            target_index = 0
            for index, option in enumerate(self._model_options):
                if (
                    option.get("provider_id") == selected_provider
                    and option.get("model_id") == selected_model
                ):
                    target_index = index
                    break
            if self._model_options:
                self._model_combo.setCurrentIndex(target_index)
            else:
                self._model_combo.setToolTip("No models available.")
            self._refresh_model_combo_tooltip()
            self._refresh_chat_workspace_summary()

        def _refresh_model_combo_tooltip(self) -> None:
            if self._model_combo is None:
                return
            option = self._model_combo.currentData()
            current = option if isinstance(option, dict) else {}
            display_name = _compact_text(current.get("display_name")) or _compact_text(current.get("model_id"))
            provider_name = _compact_text(current.get("provider_name")) or _compact_text(current.get("provider_id"))
            model_id = _compact_text(current.get("model_id"))
            if not current:
                self._model_combo.setToolTip("Select a model.")
                return
            tooltip_lines = [display_name or "Selected model"]
            if provider_name or model_id:
                tooltip_lines.append(f"{provider_name or 'Provider'} / {model_id or '-'}")
            self._model_combo.setToolTip("\n".join(line for line in tooltip_lines if line))

        def _refresh_sessions(self, preferred_session_id: str | None = None) -> None:
            selected_session_id = preferred_session_id or self._current_session_id()
            try:
                sessions = self._session_client.list_sessions_sync(
                    workspace_dir=self._effective_workspace_dir()
                )
            except Exception as exc:
                self._append_activity(f"Session refresh failed: {desktop_error_detail(exc)}", kind="error")
                self._refresh_sessions_overview()
                return

            if not sessions:
                try:
                    detail = self._session_client.ensure_default_session_sync(
                        MainAgentDefaultSessionRequest(
                            workspace_dir=self._effective_workspace_dir(),
                            surface="desktop",
                        )
                    )
                except Exception as exc:
                    self._append_activity(f"Default session ensure failed: {desktop_error_detail(exc)}", kind="error")
                    detail = None
                sessions = [detail] if detail is not None and detail.session_id else []

            self._sessions_value.setText(str(len(sessions)))
            self._session_ids_by_row = []
            self._session_list.blockSignals(True)
            self._session_list.clear()
            session_payloads = surface_payload_list_from_dtos(sessions)
            for session in session_payloads:
                session_id = str(session.get("session_id") or "").strip()
                if not session_id:
                    continue
                self._session_ids_by_row.append(session_id)
                item = qtwidgets.QListWidgetItem(format_session_row(session))
                item.setToolTip(
                    "\n".join(
                        [
                            f"Title: {_compact_text(session.get('title')) or session_id}",
                            f"Session ID: {session_id}",
                            f"State: {'busy' if bool(session.get('busy')) else 'ready'}",
                            f"Access: {'shared' if bool(session.get('shared')) else 'private'}",
                            f"Model: {_compact_text(session.get('selected_model_id')) or '-'}",
                        ]
                    )
                )
                self._session_list.addItem(item)

            if not self._session_ids_by_row:
                self._session_list.blockSignals(False)
                self._selected_session_detail = {}
                self._selected_run_summary = {}
                self._conversation_messages = []
                self._render_conversation()
                self._context_view.setPlainText("No sessions were found for the current workspace.")
                self._models_view.setPlainText(
                    format_chat_runtime_text(self._model_catalog, None, None)
                )
                self._sessions_overview_detail_view.setPlainText("No sessions were found for the current workspace.")
                self._refresh_chat_workspace_summary()
                self._update_approval_button_state()
                self._refresh_session_action_state()
                self._refresh_sessions_overview()
                self._refresh_settings_page()
                self._refresh_memory_page()
                return

            target_row = 0
            if selected_session_id:
                try:
                    target_row = self._session_ids_by_row.index(selected_session_id)
                except ValueError:
                    target_row = next(
                        (
                            index
                            for index, session in enumerate(session_payloads)
                            if bool(session.get("is_default"))
                        ),
                        0,
                    )
            self._session_list.setCurrentRow(target_row)
            self._session_list.blockSignals(False)
            self._load_selected_session_detail()
            self._refresh_sessions_overview()

        def _current_session_id(self) -> str | None:
            row = int(self._session_list.currentRow())
            if row < 0 or row >= len(self._session_ids_by_row):
                return None
            return self._session_ids_by_row[row]

        def _current_run_id(self) -> str | None:
            session_id = self._current_session_id()
            if not session_id:
                return None
            try:
                return RuntimeSessionRunControlStore.run_id_for_session(session_id)
            except Exception:
                return None

        def _on_session_selected(self, row: int) -> None:
            if row < 0 or row >= len(self._session_ids_by_row):
                return
            self._load_selected_session_detail()

        def _load_selected_run_summary(self) -> None:
            run_id = self._current_run_id()
            if not run_id:
                self._selected_run_summary = {}
                return
            try:
                run = self._run_client.get_run_sync(run_id)
            except Exception:
                self._selected_run_summary = {}
                return
            self._selected_run_summary = surface_payload_from_dto(run)

        def _load_selected_session_detail(self, *, recent_limit: int = 80) -> None:
            session_id = self._current_session_id()
            if not session_id:
                self._selected_session_detail = {}
                self._selected_run_summary = {}
                self._conversation_messages = []
                self._render_conversation()
                self._context_view.setPlainText("No session selected.")
                self._models_view.setPlainText(
                    format_chat_runtime_text(self._model_catalog, None, None)
                )
                self._sessions_overview_detail_view.setPlainText("No session selected.")
                self._refresh_chat_workspace_summary()
                self._update_approval_button_state()
                self._refresh_session_action_state()
                self._refresh_run_action_state()
                self._refresh_settings_page()
                self._refresh_memory_page()
                return
            try:
                detail = self._session_client.get_session_detail_sync(session_id, recent_limit=recent_limit)
            except Exception as exc:
                resolved = desktop_error_detail(exc)
                self._context_view.setPlainText(f"Failed to load session detail.\n{resolved}")
                self._models_view.setPlainText(f"Failed to load runtime detail.\n{resolved}")
                self._sessions_overview_detail_view.setPlainText(f"Failed to load session detail.\n{resolved}")
                self._append_activity(f"Session detail load failed for {session_id}: {resolved}", kind="error")
                return
            detail_payload = surface_payload_from_dto(detail)
            self._selected_session_detail = detail_payload
            self._load_selected_run_summary()
            self._conversation_messages = [
                {
                    "role": str(item.get("role") or "assistant"),
                    "content": str(item.get("content") or ""),
                    "surface": str(item.get("surface") or "-"),
                }
                for item in list(detail_payload.get("recent_messages") or [])
            ]
            self._render_conversation()
            self._context_view.setPlainText(
                format_chat_context_text(detail_payload, self._selected_run_summary)
            )
            self._sessions_overview_detail_view.setPlainText(
                format_session_context_text(detail_payload, self._selected_run_summary)
            )
            self._models_view.setPlainText(
                format_chat_runtime_text(
                    self._model_catalog,
                    detail_payload,
                    self._selected_run_summary,
                )
            )
            self._sync_model_combo_selection()
            self._refresh_chat_workspace_summary()
            self._update_approval_button_state()
            self._refresh_session_action_state()
            self._refresh_run_action_state()
            self._refresh_settings_page()
            self._refresh_memory_page()
            self._maybe_prompt_for_pending_approval()

        def _render_conversation(self) -> None:
            self._conversation_view.setHtml(render_conversation_html(self._conversation_messages))
            scrollbar = self._conversation_view.verticalScrollBar()
            scrollbar.setValue(scrollbar.maximum())

        def _render_activity(self) -> None:
            self._activity_view.setHtml(render_activity_html(self._activity_entries))
            scrollbar = self._activity_view.verticalScrollBar()
            scrollbar.setValue(scrollbar.maximum())

        def _set_runtime_note(self, note: str) -> None:
            text = str(note or "").strip() or "-"
            self._note_value.setText(_truncate_text(text))
            self._note_value.setToolTip(text)
            self._status_value.setToolTip(text)
            self._gateway_value.setToolTip(text)

        def _selected_session_title(self) -> str:
            return _compact_text(self._selected_session_detail.get("title")) or (
                self._current_session_id() or "Session"
            )

        def _refresh_session_action_state(self) -> None:
            has_session = bool(self._current_session_id())
            shared = bool(self._selected_session_detail.get("shared"))
            self._rename_session_button.setDisabled(self._send_busy or not has_session)
            self._share_session_button.setDisabled(self._send_busy or not has_session)
            self._fork_session_button.setDisabled(self._send_busy or not has_session)
            self._compact_session_button.setDisabled(self._send_busy or not has_session)
            self._apply_model_button.setDisabled(self._send_busy or not has_session or not bool(self._model_options))
            self._share_session_button.setText("Unshare" if shared else "Share")
            self._refresh_chat_workspace_summary()

        def _refresh_run_action_state(self) -> None:
            can_cancel = desktop_run_can_cancel(self._selected_run_summary, send_busy=self._send_busy)
            can_interrupt = desktop_run_can_interrupt(self._selected_run_summary, send_busy=self._send_busy)
            can_resume = desktop_run_can_resume(self._selected_run_summary)
            if self._interrupt_turn_button is not None:
                self._interrupt_turn_button.setDisabled(not can_interrupt)
            if self._resume_turn_button is not None:
                self._resume_turn_button.setDisabled(not can_resume)
            if self._stop_turn_button is not None:
                self._stop_turn_button.setDisabled(not can_cancel)

        def _force_select_session(self, session_id: str) -> None:
            target = _compact_text(session_id)
            if not target:
                return
            try:
                row = self._session_ids_by_row.index(target)
            except ValueError:
                return
            self._session_list.blockSignals(True)
            self._session_list.setCurrentRow(row)
            self._session_list.blockSignals(False)
            item = self._session_list.item(row)
            if item is not None:
                self._session_list.scrollToItem(item)
            self._load_selected_session_detail()
            self._refresh_sessions_overview()

        def _rename_current_session(self, checked: bool = False) -> None:
            _ = checked
            session_id = self._current_session_id()
            if not session_id:
                self.statusBar().showMessage("Select a session first.")
                return
            current_title = self._selected_session_title()
            title, accepted = qtwidgets.QInputDialog.getText(
                self,
                "Rename Session",
                "Session title:",
                text=current_title,
            )
            renamed_title = _compact_text(title)
            if not accepted or not renamed_title:
                return
            try:
                feedback = perform_desktop_session_rename(
                    session_client=self._session_client,
                    session_id=session_id,
                    requested_title=renamed_title,
                    fallback_title=current_title,
                )
            except Exception as exc:
                self._append_activity(f"Rename failed: {desktop_error_detail(exc)}", kind="error")
                self.statusBar().showMessage("Rename failed.")
                return

            self._append_activity(feedback.activity_message, kind=feedback.activity_kind)
            self.statusBar().showMessage(feedback.status_text)
            self._refresh_sessions(preferred_session_id=feedback.preferred_session_id or session_id)

        def _toggle_share_current_session(self, checked: bool = False) -> None:
            _ = checked
            session_id = self._current_session_id()
            if not session_id:
                self.statusBar().showMessage("Select a session first.")
                return
            try:
                feedback = perform_desktop_share_toggle(
                    session_client=self._session_client,
                    session_id=session_id,
                    selected_session_detail=self._selected_session_detail,
                )
            except Exception as exc:
                self._append_activity(f"Share toggle failed: {desktop_error_detail(exc)}", kind="error")
                self.statusBar().showMessage("Share toggle failed.")
                return

            self._append_activity(feedback.activity_message, kind=feedback.activity_kind)
            self.statusBar().showMessage(feedback.status_text)
            self._refresh_sessions(preferred_session_id=feedback.preferred_session_id or session_id)

        def _fork_current_session(self, checked: bool = False) -> None:
            _ = checked
            session_id = self._current_session_id()
            if not session_id:
                self.statusBar().showMessage("Select a session first.")
                return
            suggested = f"{self._selected_session_title()} copy"
            title, accepted = qtwidgets.QInputDialog.getText(
                self,
                "Fork Session",
                "Derived session title:",
                text=suggested,
            )
            if not accepted:
                return
            try:
                feedback = perform_desktop_session_fork(
                    session_client=self._session_client,
                    session_id=session_id,
                    parent_title=self._selected_session_title(),
                    requested_title=title,
                )
            except Exception as exc:
                self._append_activity(f"Fork failed: {desktop_error_detail(exc)}", kind="error")
                self.statusBar().showMessage("Fork failed.")
                return

            self._append_activity(feedback.activity_message, kind=feedback.activity_kind)
            self.statusBar().showMessage(feedback.status_text)
            self._refresh_sessions(preferred_session_id=feedback.preferred_session_id or session_id)

        def _compact_current_session(self, checked: bool = False) -> None:
            _ = checked
            session_id = self._current_session_id()
            if not session_id:
                self.statusBar().showMessage("Select a session first.")
                return
            try:
                feedback = perform_desktop_session_compact(
                    session_client=self._session_client,
                    session_id=session_id,
                    selected_session_title=self._selected_session_title(),
                )
            except Exception as exc:
                self._append_activity(f"Compact failed: {desktop_error_detail(exc)}", kind="error")
                self.statusBar().showMessage("Compact failed.")
                return

            self._append_activity(
                feedback.activity_message,
                kind=feedback.activity_kind,
                detail=feedback.activity_detail,
            )
            self.statusBar().showMessage(feedback.status_text)
            self._refresh_sessions(preferred_session_id=feedback.preferred_session_id or session_id)

        def _create_session(self, checked: bool = False) -> str | None:
            _ = checked
            current_session_id = self._current_session_id()
            try:
                feedback = perform_desktop_session_creation(
                    session_client=self._session_client,
                    workspace_dir=self._effective_workspace_dir(),
                    current_session_id=current_session_id,
                )
            except Exception as exc:
                self._append_activity(f"Create session failed: {desktop_error_detail(exc)}", kind="error")
                self.statusBar().showMessage("Create session failed.")
                return None

            created_payload = feedback.response_payload
            session_id = feedback.preferred_session_id or _compact_text(created_payload.get("session_id"))
            created_title = _compact_text(created_payload.get("title")) or session_id or "unknown"
            self._append_activity(feedback.activity_message, kind=feedback.activity_kind)
            if session_id:
                self._refresh_health()
                self._refresh_models()
                self._refresh_sessions(preferred_session_id=session_id)
                self._force_select_session(session_id)
                self.statusBar().showMessage(f"Switched to {created_title}")
            return session_id or None

        def _apply_selected_model(self, checked: bool = False) -> None:
            _ = checked
            if self._send_busy:
                self.statusBar().showMessage("Cannot switch model while a desktop turn is running.")
                return
            session_id = self._current_session_id()
            if not session_id:
                self.statusBar().showMessage("Select or create a session first.")
                return
            current = self._model_combo.currentData()
            option = current if isinstance(current, dict) else None
            if not option:
                self.statusBar().showMessage("No model option selected.")
                return
            try:
                response = self._model_client.set_agent_model_binding_sync(
                    MainAgentModelBindingRequest(
                        provider_source=option.get("provider_source"),
                        provider_id=str(option.get("provider_id") or ""),
                        model_id=str(option.get("model_id") or ""),
                    ),
                )
            except Exception as exc:
                self._append_activity(f"Model switch failed: {desktop_error_detail(exc)}", kind="error")
                self.statusBar().showMessage("Model switch failed.")
                return

            response_payload = surface_payload_from_dto(response)
            status = _compact_text(response_payload.get("binding_kind")) or "bound"
            selected_provider = _compact_text(response_payload.get("provider_id") or option.get("provider_id"))
            selected_model = _compact_text(response_payload.get("model_id") or option.get("model_id"))
            feedback = f"Agent model bound: {selected_provider}/{selected_model}"
            self._append_activity(feedback, kind="model")
            self.statusBar().showMessage(feedback)
            self._load_selected_session_detail()
            self._refresh_models()
            self._append_activity(f"Model response status: {status}", kind="model")

        def _update_approval_button_state(self) -> None:
            pending = first_pending_approval(self._selected_session_detail, self._selected_run_summary)
            self._approvals_button.setText(
                resolve_desktop_approval_button_text(
                    self._selected_session_detail,
                    self._selected_run_summary,
                )
            )
            self._approvals_button.setDisabled(pending is None)

        def _maybe_prompt_for_pending_approval(self) -> None:
            pending = first_pending_approval(self._selected_session_detail, self._selected_run_summary)
            token = _compact_text((pending or {}).get("token"))
            if not token:
                self._approval_dialog_token = None
                return
            if self._approval_dialog_token == token:
                return
            self._approval_dialog_token = token
            self._open_pending_approval_dialog()

        def _open_pending_approval_dialog(self, checked: bool = False) -> None:
            _ = checked
            pending = first_pending_approval(self._selected_session_detail, self._selected_run_summary)
            session_id = self._current_session_id()
            if not pending or not session_id:
                self.statusBar().showMessage("No pending approvals for the selected session.")
                return

            token = _compact_text(pending.get("token"))
            tool_name = _compact_text(pending.get("tool_name")) or "tool"
            kind = _compact_text(pending.get("kind")) or "-"
            reason = _compact_text(pending.get("reason")) or "-"
            arguments = pending.get("arguments") if isinstance(pending.get("arguments"), dict) else {}
            message = (
                f"Session: {_compact_text(self._selected_session_detail.get('title')) or session_id}\n"
                f"Tool: {tool_name}\n"
                f"Token: {token or '-'}\n"
                f"Kind: {kind}\n"
                f"Reason: {reason}\n\n"
                f"Arguments:\n{json.dumps(arguments, ensure_ascii=False, indent=2)}"
            )
            dialog = qtwidgets.QMessageBox(self)
            dialog.setWindowTitle("Approval Required")
            dialog.setIcon(qtwidgets.QMessageBox.Icon.Warning)
            dialog.setText("The selected session is waiting for approval.")
            dialog.setInformativeText(message)
            approve_button = dialog.addButton("Approve", qtwidgets.QMessageBox.ButtonRole.AcceptRole)
            deny_button = dialog.addButton("Deny", qtwidgets.QMessageBox.ButtonRole.RejectRole)
            dialog.addButton("Later", qtwidgets.QMessageBox.ButtonRole.ActionRole)
            dialog.exec()
            clicked = dialog.clickedButton()
            if clicked is approve_button:
                self._resolve_pending_approval(True)
            elif clicked is deny_button:
                self._resolve_pending_approval(False)

        def _resolve_pending_approval(self, approved: bool) -> None:
            session_id = self._current_session_id()
            pending = first_pending_approval(self._selected_session_detail, self._selected_run_summary)
            token = _compact_text((pending or {}).get("token"))
            if not session_id or not token:
                return
            try:
                feedback = perform_desktop_pending_approval_resolution(
                    run_client=self._run_client,
                    session_client=self._session_client,
                    session_id=session_id,
                    run_id=self._current_run_id(),
                    selected_session_detail=self._selected_session_detail,
                    selected_run_summary=self._selected_run_summary,
                    approved=approved,
                )
            except Exception as exc:
                activity_title, status_text = format_desktop_approval_failure(exc)
                self._append_activity(activity_title, kind="error")
                self.statusBar().showMessage(status_text)
                return

            if feedback.updated_run_summary is not None:
                self._selected_run_summary = feedback.updated_run_summary
            self._approval_dialog_token = None
            self._append_activity(feedback.activity_message, kind=feedback.activity_kind)
            self.statusBar().showMessage(feedback.status_text)
            self._load_selected_session_detail()

        def _cancel_current_run(self, checked: bool = False) -> None:
            _ = checked
            run_id = self._current_run_id()
            if not run_id:
                self.statusBar().showMessage("No active run to stop.")
                return
            try:
                feedback = perform_desktop_run_cancel(
                    run_client=self._run_client,
                    run_id=run_id,
                )
            except Exception as exc:
                self._append_activity(f"Stop failed: {desktop_error_detail(exc)}", kind="error")
                self.statusBar().showMessage("Stop failed.")
                return

            if feedback.updated_run_summary is not None:
                self._selected_run_summary = feedback.updated_run_summary
            self._append_activity(feedback.activity_message, kind=feedback.activity_kind)
            self.statusBar().showMessage(feedback.status_text)
            self._refresh_run_action_state()
            self._load_selected_session_detail()

        def _interrupt_current_run(self, checked: bool = False) -> None:
            _ = checked
            run_id = self._current_run_id()
            if not run_id:
                self.statusBar().showMessage("No active run to pause.")
                return
            try:
                feedback = perform_desktop_run_interrupt(
                    run_client=self._run_client,
                    run_id=run_id,
                )
            except Exception as exc:
                self._append_activity(f"Pause failed: {desktop_error_detail(exc)}", kind="error")
                self.statusBar().showMessage("Pause failed.")
                return

            if feedback.updated_run_summary is not None:
                self._selected_run_summary = feedback.updated_run_summary
            self._append_activity(feedback.activity_message, kind=feedback.activity_kind)
            self.statusBar().showMessage(feedback.status_text)
            self._refresh_run_action_state()
            self._load_selected_session_detail()

        def _resume_current_run(self, checked: bool = False) -> None:
            _ = checked
            run_id = self._current_run_id()
            if not run_id:
                self.statusBar().showMessage("No resumable run selected.")
                return
            try:
                feedback = perform_desktop_run_resume(
                    run_client=self._run_client,
                    run_id=run_id,
                    selected_run_summary=self._selected_run_summary,
                )
            except Exception as exc:
                self._append_activity(f"Resume failed: {desktop_error_detail(exc)}", kind="error")
                self.statusBar().showMessage("Resume failed.")
                return

            if feedback.updated_run_summary is not None:
                self._selected_run_summary = feedback.updated_run_summary
            self._append_activity(feedback.activity_message, kind=feedback.activity_kind)
            self.statusBar().showMessage(feedback.status_text)
            self._refresh_run_action_state()
            self._load_selected_session_detail()

        def _open_command_palette(self, checked: bool = False) -> None:
            _ = checked
            commands = [
                "Open Chat Page",
                "Open Models Page",
                "Open Providers Page",
                "Open Settings Page",
                "New Session",
                "Rename Session",
                "Share / Unshare Session",
                "Fork Session",
                "Compact Session",
                "Pause Turn",
                "Resume Turn",
                "Stop Turn",
                "Refresh",
                "Reconnect",
                "Open Approvals",
                "Focus Prompt",
                "Apply Selected Model",
            ]
            choice, accepted = qtwidgets.QInputDialog.getItem(
                self,
                "Command Palette",
                "Choose a desktop action:",
                commands,
                0,
                False,
            )
            if not accepted:
                return
            command = _compact_text(choice).lower()
            if command == "open chat page":
                self._select_page_by_id("chat")
            elif command == "open models page":
                self._select_page_by_id("models")
            elif command == "open providers page":
                self._select_page_by_id("providers")
            elif command == "open settings page":
                self._select_page_by_id("settings")
            elif command == "new session":
                self._create_session()
            elif command == "rename session":
                self._rename_current_session()
            elif command == "share / unshare session":
                self._toggle_share_current_session()
            elif command == "fork session":
                self._fork_current_session()
            elif command == "compact session":
                self._compact_current_session()
            elif command == "pause turn":
                self._interrupt_current_run()
            elif command == "resume turn":
                self._resume_current_run()
            elif command == "stop turn":
                self._cancel_current_run()
            elif command == "refresh":
                self.refresh_snapshot()
            elif command == "reconnect":
                self._reconnect_gateway()
            elif command == "open approvals":
                self._open_pending_approval_dialog()
            elif command == "focus prompt":
                self._composer.setFocus()
            elif command == "apply selected model":
                self._apply_selected_model()

        def _send_current_prompt(self, checked: bool = False) -> None:
            _ = checked
            if self._send_busy:
                self.statusBar().showMessage("A desktop turn is already running.")
                return
            message = self._composer.toPlainText().strip()
            if not message:
                return
            session_id = self._current_session_id() or self._create_session()
            if not session_id:
                return

            self._composer.clear()
            feedback = record_desktop_prompt_submission(
                self._conversation_messages,
                session_id=session_id,
                message=message,
            )
            self._render_conversation()
            self._append_activity(feedback.activity_message, kind=feedback.activity_kind)
            self._set_send_busy(True)

            self._stream_target_session_id = session_id
            self._send_thread = qtcore.QThread(self)
            self._send_worker = ChatStreamWorker(
                chat_client=self._chat_client,
                request=build_desktop_chat_request(
                    session_id=session_id,
                    message=message,
                    workspace_dir=self._effective_workspace_dir(),
                ),
            )
            self._send_worker.moveToThread(self._send_thread)
            self._send_thread.started.connect(self._send_worker.run)
            self._send_worker.chunk_received.connect(self._on_stream_chunk)
            self._send_worker.activity_received.connect(self._on_stream_activity)
            self._send_worker.approval_requested.connect(self._on_stream_approval_requested)
            self._send_worker.approval_resolved.connect(self._on_stream_approval_resolved)
            self._send_worker.done_received.connect(self._on_stream_done)
            self._send_worker.error_received.connect(self._on_stream_error)
            self._send_worker.finished.connect(self._on_stream_finished)
            self._send_worker.finished.connect(self._send_thread.quit)
            self._send_worker.finished.connect(self._send_worker.deleteLater)
            self._send_thread.finished.connect(self._send_thread.deleteLater)
            self._send_thread.start()

        def _set_send_busy(self, busy: bool) -> None:
            self._send_busy = busy
            self._send_button.setDisabled(busy)
            self._new_session_button.setDisabled(busy)
            self._session_list.setDisabled(busy)
            self._sessions_overview_list.setDisabled(busy)
            self._composer.setReadOnly(busy)
            self._apply_model_button.setDisabled(busy or not bool(self._model_options))
            self._refresh_session_action_state()
            self._refresh_run_action_state()
            self._refresh_registry_action_state()
            self._refresh_provider_action_state()
            if busy:
                self.statusBar().showMessage("Running desktop turn...")

        def _on_stream_chunk(self, chunk: str) -> None:
            append_desktop_assistant_stream_chunk(self._conversation_messages, chunk)
            self._render_conversation()

        def _on_stream_activity(self, payload: object) -> None:
            entry = payload if isinstance(payload, dict) else {"title": _compact_text(payload)}
            self._append_activity(
                str(entry.get("title") or "activity"),
                kind=str(entry.get("kind") or "activity"),
                detail=str(entry.get("detail") or ""),
                preview=str(entry.get("preview") or ""),
                activity_id=str(entry.get("activity_id") or ""),
            )

        def _on_stream_approval_requested(self, payload: object) -> None:
            pending = payload if isinstance(payload, dict) else {}
            token = _compact_text(pending.get("token"))
            if token:
                self._approval_dialog_token = None
            self._load_selected_session_detail()

        def _on_stream_approval_resolved(self) -> None:
            self._approval_dialog_token = None
            self._load_selected_session_detail()

        def _on_stream_done(self, payload: object) -> None:
            feedback = finalize_desktop_stream_completion(self._conversation_messages, payload)
            self._render_conversation()
            self._append_activity(
                feedback.activity_message,
                kind=feedback.activity_kind,
                detail=feedback.activity_detail,
            )
            self._load_selected_session_detail()
            self._refresh_models()

        def _on_stream_error(self, message: str) -> None:
            feedback = finalize_desktop_stream_error(self._conversation_messages, message)
            self._render_conversation()
            self._append_activity(feedback.activity_message, kind=feedback.activity_kind)
            self._append_managed_gateway_excerpt("Turn failure diagnostics")

        def _on_stream_finished(self) -> None:
            self._set_send_busy(False)
            self._stream_target_session_id = None
            self._send_worker = None
            self._send_thread = None
            self.refresh_snapshot()
            self.statusBar().showMessage("Desktop turn finished.")

        def _reconnect_gateway(self, checked: bool = False) -> None:
            _ = checked
            if self._send_busy:
                self.statusBar().showMessage("Cannot reconnect while a turn is running.")
                return
            try:
                self._connection = self._reconnect_handler()
                self._transport_binding.bind_connection(self._connection)
                self._refresh_runtime_identity()
                self._set_runtime_note(self._connection.note or "-")
                self._append_activity(
                    self._connection.note or "Reconnected to local gateway.",
                    kind="status",
                )
                self._append_managed_gateway_excerpt("Reconnect diagnostics")
                self.refresh_snapshot()
            except Exception as exc:
                self._append_activity(f"Reconnect failed: {desktop_error_detail(exc)}", kind="error")
                self.statusBar().showMessage("Reconnect failed.")

        def _mode_text(self) -> str:
            mode = "managed" if self._connection.managed else "external"
            if self._connection.started_here:
                mode = f"{mode} | started-by-desktop"
            if self._connection.qqbot_running:
                mode = f"{mode} | qqbot-on"
            return mode

        def _append_activity(
            self,
            message: str,
            *,
            kind: str = "activity",
            detail: str | None = None,
            preview: str | None = None,
            activity_id: str | None = None,
        ) -> None:
            append_desktop_activity_entry(
                self._activity_entries,
                message,
                kind=kind,
                detail=detail,
                preview=preview,
                activity_id=activity_id,
            )
            self._render_activity()

        def _append_managed_gateway_excerpt(self, label: str) -> None:
            if not self._connection.managed:
                return
            excerpt = self._supervisor.managed_log_tail(lines=6).strip()
            if not excerpt:
                return
            self._append_activity(label, kind="gateway", detail=excerpt)

    return DesktopMainWindow()
