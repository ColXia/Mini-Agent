"""DesktopUI shell and formatting helpers."""

from __future__ import annotations

import asyncio
from datetime import datetime
import html
import json
from typing import Any, Callable

from mini_agent.desktop.gateway_supervisor import DesktopGatewayConnection, DesktopGatewaySupervisor
from mini_agent.model_manager.session_selection_service import SessionModelSelectionService
from mini_agent.runtime.session_pending_approval_service import SessionPendingApprovalService
from mini_agent.session import SessionFeedbackService
from mini_agent.transport import GatewayClient, RemoteStreamErrorService, extract_gateway_error_info


def _compact_text(value: Any) -> str:
    return " ".join(str(value or "").split())


def _truncate_text(value: Any, *, limit: int = 88) -> str:
    text = str(value or "")
    if len(text) <= limit:
        return text
    if limit <= 1:
        return text[:limit]
    return f"{text[: limit - 1]}…"


def _source_badge(source: str | None) -> str:
    normalized = _compact_text(source).lower()
    if normalized == "custom":
        return "C"
    if normalized == "preset":
        return "P"
    if normalized == "builtin":
        return "B"
    return normalized[:1].upper() or "?"


def format_session_row(session: dict[str, Any]) -> str:
    """Render one compact session row for the left rail."""
    title = _compact_text(session.get("title")) or _compact_text(session.get("session_id")) or "Untitled"
    busy = "busy" if bool(session.get("busy")) else "idle"
    surface = _compact_text(session.get("active_surface") or session.get("origin_surface")) or "unknown"
    shared = "shared" if bool(session.get("shared")) else "local"
    model_id = _compact_text(session.get("selected_model_id")) or "-"
    return f"{title} | {surface} | {shared} | {busy} | model={model_id}"


def format_session_context_text(detail: dict[str, Any]) -> str:
    """Render concise session metadata and diagnostics for the right rail."""
    diagnostics = {
        "pending_approvals": detail.get("pending_approvals") or [],
        "memory_diagnostics": detail.get("memory_diagnostics") or {},
        "sandbox_diagnostics": detail.get("sandbox_diagnostics") or {},
    }
    lines = [
        f"Title: {_compact_text(detail.get('title')) or '-'}",
        f"Session ID: {_compact_text(detail.get('session_id')) or '-'}",
        f"Workspace: {_compact_text(detail.get('workspace_dir')) or '-'}",
        f"Surface: {_compact_text(detail.get('active_surface') or detail.get('origin_surface')) or '-'}",
        f"Shared: {bool(detail.get('shared'))}",
        f"Busy: {bool(detail.get('busy'))}",
        f"Running: {_compact_text(detail.get('running_state')) or '-'}",
        f"Model: {_compact_text(detail.get('selected_provider_id')) or '-'} / {_compact_text(detail.get('selected_model_id')) or '-'}",
        f"Updated: {_compact_text(detail.get('updated_at')) or '-'}",
        "",
        "Diagnostics:",
        json.dumps(diagnostics, ensure_ascii=False, indent=2),
    ]
    return "\n".join(lines)


def format_model_catalog_text(
    catalog: dict[str, Any] | None,
    current_detail: dict[str, Any] | None = None,
) -> str:
    """Render provider/model catalog for the right rail."""
    items = list((catalog or {}).get("items") or [])
    if not items:
        return "No model catalog available."

    selected_provider = _compact_text((current_detail or {}).get("selected_provider_id"))
    selected_model = _compact_text((current_detail or {}).get("selected_model_id"))
    lines: list[str] = []
    for provider in items:
        provider_name = _compact_text(provider.get("provider_name")) or _compact_text(provider.get("provider_id")) or "Provider"
        badge = _source_badge(provider.get("source"))
        default_model = _compact_text(provider.get("default_model_id")) or "-"
        lines.append(f"{provider_name} [{badge}] | default {default_model}")
        for model in list(provider.get("models") or []):
            model_id = _compact_text(model.get("model_id")) or "-"
            display_name = _compact_text(model.get("display_name"))
            suffix = ""
            if (
                _compact_text(provider.get("provider_id")) == selected_provider
                and model_id == selected_model
            ):
                suffix = " [session]"
            elif bool(model.get("is_default")):
                suffix = " [default]"
            if display_name and display_name != model_id:
                lines.append(f"  {model_id} ({display_name}){suffix}")
            else:
                lines.append(f"  {model_id}{suffix}")
        lines.append("")
    return "\n".join(lines).rstrip()


def collect_model_options(catalog: dict[str, Any] | None) -> list[dict[str, str]]:
    """Flatten provider/model catalog into combobox-friendly options."""
    options: list[dict[str, str]] = []
    for provider in list((catalog or {}).get("items") or []):
        provider_source = _compact_text(provider.get("source"))
        provider_id = _compact_text(provider.get("provider_id"))
        provider_name = _compact_text(provider.get("provider_name")) or provider_id or "Provider"
        for model in list(provider.get("models") or []):
            model_id = _compact_text(model.get("model_id"))
            if not provider_id or not model_id:
                continue
            display_name = _compact_text(model.get("display_name"))
            label = f"{provider_name} [{_source_badge(provider_source)}] | {model_id}"
            if display_name and display_name != model_id:
                label = f"{label} ({display_name})"
            options.append(
                {
                    "label": label,
                    "provider_source": provider_source,
                    "provider_id": provider_id,
                    "model_id": model_id,
                }
            )
    return options


def first_pending_approval(detail: dict[str, Any] | None) -> dict[str, Any] | None:
    """Return the first pending approval item from session detail."""
    items = list((detail or {}).get("pending_approvals") or [])
    if not items:
        return None
    item = items[0]
    return item if isinstance(item, dict) else None


def desktop_error_detail(exc: Exception) -> str:
    """Normalize desktop-visible gateway/remote exception detail."""
    return _compact_text(extract_gateway_error_info(exc).detail) or _compact_text(exc) or "request failed"


def format_desktop_approval_failure(exc: Exception) -> tuple[str, str]:
    """Normalize remote approval failures for desktop activity/status surfaces."""
    detail = desktop_error_detail(exc) or "Approval failed."
    summary = SessionPendingApprovalService.error_summary(detail=detail)
    title = f"Approval failed: {detail}" if summary == "approval failed" else f"Approval {summary}: {detail}"
    status = SessionPendingApprovalService.error_status_text(detail=detail)
    return title, status


