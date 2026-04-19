"""Lightweight model capability probing for provider-managed models."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
import threading
from typing import Any

from mini_agent.llm.llm_wrapper import LLMClient
from mini_agent.llm.protocol_binding import ProtocolRequestPolicy, build_protocol_execution_profile
from mini_agent.model_manager.model_discovery import (
    ModelDiscoveryService,
    ProviderType,
    discovery_confidence_for_source,
    infer_model_capabilities,
    resolve_known_context_window,
)
from mini_agent.model_manager.model_registry_service import ModelRegistryService
from mini_agent.model_manager.preset_providers import PresetProvider, get_preset_provider_config
from mini_agent.model_manager.runtime import resolve_pinned_llm_candidate
from mini_agent.retry import RetryConfig
from mini_agent.schema.schema import Message


def _normalize_text(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _normalize_optional_text(value: Any) -> str | None:
    normalized = _normalize_text(value)
    return normalized or None


def _normalize_positive_int(value: Any) -> int | None:
    try:
        parsed = int(value)
    except Exception:
        return None
    return parsed if parsed > 0 else None


def _normalize_capability_truth(value: Any) -> str:
    normalized = _normalize_text(value).lower()
    if normalized in {"supported", "unsupported", "unknown"}:
        return normalized
    return "unknown"


def _capability_truth_from_model(model: dict[str, Any], key: str) -> str:
    raw_value = model.get(key)
    if isinstance(raw_value, bool):
        return "supported" if raw_value else "unsupported"
    return _normalize_capability_truth(model.get(f"{key}_truth"))


def _build_models_endpoint(api_base: str, discovery_type: ProviderType) -> str:
    base = str(api_base or "").rstrip("/")
    if not base:
        return base
    if base.endswith("/models"):
        return base
    if discovery_type == ProviderType.OLLAMA:
        if base.endswith("/v1"):
            return f"{base}/models"
        return f"{base}/v1/models"
    return f"{base}/models"


def _run_coroutine_sync(coro: Any) -> Any:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    result: dict[str, Any] = {}
    error: dict[str, Exception] = {}

    def _runner() -> None:
        try:
            result["value"] = asyncio.run(coro)
        except Exception as exc:  # pragma: no cover - defensive
            error["value"] = exc

    thread = threading.Thread(target=_runner, daemon=True)
    thread.start()
    thread.join()
    if "value" in error:
        raise error["value"]
    return result.get("value")


@dataclass(frozen=True)
class CapabilityEvidence:
    value: bool | None
    truth: str
    confidence: str
    source: str

    def to_metadata_patch(self, key: str) -> dict[str, Any]:
        patch = {
            f"{key}_truth": self.truth,
            f"{key}_confidence": self.confidence,
            f"{key}_source": self.source,
        }
        if self.value is not None:
            patch[key] = self.value
        return patch


@dataclass(frozen=True)
class DiscoveryProbeResult:
    context_window: int | None = None
    supports_tools: CapabilityEvidence | None = None
    supports_thinking: CapabilityEvidence | None = None
    note: str | None = None


def _merge_model_preview(
    model: dict[str, Any],
    *,
    context_window: int | None,
    metadata_patch: dict[str, Any],
) -> dict[str, Any]:
    merged = dict(model)
    if context_window is not None:
        merged["context_window"] = context_window
    merged.update(metadata_patch)
    return merged


def _diff_updated_fields(before: dict[str, Any], after: dict[str, Any]) -> list[str]:
    changed: list[str] = []
    if _normalize_positive_int(before.get("context_window")) != _normalize_positive_int(after.get("context_window")):
        changed.append("context_window")

    for capability_key in ("supports_tools", "supports_thinking"):
        before_tuple = (
            before.get(capability_key),
            before.get(f"{capability_key}_truth"),
            before.get(f"{capability_key}_confidence"),
            before.get(f"{capability_key}_source"),
        )
        after_tuple = (
            after.get(capability_key),
            after.get(f"{capability_key}_truth"),
            after.get(f"{capability_key}_confidence"),
            after.get(f"{capability_key}_source"),
        )
        if before_tuple != after_tuple:
            changed.append(capability_key)
    return changed


def _classify_capability_error(
    capability_key: str,
    exc: Exception,
) -> CapabilityEvidence:
    message = _normalize_text(str(exc)).lower()
    unsupported_markers = (
        "unsupported",
        "not supported",
        "does not support",
        "not available",
        "unknown parameter",
        "invalid parameter",
        "invalid_request_error",
    )
    if capability_key == "supports_tools":
        feature_markers = ("tool", "tools", "function", "tool_choice")
        source = "active_probe_tool_error"
    else:
        feature_markers = ("thinking", "reasoning", "reasoning_split", "thinking_budget")
        source = "active_probe_thinking_error"

    if any(marker in message for marker in feature_markers) and any(
        marker in message for marker in unsupported_markers
    ):
        return CapabilityEvidence(
            value=False,
            truth="unsupported",
            confidence="high",
            source=source,
        )

    return CapabilityEvidence(
        value=None,
        truth="unknown",
        confidence="low",
        source=source,
    )


class ModelCapabilityProbeService:
    """Probe one configured model for minimal routing-relevant capability facts."""

    def __init__(self, *, catalog_path: Path | None = None) -> None:
        self._registry = ModelRegistryService(catalog_path=catalog_path)

    def probe_model(
        self,
        *,
        source: str,
        provider_id: str,
        model_id: str,
    ) -> dict[str, Any]:
        provider, model = self._registry._resolve_registry_model(
            source=source,
            provider_id=provider_id,
            model_id=model_id,
        )
        before_model = dict(model)
        notes: list[str] = []
        metadata_patch: dict[str, Any] = {}
        context_window_patch: int | None = None
        discovery_attempted = False
        active_probe_attempted = False

        needs_context = _normalize_positive_int(model.get("context_window")) is None
        needs_tools = _capability_truth_from_model(model, "supports_tools") == "unknown"
        needs_thinking = _capability_truth_from_model(model, "supports_thinking") == "unknown"

        preview_model = dict(model)
        if needs_context or needs_tools or needs_thinking:
            discovery_attempted = True
            discovery = self._discover_model_capabilities(
                source=source,
                provider=provider,
                model_id=model_id,
            )
            if discovery.note:
                notes.append(discovery.note)
            if needs_context and discovery.context_window is not None:
                context_window_patch = discovery.context_window
            if needs_tools and discovery.supports_tools is not None:
                metadata_patch.update(discovery.supports_tools.to_metadata_patch("supports_tools"))
            if needs_thinking and discovery.supports_thinking is not None:
                metadata_patch.update(discovery.supports_thinking.to_metadata_patch("supports_thinking"))
            preview_model = _merge_model_preview(
                preview_model,
                context_window=context_window_patch,
                metadata_patch=metadata_patch,
            )

        model_role = _normalize_optional_text(preview_model.get("model_role"))
        if model_role in {"embedding", "ocr"} and (needs_tools or needs_thinking):
            notes.append(f"active probe skipped for feature-role model: {model_role}")
        else:
            if _capability_truth_from_model(preview_model, "supports_tools") == "unknown":
                active_probe_attempted = True
                tools_evidence, note = self._probe_tools_support(
                    source=source,
                    provider_id=provider_id,
                    model_id=model_id,
                )
                if note:
                    notes.append(note)
                if tools_evidence is not None:
                    metadata_patch.update(tools_evidence.to_metadata_patch("supports_tools"))
                preview_model = _merge_model_preview(
                    preview_model,
                    context_window=context_window_patch,
                    metadata_patch=metadata_patch,
                )

            if _capability_truth_from_model(preview_model, "supports_thinking") == "unknown":
                active_probe_attempted = True
                thinking_evidence, note = self._probe_thinking_support(
                    source=source,
                    provider_id=provider_id,
                    model_id=model_id,
                )
                if note:
                    notes.append(note)
                if thinking_evidence is not None:
                    metadata_patch.update(thinking_evidence.to_metadata_patch("supports_thinking"))
                preview_model = _merge_model_preview(
                    preview_model,
                    context_window=context_window_patch,
                    metadata_patch=metadata_patch,
                )

        if context_window_patch is not None or metadata_patch:
            updated_provider = self._registry.record_model_capabilities(
                source=source,
                provider_id=provider_id,
                model_id=model_id,
                context_window=context_window_patch,
                metadata_patch=metadata_patch,
            )
            _, after_model = self._find_provider_model(
                updated_provider,
                model_id=model_id,
            )
        else:
            updated_provider = provider
            after_model = before_model

        return {
            "source": str(updated_provider.get("source") or source),
            "provider_id": str(updated_provider.get("provider_id") or provider_id),
            "provider_name": _normalize_optional_text(updated_provider.get("provider_name")),
            "api_type": _normalize_optional_text(updated_provider.get("api_type")),
            "api_base": _normalize_optional_text(updated_provider.get("api_base")),
            "model_id": str(after_model.get("model_id") or model_id),
            "updated_fields": _diff_updated_fields(before_model, after_model),
            "discovery_attempted": discovery_attempted,
            "active_probe_attempted": active_probe_attempted,
            "notes": notes,
            "model": after_model,
        }

    def _discover_model_capabilities(
        self,
        *,
        source: str,
        provider: dict[str, Any],
        model_id: str,
    ) -> DiscoveryProbeResult:
        try:
            connection = self._resolve_probe_connection(source=source, provider_id=str(provider.get("provider_id") or ""))
        except Exception as exc:
            provider_type = self._infer_discovery_provider_type(
                provider=provider,
                api_type=str(provider.get("api_type") or ""),
                api_base=str(provider.get("api_base") or ""),
            )
            known_context = resolve_known_context_window(provider_type, model_id)
            note = f"discovery probe skipped: {exc}"
            return DiscoveryProbeResult(context_window=known_context, note=note)

        provider_type = self._infer_discovery_provider_type(
            provider=provider,
            api_type=str(connection.get("api_type") or provider.get("api_type") or ""),
            api_base=str(connection.get("api_base") or provider.get("api_base") or ""),
        )
        endpoint = _build_models_endpoint(str(connection.get("api_base") or ""), provider_type)
        discovery_service = ModelDiscoveryService(timeout=10.0)

        try:
            result = _run_coroutine_sync(
                asyncio.wait_for(
                    discovery_service.discover_models(
                        provider=provider_type,
                        api_key=str(connection.get("api_key") or ""),
                        api_base=endpoint,
                        use_cache=False,
                    ),
                    timeout=12.0,
                )
            )
        except Exception as exc:
            known_context = resolve_known_context_window(provider_type, model_id)
            return DiscoveryProbeResult(
                context_window=known_context,
                note=f"discovery probe failed: {exc}",
            )

        matched = next(
            (
                item
                for item in result.available_models
                if _normalize_text(item.id).lower() == _normalize_text(model_id).lower()
            ),
            None,
        )
        if matched is None:
            return DiscoveryProbeResult(
                context_window=resolve_known_context_window(provider_type, model_id),
                note=f"discovery probe did not return model '{model_id}'",
            )

        discovery_confidence = discovery_confidence_for_source(result.discovery_source)
        supports = infer_model_capabilities(
            provider_type,
            model_id,
            raw_capabilities=matched.capabilities,
        )
        return DiscoveryProbeResult(
            context_window=(
                _normalize_positive_int(matched.context_window)
                or resolve_known_context_window(provider_type, model_id)
            ),
            supports_tools=CapabilityEvidence(
                value=supports.get("supports_tools"),
                truth=_normalize_capability_truth(supports.get("supports_tools_truth")),
                confidence=_normalize_optional_text(supports.get("supports_tools_confidence"))
                or discovery_confidence,
                source=_normalize_optional_text(supports.get("supports_tools_source"))
                or result.discovery_source,
            ),
            supports_thinking=CapabilityEvidence(
                value=supports.get("supports_thinking"),
                truth=_normalize_capability_truth(supports.get("supports_thinking_truth")),
                confidence=_normalize_optional_text(supports.get("supports_thinking_confidence"))
                or discovery_confidence,
                source=_normalize_optional_text(supports.get("supports_thinking_source"))
                or result.discovery_source,
            ),
        )

    def _resolve_probe_connection(
        self,
        *,
        source: str,
        provider_id: str,
    ) -> dict[str, str]:
        normalized_source = _normalize_text(source).lower()
        normalized_provider_id = _normalize_text(provider_id)
        if normalized_source == "custom":
            provider = self._registry._load_custom_catalog().find(normalized_provider_id)
            if provider is None:
                raise ValueError(f"custom provider not found: {provider_id}")
            return {
                "api_type": provider.api_type.value,
                "api_base": provider.api_base,
                "api_key": provider.api_key,
            }

        preset = get_preset_provider_config(
            PresetProvider(normalized_provider_id),
            use_latest_model=False,
            allow_unreachable_local=True,
            discover_inventory=False,
        )
        if not preset:
            raise ValueError(f"preset provider not configured: {provider_id}")
        return {
            "api_type": str(preset["api_type"]),
            "api_base": str(preset["api_base"]),
            "api_key": str(preset["api_key"]),
        }

    @staticmethod
    def _infer_discovery_provider_type(
        *,
        provider: dict[str, Any],
        api_type: str,
        api_base: str,
    ) -> ProviderType:
        variant = _normalize_text(provider.get("provider_variant")).lower()
        family = _normalize_text(provider.get("provider_family")).lower()
        provider_id = _normalize_text(provider.get("provider_id")).lower()
        base = _normalize_text(api_base).lower()
        normalized_api_type = _normalize_text(api_type).lower()
        if variant == "minimax" or "minimax" in base or "minimaxi" in base:
            return ProviderType.MINIMAX
        if provider_id == "ollama" or family == "ollama" or "11434" in base:
            return ProviderType.OLLAMA
        if normalized_api_type == "anthropic" or family == "anthropic":
            return ProviderType.ANTHROPIC
        return ProviderType.OPENAI

    async def _run_probe_completion(
        self,
        *,
        source: str,
        provider_id: str,
        model_id: str,
        request_policy: ProtocolRequestPolicy,
        messages: list[Message],
        tools: list[dict[str, Any]] | None = None,
    ) -> Any:
        candidate = resolve_pinned_llm_candidate(
            provider_source=source,
            provider_id=provider_id,
            model_id=model_id,
            catalog_path=self._registry.catalog_path,
        )
        profile = build_protocol_execution_profile(
            api_key=candidate.api_key,
            provider=candidate.provider,
            api_base=candidate.api_base,
            model=candidate.model,
            client_headers=dict(candidate.headers or {}),
            request_timeout_seconds=min(int(candidate.timeout or 60), 20),
            request_policy=request_policy,
        )
        client = LLMClient(
            profile=profile,
            retry_config=RetryConfig(enabled=False),
        )
        try:
            return await client.generate(messages=messages, tools=tools)
        finally:
            await client.close()

    def _probe_tools_support(
        self,
        *,
        source: str,
        provider_id: str,
        model_id: str,
    ) -> tuple[CapabilityEvidence | None, str | None]:
        messages = [
            Message(
                role="user",
                content='Call the noop_probe tool with {"ping":"pong"} and do not add extra text.',
            )
        ]
        tools = [
            {
                "name": "noop_probe",
                "description": "Capability probe tool.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "ping": {"type": "string"},
                    },
                    "required": ["ping"],
                },
            }
        ]

        def _execute_tool_probe(*, tool_choice_policy: str) -> Any:
            request_policy = ProtocolRequestPolicy(
                max_output_tokens=64,
                temperature=0.0,
                streaming_enabled=False,
                include_stream_usage=False,
                tool_choice_policy=tool_choice_policy,
            )
            return _run_coroutine_sync(
                self._run_probe_completion(
                    source=source,
                    provider_id=provider_id,
                    model_id=model_id,
                    request_policy=request_policy,
                    messages=messages,
                    tools=tools,
                )
            )

        required_result: Any | None = None
        required_failure: Exception | None = None
        try:
            required_result = _execute_tool_probe(tool_choice_policy="required")
        except Exception as exc:
            required_failure = exc

        if getattr(required_result, "tool_calls", None):
            return (
                CapabilityEvidence(
                    value=True,
                    truth="supported",
                    confidence="high",
                    source="active_probe_tool_call",
                ),
                None,
            )

        auto_note: str | None = None
        try:
            auto_result = _execute_tool_probe(tool_choice_policy="auto")
        except Exception as exc:
            if required_failure is not None:
                auto_note = (
                    "tool probe failed after auto fallback; "
                    f"required-mode failure: {required_failure}"
                )
            elif required_result is not None:
                auto_note = "tool probe failed after auto fallback from required-mode no-tool result"
            return _classify_capability_error("supports_tools", exc), (
                f"tool probe failed: {exc}"
                if auto_note is None
                else f"{auto_note}; auto-mode failure: {exc}"
            )

        if getattr(auto_result, "tool_calls", None):
            if required_failure is not None:
                auto_note = f"tool probe auto-mode succeeded after required-mode failure: {required_failure}"
            elif required_result is not None:
                auto_note = "tool probe auto-mode succeeded after required-mode returned no tool call"
            return (
                CapabilityEvidence(
                    value=True,
                    truth="supported",
                    confidence="high",
                    source="active_probe_tool_call",
                ),
                auto_note,
            )

        if required_failure is not None:
            auto_note = (
                "tool probe auto-mode returned no tool call after "
                f"required-mode failure: {required_failure}"
            )
        elif required_result is not None:
            auto_note = "tool probe auto-mode returned no tool call after required-mode returned no tool call"
        return (
            CapabilityEvidence(
                value=False,
                truth="unsupported",
                confidence="medium",
                source="active_probe_no_tool_call",
            ),
            auto_note,
        )

    def _probe_thinking_support(
        self,
        *,
        source: str,
        provider_id: str,
        model_id: str,
    ) -> tuple[CapabilityEvidence | None, str | None]:
        request_policy = ProtocolRequestPolicy(
            max_output_tokens=96,
            temperature=0.0,
            streaming_enabled=False,
            include_stream_usage=False,
            thinking_budget_tokens=256,
        )
        messages = [
            Message(
                role="user",
                content="Think briefly, then answer with the single word READY.",
            )
        ]

        try:
            result = _run_coroutine_sync(
                self._run_probe_completion(
                    source=source,
                    provider_id=provider_id,
                    model_id=model_id,
                    request_policy=request_policy,
                    messages=messages,
                )
            )
        except Exception as exc:
            return _classify_capability_error("supports_thinking", exc), f"thinking probe failed: {exc}"

        if _normalize_optional_text(getattr(result, "thinking", None)):
            return (
                CapabilityEvidence(
                    value=True,
                    truth="supported",
                    confidence="high",
                    source="active_probe_thinking_content",
                ),
                None,
            )

        return (
            CapabilityEvidence(
                value=False,
                truth="unsupported",
                confidence="medium",
                source="active_probe_no_thinking",
            ),
            None,
        )

    @staticmethod
    def _find_provider_model(provider: dict[str, Any], *, model_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
        normalized_model_id = _normalize_text(model_id).lower()
        for item in provider.get("models", []):
            if _normalize_text(item.get("model_id")).lower() == normalized_model_id:
                return provider, dict(item)
        raise ValueError(f"model '{model_id}' is not available in provider summary")
