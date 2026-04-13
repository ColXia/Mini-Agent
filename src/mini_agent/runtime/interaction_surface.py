"""Shared interaction-surface normalization for entrance/channel boundaries."""

from __future__ import annotations

from dataclasses import dataclass


USER_ENTRANCES: tuple[str, ...] = ("cli", "tui", "desktop", "webui", "remote")
REMOTE_CHANNEL_ADAPTERS: tuple[str, ...] = ("qq", "wechat", "feishu")

_SURFACE_ALIASES: dict[str, str] = {
    "qqbot": "qq",
    "qq-bot": "qq",
    "desktopui": "desktop",
    "desktop-ui": "desktop",
    "pyside6": "desktop",
    "qt": "desktop",
    "weixin": "wechat",
    "wx": "wechat",
    "feishu-bot": "feishu",
    "lark": "feishu",
}

_CHANNEL_ALIASES: dict[str, str] = {
    "qqbot": "qq",
    "qq-bot": "qq",
    "weixin": "wechat",
    "wx": "wechat",
    "lark": "feishu",
}

_WEB_ENTRANCE_ALIASES = {
    "web",
    "browser",
    "open_webui",
    "open-webui",
    "openwebui",
}

_CLI_ENTRANCE_ALIASES = {
    "headless",
    "terminal",
    "console",
    "local",
}

_REMOTE_ENTRANCE_ALIASES = {
    "api",
    "gateway",
    "http",
    "channel",
}


def _clean(value: str | None) -> str:
    return " ".join(str(value or "").strip().lower().split())


def normalize_surface_label(surface: str | None) -> str:
    """Normalize surface labels while preserving existing session semantics."""

    raw = _clean(surface)
    if not raw:
        return "api"
    return _SURFACE_ALIASES.get(raw, raw)


def normalize_channel_type(channel_type: str | None) -> str | None:
    """Normalize channel adapter labels."""

    raw = _clean(channel_type)
    if not raw:
        return None
    return _CHANNEL_ALIASES.get(raw, raw)


def resolve_remote_channel(surface: str | None, channel_type: str | None) -> str | None:
    """Resolve concrete remote channel adapter identity."""

    normalized_surface = normalize_surface_label(surface)
    normalized_channel = normalize_channel_type(channel_type)
    if normalized_channel in REMOTE_CHANNEL_ADAPTERS:
        return normalized_channel
    if normalized_surface in REMOTE_CHANNEL_ADAPTERS:
        return normalized_surface
    return None


def resolve_user_entrance(surface: str | None, channel_type: str | None) -> str:
    """Resolve one of the four user entrances for current interaction context."""

    normalized_surface = normalize_surface_label(surface)
    if normalized_surface in USER_ENTRANCES and normalized_surface != "remote":
        return normalized_surface
    remote_channel = resolve_remote_channel(normalized_surface, channel_type)
    if remote_channel is not None:
        return "remote"
    if normalized_surface in USER_ENTRANCES:
        return normalized_surface
    if normalized_surface in _WEB_ENTRANCE_ALIASES:
        return "webui"
    if normalized_surface in _CLI_ENTRANCE_ALIASES:
        return "cli"
    if normalized_surface in _REMOTE_ENTRANCE_ALIASES:
        return "remote"
    return "cli"


@dataclass(frozen=True)
class InteractionSurface:
    """Resolved interaction context with explicit entrance/channel dimensions."""

    surface: str
    channel_type: str | None
    entrance: str
    remote_channel: str | None


@dataclass(frozen=True)
class InteractionBinding:
    """Normalized interaction binding for shared request/session surfaces."""

    surface: str | None
    channel_type: str | None
    conversation_id: str | None
    sender_id: str | None
    entrance: str | None
    remote_channel: str | None


def resolve_interaction_surface(surface: str | None, channel_type: str | None) -> InteractionSurface:
    """Resolve normalized surface + channel with explicit entrance classification."""

    normalized_surface = normalize_surface_label(surface)
    normalized_channel = normalize_channel_type(channel_type)
    if not _clean(surface) and normalized_channel in REMOTE_CHANNEL_ADAPTERS:
        normalized_surface = normalized_channel
    remote_channel = resolve_remote_channel(normalized_surface, normalized_channel)
    entrance = resolve_user_entrance(normalized_surface, normalized_channel)
    return InteractionSurface(
        surface=normalized_surface,
        channel_type=normalized_channel,
        entrance=entrance,
        remote_channel=remote_channel,
    )


def resolve_interaction_binding(
    *,
    surface: str | None,
    channel_type: str | None,
    conversation_id: str | None = None,
    sender_id: str | None = None,
    default_surface: str | None = None,
) -> InteractionBinding:
    """Resolve one normalized binding without forcing empty surface values into fake sources.

    Resolution order for the surface label is:
    1. explicit surface
    2. concrete channel type, when present
    3. caller-provided default surface
    """

    normalized_channel = normalize_channel_type(channel_type)
    candidate_surface = _clean(surface) or _clean(channel_type) or _clean(default_surface)
    if candidate_surface:
        interaction = resolve_interaction_surface(candidate_surface, normalized_channel)
        resolved_surface = interaction.surface
        entrance = interaction.entrance
        remote_channel = interaction.remote_channel
    else:
        resolved_surface = None
        entrance = None
        remote_channel = normalized_channel if normalized_channel in REMOTE_CHANNEL_ADAPTERS else None
    return InteractionBinding(
        surface=resolved_surface,
        channel_type=normalized_channel,
        conversation_id=_clean(conversation_id) or None,
        sender_id=_clean(sender_id) or None,
        entrance=entrance,
        remote_channel=remote_channel,
    )


__all__ = [
    "InteractionBinding",
    "InteractionSurface",
    "REMOTE_CHANNEL_ADAPTERS",
    "USER_ENTRANCES",
    "normalize_channel_type",
    "normalize_surface_label",
    "resolve_interaction_binding",
    "resolve_interaction_surface",
    "resolve_remote_channel",
    "resolve_user_entrance",
]
