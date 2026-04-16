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
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any
from urllib.parse import urlsplit

import httpx


class PresetProvider(str, Enum):
    """Supported preset providers with standard environment variables."""

    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    MINIMAX = "minimax"
    OLLAMA = "ollama"


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
    bootstrap_priority: int = 0
    description: str = ""
    discovery_type: str = ""


@dataclass(frozen=True)
class BootstrapPresetCandidate:
    """Detected preset candidate for bootstrap selection."""

    provider: PresetProvider
    api_key: str
    env_key: str
    bootstrap_priority: int
    priority: int
    local_provider: bool


@dataclass(frozen=True)
class BootstrapPresetSelection:
    """Policy-driven bootstrap preset selection outcome."""

    preset: dict[str, Any] | None
    selected_provider: PresetProvider | None
    selected_reason: str | None
    selection_policy: str
    preferred_provider: str | None = None
    preferred_provider_available: bool = False
    alternatives: list[dict[str, Any]] = field(default_factory=list)


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
        bootstrap_priority=400,
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
        bootstrap_priority=300,
        description="Anthropic Claude models",
        discovery_type="anthropic",
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
        bootstrap_priority=200,
        description="MiniMax models (China region)",
        discovery_type="minimax",
    ),
    PresetProvider.OLLAMA: PresetProviderConfig(
        name="Ollama Local",
        env_key="MINI_AGENT_OLLAMA_ENABLED",
        api_base="http://localhost:11434",
        api_type="anthropic",
        default_model="qwen3-coder",
        models=[
            "qwen3-coder",
            "gpt-oss:20b",
            "glm-4.7:cloud",
            "minimax-m2.1:cloud",
        ],
        priority=1,
        bootstrap_priority=100,
        description="Local Ollama daemon (set MINI_AGENT_OLLAMA_ENABLED=1, optional OLLAMA_HOST override)",
        discovery_type="ollama",
    ),
}

_OLLAMA_SENTINEL_API_KEY = "ollama"
_OLLAMA_REACHABILITY_CACHE: dict[str, Any] = {
    "host_base": None,
    "available": False,
    "checked_at": 0.0,
}


def _parse_bool(value: str | None, *, default: bool) -> bool:
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return default


def _normalize_local_url(value: str | None, *, fallback: str) -> str:
    raw = str(value or "").strip().rstrip("/")
    if not raw:
        raw = fallback
    if "://" not in raw:
        raw = f"http://{raw}"
    parsed = urlsplit(raw)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return fallback
    path = parsed.path.rstrip("/")
    lowered = path.lower()
    for suffix in ("/v1", "/anthropic"):
        if lowered.endswith(suffix):
            path = path[: -len(suffix)]
            lowered = path.lower()
    return f"{parsed.scheme}://{parsed.netloc}{path}"


def _is_loopback_host(url: str | None) -> bool:
    normalized = str(url or "").strip()
    if not normalized:
        return False
    try:
        parsed = urlsplit(normalized)
    except Exception:
        return False
    host = str(parsed.hostname or "").strip().lower()
    return host in {"localhost", "127.0.0.1", "::1"}


def _ollama_host_base() -> str:
    return _normalize_local_url(
        os.getenv("OLLAMA_HOST") or os.getenv("MINI_AGENT_OLLAMA_BASE_URL"),
        fallback="http://localhost:11434",
    )


def _ollama_protocol() -> str:
    normalized = " ".join(
        (os.getenv("MINI_AGENT_OLLAMA_PROTOCOL") or "").strip().split()
    ).lower()
    if normalized == "openai":
        return "openai"
    return "anthropic"


def _ollama_api_base() -> str:
    host = _ollama_host_base()
    if _ollama_protocol() == "openai":
        return f"{host}/v1"
    return host


def _ollama_enabled() -> bool:
    return _parse_bool(
        os.getenv("MINI_AGENT_OLLAMA_ENABLED") or os.getenv("MINI_AGENT_ENABLE_OLLAMA"),
        default=False,
    )


def _is_ollama_reachable(host_base: str) -> bool:
    now = time.monotonic()
    cached_host = str(_OLLAMA_REACHABILITY_CACHE.get("host_base") or "")
    checked_at = float(_OLLAMA_REACHABILITY_CACHE.get("checked_at") or 0.0)
    if cached_host == host_base and (now - checked_at) < 5.0:
        return bool(_OLLAMA_REACHABILITY_CACHE.get("available"))

    available = False
    try:
        with httpx.Client(timeout=1.0, trust_env=not _is_loopback_host(host_base)) as client:
            response = client.get(f"{host_base}/api/tags")
            response.raise_for_status()
            available = True
    except Exception:
        try:
            with httpx.Client(timeout=1.0, trust_env=not _is_loopback_host(host_base)) as client:
                response = client.get(f"{host_base}/v1/models")
                response.raise_for_status()
                available = True
        except Exception:
            available = False

    _OLLAMA_REACHABILITY_CACHE.update(
        {
            "host_base": host_base,
            "available": available,
            "checked_at": now,
        }
    )
    return available


