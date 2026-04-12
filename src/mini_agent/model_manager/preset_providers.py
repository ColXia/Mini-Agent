"""Preset provider configurations for quick setup via environment variables.

This module provides predefined provider configurations that can be activated
by setting standard environment variables (OPENAI_API_KEY, ANTHROPIC_API_KEY, etc).

Usage:
    export OPENAI_API_KEY="sk-..."
    mini-agent  # Automatically uses OpenAI provider

    export ANTHROPIC_API_KEY="sk-ant-..."
    mini-agent  # Automatically uses Anthropic/Claude provider
"""

from __future__ import annotations

import asyncio
import os
import threading
from dataclasses import dataclass
from enum import Enum
from typing import Any


class PresetProvider(str, Enum):
    """Supported preset providers with standard environment variables."""

    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GEMINI = "gemini"
    MINIMAX = "minimax"


@dataclass
class PresetProviderConfig:
    """Configuration for a preset provider."""

    name: str
    env_key: str
    api_base: str
    api_type: str
    default_model: str
    models: list[str]
    priority: int = 0
    description: str = ""
    discovery_type: str = ""


# Preset provider configurations
PRESET_PROVIDERS: dict[PresetProvider, PresetProviderConfig] = {
    PresetProvider.OPENAI: PresetProviderConfig(
        name="OpenAI",
        env_key="OPENAI_API_KEY",
        api_base="https://api.openai.com/v1",
        api_type="openai",
        default_model="gpt-5.4",
        models=[
            "gpt-5.4",
            "gpt-5.3",
            "gpt-5.2",
            "gpt-5.1",
            "gpt-4.1",
            "gpt-4o",
        ],
        priority=10,
        description="OpenAI GPT models",
        discovery_type="openai",
    ),
    PresetProvider.ANTHROPIC: PresetProviderConfig(
        name="Anthropic Claude",
        env_key="ANTHROPIC_API_KEY",
        api_base="https://api.anthropic.com",
        api_type="anthropic",
        default_model="claude-sonnet-4-6",
        models=[
            "claude-sonnet-4-6",
            "claude-opus-4-1",
            "claude-sonnet-4-5",
            "claude-haiku-4-0",
        ],
        priority=10,
        description="Anthropic Claude models",
        discovery_type="anthropic",
    ),
    PresetProvider.GEMINI: PresetProviderConfig(
        name="Google Gemini",
        env_key="GEMINI_API_KEY",
        api_base="https://generativelanguage.googleapis.com/v1beta",
        api_type="openai",
        default_model="gemini-3.1-pro",
        models=[
            "gemini-3.1-pro",
            "gemini-3.1-flash",
            "gemini-2.5-pro",
            "gemini-2.0-flash",
            "gemini-1.5-pro",
        ],
        priority=10,
        description="Google Gemini models",
        discovery_type="gemini",
    ),
    PresetProvider.MINIMAX: PresetProviderConfig(
        name="MiniMax",
        env_key="MINIMAX_API_KEY",
        api_base="https://api.minimaxi.com",
        api_type="anthropic",
        default_model="MiniMax-M2.7",
        models=[
            "MiniMax-M2.7",
            "MiniMax-M2.5",
            "MiniMax-M1",
            "abab6.5s-chat",
            "abab6.5-chat",
        ],
        priority=10,
        description="MiniMax models (China region)",
        discovery_type="minimax",
    ),
}


def _resolve_api_key_from_env(
    config: PresetProviderConfig,
) -> tuple[str | None, str | None]:
    """Resolve provider API key from primary env key then aliases."""
    env_key = config.env_key
    api_key = os.getenv(env_key)
    if api_key and not _is_placeholder_key(api_key):
        return api_key, env_key
    return None, None


def detect_preset_providers() -> list[tuple[PresetProvider, str]]:
    """Detect available preset providers from environment variables.

    Returns:
        List of (provider, api_key) tuples for providers with valid API keys
    """
    detected = []

    for provider, config in PRESET_PROVIDERS.items():
        api_key, _ = _resolve_api_key_from_env(config)
        if api_key:
            detected.append((provider, api_key))

    return detected


def _run_coroutine_sync(coro: Any) -> Any:
    """Run coroutine from sync context, even if an event loop is active."""
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


def _discovery_provider_name(provider: PresetProvider) -> str:
    config = PRESET_PROVIDERS.get(provider)
    if config and config.discovery_type:
        return config.discovery_type
    return provider.value


