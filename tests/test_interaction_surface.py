"""Tests for four-entrance interaction surface classification."""

from __future__ import annotations

from mini_agent.interaction import (
    resolve_interaction_binding,
    normalize_channel_type,
    normalize_surface_label,
    resolve_interaction_surface,
    resolve_remote_channel,
    resolve_user_entrance,
)


def test_normalize_surface_label_preserves_current_surface_semantics() -> None:
    assert normalize_surface_label("QQBOT") == "qq"
    assert normalize_surface_label("qq") == "qq"
    assert normalize_surface_label("TUI") == "tui"
    assert normalize_surface_label(None) == "api"


def test_normalize_channel_type_handles_remote_aliases() -> None:
    assert normalize_channel_type("QQBOT") == "qq"
    assert normalize_channel_type("custom-remote") == "custom-remote"
    assert normalize_channel_type("") is None


def test_resolve_user_entrance_for_remote_channels() -> None:
    assert resolve_user_entrance("qq", None) == "remote"
    assert resolve_user_entrance("api", "qq") == "remote"
    assert resolve_user_entrance(None, "custom-remote") == "remote"
    assert resolve_user_entrance("remote", "qq") == "remote"


def test_resolve_user_entrance_for_local_and_removed_browser_variants() -> None:
    assert resolve_user_entrance("headless", None) == "cli"
    assert resolve_user_entrance("tui", None) == "tui"
    assert resolve_user_entrance("desktopui", None) == "desktop"
    assert resolve_user_entrance("desktop", None) == "desktop"
    assert resolve_user_entrance("browser", None) == "cli"
    assert resolve_user_entrance("webui", None) == "cli"


def test_resolve_remote_channel_prefers_explicit_channel_type() -> None:
    assert resolve_remote_channel("remote", "qq") == "qq"
    assert resolve_remote_channel("custom-remote", None) is None
    assert resolve_remote_channel("remote", "custom-remote") is None
    assert resolve_remote_channel("tui", None) is None


def test_resolve_interaction_surface_exposes_entrance_and_remote_channel() -> None:
    remote = resolve_interaction_surface(surface="qqbot", channel_type="qq")
    assert remote.surface == "qq"
    assert remote.channel_type == "qq"
    assert remote.entrance == "remote"
    assert remote.remote_channel == "qq"

    remote_from_channel = resolve_interaction_surface(surface=None, channel_type="qqbot")
    assert remote_from_channel.surface == "qq"
    assert remote_from_channel.channel_type == "qq"
    assert remote_from_channel.entrance == "remote"
    assert remote_from_channel.remote_channel == "qq"

    local = resolve_interaction_surface(surface="tui", channel_type="qq")
    assert local.surface == "tui"
    assert local.channel_type == "qq"
    assert local.entrance == "tui"
    assert local.remote_channel == "qq"

    desktop = resolve_interaction_surface(surface="desktopui", channel_type=None)
    assert desktop.surface == "desktop"
    assert desktop.channel_type is None
    assert desktop.entrance == "desktop"
    assert desktop.remote_channel is None


def test_resolve_interaction_binding_normalizes_aliases_without_forcing_empty_surface() -> None:
    remote = resolve_interaction_binding(
        surface=None,
        channel_type=" qqbot ",
        conversation_id=" group:demo ",
        sender_id=" user-1 ",
    )
    assert remote.surface == "qq"
    assert remote.channel_type == "qq"
    assert remote.conversation_id == "group:demo"
    assert remote.sender_id == "user-1"
    assert remote.entrance == "remote"
    assert remote.remote_channel == "qq"

    local = resolve_interaction_binding(
        surface=None,
        channel_type=None,
    )
    assert local.surface is None
    assert local.channel_type is None
    assert local.entrance is None
