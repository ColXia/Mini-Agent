"""Configuration model for novel subprogram agent profile."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


def _clean_text(raw: str | None, fallback: str) -> str:
    value = (raw or "").strip()
    return value or fallback


def _clean_positive_float(raw: str | None, fallback: float) -> float:
    value = (raw or "").strip()
    if not value:
        return fallback
    try:
        parsed = float(value)
    except ValueError:
        return fallback
    if parsed < 0:
        return fallback
    return parsed


def _clean_bool(raw: str | None, fallback: bool) -> bool:
    value = (raw or "").strip().lower()
    if not value:
        return fallback
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    return fallback


@dataclass(frozen=True, slots=True)
class NovelAgentProfile:
    """Runtime profile defaults for novel generation subprogram."""

    profile_id: str
    api_host: str
    default_style_type: str
    default_style_weight: float
    default_cover_aspect_ratio: str
    default_illustration_aspect_ratio: str
    memory_namespace: str
    tool_profile_id: str
    enable_text_tools: bool
    enable_image_tools: bool
    enable_audio_tools: bool

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "NovelAgentProfile":
        source = dict(env or {})
        return cls(
            profile_id=_clean_text(source.get("MINI_AGENT_NOVEL_PROFILE_ID"), "novel-default"),
            api_host=_clean_text(source.get("MINI_AGENT_NOVEL_API_HOST"), "https://api.minimaxi.com").rstrip("/"),
            default_style_type=_clean_text(source.get("MINI_AGENT_NOVEL_STYLE_TYPE"), "漫画"),
            default_style_weight=_clean_positive_float(source.get("MINI_AGENT_NOVEL_STYLE_WEIGHT"), 1.0),
            default_cover_aspect_ratio=_clean_text(source.get("MINI_AGENT_NOVEL_COVER_ASPECT_RATIO"), "1:1"),
            default_illustration_aspect_ratio=_clean_text(
                source.get("MINI_AGENT_NOVEL_ILLUSTRATION_ASPECT_RATIO"),
                "16:9",
            ),
            memory_namespace=_clean_text(source.get("MINI_AGENT_NOVEL_MEMORY_NAMESPACE"), "novel-main"),
            tool_profile_id=_clean_text(source.get("MINI_AGENT_NOVEL_TOOL_PROFILE_ID"), "novel-default-tools"),
            enable_text_tools=_clean_bool(source.get("MINI_AGENT_NOVEL_ENABLE_TEXT_TOOLS"), True),
            enable_image_tools=_clean_bool(source.get("MINI_AGENT_NOVEL_ENABLE_IMAGE_TOOLS"), True),
            enable_audio_tools=_clean_bool(source.get("MINI_AGENT_NOVEL_ENABLE_AUDIO_TOOLS"), True),
        )

    def resolve_api_host(self, api_host: str | None) -> str:
        value = (api_host or "").strip()
        if value:
            return value.rstrip("/")
        return self.api_host

    def resolve_style_type(self, style_type: str | None) -> str:
        value = (style_type or "").strip()
        if value:
            return value
        return self.default_style_type

    def resolve_style_weight(self, style_weight: float | None) -> float:
        if style_weight is None:
            return self.default_style_weight
        if style_weight < 0:
            return self.default_style_weight
        return style_weight

    def resolve_cover_aspect_ratio(self, aspect_ratio: str | None) -> str:
        value = (aspect_ratio or "").strip()
        if value:
            return value
        return self.default_cover_aspect_ratio

    def resolve_illustration_aspect_ratio(self, aspect_ratio: str | None) -> str:
        value = (aspect_ratio or "").strip()
        if value:
            return value
        return self.default_illustration_aspect_ratio

    def to_public_payload(self) -> dict[str, Any]:
        return {
            "profile_id": self.profile_id,
            "api_host": self.api_host,
            "default_style_type": self.default_style_type,
            "default_style_weight": self.default_style_weight,
            "default_cover_aspect_ratio": self.default_cover_aspect_ratio,
            "default_illustration_aspect_ratio": self.default_illustration_aspect_ratio,
            "memory_namespace": self.memory_namespace,
            "tool_profile_id": self.tool_profile_id,
            "enable_text_tools": self.enable_text_tools,
            "enable_image_tools": self.enable_image_tools,
            "enable_audio_tools": self.enable_audio_tools,
        }

    def assert_operation_allowed(self, operation: str) -> None:
        op = (operation or "").strip().lower()
        text_ops = {"setup", "write", "finalize"}
        image_ops = {"cover", "illustrate"}
        audio_ops = {"tts", "clone_voice"}

        if op in text_ops and not self.enable_text_tools:
            raise PermissionError(
                f"Novel profile '{self.profile_id}' blocks text operation '{op}' "
                f"(tool profile: {self.tool_profile_id})."
            )
        if op in image_ops and not self.enable_image_tools:
            raise PermissionError(
                f"Novel profile '{self.profile_id}' blocks image operation '{op}' "
                f"(tool profile: {self.tool_profile_id})."
            )
        if op in audio_ops and not self.enable_audio_tools:
            raise PermissionError(
                f"Novel profile '{self.profile_id}' blocks audio operation '{op}' "
                f"(tool profile: {self.tool_profile_id})."
            )
