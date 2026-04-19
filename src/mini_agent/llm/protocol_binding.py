"""Protocol binding profiles for runtime LLM execution.

This module converts routed provider settings into protocol execution profiles.
Provider compatibility rules live here so protocol clients can stay focused on
OpenAI / Anthropic protocol mechanics only.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from mini_agent.model_manager.rectifier import RequestRectifierOptions

from ..schema.schema import LLMProvider


_MINIMAX_DOMAINS = ("api.minimax.io", "api.minimaxi.com")


def _parse_bool(value: str | None, *, default: bool) -> bool:
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return default


def _parse_optional_bool(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return None


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


def _parse_float(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        return float(value.strip())
    except Exception:
        return None


def _normalize_api_base(api_base: str) -> str:
    normalized = str(api_base or "").strip().rstrip("/")
    if not normalized:
        raise ValueError("api_base must not be empty")
    return normalized


def _is_minimax_endpoint(api_base: str) -> bool:
    lowered = api_base.lower()
    return any(domain in lowered for domain in _MINIMAX_DOMAINS)


def _strip_protocol_suffix(api_base: str) -> str:
    normalized = api_base.rstrip("/")
    lowered = normalized.lower()
    for suffix in ("/anthropic", "/v1"):
        if lowered.endswith(suffix):
            return normalized[: -len(suffix)]
    return normalized


def _copy_mapping(value: dict[str, Any]) -> dict[str, Any]:
    return {str(key): item for key, item in value.items()}


@dataclass(frozen=True)
class ProtocolRequestPolicy:
    """Explicit request-policy defaults bound to one routed execution profile."""

    max_output_tokens: int | None = None
    reasoning_split_enabled: bool | None = None
    thinking_budget_tokens: int | None = None
    temperature: float | None = None
    streaming_enabled: bool | None = None
    include_stream_usage: bool | None = None
    tool_choice_policy: str | dict[str, Any] | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "max_output_tokens",
            _parse_int(str(self.max_output_tokens)) if self.max_output_tokens is not None else None,
        )
        object.__setattr__(
            self,
            "thinking_budget_tokens",
            _parse_int(str(self.thinking_budget_tokens))
            if self.thinking_budget_tokens is not None
            else None,
        )
        object.__setattr__(
            self,
            "temperature",
            _parse_float(str(self.temperature)) if self.temperature is not None else None,
        )
        object.__setattr__(
            self,
            "reasoning_split_enabled",
            _parse_optional_bool(self.reasoning_split_enabled),
        )
        object.__setattr__(
            self,
            "streaming_enabled",
            _parse_optional_bool(self.streaming_enabled),
        )
        object.__setattr__(
            self,
            "include_stream_usage",
            _parse_optional_bool(self.include_stream_usage),
        )
        if isinstance(self.tool_choice_policy, dict):
            object.__setattr__(self, "tool_choice_policy", _copy_mapping(self.tool_choice_policy))

    def _openai_tool_choice(self) -> str | dict[str, Any] | None:
        if isinstance(self.tool_choice_policy, dict):
            return _copy_mapping(self.tool_choice_policy)
        if isinstance(self.tool_choice_policy, str):
            normalized = self.tool_choice_policy.strip()
            return normalized or None
        return None

    def _anthropic_tool_choice(self) -> dict[str, Any] | None:
        if isinstance(self.tool_choice_policy, dict):
            return _copy_mapping(self.tool_choice_policy)
        normalized = str(self.tool_choice_policy or "").strip().lower()
        if normalized == "auto":
            return {"type": "auto"}
        if normalized in {"required", "any"}:
            return {"type": "any"}
        return None

    def openai_request_kwargs(
        self,
        *,
        tools_enabled: bool = False,
        streaming: bool = False,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {}
        if self.max_output_tokens is not None:
            params["max_tokens"] = self.max_output_tokens
        if self.temperature is not None:
            params["temperature"] = self.temperature
        if tools_enabled:
            tool_choice = self._openai_tool_choice()
            if tool_choice is not None:
                params["tool_choice"] = tool_choice

        extra_body: dict[str, Any] = {}
        if bool(self.reasoning_split_enabled):
            extra_body["reasoning_split"] = True
        if self.thinking_budget_tokens is not None:
            extra_body["thinking_budget"] = self.thinking_budget_tokens
        if extra_body:
            params["extra_body"] = extra_body

        if streaming:
            params["stream"] = True
            if self.include_stream_usage is not False:
                params["stream_options"] = {"include_usage": True}
        return params

    def anthropic_request_kwargs(
        self,
        *,
        tools_enabled: bool = False,
        streaming: bool = False,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {}
        if self.max_output_tokens is not None:
            params["max_tokens"] = self.max_output_tokens
        if self.temperature is not None:
            params["temperature"] = self.temperature
        if self.thinking_budget_tokens is not None:
            params["thinking"] = {
                "type": "enabled",
                "budget_tokens": self.thinking_budget_tokens,
            }
        if tools_enabled:
            tool_choice = self._anthropic_tool_choice()
            if tool_choice is not None:
                params["tool_choice"] = tool_choice
        if streaming:
            params["stream"] = True
        return params


def _default_request_policy(
    *,
    provider: LLMProvider,
    api_base: str,
) -> ProtocolRequestPolicy:
    return ProtocolRequestPolicy(
        max_output_tokens=16384 if provider == LLMProvider.ANTHROPIC else None,
        reasoning_split_enabled=(provider == LLMProvider.OPENAI),
        thinking_budget_tokens=None,
        temperature=None,
        streaming_enabled=True,
        include_stream_usage=True,
    )


def _merge_request_policy(
    *,
    defaults: ProtocolRequestPolicy,
    overrides: ProtocolRequestPolicy | None,
) -> ProtocolRequestPolicy:
    if overrides is None:
        return defaults
    return ProtocolRequestPolicy(
        max_output_tokens=(
            overrides.max_output_tokens
            if overrides.max_output_tokens is not None
            else defaults.max_output_tokens
        ),
        reasoning_split_enabled=(
            overrides.reasoning_split_enabled
            if overrides.reasoning_split_enabled is not None
            else defaults.reasoning_split_enabled
        ),
        thinking_budget_tokens=(
            overrides.thinking_budget_tokens
            if overrides.thinking_budget_tokens is not None
            else defaults.thinking_budget_tokens
        ),
        temperature=(
            overrides.temperature
            if overrides.temperature is not None
            else defaults.temperature
        ),
        streaming_enabled=(
            overrides.streaming_enabled
            if overrides.streaming_enabled is not None
            else defaults.streaming_enabled
        ),
        include_stream_usage=(
            overrides.include_stream_usage
            if overrides.include_stream_usage is not None
            else defaults.include_stream_usage
        ),
        tool_choice_policy=(
            overrides.tool_choice_policy
            if overrides.tool_choice_policy is not None
            else defaults.tool_choice_policy
        ),
    )


@dataclass(frozen=True)
class ProtocolExecutionProfile:
    """Fully bound execution profile for one protocol client instance."""

    provider: LLMProvider
    api_key: str
    api_base: str
    model: str
    client_headers: dict[str, str] = field(default_factory=dict)
    client_timeout_seconds: float | None = None
    request_policy: ProtocolRequestPolicy = field(default_factory=ProtocolRequestPolicy)
    rectifier_options: RequestRectifierOptions = field(default_factory=RequestRectifierOptions)


def build_protocol_execution_profile(
    *,
    api_key: str,
    provider: LLMProvider,
    api_base: str,
    model: str,
    client_headers: dict[str, Any] | None = None,
    request_timeout_seconds: float | int | None = None,
    rectifier_options: RequestRectifierOptions | None = None,
    request_policy: ProtocolRequestPolicy | None = None,
) -> ProtocolExecutionProfile:
    """Bind provider-compatible settings into one execution profile."""

    normalized_base = _normalize_api_base(api_base)
    options = rectifier_options or RequestRectifierOptions()
    normalized_headers = _copy_mapping(client_headers or {})

    if provider == LLMProvider.ANTHROPIC:
        if _is_minimax_endpoint(normalized_base):
            normalized_base = f"{_strip_protocol_suffix(normalized_base)}/anthropic"
        # Preserve current compatibility behavior while keeping it out of the client.
        normalized_headers["Authorization"] = f"Bearer {api_key}"
    elif provider == LLMProvider.OPENAI:
        if _is_minimax_endpoint(normalized_base):
            normalized_base = f"{_strip_protocol_suffix(normalized_base)}/v1"
    else:
        raise ValueError(f"Unsupported provider: {provider}")

    normalized_timeout = (
        _parse_float(str(request_timeout_seconds))
        if request_timeout_seconds is not None
        else None
    )
    if normalized_timeout is not None and normalized_timeout <= 0:
        normalized_timeout = None

    return ProtocolExecutionProfile(
        provider=provider,
        api_key=api_key,
        api_base=normalized_base,
        model=model,
        client_headers=normalized_headers,
        client_timeout_seconds=normalized_timeout,
        request_policy=_merge_request_policy(
            defaults=_default_request_policy(provider=provider, api_base=normalized_base),
            overrides=request_policy,
        ),
        rectifier_options=options,
    )
