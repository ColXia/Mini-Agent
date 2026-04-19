"""Tests for DesktopUI app bootstrap helpers."""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest

import mini_agent.desktop.app as app


def test_load_qt_modules_reports_install_hint(monkeypatch) -> None:
    real_import = importlib.import_module

    def _fake_import(name: str, package: str | None = None):
        if name.startswith("PySide6"):
            raise ModuleNotFoundError("No module named 'PySide6'", name="PySide6")
        return real_import(name, package)

    monkeypatch.setattr(app.importlib, "import_module", _fake_import)

    with pytest.raises(RuntimeError, match="PySide6 is not installed"):
        app._load_qt_modules()


def test_launch_desktop_ui_uses_desktop_timeout_for_gateway_client(monkeypatch, tmp_path: Path) -> None:
    captured: dict[str, object] = {}

    class _FakeQApplication:
        _instance = None

        def __init__(self, _argv):
            type(self)._instance = self

        @classmethod
        def instance(cls):
            return cls._instance

        def setApplicationName(self, _name: str) -> None:
            return None

        def setOrganizationName(self, _name: str) -> None:
            return None

        def exec(self) -> int:
            return 0

    class _FakeWindow:
        def show(self) -> None:
            return None

    class _FakeQtWidgets:
        QApplication = _FakeQApplication

    class _FakeQtCore:
        pass

    class _FakeSupervisor:
        def __init__(self, *, source_root, repo_root):
            captured["source_root"] = source_root
            captured["repo_root"] = repo_root

        def ensure_gateway_running(self, **kwargs):
            captured["ensure_kwargs"] = kwargs
            return type(
                "_Conn",
                (),
                {
                    "base_url": "http://127.0.0.1:8008",
                    "workspace": kwargs["workspace"],
                    "note": "desktop",
                    "managed": False,
                    "started_here": False,
                    "qqbot_running": False,
                },
            )()

    class _FakeClient:
        def __init__(self, *, base_url: str, timeout_seconds: float):
            captured["client_base_url"] = base_url
            captured["client_timeout_seconds"] = timeout_seconds

    monkeypatch.setattr(app, "_load_qt_modules", lambda: (_FakeQtWidgets, _FakeQtCore))
    monkeypatch.setattr(app, "DesktopGatewaySupervisor", _FakeSupervisor)
    monkeypatch.setattr(app, "GatewayClient", _FakeClient)
    monkeypatch.setattr(app, "create_desktop_main_window", lambda **_: _FakeWindow())

    exit_code = app.launch_desktop_ui(
        host="127.0.0.1",
        port=8008,
        workspace=tmp_path / "workspace",
        approval_profile="build",
        access_level="default",
        startup_timeout=20.0,
        attach_only=False,
        source_root=tmp_path,
        repo_root=tmp_path,
    )

    assert exit_code == 0
    assert captured["client_base_url"] == "http://127.0.0.1:8008"
    assert captured["client_timeout_seconds"] == app.DESKTOP_GATEWAY_TIMEOUT_SECONDS