def _is_flagship_model(provider: PresetProvider, model_id: str) -> bool:
    """Filter obvious non-chat/non-flagship models from discovery output."""
    normalized = model_id.lower()
    blocked_tokens = (
        "embedding",
        "moderation",
        "whisper",
        "tts",
        "audio",
        "image",
        "vision",
        "speech",
        "transcribe",
        "rerank",
    )
    if any(token in normalized for token in blocked_tokens):
        return False

    if provider == PresetProvider.OPENAI:
        return normalized.startswith("gpt-") or normalized.startswith("o")
    if provider == PresetProvider.ANTHROPIC:
        return "claude" in normalized
    if provider == PresetProvider.GEMINI:
        return normalized.startswith("gemini")
    if provider == PresetProvider.MINIMAX:
        return normalized.startswith("minimax") or normalized.startswith("abab")
    return True


def _discover_latest_model(provider: PresetProvider, api_key: str) -> str | None:
    """Discover latest available model and return a flagship candidate."""
    from mini_agent.model_manager.model_discovery import get_latest_model_id

    provider_name = _discovery_provider_name(provider)
    try:
        model_id = _run_coroutine_sync(
            asyncio.wait_for(get_latest_model_id(provider_name, api_key), timeout=6.0)
        )
    except Exception:
        return None

    if isinstance(model_id, str) and model_id and _is_flagship_model(provider, model_id):
        return model_id
    return None


def get_preset_provider_config(
    provider: PresetProvider,
    api_key: str | None = None,
    *,
    use_latest_model: bool = True,
) -> dict[str, Any] | None:
    """Get configuration for a preset provider.

    Args:
        provider: Preset provider type
        api_key: Optional API key (uses environment variable if not provided)

    Returns:
        Provider configuration dict or None if not available
    """
    config = PRESET_PROVIDERS.get(provider)
    if not config:
        return None

    # Get API key from environment if not provided
    if not api_key:
        api_key, _ = _resolve_api_key_from_env(config)

    if not api_key or _is_placeholder_key(api_key):
        return None

    selected_model = config.default_model
    if use_latest_model:
        latest_model = _discover_latest_model(provider, api_key)
        if latest_model:
            selected_model = latest_model

    model_candidates = [selected_model, *[m for m in config.models if m != selected_model]]

    return {
        "id": f"preset-{provider.value}",
        "provider": provider.value,
        "name": config.name,
        "api_type": config.api_type,
        "api_base": config.api_base,
        "api_key": api_key,
        "model": selected_model,
        "default_model": config.default_model,
        "models": model_candidates,
        "enabled": True,
        "priority": config.priority,
    }


def get_first_available_preset(*, use_latest_model: bool = True) -> dict[str, Any] | None:
    """Get the first available preset provider configuration.

    Returns:
        Provider configuration dict or None if no presets available
    """
    detected = detect_preset_providers()
    if not detected:
        return None

    provider, api_key = detected[0]
    return get_preset_provider_config(
        provider,
        api_key,
        use_latest_model=use_latest_model,
    )


def _is_placeholder_key(api_key: str) -> bool:
    """Check if API key is a placeholder value.

    Args:
        api_key: API key to check

    Returns:
        True if the key is a placeholder
    """
    placeholders = {
        "YOUR_API_KEY_HERE",
        "YOUR_OPENAI_API_KEY_HERE",
        "YOUR_GEMINI_API_KEY_HERE",
        "YOUR_ANTHROPIC_API_KEY_HERE",
        "YOUR_MINIMAX_API_KEY_HERE",
        "your_api_key",
        "your-api-key",
        "sk-cp-xxxxx",
        "sk-...",
        "sk-ant-...",
    }

    stripped = api_key.strip()
    return (
        stripped in placeholders
        or stripped.endswith("...")
        or (stripped.startswith("${") and stripped.endswith("}"))
        or (stripped.startswith("$") and len(stripped) > 1)
    )


def list_preset_providers() -> list[dict[str, Any]]:
    """List all preset providers with their status.

    Returns:
        List of provider info dicts
    """
    result = []

    for provider, config in PRESET_PROVIDERS.items():
        api_key, configured_env_key = _resolve_api_key_from_env(config)
        is_configured = bool(api_key)
        env_label = config.env_key

        result.append(
            {
                "provider": provider.value,
                "name": config.name,
                "env_key": env_label,
                "configured_env_key": configured_env_key,
                "api_base": config.api_base,
                "default_model": config.default_model,
                "is_configured": is_configured,
                "description": config.description,
            }
        )

    return result


def list_configured_preset_provider_configs(
    *,
    use_latest_model: bool = True,
) -> list[dict[str, Any]]:
    """Return configured preset provider configs (API key available)."""
    configured: list[dict[str, Any]] = []
    for provider in PresetProvider:
        preset = get_preset_provider_config(provider, use_latest_model=use_latest_model)
        if preset:
            configured.append(preset)
    return configured