def render_conversation_html(messages: list[dict[str, Any]]) -> str:
    """Render transcript entries as lightweight HTML blocks."""
    if not messages:
        return (
            "<html><body style='font-family: Consolas, \"Microsoft YaHei UI\"; color: #dbe4ff;'>"
            "<div style='opacity: 0.72;'>No transcript entries yet.</div>"
            "</body></html>"
        )

    role_styles = {
        "user": ("#cfe1ff", "#12233e", "#5ca8ff"),
        "assistant": ("#e8f4ff", "#10263b", "#78d2ff"),
        "system": ("#f7e8ff", "#2e143c", "#c88cff"),
        "tool": ("#e5fff1", "#0f2b20", "#5fd68c"),
    }
    parts = [
        "<html><body style='font-family: Consolas, \"Microsoft YaHei UI\"; background: transparent;'>"
    ]
    for message in messages:
        role = _compact_text(message.get("role")).lower() or "assistant"
        surface = _compact_text(message.get("surface")) or "-"
        content = html.escape(str(message.get("content") or "")).replace("\n", "<br>")
        fg, bg, border = role_styles.get(role, ("#ffffff", "#1b2230", "#6a7b98"))
        parts.append(
            "<div style='margin: 0 0 10px 0; padding: 10px 12px; "
            f"border-left: 4px solid {border}; background: {bg}; color: {fg}; border-radius: 8px;'>"
            f"<div style='font-size: 11px; opacity: 0.82; margin-bottom: 6px;'>{html.escape(role)} | {html.escape(surface)}</div>"
            f"<div style='font-size: 13px; line-height: 1.45;'>{content or '&nbsp;'}</div>"
            "</div>"
        )
    parts.append("</body></html>")
    return "".join(parts)


def render_activity_html(entries: list[dict[str, Any]]) -> str:
    """Render structured activity entries as compact operator cards."""
    if not entries:
        return (
            "<html><body style='font-family: Consolas, \"Microsoft YaHei UI\"; color: #dbe4ff;'>"
            "<div style='opacity: 0.72;'>No activity yet.</div>"
            "</body></html>"
        )

    palette = {
        "activity": ("#dbe9ff", "#13233d", "#77b0ff"),
        "approval": ("#fff4d9", "#382b11", "#ffcf70"),
        "delegation": ("#e4fff0", "#113021", "#6cd79a"),
        "error": ("#ffe3e3", "#3c1717", "#ff8585"),
        "gateway": ("#efe4ff", "#28183c", "#b894ff"),
        "health": ("#dffcf0", "#123125", "#67d9a2"),
        "model": ("#e8ecff", "#151e3a", "#98aeff"),
        "session": ("#dcf8ff", "#10303a", "#6bd4f1"),
        "status": ("#e8f4ff", "#14263b", "#86cfff"),
    }
    parts = [
        "<html><body style='font-family: Consolas, \"Microsoft YaHei UI\"; background: transparent;'>"
    ]
    for entry in entries:
        kind = _compact_text(entry.get("kind")).lower() or "activity"
        timestamp = _compact_text(entry.get("timestamp")) or "--:--:--"
        title = html.escape(_compact_text(entry.get("title")) or "activity")
        detail = str(entry.get("detail") or "")
        preview = _compact_text(entry.get("preview"))
        fg, bg, border = palette.get(kind, ("#ffffff", "#1b2230", "#6a7b98"))
        parts.append(
            "<div style='margin: 0 0 8px 0; padding: 10px 12px; "
            f"border-left: 4px solid {border}; background: {bg}; color: {fg}; border-radius: 8px;'>"
            f"<div style='font-size: 11px; opacity: 0.80; margin-bottom: 5px;'>{html.escape(timestamp)} | {html.escape(kind)}</div>"
            f"<div style='font-size: 13px; font-weight: 600; margin-bottom: 4px;'>{title}</div>"
        )
        if preview:
            parts.append(
                "<div style='font-size: 11px; opacity: 0.76; margin-bottom: 4px;'>"
                f"{html.escape(preview)}</div>"
            )
        if detail:
            parts.append(
                "<div style='font-size: 12px; line-height: 1.4; white-space: pre-wrap;'>"
                f"{html.escape(detail)}</div>"
            )
        parts.append("</div>")
    parts.append("</body></html>")
    return "".join(parts)


