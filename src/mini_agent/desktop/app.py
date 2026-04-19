"""DesktopUI application bootstrap."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from typing import Any

from mini_agent.desktop.gateway_supervisor import DesktopGatewaySupervisor
from mini_agent.desktop.gateway_transport_binding import DesktopGatewayTransportBinding
from mini_agent.desktop.window import create_desktop_main_window
from mini_agent.transport.gateway_client import GatewayClient

DESKTOP_GATEWAY_TIMEOUT_SECONDS = 15.0


def _load_qt_modules() -> tuple[Any, Any]:
    """Lazy-load PySide6 so the core package stays optional."""
    try:
        qtwidgets = importlib.import_module("PySide6.QtWidgets")
        qtcore = importlib.import_module("PySide6.QtCore")
    except ModuleNotFoundError as exc:
        if str(exc.name or "").startswith("PySide6"):
            raise RuntimeError(
                "PySide6 is not installed. Run `uv sync --extra desktop` "
                "or install `PySide6` before using `mini-agent desktop`."
            ) from exc
        raise
    return qtwidgets, qtcore


def launch_desktop_ui(
    *,
    host: str,
    port: int,
    workspace: Path,
    approval_profile: str | None,
    access_level: str | None,
    startup_timeout: float,
    attach_only: bool,
    source_root: Path,
    repo_root: Path,
) -> int:
    """Launch the minimal DesktopUI shell."""
    qtwidgets, qtcore = _load_qt_modules()

    supervisor = DesktopGatewaySupervisor(source_root=source_root, repo_root=repo_root)
    requested_workspace = workspace.resolve()

    def _ensure_connection() -> Any:
        return supervisor.ensure_gateway_running(
            host=host,
            port=port,
            workspace=requested_workspace,
            approval_profile=approval_profile,
            access_level=access_level,
            startup_timeout=startup_timeout,
            attach_only=attach_only,
        )

    connection = _ensure_connection()
    gateway_client = GatewayClient(
        base_url=connection.base_url,
        timeout_seconds=DESKTOP_GATEWAY_TIMEOUT_SECONDS,
    )
    transport_binding = DesktopGatewayTransportBinding.from_gateway_client(gateway_client)

    app = qtwidgets.QApplication.instance()
    if app is None:
        app = qtwidgets.QApplication(sys.argv)
    app.setApplicationName("Mini-Agent DesktopUI")
    app.setOrganizationName("Mini-Agent")

    window = create_desktop_main_window(
        qtwidgets=qtwidgets,
        qtcore=qtcore,
        transport_binding=transport_binding,
        supervisor=supervisor,
        connection=connection,
        reconnect_handler=_ensure_connection,
    )
    window.show()
    return int(app.exec())
