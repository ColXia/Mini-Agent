"""Request rectifier for provider protocol and payload normalization."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import os
from threading import RLock
from typing import Any


def _parse_bool(value: str | None, *, default: bool) -> bool:
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return default


def _parse_int(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        parsed = int(value.strip())
    except Exception:
        return None
    if parsed <= 0:
        return None
    return parsed


def _to_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return str(value)


def _copy_block(block: dict[str, Any]) -> dict[str, Any]:
    return {str(k): v for k, v in block.items()}


def _to_text_blocks(content: Any) -> list[dict[str, Any]]:
    if isinstance(content, list):
        blocks: list[dict[str, Any]] = []
        for item in content:
            if isinstance(item, dict):
                blocks.append(_copy_block(item))
            else:
                text = _to_text(item)
                if text:
                    blocks.append({"type": "text", "text": text})
        return blocks
    text = _to_text(content)
    if not text:
        return []
    return [{"type": "text", "text": text}]


def _is_minimax_endpoint(api_base: str | None) -> bool:
    if not api_base:
        return False
    lowered = api_base.lower()
    return "api.minimax.io" in lowered or "api.minimaxi.com" in lowered


def _inject_cache_control(blocks: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    if not blocks:
        return blocks, 0
    output = [_copy_block(item) for item in blocks]
    for idx in range(len(output) - 1, -1, -1):
        block_type = _to_text(output[idx].get("type")).strip().lower()
        if block_type in {"text", "tool_result"}:
            updated = _copy_block(output[idx])
            previous = updated.get("cache_control")
            updated["cache_control"] = {"type": "ephemeral"}
            output[idx] = updated
            return output, 0 if previous == {"type": "ephemeral"} else 1
    return output, 0


def _normalize_reasoning_details(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []
    normalized: list[dict[str, str]] = []
    for item in value:
        if isinstance(item, dict):
            text = _to_text(item.get("text")).strip()
        else:
            text = _to_text(item).strip()
        if not text:
            continue
        normalized.append({"text": text})
    return normalized


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _utc_iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(timezone.utc).isoformat()


@dataclass
class _RectifierMetrics:
    total_requests: int = 0
    openai_requests: int = 0
    anthropic_requests: int = 0
    thinking_budget_injections: int = 0
    cache_injections: int = 0
    signature_strips: int = 0
    protocol_conversion_calls: int = 0
    openai_to_anthropic_conversions: int = 0
    anthropic_to_openai_conversions: int = 0
    openai_to_gemini_conversions: int = 0
    last_rectified_at: datetime | None = None


_RECTIFIER_METRICS = _RectifierMetrics()
_RECTIFIER_LOCK = RLock()


def reset_rectifier_metrics() -> None:
    with _RECTIFIER_LOCK:
        _RECTIFIER_METRICS.total_requests = 0
        _RECTIFIER_METRICS.openai_requests = 0
        _RECTIFIER_METRICS.anthropic_requests = 0
        _RECTIFIER_METRICS.thinking_budget_injections = 0
        _RECTIFIER_METRICS.cache_injections = 0
        _RECTIFIER_METRICS.signature_strips = 0
        _RECTIFIER_METRICS.protocol_conversion_calls = 0
        _RECTIFIER_METRICS.openai_to_anthropic_conversions = 0
        _RECTIFIER_METRICS.anthropic_to_openai_conversions = 0
        _RECTIFIER_METRICS.openai_to_gemini_conversions = 0
        _RECTIFIER_METRICS.last_rectified_at = None


def snapshot_rectifier_metrics() -> dict[str, Any]:
    with _RECTIFIER_LOCK:
        return {
            "total_requests": _RECTIFIER_METRICS.total_requests,
            "openai_requests": _RECTIFIER_METRICS.openai_requests,
            "anthropic_requests": _RECTIFIER_METRICS.anthropic_requests,
            "thinking_budget_injections": _RECTIFIER_METRICS.thinking_budget_injections,
            "cache_injections": _RECTIFIER_METRICS.cache_injections,
            "signature_strips": _RECTIFIER_METRICS.signature_strips,
            "protocol_conversion_calls": _RECTIFIER_METRICS.protocol_conversion_calls,
            "openai_to_anthropic_conversions": _RECTIFIER_METRICS.openai_to_anthropic_conversions,
            "anthropic_to_openai_conversions": _RECTIFIER_METRICS.anthropic_to_openai_conversions,
            "openai_to_gemini_conversions": _RECTIFIER_METRICS.openai_to_gemini_conversions,
            "last_rectified_at": _utc_iso(_RECTIFIER_METRICS.last_rectified_at),
        }


def _record_rectify(
    protocol: str,
    *,
    thinking_budget_injected: bool = False,
    cache_injections: int = 0,
    signature_strips: int = 0,
) -> None:
    with _RECTIFIER_LOCK:
        _RECTIFIER_METRICS.total_requests += 1
        if protocol == "openai":
            _RECTIFIER_METRICS.openai_requests += 1
        elif protocol == "anthropic":
            _RECTIFIER_METRICS.anthropic_requests += 1

        if thinking_budget_injected:
            _RECTIFIER_METRICS.thinking_budget_injections += 1
        _RECTIFIER_METRICS.cache_injections += max(0, int(cache_injections))
        _RECTIFIER_METRICS.signature_strips += max(0, int(signature_strips))
        _RECTIFIER_METRICS.last_rectified_at = _utc_now()


def _record_protocol_conversion(kind: str) -> None:
    with _RECTIFIER_LOCK:
        _RECTIFIER_METRICS.protocol_conversion_calls += 1
        if kind == "openai_to_anthropic":
            _RECTIFIER_METRICS.openai_to_anthropic_conversions += 1
        elif kind == "anthropic_to_openai":
            _RECTIFIER_METRICS.anthropic_to_openai_conversions += 1
        elif kind == "openai_to_gemini":
            _RECTIFIER_METRICS.openai_to_gemini_conversions += 1


@dataclass(frozen=True)
class RequestRectifierOptions:
    """Rectifier options loaded from env (minimal and provider-agnostic)."""

    enabled: bool = True
    thinking_budget_tokens: int | None = None
    cache_injection: bool = True
    strip_thinking_signature: bool = True

    @staticmethod
    def from_env() -> "RequestRectifierOptions":
        return RequestRectifierOptions(
            enabled=_parse_bool(os.getenv("MINI_AGENT_RECTIFIER_ENABLED"), default=True),
            thinking_budget_tokens=_parse_int(os.getenv("MINI_AGENT_THINKING_BUDGET_TOKENS")),
            cache_injection=_parse_bool(os.getenv("MINI_AGENT_RECTIFIER_CACHE_INJECTION"), default=True),
            strip_thinking_signature=_parse_bool(
                os.getenv("MINI_AGENT_RECTIFIER_STRIP_THINKING_SIGNATURE"),
                default=True,
            ),
        )


def rectify_openai_request(
    params: dict[str, Any],
    *,
    api_base: str | None = None,
    options: RequestRectifierOptions | None = None,
) -> dict[str, Any]:
    """Normalize OpenAI-format request payload."""
    resolved = options or RequestRectifierOptions.from_env()
    if not resolved.enabled:
        return dict(params)

    output = dict(params)
    thinking_budget_injected = False
    messages_raw = output.get("messages", [])
    normalized_messages: list[dict[str, Any]] = []
    if isinstance(messages_raw, list):
        for item in messages_raw:
            if not isinstance(item, dict):
                continue
            message = dict(item)
            role = _to_text(message.get("role")).strip() or "user"
            message["role"] = role
            if role == "assistant":
                if "reasoning_details" in message:
                    reasoning = _normalize_reasoning_details(message.get("reasoning_details"))
                    if reasoning:
                        message["reasoning_details"] = reasoning
                    else:
                        message.pop("reasoning_details", None)
                if message.get("content") is None:
                    message["content"] = ""
            else:
                if message.get("content") is None and role != "tool":
                    message["content"] = ""
            normalized_messages.append(message)
    output["messages"] = normalized_messages

    if resolved.thinking_budget_tokens and _is_minimax_endpoint(api_base):
        extra_body_raw = output.get("extra_body")
        extra_body = dict(extra_body_raw) if isinstance(extra_body_raw, dict) else {}
        if "thinking_budget" not in extra_body:
            extra_body["thinking_budget"] = resolved.thinking_budget_tokens
            thinking_budget_injected = True
        output["extra_body"] = extra_body

    _record_rectify(
        "openai",
        thinking_budget_injected=thinking_budget_injected,
    )
    return output


def rectify_anthropic_request(
    params: dict[str, Any],
    *,
    options: RequestRectifierOptions | None = None,
) -> dict[str, Any]:
    """Normalize Anthropic-format request payload."""
    resolved = options or RequestRectifierOptions.from_env()
    if not resolved.enabled:
        return dict(params)

    output = dict(params)
    thinking_budget_injected = False
    cache_injection_count = 0
    signature_strip_count = 0

    if resolved.thinking_budget_tokens:
        output["thinking"] = {
            "type": "enabled",
            "budget_tokens": resolved.thinking_budget_tokens,
        }
        thinking_budget_injected = True

    system_message = output.get("system")
    if isinstance(system_message, str):
        if resolved.cache_injection and system_message.strip():
            output["system"], injected = _inject_cache_control(_to_text_blocks(system_message))
            cache_injection_count += injected
    elif isinstance(system_message, list):
        normalized_system = _to_text_blocks(system_message)
        if resolved.cache_injection:
            normalized_system, injected = _inject_cache_control(normalized_system)
            cache_injection_count += injected
        output["system"] = normalized_system

    messages_raw = output.get("messages", [])
    normalized_messages: list[dict[str, Any]] = []
    if isinstance(messages_raw, list):
        for raw_message in messages_raw:
            if not isinstance(raw_message, dict):
                continue
            message = dict(raw_message)
            role = _to_text(message.get("role")).strip() or "user"
            message["role"] = role
            content = message.get("content")
            if isinstance(content, list):
                normalized_blocks: list[dict[str, Any]] = []
                for raw_block in content:
                    if not isinstance(raw_block, dict):
                        text = _to_text(raw_block)
                        if text:
                            normalized_blocks.append({"type": "text", "text": text})
                        continue
                    block = _copy_block(raw_block)
                    block_type = _to_text(block.get("type")).strip().lower()
                    if block_type == "thinking":
                        thinking_text = _to_text(block.get("thinking")).strip()
                        if not thinking_text:
                            continue
                        block["thinking"] = thinking_text
                        if resolved.strip_thinking_signature and "signature" in block:
                            block.pop("signature", None)
                            signature_strip_count += 1
                    normalized_blocks.append(block)
                message["content"] = normalized_blocks
            elif isinstance(content, str):
                if role == "assistant" and resolved.strip_thinking_signature:
                    message["content"] = content
                else:
                    message["content"] = content
            else:
                message["content"] = _to_text(content)
            normalized_messages.append(message)

    if resolved.cache_injection:
        for idx in range(len(normalized_messages) - 1, -1, -1):
            if normalized_messages[idx].get("role") != "user":
                continue
            user_message = dict(normalized_messages[idx])
            user_message["content"], injected = _inject_cache_control(_to_text_blocks(user_message.get("content")))
            cache_injection_count += injected
            normalized_messages[idx] = user_message
            break

    output["messages"] = normalized_messages
    _record_rectify(
        "anthropic",
        thinking_budget_injected=thinking_budget_injected,
        cache_injections=cache_injection_count,
        signature_strips=signature_strip_count,
    )
    return output


def openai_messages_to_anthropic(
    openai_messages: list[dict[str, Any]],
) -> tuple[str | None, list[dict[str, Any]]]:
    """Convert OpenAI-format message list to Anthropic format."""
    _record_protocol_conversion("openai_to_anthropic")
    system_parts: list[str] = []
    anthropic_messages: list[dict[str, Any]] = []

    for raw in openai_messages:
        if not isinstance(raw, dict):
            continue
        role = _to_text(raw.get("role")).strip().lower()
        if role == "system":
            text = _to_text(raw.get("content")).strip()
            if text:
                system_parts.append(text)
            continue

        if role == "tool":
            anthropic_messages.append(
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": _to_text(raw.get("tool_call_id")).strip(),
                            "content": _to_text(raw.get("content")),
                        }
                    ],
                }
            )
            continue

        if role == "assistant":
            blocks: list[dict[str, Any]] = []
            for detail in _normalize_reasoning_details(raw.get("reasoning_details")):
                blocks.append({"type": "thinking", "thinking": detail["text"]})
            text_content = raw.get("content")
            if text_content not in {None, ""}:
                blocks.append({"type": "text", "text": _to_text(text_content)})
            tool_calls = raw.get("tool_calls")
            if isinstance(tool_calls, list):
                for tool_call in tool_calls:
                    if not isinstance(tool_call, dict):
                        continue
                    function = tool_call.get("function")
                    if not isinstance(function, dict):
                        continue
                    blocks.append(
                        {
                            "type": "tool_use",
                            "id": _to_text(tool_call.get("id")),
                            "name": _to_text(function.get("name")),
                            "input": function.get("arguments", {}),
                        }
                    )
            anthropic_messages.append({"role": "assistant", "content": blocks or _to_text(text_content)})
            continue

        anthropic_messages.append(
            {
                "role": "user",
                "content": _to_text(raw.get("content")),
            }
        )

    system_message = "\n\n".join(system_parts) if system_parts else None
    return system_message, anthropic_messages


def anthropic_messages_to_openai(
    system_message: str | None,
    anthropic_messages: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Convert Anthropic-format messages to OpenAI format messages."""
    _record_protocol_conversion("anthropic_to_openai")
    openai_messages: list[dict[str, Any]] = []
    if system_message and system_message.strip():
        openai_messages.append({"role": "system", "content": system_message})

    for raw in anthropic_messages:
        if not isinstance(raw, dict):
            continue
        role = _to_text(raw.get("role")).strip().lower()
        content = raw.get("content")
        if isinstance(content, list):
            if role == "assistant":
                assistant_msg: dict[str, Any] = {"role": "assistant", "content": ""}
                reasoning_details: list[dict[str, str]] = []
                tool_calls: list[dict[str, Any]] = []
                text_parts: list[str] = []
                for block in content:
                    if not isinstance(block, dict):
                        text_parts.append(_to_text(block))
                        continue
                    block_type = _to_text(block.get("type")).strip().lower()
                    if block_type == "thinking":
                        thinking_text = _to_text(block.get("thinking")).strip()
                        if thinking_text:
                            reasoning_details.append({"text": thinking_text})
                    elif block_type == "tool_use":
                        tool_calls.append(
                            {
                                "id": _to_text(block.get("id")),
                                "type": "function",
                                "function": {
                                    "name": _to_text(block.get("name")),
                                    "arguments": block.get("input", {}),
                                },
                            }
                        )
                    elif block_type == "text":
                        text_parts.append(_to_text(block.get("text")))
                assistant_msg["content"] = "".join(text_parts)
                if reasoning_details:
                    assistant_msg["reasoning_details"] = reasoning_details
                if tool_calls:
                    assistant_msg["tool_calls"] = tool_calls
                openai_messages.append(assistant_msg)
            else:
                for block in content:
                    if isinstance(block, dict) and _to_text(block.get("type")).strip().lower() == "tool_result":
                        openai_messages.append(
                            {
                                "role": "tool",
                                "tool_call_id": _to_text(block.get("tool_use_id")),
                                "content": _to_text(block.get("content")),
                            }
                        )
                    elif isinstance(block, dict):
                        openai_messages.append(
                            {
                                "role": "user",
                                "content": _to_text(block.get("text") or block.get("content")),
                            }
                        )
        else:
            openai_messages.append(
                {
                    "role": "assistant" if role == "assistant" else "user",
                    "content": _to_text(content),
                }
            )
    return openai_messages


def openai_messages_to_gemini_contents(openai_messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convert OpenAI-format messages to minimal Gemini contents format."""
    _record_protocol_conversion("openai_to_gemini")
    contents: list[dict[str, Any]] = []
    for raw in openai_messages:
        if not isinstance(raw, dict):
            continue
        role = _to_text(raw.get("role")).strip().lower()
        if role == "system":
            continue
        text = _to_text(raw.get("content"))
        if role == "assistant":
            gemini_role = "model"
        else:
            gemini_role = "user"
        contents.append(
            {
                "role": gemini_role,
                "parts": [{"text": text}],
            }
        )
    return contents
