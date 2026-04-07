"""Preset provider configurations for quick setup via environment variables.

This module provides predefined provider configurations that can be activated
by setting standard environment variables (OPENAI_API_KEY, ANTHROPIC_API_KEY, etc).

Usage:
    export OPENAI_API_KEY="sk-..."
    mini-agent  # Automatically uses OpenAI provider

    export ANTHROPIC_API_KEY="sk-ant-..."
    mini-agent  # Automatically uses Anthropic provider
"""

from __future__ import annotations

import os
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


# Preset provider configurations
PRESET_PROVIDERS: dict[PresetProvider, PresetProviderConfig] = {
    PresetProvider.OPENAI: PresetProviderConfig(
        name="OpenAI",
        env_key="OPENAI_API_KEY",
        api_base="https://api.openai.com/v1",
        api_type="openai",
        default_model="gpt-4o",
        models=[
            "gpt-4o",
            "gpt-4o-mini",
            "gpt-4-turbo",
            "gpt-4",
            "gpt-3.5-turbo",
            "o1",
            "o1-mini",
            "o1-preview",
        ],
        priority=10,
        description="OpenAI GPT models",
    ),
    PresetProvider.ANTHROPIC: PresetProviderConfig(
        name="Anthropic",
        env_key="ANTHROPIC_API_KEY",
        api_base="https://api.anthropic.com",
        api_type="anthropic",
        default_model="claude-3-5-sonnet-20241022",
        models=[
            "claude-3-5-sonnet-20241022",
            "claude-3-5-haiku-20241022",
            "claude-3-opus-20240229",
            "claude-3-sonnet-20240229",
            "claude-3-haiku-20240307",
        ],
        priority=10,
        description="Anthropic Claude models",
    ),
    PresetProvider.GEMINI: PresetProviderConfig(
        name="Google Gemini",
        env_key="GEMINI_API_KEY",
        api_base="https://generativelanguage.googleapis.com/v1beta",
        api_type="openai",
        default_model="gemini-2.0-flash-exp",
        models=[
            "gemini-2.0-flash-exp",
            "gemini-exp-1206",
            "gemini-1.5-pro",
            "gemini-1.5-flash",
            "gemini-1.5-pro-002",
            "gemini-1.5-flash-002",
        ],
        priority=10,
        description="Google Gemini models",
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
    ),
}


def detect_preset_providers() -> list[tuple[PresetProvider, str]]:
    """Detect available preset providers from environment variables.

    Returns:
        List of (provider, api_key) tuples for providers with valid API keys
    """
    detected = []

    for provider, config in PRESET_PROVIDERS.items():
        api_key = os.getenv(config.env_key)
        if api_key and not _is_placeholder_key(api_key):
            detected.append((provider, api_key))

    return detected


def get_preset_provider_config(
    provider: PresetProvider,
    api_key: str | None = None,
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
        api_key = os.getenv(config.env_key)

    if not api_key or _is_placeholder_key(api_key):
        return None

    return {
        "id": f"preset-{provider.value}",
        "name": config.name,
        "api_type": config.api_type,
        "api_base": config.api_base,
        "api_key": api_key,
        "models": config.models,
        "enabled": True,
        "priority": config.priority,
    }


def get_first_available_preset() -> dict[str, Any] | None:
    """Get the first available preset provider configuration.

    Returns:
        Provider configuration dict or None if no presets available
    """
    detected = detect_preset_providers()
    if not detected:
        return None

    provider, api_key = detected[0]
    return get_preset_provider_config(provider, api_key)


def _is_placeholder_key(api_key: str) -> bool:
    """Check if API key is a placeholder value.

    Args:
        api_key: API key to check

    Returns:
        True if the key is a placeholder
    """
    placeholders = {
        "YOUR_API_KEY_HERE",
        "your_api_key",
        "your-api-key",
        "sk-cp-xxxxx",
        "sk-...",
        "sk-ant-...",
    }

    return api_key.strip() in placeholders or api_key.strip().endswith("...")


def list_preset_providers() -> list[dict[str, Any]]:
    """List all preset providers with their status.

    Returns:
        List of provider info dicts
    """
    result = []

    for provider, config in PRESET_PROVIDERS.items():
        api_key = os.getenv(config.env_key)
        is_configured = bool(api_key and not _is_placeholder_key(api_key))

        result.append(
            {
                "provider": provider.value,
                "name": config.name,
                "env_key": config.env_key,
                "api_base": config.api_base,
                "default_model": config.default_model,
                "is_configured": is_configured,
                "description": config.description,
            }
        )

    return result