def create_desktop_main_window(
    *,
    qtwidgets: Any,
    qtcore: Any,
    gateway_client: GatewayClient,
    supervisor: DesktopGatewaySupervisor,
    connection: DesktopGatewayConnection,
    reconnect_handler: Callable[[], DesktopGatewayConnection],
) -> Any:
    """Build the DesktopUI main window without importing Qt at module import time."""

    class ChatStreamWorker(qtcore.QObject):
        chunk_received = qtcore.Signal(str)
        activity_received = qtcore.Signal(object)
        approval_requested = qtcore.Signal(object)
        approval_resolved = qtcore.Signal()
        done_received = qtcore.Signal(object)
        error_received = qtcore.Signal(str)
        finished = qtcore.Signal()

        def __init__(
            self,
            *,
            client: GatewayClient,
            session_id: str,
            message: str,
            workspace_dir: str,
            surface: str,
        ) -> None:
            super().__init__()
            self._client = client
            self._session_id = session_id
            self._message = message
            self._workspace_dir = workspace_dir
            self._surface = surface

        @qtcore.Slot()
        def run(self) -> None:
            try:
                asyncio.run(self._consume())
            except Exception as exc:
                self.error_received.emit(RemoteStreamErrorService.exception_detail(exc))
            finally:
                self.finished.emit()

        async def _consume(self) -> None:
            stream_chat = getattr(self._client, "stream_chat_events", None)
            if callable(stream_chat):
                async for event_type, payload in stream_chat(
                    session_id=self._session_id,
                    message=self._message,
                    workspace_dir=self._workspace_dir,
                    surface=self._surface,
                ):
                    event = _compact_text(event_type).lower() or "message"
                    data = payload if isinstance(payload, dict) else {}
                    if event == "delta":
                        chunk = str(data.get("chunk") or "")
                        if chunk:
                            self.chunk_received.emit(chunk)
                        continue
                    if event == "activity":
                        label = _compact_text(data.get("label")) or "activity"
                        detail = _compact_text(data.get("detail")) or "running"
                        preview = _compact_text(data.get("preview"))
                        self.activity_received.emit(
                            {
                                "kind": label,
                                "title": detail,
                                "preview": preview,
                            }
                        )
                        continue
                    if event == "status":
                        stage = _compact_text(data.get("stage")) or "running"
                        self.activity_received.emit({"kind": "status", "title": stage})
                        continue
                    if event == "approval_requested":
                        tool_name = _compact_text(data.get("tool_name")) or "tool"
                        self.activity_received.emit(
                            {
                                "kind": "approval",
                                "title": f"{tool_name} needs approval",
                                "detail": _compact_text(data.get("reason")),
                            }
                        )
                        self.approval_requested.emit(data)
                        continue
                    if event == "approval_resolved":
                        self.activity_received.emit({"kind": "approval", "title": "Approval resolved"})
                        self.approval_resolved.emit()
                        continue
                    if event.startswith("delegation."):
                        detail = event.split(".", 1)[-1] or "delegation"
                        owner = _compact_text(data.get("worker_id") or data.get("owner"))
                        self.activity_received.emit(
                            {
                                "kind": "delegation",
                                "title": detail,
                                "preview": owner,
                            }
                        )
                        continue
                    if event == "error":
                        detail = RemoteStreamErrorService.payload_detail(data)
                        self.activity_received.emit(
                            {
                                "kind": "error",
                                "title": detail,
                            }
                        )
                        raise RuntimeError(detail)
                    if event == "done":
                        self.done_received.emit(data)
                        return
            response = await self._client.run_chat(
                session_id=self._session_id,
                message=self._message,
                workspace_dir=self._workspace_dir,
                surface=self._surface,
            )
            self.done_received.emit(response)

    class DesktopMainWindow(qtwidgets.QMainWindow):
        REFRESH_INTERVAL_MS = 5000

        def __init__(self) -> None:
            super().__init__()
            self._client = gateway_client
            self._supervisor = supervisor
            self._connection = connection
            self._reconnect_handler = reconnect_handler
            self._session_ids_by_row: list[str] = []
            self._model_catalog: dict[str, Any] = {}
            self._selected_session_detail: dict[str, Any] = {}
            self._conversation_messages: list[dict[str, Any]] = []
            self._activity_entries: list[dict[str, Any]] = []
            self._send_thread: Any = None
            self._send_worker: Any = None
            self._send_busy = False
            self._stream_target_session_id: str | None = None
            self._model_options: list[dict[str, str]] = []
            self._approval_dialog_token: str | None = None

            self.setWindowTitle("Mini-Agent DesktopUI")
            self.resize(1520, 920)

            central = qtwidgets.QWidget()
            root_layout = qtwidgets.QVBoxLayout(central)
            root_layout.setContentsMargins(12, 12, 12, 12)
            root_layout.setSpacing(10)

            info_card = qtwidgets.QGroupBox("Runtime")
            info_layout = qtwidgets.QGridLayout(info_card)
            self._status_value = qtwidgets.QLabel("Connecting")
            self._gateway_value = qtwidgets.QLabel(self._connection.base_url)
            self._workspace_value = qtwidgets.QLabel(str(self._connection.workspace))
            self._sessions_value = qtwidgets.QLabel("0")
            self._mode_value = qtwidgets.QLabel(self._mode_text())
            self._note_value = qtwidgets.QLabel(self._connection.note or "-")
            self._note_value.setWordWrap(False)
            self._set_runtime_note(self._connection.note or "-")
            info_layout.setContentsMargins(8, 8, 8, 8)
            info_layout.setHorizontalSpacing(12)
            info_layout.setVerticalSpacing(4)
            info_layout.addWidget(qtwidgets.QLabel("Status"), 0, 0)
            info_layout.addWidget(self._status_value, 0, 1)
            info_layout.addWidget(qtwidgets.QLabel("Gateway"), 1, 0)
            info_layout.addWidget(self._gateway_value, 1, 1)
            info_layout.addWidget(qtwidgets.QLabel("Workspace"), 2, 0)
            info_layout.addWidget(self._workspace_value, 2, 1)
            info_layout.addWidget(qtwidgets.QLabel("Sessions"), 0, 2)
            info_layout.addWidget(self._sessions_value, 0, 3)
            info_layout.addWidget(qtwidgets.QLabel("Mode"), 1, 2)
            info_layout.addWidget(self._mode_value, 1, 3)
            self._note_value.hide()
            info_card.setMaximumHeight(78)
            root_layout.addWidget(info_card)

            toolbar_row = qtwidgets.QHBoxLayout()
            self._new_session_button = qtwidgets.QPushButton("New Session")
            self._new_session_button.clicked.connect(self._create_session)
            self._refresh_button = qtwidgets.QPushButton("Refresh")
            self._refresh_button.clicked.connect(self.refresh_snapshot)
            self._reconnect_button = qtwidgets.QPushButton("Reconnect")
            self._reconnect_button.clicked.connect(self._reconnect_gateway)
            self._approvals_button = qtwidgets.QPushButton("Approvals")
            self._approvals_button.clicked.connect(self._open_pending_approval_dialog)
            self._command_button = qtwidgets.QPushButton("Commands")
            self._command_button.clicked.connect(self._open_command_palette)
            toolbar_row.addWidget(self._new_session_button)
            toolbar_row.addWidget(self._refresh_button)
            toolbar_row.addWidget(self._reconnect_button)
            toolbar_row.addWidget(self._approvals_button)
            toolbar_row.addWidget(self._command_button)
            toolbar_row.addStretch(1)
            root_layout.addLayout(toolbar_row)

            body_splitter = qtwidgets.QSplitter(qtcore.Qt.Horizontal)

            session_group = qtwidgets.QGroupBox("Sessions")
            session_layout = qtwidgets.QVBoxLayout(session_group)
            self._session_list = qtwidgets.QListWidget()
            self._session_list.currentRowChanged.connect(self._on_session_selected)
            session_layout.addWidget(self._session_list)
            session_actions = qtwidgets.QGridLayout()
            self._rename_session_button = qtwidgets.QPushButton("Rename")
            self._rename_session_button.clicked.connect(self._rename_current_session)
            self._share_session_button = qtwidgets.QPushButton("Share")
            self._share_session_button.clicked.connect(self._toggle_share_current_session)
            self._fork_session_button = qtwidgets.QPushButton("Fork")
            self._fork_session_button.clicked.connect(self._fork_current_session)
            self._compact_session_button = qtwidgets.QPushButton("Compact")
            self._compact_session_button.clicked.connect(self._compact_current_session)
            session_actions.addWidget(self._rename_session_button, 0, 0)
            session_actions.addWidget(self._share_session_button, 0, 1)
            session_actions.addWidget(self._fork_session_button, 1, 0)
            session_actions.addWidget(self._compact_session_button, 1, 1)
            session_layout.addLayout(session_actions)
            body_splitter.addWidget(session_group)

            conversation_group = qtwidgets.QGroupBox("Conversation")
            conversation_layout = qtwidgets.QVBoxLayout(conversation_group)
            self._conversation_view = qtwidgets.QTextBrowser()
            self._conversation_view.setOpenExternalLinks(False)
            conversation_layout.addWidget(self._conversation_view, 1)

            composer_label = qtwidgets.QLabel("Prompt")
            conversation_layout.addWidget(composer_label)
            self._composer = qtwidgets.QPlainTextEdit()
            self._composer.setPlaceholderText("Type a prompt for the selected session. Ctrl+Enter to send.")
            self._composer.setFixedHeight(120)
            self._composer.installEventFilter(self)
            conversation_layout.addWidget(self._composer)

            composer_actions = qtwidgets.QHBoxLayout()
            self._send_button = qtwidgets.QPushButton("Send")
            self._send_button.clicked.connect(self._send_current_prompt)
            self._send_button.setDefault(True)
            self._clear_button = qtwidgets.QPushButton("Clear Input")
            self._clear_button.clicked.connect(self._composer.clear)
            composer_actions.addStretch(1)
            composer_actions.addWidget(self._clear_button)
            composer_actions.addWidget(self._send_button)
            conversation_layout.addLayout(composer_actions)
            body_splitter.addWidget(conversation_group)

            right_splitter = qtwidgets.QSplitter(qtcore.Qt.Vertical)

            models_group = qtwidgets.QGroupBox("Models")
            models_layout = qtwidgets.QVBoxLayout(models_group)
            model_controls = qtwidgets.QHBoxLayout()
            self._model_combo = qtwidgets.QComboBox()
            self._model_combo.setMinimumWidth(280)
            self._apply_model_button = qtwidgets.QPushButton("Apply Model")
            self._apply_model_button.clicked.connect(self._apply_selected_model)
            model_controls.addWidget(self._model_combo, 1)
            model_controls.addWidget(self._apply_model_button)
            models_layout.addLayout(model_controls)
            self._models_view = qtwidgets.QPlainTextEdit()
            self._models_view.setReadOnly(True)
            models_layout.addWidget(self._models_view)
            right_splitter.addWidget(models_group)

            context_group = qtwidgets.QGroupBox("Session Context")
            context_layout = qtwidgets.QVBoxLayout(context_group)
            self._context_view = qtwidgets.QPlainTextEdit()
            self._context_view.setReadOnly(True)
            context_layout.addWidget(self._context_view)
            right_splitter.addWidget(context_group)

            activity_group = qtwidgets.QGroupBox("Activity")
            activity_layout = qtwidgets.QVBoxLayout(activity_group)
            self._activity_view = qtwidgets.QTextBrowser()
            self._activity_view.setOpenExternalLinks(False)
            activity_layout.addWidget(self._activity_view)
            right_splitter.addWidget(activity_group)

            right_splitter.setStretchFactor(0, 2)
            right_splitter.setStretchFactor(1, 1)
            right_splitter.setStretchFactor(2, 5)
            body_splitter.addWidget(right_splitter)

            body_splitter.setStretchFactor(0, 2)
            body_splitter.setStretchFactor(1, 9)
            body_splitter.setStretchFactor(2, 2)
            root_layout.addWidget(body_splitter, 1)

            self.setCentralWidget(central)
            self.statusBar().showMessage("DesktopUI attached.")

            self._render_conversation()
            self._render_activity()
            self._models_view.setPlainText("Loading model catalog...")
            self._context_view.setPlainText("No session selected.")
            self._append_activity(self._connection.note or "DesktopUI bootstrapped.", kind="status")
            self._append_managed_gateway_excerpt("Managed gateway log tail")
            self.refresh_snapshot()

            self._timer = qtcore.QTimer(self)
            self._timer.setInterval(self.REFRESH_INTERVAL_MS)
            self._timer.timeout.connect(self.refresh_snapshot)
            self._timer.start()
            self._refresh_session_action_state()

        def eventFilter(self, obj: Any, event: Any) -> bool:
            if (
                obj is self._composer
                and event.type() == qtcore.QEvent.Type.KeyPress
                and event.key() in {qtcore.Qt.Key.Key_Return, qtcore.Qt.Key.Key_Enter}
                and bool(event.modifiers() & qtcore.Qt.KeyboardModifier.ControlModifier)
            ):
                self._send_current_prompt()
                return True
            return super().eventFilter(obj, event)

        def keyPressEvent(self, event: Any) -> None:  # noqa: N802 - Qt naming
            if (
                event.key() == qtcore.Qt.Key.Key_K
                and bool(event.modifiers() & qtcore.Qt.KeyboardModifier.ControlModifier)
            ):
                self._open_command_palette()
                return
            super().keyPressEvent(event)

        def refresh_snapshot(self, checked: bool = False) -> None:
            _ = checked
            self._refresh_health()
            self._refresh_models()
            if not self._send_busy:
                self._refresh_sessions()

        def _refresh_health(self) -> None:
            try:
                payload = self._client.get_system_health_sync()
                runtime = payload.get("runtime") if isinstance(payload, dict) else {}
                active_sessions = int((runtime or {}).get("active_sessions", 0))
                max_sessions = int((runtime or {}).get("max_active_sessions", 0))
                status = str(payload.get("status") or "unknown") if isinstance(payload, dict) else "unknown"
                self._status_value.setText(f"{status} | runtime {active_sessions}/{max_sessions}")
                self.statusBar().showMessage(f"Gateway healthy: {self._connection.base_url}")
            except Exception as exc:
                detail = desktop_error_detail(exc)
                self._status_value.setText(f"unreachable | {detail}")
                self.statusBar().showMessage("Gateway unreachable.")
                self._append_activity(f"Health check failed: {detail}", kind="error")
                self._append_managed_gateway_excerpt("Gateway health diagnostics")

        def _refresh_models(self) -> None:
            try:
                self._model_catalog = self._client.list_agent_models_sync()
                self._model_options = collect_model_options(self._model_catalog)
                self._rebuild_model_combo()
                self._models_view.setPlainText(
                    format_model_catalog_text(self._model_catalog, self._selected_session_detail)
                )
            except Exception as exc:
                detail = desktop_error_detail(exc)
                self._models_view.setPlainText(f"Failed to load model catalog.\n{detail}")
                self._append_activity(f"Model catalog refresh failed: {detail}", kind="error")

        def _rebuild_model_combo(self) -> None:
            self._model_combo.blockSignals(True)
            self._model_combo.clear()
            for option in self._model_options:
                self._model_combo.addItem(option["label"], option)
            self._sync_model_combo_selection()
            self._model_combo.blockSignals(False)
            self._refresh_session_action_state()

        def _sync_model_combo_selection(self) -> None:
            selected_provider = _compact_text(self._selected_session_detail.get("selected_provider_id"))
            selected_model = _compact_text(self._selected_session_detail.get("selected_model_id"))
            target_index = 0
            for index, option in enumerate(self._model_options):
                if (
                    option.get("provider_id") == selected_provider
                    and option.get("model_id") == selected_model
                ):
                    target_index = index
                    break
            if self._model_options:
                self._model_combo.setCurrentIndex(target_index)

        def _refresh_sessions(self, preferred_session_id: str | None = None) -> None:
            selected_session_id = preferred_session_id or self._current_session_id()
            try:
                sessions = self._client.list_sessions_sync(workspace_dir=str(self._connection.workspace))
            except Exception as exc:
                self._append_activity(f"Session refresh failed: {desktop_error_detail(exc)}", kind="error")
                return

            if not sessions:
                try:
                    detail = self._client.ensure_default_session_sync(
                        workspace_dir=str(self._connection.workspace),
                        surface="desktop",
                    )
                except Exception as exc:
                    self._append_activity(f"Default session ensure failed: {desktop_error_detail(exc)}", kind="error")
                    detail = {}
                sessions = [detail] if isinstance(detail, dict) and detail.get("session_id") else []

            self._sessions_value.setText(str(len(sessions)))
            self._session_ids_by_row = []
            self._session_list.blockSignals(True)
            self._session_list.clear()
            for session in sessions:
                session_id = str(session.get("session_id") or "").strip()
                if not session_id:
                    continue
                self._session_ids_by_row.append(session_id)
                self._session_list.addItem(format_session_row(session))

            if not self._session_ids_by_row:
                self._session_list.blockSignals(False)
                self._selected_session_detail = {}
                self._conversation_messages = []
                self._render_conversation()
                self._context_view.setPlainText("No sessions were found for the current workspace.")
                self._update_approval_button_state()
                self._refresh_session_action_state()
                return

            target_row = 0
            if selected_session_id:
                try:
                    target_row = self._session_ids_by_row.index(selected_session_id)
                except ValueError:
                    target_row = next(
                        (
                            index
                            for index, session in enumerate(sessions)
                            if bool(session.get("is_default"))
                        ),
                        0,
                    )
            self._session_list.setCurrentRow(target_row)
            self._session_list.blockSignals(False)
            self._load_selected_session_detail()

        def _current_session_id(self) -> str | None:
            row = int(self._session_list.currentRow())
            if row < 0 or row >= len(self._session_ids_by_row):
                return None
            return self._session_ids_by_row[row]

        def _on_session_selected(self, row: int) -> None:
            if row < 0 or row >= len(self._session_ids_by_row):
                return
            self._load_selected_session_detail()

        def _load_selected_session_detail(self, *, recent_limit: int = 80) -> None:
            session_id = self._current_session_id()
            if not session_id:
                self._selected_session_detail = {}
                self._conversation_messages = []
                self._render_conversation()
                self._context_view.setPlainText("No session selected.")
                self._update_approval_button_state()
                self._refresh_session_action_state()
                return
            try:
                detail = self._client.get_session_detail_sync(session_id, recent_limit=recent_limit)
            except Exception as exc:
                resolved = desktop_error_detail(exc)
                self._context_view.setPlainText(f"Failed to load session detail.\n{resolved}")
                self._append_activity(f"Session detail load failed for {session_id}: {resolved}", kind="error")
                return
            self._selected_session_detail = detail
            self._conversation_messages = [
                {
                    "role": str(item.get("role") or "assistant"),
                    "content": str(item.get("content") or ""),
                    "surface": str(item.get("surface") or "-"),
                }
                for item in list(detail.get("recent_messages") or [])
            ]
            self._render_conversation()
            self._context_view.setPlainText(format_session_context_text(detail))
            self._models_view.setPlainText(format_model_catalog_text(self._model_catalog, detail))
            self._sync_model_combo_selection()
            self._update_approval_button_state()
            self._refresh_session_action_state()
            self._maybe_prompt_for_pending_approval()

        def _render_conversation(self) -> None:
            self._conversation_view.setHtml(render_conversation_html(self._conversation_messages))
            scrollbar = self._conversation_view.verticalScrollBar()
            scrollbar.setValue(scrollbar.maximum())

        def _render_activity(self) -> None:
            self._activity_view.setHtml(render_activity_html(self._activity_entries))
            scrollbar = self._activity_view.verticalScrollBar()
            scrollbar.setValue(scrollbar.maximum())

        def _set_runtime_note(self, note: str) -> None:
            text = str(note or "").strip() or "-"
            self._note_value.setText(_truncate_text(text))
            self._note_value.setToolTip(text)
            self._status_value.setToolTip(text)
            self._gateway_value.setToolTip(text)

        def _selected_session_title(self) -> str:
            return _compact_text(self._selected_session_detail.get("title")) or (
                self._current_session_id() or "Session"
            )

        def _refresh_session_action_state(self) -> None:
            has_session = bool(self._current_session_id())
            shared = bool(self._selected_session_detail.get("shared"))
            self._rename_session_button.setDisabled(self._send_busy or not has_session)
            self._share_session_button.setDisabled(self._send_busy or not has_session)
            self._fork_session_button.setDisabled(self._send_busy or not has_session)
            self._compact_session_button.setDisabled(self._send_busy or not has_session)
            self._apply_model_button.setDisabled(self._send_busy or not has_session or not bool(self._model_options))
            self._share_session_button.setText("Unshare" if shared else "Share")

        def _force_select_session(self, session_id: str) -> None:
            target = _compact_text(session_id)
            if not target:
                return
            try:
                row = self._session_ids_by_row.index(target)
            except ValueError:
                return
            self._session_list.blockSignals(True)
            self._session_list.setCurrentRow(row)
            self._session_list.blockSignals(False)
            item = self._session_list.item(row)
            if item is not None:
                self._session_list.scrollToItem(item)
            self._load_selected_session_detail()

        def _rename_current_session(self, checked: bool = False) -> None:
            _ = checked
            session_id = self._current_session_id()
            if not session_id:
                self.statusBar().showMessage("Select a session first.")
                return
            current_title = self._selected_session_title()
            title, accepted = qtwidgets.QInputDialog.getText(
                self,
                "Rename Session",
                "Session title:",
                text=current_title,
            )
            renamed_title = _compact_text(title)
            if not accepted or not renamed_title:
                return
            try:
                response = self._client.rename_session_sync(session_id, title=renamed_title)
            except Exception as exc:
                self._append_activity(f"Rename failed: {desktop_error_detail(exc)}", kind="error")
                self.statusBar().showMessage("Rename failed.")
                return

            applied_title = _compact_text(response.get("title")) or renamed_title
            feedback = SessionFeedbackService.mutation_feedback(
                status=str(response.get("status") or "renamed"),
                title=applied_title,
                shared=response.get("shared") if isinstance(response.get("shared"), bool) else None,
            )
            self._append_activity(feedback.status_text, kind="session")
            self.statusBar().showMessage(feedback.status_text)
            self._refresh_sessions(preferred_session_id=session_id)

        def _toggle_share_current_session(self, checked: bool = False) -> None:
            _ = checked
            session_id = self._current_session_id()
            if not session_id:
                self.statusBar().showMessage("Select a session first.")
                return
            next_shared = not bool(self._selected_session_detail.get("shared"))
            try:
                response = self._client.set_session_shared_sync(session_id, shared=next_shared)
            except Exception as exc:
                self._append_activity(f"Share toggle failed: {desktop_error_detail(exc)}", kind="error")
                self.statusBar().showMessage("Share toggle failed.")
                return

            shared = bool(response.get("shared"))
            title = _compact_text(response.get("title")) or self._selected_session_title()
            feedback = SessionFeedbackService.mutation_feedback(
                status=str(response.get("status") or ("shared" if shared else "unshared")),
                title=title,
                shared=shared,
            )
            self._append_activity(feedback.status_text, kind="session")
            self.statusBar().showMessage(feedback.status_text)
            self._refresh_sessions(preferred_session_id=session_id)

        def _fork_current_session(self, checked: bool = False) -> None:
            _ = checked
            session_id = self._current_session_id()
            if not session_id:
                self.statusBar().showMessage("Select a session first.")
                return
            suggested = f"{self._selected_session_title()} copy"
            title, accepted = qtwidgets.QInputDialog.getText(
                self,
                "Fork Session",
                "Derived session title:",
                text=suggested,
            )
            if not accepted:
                return
            try:
                response = self._client.create_derived_session_sync(
                    session_id,
                    title=_compact_text(title) or None,
                    surface="desktop",
                )
            except Exception as exc:
                self._append_activity(f"Fork failed: {desktop_error_detail(exc)}", kind="error")
                self.statusBar().showMessage("Fork failed.")
                return

            created_id = _compact_text(response.get("session_id"))
            created_title = _compact_text(response.get("title")) or created_id or "derived session"
            feedback = SessionFeedbackService.fork_feedback(
                title=created_title,
                parent_title=self._selected_session_title(),
            )
            self._append_activity(feedback.status_text, kind="session")
            self.statusBar().showMessage(feedback.status_text)
            self._refresh_sessions(preferred_session_id=created_id or session_id)

        def _compact_current_session(self, checked: bool = False) -> None:
            _ = checked
            session_id = self._current_session_id()
            if not session_id:
                self.statusBar().showMessage("Select a session first.")
                return
            try:
                response = self._client.control_session_sync(
                    session_id,
                    action="compact",
                    reason="desktop compact request",
                    surface="desktop",
                )
            except Exception as exc:
                self._append_activity(f"Compact failed: {desktop_error_detail(exc)}", kind="error")
                self.statusBar().showMessage("Compact failed.")
                return

            applied = bool(response.get("applied"))
            before = int(response.get("message_count_before") or 0)
            after = int(response.get("message_count_after") or 0)
            title = self._selected_session_title()
            if applied:
                self._append_activity(
                    f"{title} compacted",
                    kind="session",
                    detail=f"Messages: {before} -> {after}",
                )
                self.statusBar().showMessage(f"Compacted {title}.")
            else:
                self._append_activity(
                    f"{title} already compact",
                    kind="session",
                    detail=f"Messages: {before} -> {after}",
                )
                self.statusBar().showMessage(f"{title} was already compact.")
            self._refresh_sessions(preferred_session_id=session_id)

        def _create_session(self, checked: bool = False) -> str | None:
            _ = checked
            current_session_id = self._current_session_id()
            try:
                if current_session_id:
                    created = self._client.create_derived_session_sync(
                        current_session_id,
                        title="Session",
                        surface="desktop",
                    )
                else:
                    created = self._client.create_session_sync(
                        workspace_dir=str(self._connection.workspace),
                        surface="desktop",
                        shared=False,
                    )
            except Exception as exc:
                self._append_activity(f"Create session failed: {desktop_error_detail(exc)}", kind="error")
                self.statusBar().showMessage("Create session failed.")
                return None

            session_id = _compact_text(created.get("session_id"))
            created_title = _compact_text(created.get("title")) or session_id or "unknown"
            create_feedback = SessionFeedbackService.creation_feedback(
                title=created_title,
                derived=bool(current_session_id),
            )
            self._append_activity(create_feedback.status_text, kind="session")
            if session_id:
                self._refresh_health()
                self._refresh_models()
                self._refresh_sessions(preferred_session_id=session_id)
                self._force_select_session(session_id)
                self.statusBar().showMessage(f"Switched to {created_title}")
            return session_id or None

        def _apply_selected_model(self, checked: bool = False) -> None:
            _ = checked
            if self._send_busy:
                self.statusBar().showMessage("Cannot switch model while a desktop turn is running.")
                return
            session_id = self._current_session_id()
            if not session_id:
                self.statusBar().showMessage("Select or create a session first.")
                return
            current = self._model_combo.currentData()
            option = current if isinstance(current, dict) else None
            if not option:
                self.statusBar().showMessage("No model option selected.")
                return
            try:
                response = self._client.update_session_model_sync(
                    session_id,
                    provider_source=option.get("provider_source"),
                    provider_id=str(option.get("provider_id") or ""),
                    model_id=str(option.get("model_id") or ""),
                    surface="desktop",
                )
            except Exception as exc:
                self._append_activity(f"Model switch failed: {desktop_error_detail(exc)}", kind="error")
                self.statusBar().showMessage("Model switch failed.")
                return

            status = _compact_text(response.get("status")) or "selected"
            selected_provider = _compact_text(
                response.get("selected_provider_id") or option.get("provider_id")
            )
            selected_model = _compact_text(
                response.get("selected_model_id") or option.get("model_id")
            )
            queued = bool(response.get("queued"))
            if queued:
                pending_model = _compact_text(response.get("pending_model_id")) or selected_model
                feedback = SessionModelSelectionService.queued_feedback(
                    model_label=f"{selected_provider}/{pending_model}",
                    session_title=self._selected_session_title(),
                )
                self._append_activity(
                    feedback.compact_text,
                    kind="model",
                )
                self.statusBar().showMessage(feedback.compact_text)
            else:
                feedback = SessionModelSelectionService.applied_feedback(
                    model_label=f"{selected_provider}/{selected_model}",
                    session_title=self._selected_session_title(),
                )
                self._append_activity(
                    feedback.compact_text,
                    kind="model",
                )
                self.statusBar().showMessage(feedback.compact_text)
            self._load_selected_session_detail()
            self._refresh_models()
            self._append_activity(f"Model response status: {status}", kind="model")

        def _update_approval_button_state(self) -> None:
            pending = first_pending_approval(self._selected_session_detail)
            self._approvals_button.setDisabled(pending is None)

        def _maybe_prompt_for_pending_approval(self) -> None:
            pending = first_pending_approval(self._selected_session_detail)
            token = _compact_text((pending or {}).get("token"))
            if not token:
                self._approval_dialog_token = None
                return
            if self._approval_dialog_token == token:
                return
            self._approval_dialog_token = token
            self._open_pending_approval_dialog()

        def _open_pending_approval_dialog(self, checked: bool = False) -> None:
            _ = checked
            pending = first_pending_approval(self._selected_session_detail)
            session_id = self._current_session_id()
            if not pending or not session_id:
                self.statusBar().showMessage("No pending approvals for the selected session.")
                return

            token = _compact_text(pending.get("token"))
            tool_name = _compact_text(pending.get("tool_name")) or "tool"
            kind = _compact_text(pending.get("kind")) or "-"
            reason = _compact_text(pending.get("reason")) or "-"
            arguments = pending.get("arguments") if isinstance(pending.get("arguments"), dict) else {}
            message = (
                f"Session: {_compact_text(self._selected_session_detail.get('title')) or session_id}\n"
                f"Tool: {tool_name}\n"
                f"Token: {token or '-'}\n"
                f"Kind: {kind}\n"
                f"Reason: {reason}\n\n"
                f"Arguments:\n{json.dumps(arguments, ensure_ascii=False, indent=2)}"
            )
            dialog = qtwidgets.QMessageBox(self)
            dialog.setWindowTitle("Approval Required")
            dialog.setIcon(qtwidgets.QMessageBox.Icon.Warning)
            dialog.setText("The selected session is waiting for approval.")
            dialog.setInformativeText(message)
            approve_button = dialog.addButton("Approve", qtwidgets.QMessageBox.ButtonRole.AcceptRole)
            deny_button = dialog.addButton("Deny", qtwidgets.QMessageBox.ButtonRole.RejectRole)
            dialog.addButton("Later", qtwidgets.QMessageBox.ButtonRole.ActionRole)
            dialog.exec()
            clicked = dialog.clickedButton()
            if clicked is approve_button:
                self._resolve_pending_approval(True)
            elif clicked is deny_button:
                self._resolve_pending_approval(False)

        def _resolve_pending_approval(self, approved: bool) -> None:
            session_id = self._current_session_id()
            pending = first_pending_approval(self._selected_session_detail)
            token = _compact_text((pending or {}).get("token"))
            if not session_id or not token:
                return
            try:
                response = self._client.respond_to_approval_sync(
                    session_id,
                    approved=approved,
                    token=token,
                    surface="desktop",
                )
            except Exception as exc:
                activity_title, status_text = format_desktop_approval_failure(exc)
                self._append_activity(activity_title, kind="error")
                self.statusBar().showMessage(status_text)
                return

            decision = _compact_text(response.get("decision")) or ("approved" if approved else "denied")
            tool_name = _compact_text(response.get("tool_name")) or _compact_text((pending or {}).get("tool_name")) or "tool"
            self._approval_dialog_token = None
            self._append_activity(f"Approval {decision}: {tool_name}", kind="approval")
            self.statusBar().showMessage(f"Approval {decision}: {tool_name}")
            self._load_selected_session_detail()

        def _open_command_palette(self, checked: bool = False) -> None:
            _ = checked
            commands = [
                "New Session",
                "Rename Session",
                "Share / Unshare Session",
                "Fork Session",
                "Compact Session",
                "Refresh",
                "Reconnect",
                "Open Approvals",
                "Focus Prompt",
                "Apply Selected Model",
            ]
            choice, accepted = qtwidgets.QInputDialog.getItem(
                self,
                "Command Palette",
                "Choose a desktop action:",
                commands,
                0,
                False,
            )
            if not accepted:
                return
            command = _compact_text(choice).lower()
            if command == "new session":
                self._create_session()
            elif command == "rename session":
                self._rename_current_session()
            elif command == "share / unshare session":
                self._toggle_share_current_session()
            elif command == "fork session":
                self._fork_current_session()
            elif command == "compact session":
                self._compact_current_session()
            elif command == "refresh":
                self.refresh_snapshot()
            elif command == "reconnect":
                self._reconnect_gateway()
            elif command == "open approvals":
                self._open_pending_approval_dialog()
            elif command == "focus prompt":
                self._composer.setFocus()
            elif command == "apply selected model":
                self._apply_selected_model()

        def _send_current_prompt(self, checked: bool = False) -> None:
            _ = checked
            if self._send_busy:
                self.statusBar().showMessage("A desktop turn is already running.")
                return
            message = self._composer.toPlainText().strip()
            if not message:
                return
            session_id = self._current_session_id() or self._create_session()
            if not session_id:
                return

            self._composer.clear()
            self._conversation_messages.append(
                {
                    "role": "user",
                    "content": message,
                    "surface": "desktop",
                }
            )
            self._render_conversation()
            self._append_activity(f"Prompt submitted to {session_id}.", kind="session")
            self._set_send_busy(True)

            self._stream_target_session_id = session_id
            self._send_thread = qtcore.QThread(self)
            self._send_worker = ChatStreamWorker(
                client=self._client,
                session_id=session_id,
                message=message,
                workspace_dir=str(self._connection.workspace),
                surface="desktop",
            )
            self._send_worker.moveToThread(self._send_thread)
            self._send_thread.started.connect(self._send_worker.run)
            self._send_worker.chunk_received.connect(self._on_stream_chunk)
            self._send_worker.activity_received.connect(self._on_stream_activity)
            self._send_worker.approval_requested.connect(self._on_stream_approval_requested)
            self._send_worker.approval_resolved.connect(self._on_stream_approval_resolved)
            self._send_worker.done_received.connect(self._on_stream_done)
            self._send_worker.error_received.connect(self._on_stream_error)
            self._send_worker.finished.connect(self._on_stream_finished)
            self._send_worker.finished.connect(self._send_thread.quit)
            self._send_worker.finished.connect(self._send_worker.deleteLater)
            self._send_thread.finished.connect(self._send_thread.deleteLater)
            self._send_thread.start()

        def _set_send_busy(self, busy: bool) -> None:
            self._send_busy = busy
            self._send_button.setDisabled(busy)
            self._new_session_button.setDisabled(busy)
            self._session_list.setDisabled(busy)
            self._composer.setReadOnly(busy)
            self._apply_model_button.setDisabled(busy or not bool(self._model_options))
            self._refresh_session_action_state()
            if busy:
                self.statusBar().showMessage("Running desktop turn...")

        def _on_stream_chunk(self, chunk: str) -> None:
            if (
                self._conversation_messages
                and self._conversation_messages[-1].get("role") == "assistant"
                and self._conversation_messages[-1].get("surface") == "desktop"
                and bool(self._conversation_messages[-1].get("streaming"))
            ):
                self._conversation_messages[-1]["content"] = (
                    str(self._conversation_messages[-1].get("content") or "") + chunk
                )
            else:
                self._conversation_messages.append(
                    {
                        "role": "assistant",
                        "content": chunk,
                        "surface": "desktop",
                        "streaming": True,
                    }
                )
            self._render_conversation()

        def _on_stream_activity(self, payload: object) -> None:
            entry = payload if isinstance(payload, dict) else {"title": _compact_text(payload)}
            self._append_activity(
                str(entry.get("title") or "activity"),
                kind=str(entry.get("kind") or "activity"),
                detail=str(entry.get("detail") or ""),
                preview=str(entry.get("preview") or ""),
            )

        def _on_stream_approval_requested(self, payload: object) -> None:
            pending = payload if isinstance(payload, dict) else {}
            token = _compact_text(pending.get("token"))
            if token:
                self._approval_dialog_token = None
            self._load_selected_session_detail()

        def _on_stream_approval_resolved(self) -> None:
            self._approval_dialog_token = None
            self._load_selected_session_detail()

        def _on_stream_done(self, payload: object) -> None:
            response = payload if isinstance(payload, dict) else {}
            reply = str(response.get("reply") or "")
            if (
                reply
                and not (
                    self._conversation_messages
                    and self._conversation_messages[-1].get("role") == "assistant"
                    and str(self._conversation_messages[-1].get("content") or "").strip()
                )
            ):
                self._conversation_messages.append(
                    {
                        "role": "assistant",
                        "content": reply,
                        "surface": "desktop",
                    }
                )
            if self._conversation_messages and self._conversation_messages[-1].get("role") == "assistant":
                self._conversation_messages[-1].pop("streaming", None)
            self._render_conversation()
            token_usage = response.get("token_usage")
            if token_usage is not None:
                self._append_activity(
                    "Turn completed",
                    kind="status",
                    detail=f"token_usage={token_usage}",
                )
            else:
                self._append_activity("Turn completed", kind="status")
            self._load_selected_session_detail()
            self._refresh_models()

        def _on_stream_error(self, message: str) -> None:
            error_text = message or "Desktop turn failed."
            self._conversation_messages.append(
                {
                    "role": "system",
                    "content": f"Desktop turn failed: {error_text}",
                    "surface": "desktop",
                }
            )
            self._render_conversation()
            self._append_activity(f"Turn failed: {error_text}", kind="error")
            self._append_managed_gateway_excerpt("Turn failure diagnostics")

        def _on_stream_finished(self) -> None:
            self._set_send_busy(False)
            self._stream_target_session_id = None
            self._send_worker = None
            self._send_thread = None
            self.refresh_snapshot()
            self.statusBar().showMessage("Desktop turn finished.")

        def _reconnect_gateway(self, checked: bool = False) -> None:
            _ = checked
            if self._send_busy:
                self.statusBar().showMessage("Cannot reconnect while a turn is running.")
                return
            try:
                self._connection = self._reconnect_handler()
                self._client.base_url = self._connection.base_url
                self._gateway_value.setText(self._connection.base_url)
                self._workspace_value.setText(str(self._connection.workspace))
                self._mode_value.setText(self._mode_text())
                self._set_runtime_note(self._connection.note or "-")
                self._append_activity(
                    self._connection.note or "Reconnected to local gateway.",
                    kind="status",
                )
                self._append_managed_gateway_excerpt("Reconnect diagnostics")
                self.refresh_snapshot()
            except Exception as exc:
                self._append_activity(f"Reconnect failed: {desktop_error_detail(exc)}", kind="error")
                self.statusBar().showMessage("Reconnect failed.")

        def _mode_text(self) -> str:
            mode = "managed" if self._connection.managed else "external"
            if self._connection.started_here:
                mode = f"{mode} | started-by-desktop"
            if self._connection.qqbot_running:
                mode = f"{mode} | qqbot-on"
            return mode

        def _append_activity(
            self,
            message: str,
            *,
            kind: str = "activity",
            detail: str | None = None,
            preview: str | None = None,
        ) -> None:
            normalized_message = str(message or "").strip() or "activity"
            normalized_detail = str(detail or "")
            if not normalized_detail and "\n" in normalized_message:
                first_line, remainder = normalized_message.split("\n", 1)
                normalized_message = first_line.strip() or "activity"
                normalized_detail = remainder.strip()
            self._activity_entries.append(
                {
                    "timestamp": datetime.now().strftime("%H:%M:%S"),
                    "kind": _compact_text(kind).lower() or "activity",
                    "title": normalized_message,
                    "detail": normalized_detail,
                    "preview": _compact_text(preview),
                }
            )
            if len(self._activity_entries) > 120:
                self._activity_entries = self._activity_entries[-120:]
            self._render_activity()

        def _append_managed_gateway_excerpt(self, label: str) -> None:
            if not self._connection.managed:
                return
            excerpt = self._supervisor.managed_log_tail(lines=6).strip()
            if not excerpt:
                return
            self._append_activity(label, kind="gateway", detail=excerpt)

    return DesktopMainWindow()