def _resolve_api_key_from_env(
    provider: PresetProvider,
    config: PresetProviderConfig,
    *,
    allow_unreachable_local: bool = False,
) -> tuple[str | None, str | None]:
    """Resolve provider API key from primary env key then aliases."""
    if provider == PresetProvider.OLLAMA:
        if not _ollama_enabled():
            return None, None
        if not allow_unreachable_local and not _is_ollama_reachable(_ollama_host_base()):
            return None, None
        return _OLLAMA_SENTINEL_API_KEY, config.env_key

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
        api_key, _ = _resolve_api_key_from_env(provider, config)
        if api_key:
            detected.append((provider, api_key))

    return detected


def _normalize_preset_provider_name(value: PresetProvider | str | None) -> PresetProvider | None:
    if isinstance(value, PresetProvider):
        return value
    normalized = " ".join(str(value or "").strip().split()).lower()
    if not normalized:
        return None
    try:
        return PresetProvider(normalized)
    except ValueError:
        return None


def _bootstrap_preferred_provider(
    preferred_provider: PresetProvider | str | None = None,
) -> PresetProvider | None:
    explicit = _normalize_preset_provider_name(preferred_provider)
    if explicit is not None:
        return explicit
    return _normalize_preset_provider_name(
        os.getenv("MINI_AGENT_BOOTSTRAP_PRESET_PROVIDER")
        or os.getenv("MINI_AGENT_BOOTSTRAP_PROVIDER")
    )


def _bootstrap_preset_candidates() -> list[BootstrapPresetCandidate]:
    candidates: list[BootstrapPresetCandidate] = []
    for provider, api_key in detect_preset_providers():
        config = PRESET_PROVIDERS.get(provider)
        if config is None:
            continue
        candidates.append(
            BootstrapPresetCandidate(
                provider=provider,
                api_key=api_key,
                env_key=config.env_key,
                bootstrap_priority=int(config.bootstrap_priority),
                priority=int(config.priority),
                local_provider=provider == PresetProvider.OLLAMA,
            )
        )
    return candidates


def _bootstrap_candidate_sort_key(
    candidate: BootstrapPresetCandidate,
    *,
    preferred_provider: PresetProvider | None,
) -> tuple[int, int, str]:
    return (
        1 if preferred_provider is not None and candidate.provider == preferred_provider else 0,
        int(candidate.bootstrap_priority),
        candidate.provider.value,
    )


def resolve_bootstrap_preset_selection(
    *,
    use_latest_model: bool = True,
    preferred_provider: PresetProvider | str | None = None,
) -> BootstrapPresetSelection:
    """Resolve one bootstrap preset using explicit policy instead of dict order."""

    selection_policy = "explicit_preference_then_bootstrap_priority_then_provider_id"
    resolved_preference = _bootstrap_preferred_provider(preferred_provider)
    candidates = sorted(
        _bootstrap_preset_candidates(),
        key=lambda item: _bootstrap_candidate_sort_key(
            item,
            preferred_provider=resolved_preference,
        ),
        reverse=True,
    )
    preferred_available = any(
        resolved_preference is not None and item.provider == resolved_preference
        for item in candidates
    )

    selected_preset: dict[str, Any] | None = None
    selected_provider: PresetProvider | None = None
    selected_reason: str | None = None

    for candidate in candidates:
        preset = get_preset_provider_config(
            candidate.provider,
            candidate.api_key,
            use_latest_model=use_latest_model,
        )
        if preset is None:
            continue
        selected_preset = preset
        selected_provider = candidate.provider
        if resolved_preference is not None and candidate.provider == resolved_preference:
            selected_reason = "explicit_preference"
        else:
            selected_reason = "bootstrap_priority"
        break

    alternatives = [
        {
            "provider": candidate.provider.value,
            "env_key": candidate.env_key,
            "bootstrap_priority": candidate.bootstrap_priority,
            "priority": candidate.priority,
            "local_provider": candidate.local_provider,
        }
        for candidate in candidates
        if selected_provider is None or candidate.provider != selected_provider
    ]

    if selected_preset is not None and selected_provider is not None:
        selected_preset = {
            **selected_preset,
            "bootstrap_selected_provider": selected_provider.value,
            "bootstrap_selection_reason": selected_reason,
            "bootstrap_selection_policy": selection_policy,
            "bootstrap_preferred_provider": (
                resolved_preference.value if resolved_preference is not None else None
            ),
            "bootstrap_preferred_provider_available": preferred_available,
            "bootstrap_alternatives": alternatives,
        }

    return BootstrapPresetSelection(
        preset=selected_preset,
        selected_provider=selected_provider,
        selected_reason=selected_reason,
        selection_policy=selection_policy,
        preferred_provider=resolved_preference.value if resolved_preference is not None else None,
        preferred_provider_available=preferred_available,
        alternatives=alternatives,
    )


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


