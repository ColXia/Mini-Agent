"""Bootstrap-only LLM route input models."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


def _normalize_text(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


@dataclass(frozen=True)
class BootstrapLLMSettings:
    """Minimal bootstrap input for synthetic registry fallback."""

    provider: str
    api_base: str
    api_key: str
    model: str
    bootstrap_selected_provider: str | None = None
    bootstrap_selection_reason: str | None = None
    bootstrap_selection_policy: str | None = None
    bootstrap_preferred_provider: str | None = None
    bootstrap_preferred_provider_available: bool | None = None
    bootstrap_alternatives: tuple[dict[str, Any], ...] = ()


def bootstrap_llm_settings_from_config(config: Any) -> BootstrapLLMSettings | None:
    """Extract the minimal bootstrap route input from a loaded config object."""

    llm = getattr(config, "llm", None)
    if llm is None:
        return None

    provider = _normalize_text(getattr(llm, "provider", ""))
    api_base = _normalize_text(getattr(llm, "api_base", ""))
    api_key = _normalize_text(getattr(llm, "api_key", ""))
    model = _normalize_text(getattr(llm, "model", ""))
    if not provider or not api_base or not api_key or not model:
        return None

    return BootstrapLLMSettings(
        provider=provider,
        api_base=api_base,
        api_key=api_key,
        model=model,
        bootstrap_selected_provider=_normalize_text(
            getattr(llm, "bootstrap_selected_provider", "")
        )
        or None,
        bootstrap_selection_reason=_normalize_text(
            getattr(llm, "bootstrap_selection_reason", "")
        )
        or None,
        bootstrap_selection_policy=_normalize_text(
            getattr(llm, "bootstrap_selection_policy", "")
        )
        or None,
        bootstrap_preferred_provider=_normalize_text(
            getattr(llm, "bootstrap_preferred_provider", "")
        )
        or None,
        bootstrap_preferred_provider_available=(
            bool(getattr(llm, "bootstrap_preferred_provider_available"))
            if getattr(llm, "bootstrap_preferred_provider_available", None) is not None
            else None
        ),
        bootstrap_alternatives=tuple(
            dict(item)
            for item in getattr(llm, "bootstrap_alternatives", ()) or ()
            if isinstance(item, dict)
        ),
    )


__all__ = [
    "BootstrapLLMSettings",
    "bootstrap_llm_settings_from_config",
]
