from __future__ import annotations

from mini_agent.config import Config
from mini_agent.config_bootstrap import load_entry_config, load_noninteractive_config


def test_load_entry_config_defaults_to_interactive_setup(monkeypatch) -> None:
    sentinel = object()
    captured: dict[str, object] = {}

    def _fake_load(cls, *, allow_interactive_setup: bool = True):
        captured["allow_interactive_setup"] = allow_interactive_setup
        return sentinel

    monkeypatch.setattr(Config, "load", classmethod(_fake_load))

    assert load_entry_config() is sentinel
    assert captured["allow_interactive_setup"] is True


def test_load_entry_config_accepts_positional_false(monkeypatch) -> None:
    sentinel = object()
    captured: dict[str, object] = {}

    def _fake_load(cls, *, allow_interactive_setup: bool = True):
        captured["allow_interactive_setup"] = allow_interactive_setup
        return sentinel

    monkeypatch.setattr(Config, "load", classmethod(_fake_load))

    assert load_entry_config(False) is sentinel
    assert captured["allow_interactive_setup"] is False


def test_load_noninteractive_config_disables_interactive_setup(monkeypatch) -> None:
    sentinel = object()
    captured: dict[str, object] = {}

    def _fake_load(cls, *, allow_interactive_setup: bool = True):
        captured["allow_interactive_setup"] = allow_interactive_setup
        return sentinel

    monkeypatch.setattr(Config, "load", classmethod(_fake_load))

    assert load_noninteractive_config() is sentinel
    assert captured["allow_interactive_setup"] is False