def _discover_preset_inventory(
    provider: PresetProvider,
    api_key: str,
    *,
    api_base: str | None = None,
) -> dict[str, Any] | None:
    """Discover preset inventory and choose a recommended model explicitly."""

    from mini_agent.model_manager.model_discovery import (
        ModelDiscoveryService,
        ProviderType,
        is_flagship_model,
        recommend_discovered_model,
    )

    config = PRESET_PROVIDERS[provider]
    provider_name = _discovery_provider_name(provider)
    try:
        provider_type = ProviderType(provider_name)
        result = _run_coroutine_sync(
            asyncio.wait_for(
                ModelDiscoveryService().discover_models(
                    provider_type,
                    api_key,
                    api_base=api_base,
                ),
                timeout=6.0,
            )
        )
    except Exception:
        return None

    discovered_models: list[str] = []
    seen: set[str] = set()
    for item in result.available_models:
        model_id = str(item.id or "").strip()
        if not model_id or not is_flagship_model(provider_type, model_id):
            continue
        lowered = model_id.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        discovered_models.append(model_id)

    recommendation = recommend_discovered_model(
        provider_type,
        result,
        curated_order=config.models,
        official_default=config.default_model,
    )
    if recommendation is None:
        return None

    return {
        "selected_model": recommendation.model_id,
        "selection_strategy": recommendation.strategy,
        "selection_confidence": recommendation.confidence,
        "discovery_source": recommendation.discovery_source,
        "discovered_models": discovered_models,
    }


def get_preset_provider_config(
    provider: PresetProvider,
    api_key: str | None = None,
    *,
    use_latest_model: bool = True,
    allow_unreachable_local: bool = False,
    discover_inventory: bool | None = None,
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
        api_key, _ = _resolve_api_key_from_env(
            provider,
            config,
            allow_unreachable_local=allow_unreachable_local,
        )

    if not api_key or _is_placeholder_key(api_key):
        return None

    resolved_api_base = _ollama_api_base() if provider == PresetProvider.OLLAMA else config.api_base
    resolved_api_type = _ollama_protocol() if provider == PresetProvider.OLLAMA else config.api_type

    selected_model = config.default_model
    default_model_strategy = "official_default"
    default_model_confidence = "medium"
    discovery_source = "configured_default"
    discovered_models: list[str] = []
    should_discover = (
        bool(discover_inventory)
        if discover_inventory is not None
        else (use_latest_model or provider == PresetProvider.OLLAMA)
    )
    if should_discover:
        inventory = _discover_preset_inventory(
            provider,
            api_key,
            api_base=resolved_api_base,
        )
        if inventory:
            selected_model = str(inventory.get("selected_model") or selected_model).strip() or selected_model
            default_model_strategy = str(inventory.get("selection_strategy") or default_model_strategy)
            default_model_confidence = str(
                inventory.get("selection_confidence") or default_model_confidence
            )
            discovery_source = str(inventory.get("discovery_source") or discovery_source)
            discovered_models = [
                str(item).strip()
                for item in inventory.get("discovered_models", [])
                if str(item).strip()
            ]
        elif provider == PresetProvider.OLLAMA and not allow_unreachable_local:
            return None

    model_candidates = [
        selected_model,
        *[m for m in discovered_models if m != selected_model],
        *[m for m in config.models if m != selected_model and m not in discovered_models],
    ]

    return {
        "id": f"preset-{provider.value}",
        "provider": provider.value,
        "name": config.name,
        "api_type": resolved_api_type,
        "api_base": resolved_api_base,
        "api_key": api_key,
        "model": selected_model,
        "default_model": config.default_model,
        "models": model_candidates,
        "default_model_strategy": default_model_strategy,
        "default_model_confidence": default_model_confidence,
        "discovery_source": discovery_source,
        "enabled": True,
        "priority": config.priority,
    }


def get_first_available_preset(*, use_latest_model: bool = True) -> dict[str, Any] | None:
    """Get the first available preset provider configuration.

    Returns:
        Provider configuration dict or None if no presets available
    """
    selection = resolve_bootstrap_preset_selection(use_latest_model=use_latest_model)
    return selection.preset


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
        api_key, configured_env_key = _resolve_api_key_from_env(provider, config)
        is_configured = bool(api_key)
        env_label = config.env_key
        api_base = _ollama_api_base() if provider == PresetProvider.OLLAMA else config.api_base
        default_model = config.default_model
        if provider == PresetProvider.OLLAMA and is_configured:
            preset = get_preset_provider_config(provider, api_key, use_latest_model=True)
            if preset:
                default_model = str(preset.get("model") or default_model)

        result.append(
            {
                "provider": provider.value,
                "name": config.name,
                "env_key": env_label,
                "configured_env_key": configured_env_key,
                "api_base": api_base,
                "default_model": default_model,
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
