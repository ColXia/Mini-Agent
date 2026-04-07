"""Provider configuration models with normalization and validation."""

from __future__ import annotations

from enum import Enum
from typing import Any
import re
from urllib.parse import urlsplit

from pydantic import BaseModel, Field, field_validator, model_validator


_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_RESERVED_HEADER_KEYS = {"authorization", "content-length", "host"}
_PLACEHOLDER_KEYS = {"YOUR_API_KEY_HERE", "sk-cp-xxxxx", "your_api_key", "your-api-key"}


class ProviderAPIType(str, Enum):
    """Supported provider API protocol types."""

    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GEMINI = "gemini"
    CUSTOM = "custom"


def _normalize_text(value: str) -> str:
    return " ".join(value.strip().split())


def _slugify(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip().lower()).strip("-")
    if not slug:
        return "provider"
    if not re.match(r"^[A-Za-z0-9]", slug):
        return f"p-{slug}"
    return slug


def _normalize_api_base(value: str) -> str:
    raw = value.strip().rstrip("/")
    if not raw:
        raise ValueError("api_base must not be empty.")

    parsed = urlsplit(raw)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("api_base must start with http:// or https://.")
    if not parsed.netloc:
        raise ValueError("api_base must include host.")
    if parsed.query or parsed.fragment:
        raise ValueError("api_base must not include query or fragment.")
    return raw


def _normalize_headers(value: dict[str, Any]) -> dict[str, str]:
    normalized: dict[str, str] = {}
    for raw_key, raw_val in value.items():
        key = _normalize_text(str(raw_key))
        if not key:
            continue
        lower = key.lower()
        if lower in _RESERVED_HEADER_KEYS:
            continue
        val = _normalize_text(str(raw_val))
        if not val:
            continue
        normalized[key] = val
    return normalized


def _normalize_models(value: list[Any]) -> list[str]:
    models: list[str] = []
    seen: set[str] = set()
    for raw in value:
        candidate = _normalize_text(str(raw))
        if not candidate:
            continue
        lowered = candidate.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        models.append(candidate)
    if not models:
        raise ValueError("models must include at least one model id.")
    return models


class ProviderConfig(BaseModel):
    """Custom provider configuration."""

    id: str | None = None
    name: str
    api_type: ProviderAPIType = ProviderAPIType.OPENAI
    api_base: str
    api_key: str
    models: list[str] = Field(default_factory=list)
    enabled: bool = True
    priority: int = 0
    headers: dict[str, str] = Field(default_factory=dict)
    timeout: int = 60

    @model_validator(mode="before")
    @classmethod
    def _default_id(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        payload = dict(data)
        current_id = payload.get("id")
        if current_id is None or not str(current_id).strip():
            fallback = str(payload.get("name") or payload.get("api_base") or "provider")
            payload["id"] = _slugify(fallback)
        return payload

    @field_validator("id")
    @classmethod
    def _validate_id(cls, value: str | None) -> str:
        candidate = _normalize_text(str(value or ""))
        if not _ID_PATTERN.fullmatch(candidate):
            raise ValueError("id must match [A-Za-z0-9][A-Za-z0-9._-]{0,127}.")
        return candidate

    @field_validator("name")
    @classmethod
    def _validate_name(cls, value: str) -> str:
        candidate = _normalize_text(value)
        if not candidate:
            raise ValueError("name must not be empty.")
        return candidate

    @field_validator("api_base")
    @classmethod
    def _validate_api_base(cls, value: str) -> str:
        return _normalize_api_base(value)

    @field_validator("api_key")
    @classmethod
    def _validate_api_key(cls, value: str) -> str:
        candidate = value.strip()
        if not candidate:
            raise ValueError("api_key must not be empty.")
        if candidate in _PLACEHOLDER_KEYS:
            raise ValueError("api_key must not be a placeholder.")
        return candidate

    @field_validator("models", mode="before")
    @classmethod
    def _validate_models(cls, value: Any) -> list[str]:
        if isinstance(value, str):
            value = [value]
        if not isinstance(value, list):
            raise ValueError("models must be a list of model ids.")
        return _normalize_models(value)

    @field_validator("priority")
    @classmethod
    def _validate_priority(cls, value: int) -> int:
        return int(value)

    @field_validator("timeout")
    @classmethod
    def _validate_timeout(cls, value: int) -> int:
        timeout = int(value)
        if timeout < 5 or timeout > 600:
            raise ValueError("timeout must be between 5 and 600 seconds.")
        return timeout

    @field_validator("headers", mode="before")
    @classmethod
    def _validate_headers(cls, value: Any) -> dict[str, str]:
        if value is None:
            return {}
        if not isinstance(value, dict):
            raise ValueError("headers must be an object.")
        return _normalize_headers(value)

    @property
    def default_model(self) -> str:
        return self.models[0]

    def supports_model(self, model: str) -> bool:
        normalized = _normalize_text(model).lower()
        if not normalized:
            return False
        return normalized in {item.lower() for item in self.models}

    def redacted(self) -> dict[str, Any]:
        payload = self.model_dump()
        key = payload.get("api_key", "")
        if isinstance(key, str):
            if len(key) <= 8:
                masked = "*" * len(key)
            else:
                masked = f"{key[:4]}***{key[-4:]}"
            payload["api_key"] = masked
        return payload


class ProviderCatalog(BaseModel):
    """Collection of provider configs with uniqueness and ordering normalization."""

    providers: list[ProviderConfig] = Field(default_factory=list)

    @field_validator("providers")
    @classmethod
    def _validate_unique_ids(cls, value: list[ProviderConfig]) -> list[ProviderConfig]:
        seen: set[str] = set()
        for provider in value:
            if provider.id in seen:
                raise ValueError(f"duplicate provider id: {provider.id}")
            seen.add(provider.id)
        return value

    def normalized(self) -> "ProviderCatalog":
        ordered = sorted(
            self.providers,
            key=lambda provider: (
                not provider.enabled,  # enabled first
                -provider.priority,
                provider.name.lower(),
                provider.id,
            ),
        )
        return ProviderCatalog(providers=ordered)

    def enabled(self) -> list[ProviderConfig]:
        return [provider for provider in self.providers if provider.enabled]

    def find(self, provider_id: str) -> ProviderConfig | None:
        lookup = _normalize_text(provider_id)
        for provider in self.providers:
            if provider.id == lookup:
                return provider
        return None

    def redacted(self) -> dict[str, Any]:
        return {"providers": [provider.redacted() for provider in self.providers]}


def normalize_provider_config(payload: dict[str, Any]) -> ProviderConfig:
    """Normalize and validate one provider payload."""
    return ProviderConfig.model_validate(payload)


def normalize_provider_catalog(payload: dict[str, Any] | list[dict[str, Any]]) -> ProviderCatalog:
    """Normalize and validate a provider catalog payload."""
    if isinstance(payload, list):
        catalog = ProviderCatalog.model_validate({"providers": payload})
    elif isinstance(payload, dict):
        if "providers" in payload:
            catalog = ProviderCatalog.model_validate(payload)
        else:
            catalog = ProviderCatalog.model_validate({"providers": [payload]})
    else:
        raise ValueError("payload must be an object or a list.")
    return catalog.normalized()
