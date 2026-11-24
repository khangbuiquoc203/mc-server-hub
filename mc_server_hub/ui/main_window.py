"""Main window. It displays state and sends commands; it does not own processes."""

from __future__ import annotations

import os
import time

from PySide6.QtCore import QEvent, QEventLoop, Qt, QTimer, QObject, Signal
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSplitter,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)

from mc_server_hub import __version__
from mc_server_hub.core.supervisor_client import SupervisorClient
from mc_server_hub.models.app_settings import AppSettings
from mc_server_hub.models.server_config import ServerConfig
from mc_server_hub.ui.console import ConsolePanel
from mc_server_hub.ui.dashboard import Dashboard
from mc_server_hub.ui.server_dialog import ServerDialog
from mc_server_hub.ui.server_list import ServerList
from mc_server_hub.ui.settings_dialog import SettingsDialog
from mc_server_hub.ui.theme import app_icon, stylesheet
from mc_server_hub.utils.path_utils import get_app_root


class GuiClient(QObject):
    logs_received = Signal(object)
    runtime_received = Signal(object)
    snapshot_received = Signal(object)
    ack_received = Signal(object)
    connection_changed = Signal(bool, str)

    def __init__(self) -> None:
        super().__init__()
        self.client = SupervisorClient()
        self.client.on_logs = self.logs_received.emit
        self.client.on_runtime = self.runtime_received.emit
        self.client.on_snapshot = self.snapshot_received.emit
        self.client.on_ack = self.ack_received.emit
        self.client.on_connection = self.connection_changed.emit

    def start(self, app_root) -> None:
        self.client.start(app_root)

    def send(self, message: dict) -> None:
        self.client.send(message)

    def stop(self) -> None:
        self.client.stop()


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.app_root = get_app_root()
        self.settings = AppSettings()
        self.configs: dict[str, dict] = {}
        self.runtimes: dict[str, dict] = {}
        self.connected = False
        self._force_quit = False
        self._warnings_shown = False
        self._command_history: list[str] = []
        self._history_index = 0

        self.setWindowTitle(f"MC Server Hub {__version__}")
        self.resize(1280, 800)
        self.setMinimumSize(980, 640)
        self.setWindowIcon(app_icon())

        self.client = GuiClient()
        self.client.logs_received.connect(self._on_logs)
        self.client.runtime_received.connect(self._on_runtime)
        self.client.snapshot_received.connect(self._on_snapshot)
        self.client.ack_received.connect(self._on_ack)
        self.client.connection_changed.connect(self._on_connection)

        self.dashboard = Dashboard()
        self.server_list = ServerList()
        self.server_list.selected.connect(self._on_selected)
        self.console = ConsolePanel()
        self._build_shell()
        self._build_menu()
        self._build_tray()
        self._apply_theme()
        self.statusBar().showMessage("Connecting to the local supervisor...")

        self._clock = QTimer(self)
        self._clock.setInterval(500)
        self._clock.timeout.connect(self.server_list.refresh_clocks)
        self._clock.start()
        self.client.start(self.app_root)

    def _build_shell(self) -> None:
        header = QFrame()
        header.setObjectName("Header")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(16, 10, 16, 10)
        title_box = QVBoxLayout()
        title = QLabel("MC Server Hub")
        title.setObjectName("Title")
        subtitle = QLabel("Local Minecraft servers, one console, crash restart on process exit")
        subtitle.setObjectName("Subtitle")
        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        header_layout.addLayout(title_box)
        header_layout.addStretch(1)
        self.add_button = self._button("Add server", self._add_server, primary=True)
        self.edit_button = self._button("Edit", self._edit_server)
        self.remove_button = self._button("Remove", self._remove_server, danger=True)
        self.start_button = self._button("Start", self._start_selected, primary=True)
        self.stop_button = self._button("Stop", self._stop_selected, danger=True)
        self.restart_button = self._button("Restart", self._restart_selected)
        self.start_all_button = self._button("Start all", self._start_all)
        self.stop_all_button = self._button("Stop all", self._stop_all, danger=True)
        self.settings_button = self._button("Settings", self._open_settings)
        for button in (
            self.add_button,
            self.edit_button,
            self.remove_button,
            self.start_button,
            self.stop_button,
            self.restart_button,
            self.start_all_button,
            self.stop_all_button,
            self.settings_button,
        ):
            header_layout.addWidget(button)

        sidebar = QFrame()
        sidebar.setObjectName("Sidebar")
        sidebar.setMinimumWidth(300)
        sidebar.setMaximumWidth(460)
        side_layout = QVBoxLayout(sidebar)
        side_layout.setContentsMargins(0, 0, 0, 0)
        heading = QLabel("  Servers")
        heading.setObjectName("Muted")
        heading.setContentsMargins(8, 8, 8, 4)
        side_layout.addWidget(heading)
        side_layout.addWidget(self.server_list, 1)

        splitter = QSplitter()
        splitter.addWidget(sidebar)
        splitter.addWidget(self.console)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([340, 900])

        command_row = QHBoxLayout()
        command_row.setContentsMargins(12, 8, 12, 8)
        command_row.setSpacing(10)
        command_label = QLabel("Command")
        command_label.setMinimumWidth(72)
        command_row.addWidget(command_label)
        self.command_target = QLabel("No server selected")
        self.command_target.setObjectName("Muted")
        self.command_target.setMinimumWidth(160)
        self.command_input = QLineEdit()
        self.command_input.setPlaceholderText("say Server restarting    list    stop")
        self.command_input.returnPressed.connect(self._send_command)
        self.command_input.installEventFilter(self)
        send = QPushButton("Send")
        send.setObjectName("Primary")
        send.clicked.connect(self._send_command)
        self.logs_button = QPushButton("Open logs")
        self.logs_button.clicked.connect(self._open_logs)
        command_row.addWidget(self.command_target)
        command_row.addWidget(self.command_input, 1)
        command_row.addWidget(send)
        command_row.addWidget(self.logs_button)

        central = QWidget()
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(header)
        layout.addWidget(self.dashboard)
        layout.addWidget(splitter, 1)
        layout.addLayout(command_row)
        self.setCentralWidget(central)
        self._refresh_actions()

    def _build_menu(self) -> None:
        file_menu = self.menuBar().addMenu("File")
        file_menu.addAction("Settings", self._open_settings)
        file_menu.addSeparator()
        file_menu.addAction("Exit", self._request_quit)
        server_menu = self.menuBar().addMenu("Server")
        server_menu.addAction("Add", self._add_server)
        server_menu.addAction("Edit", self._edit_server)
        server_menu.addAction("Remove", self._remove_server)
        server_menu.addSeparator()
        server_menu.addAction("Start", self._start_selected)
        server_menu.addAction("Stop", self._stop_selected)
        server_menu.addAction("Restart", self._restart_selected)
        server_menu.addSeparator()
        server_menu.addAction("Start all", self._start_all)
        server_menu.addAction("Stop all", self._stop_all)
        view_menu = self.menuBar().addMenu("View")
        view_menu.addAction("Clear console view", self.console.clear_view)
        view_menu.addAction("Export console", self.console.export_view)
        view_menu.addAction("Open logs folder", self._open_logs)

    def _build_tray(self) -> None:
        self.tray = QSystemTrayIcon(app_icon(), self)
        self.tray.setToolTip("MC Server Hub")
        menu = self.tray.contextMenu() or self._new_tray_menu()
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._tray_activated)

    def _new_tray_menu(self):
        from PySide6.QtWidgets import QMenu
        menu = QMenu(self)
        menu.addAction("Show", self._show_from_tray)
        menu.addAction("Quit", self._request_quit)
        return menu

    def _button(self, text: str, handler, *, primary: bool = False, danger: bool = False) -> QPushButton:
        button = QPushButton(text)
        if primary:
            button.setObjectName("Primary")
        if danger:
            button.setObjectName("Danger")
        button.clicked.connect(handler)
        return button

    def _apply_theme(self) -> None:
        app = QApplication.instance()
        if app is not None:
            app.setStyleSheet(stylesheet(self.settings.theme))

    def _on_connection(self, ok: bool, message: str) -> None:
        self.connected = ok
        self.statusBar().showMessage(message)
        self._refresh_actions()

    def _on_snapshot(self, payload: dict) -> None:
        self.settings = AppSettings.from_dict(payload.get("settings"))
        self._apply_theme()
        self.tray.setVisible(self.settings.minimize_to_tray)
        self.configs = {item["id"]: item for item in payload.get("configs", []) if isinstance(item, dict)}
        self.runtimes = {
            item["server_id"]: item for item in payload.get("runtimes", []) if isinstance(item, dict)
        }
        self.server_list.sync(self.configs, self.runtimes)
        self.console.set_colors({server_id: item.get("color", "#4FC1FF") for server_id, item in self.configs.items()})
        self.console.set_servers([(server_id, item.get("name", server_id)) for server_id, item in self.configs.items()])
        self.console.set_limit(self.settings.max_console_lines)
        if payload.get("logs") is not None:
            self.console.replace(list(payload.get("logs") or []))
        warnings = payload.get("warnings") or []
        if warnings and not self._warnings_shown:
            self._warnings_shown = True
            QMessageBox.warning(self, "Configuration", "\n".join(str(item) for item in warnings))
        self._refresh_dashboard()
        self._refresh_actions()

    def _on_runtime(self, runtime: dict) -> None:
        server_id = str(runtime.get("server_id", ""))
        if not server_id:
            return
        self.runtimes[server_id] = runtime
        self.server_list.update_one(self.configs.get(server_id), runtime)
        self._refresh_dashboard()
        self._refresh_actions()

    def _on_logs(self, entries: list) -> None:
        self.console.add_entries(list(entries))

    def _on_ack(self, payload: dict) -> None:
        if payload.get("ok", True):
            return
        message = str(payload.get("message") or "The supervisor rejected the command.")
        QMessageBox.warning(self, "MC Server Hub", message)

    def _refresh_dashboard(self) -> None:
        values = list(self.runtimes.values())
        running = sum(1 for item in values if item.get("status") in {"RUNNING", "STARTING"})
        stopped = sum(1 for item in values if item.get("status") in {"STOPPED", "STOPPING"})
        trouble = sum(1 for item in values if item.get("status") in {"CRASHED", "RESTARTING", "ERROR"})
        self.dashboard.set_counts(len(values), running, stopped, trouble)

    def _refresh_actions(self) -> None:
        server_id = self.server_list.current_id()
        runtime = self.runtimes.get(server_id, {})
        status = runtime.get("status", "STOPPED")
        config = self.configs.get(server_id)
        self.command_target.setText(config.get("name", "No server selected") if config else "No server selected")
        has = bool(server_id) and self.connected
        self.edit_button.setEnabled(has)
        self.remove_button.setEnabled(has)
        self.start_button.setEnabled(has and status in {"STOPPED", "CRASHED", "ERROR", "RESTARTING"})
        self.stop_button.setEnabled(has and status in {"RUNNING", "STARTING", "RESTARTING"})
        self.restart_button.setEnabled(has and status != "STOPPING")
        self.add_button.setEnabled(self.connected)
        self.start_all_button.setEnabled(self.connected)
        self.stop_all_button.setEnabled(self.connected)
        self.command_input.setEnabled(has and status in {"RUNNING", "STARTING"})

    def _on_selected(self, _server_id: str) -> None:
        self._refresh_actions()

    def _selected_id(self) -> str:
        server_id = self.server_list.current_id()
        if not server_id:
            QMessageBox.information(self, "MC Server Hub", "Select a server first.")
        return server_id

    def _add_server(self) -> None:
        if not self._require_connection():
            return
        dialog = ServerDialog(self.settings, parent=self)
        if dialog.exec() != ServerDialog.DialogCode.Accepted or dialog.result_config is None:
            return
        self.client.send({"type": "add_server", "config": dialog.result_config.to_dict()})

    def _edit_server(self) -> None:
        server_id = self._selected_id()
        if not server_id or not self._require_connection():
            return
        dialog = ServerDialog(self.settings, ServerConfig.from_dict(self.configs[server_id]), self)
        if dialog.exec() != ServerDialog.DialogCode.Accepted or dialog.result_config is None:
            return
        self.client.send({"type": "update_server", "config": dialog.result_config.to_dict()})

    def _remove_server(self) -> None:
        server_id = self._selected_id()
        if not server_id or not self._require_connection():
            return
        name = self.configs.get(server_id, {}).get("name", "this server")
        if not self._confirm(f"Remove {name}? A running process will be stopped."):
            return
        self.client.send({"type": "remove_server", "id": server_id})

    def _start_selected(self) -> None:
        server_id = self._selected_id()
        if server_id and self._require_connection():
            self.client.send({"type": "start_server", "id": server_id})

    def _stop_selected(self) -> None:
        server_id = self._selected_id()
        if not server_id or not self._require_connection():
            return
        name = self.configs.get(server_id, {}).get("name", "this server")
        if self.settings.confirm_before_stop and not self._confirm(f"Stop {name}?"):
            return
        self.client.send({"type": "stop_server", "id": server_id})

    def _restart_selected(self) -> None:
        server_id = self._selected_id()
        if server_id and self._require_connection():
            self.client.send({"type": "restart_server", "id": server_id})

    def _start_all(self) -> None:
        if self._require_connection():
            self.client.send({"type": "start_all"})

    def _stop_all(self) -> None:
        if not self._require_connection():
            return
        if self.settings.confirm_before_stop and not self._confirm("Stop every running server?"):
            return
        self.client.send({"type": "stop_all"})

    def _open_settings(self) -> None:
        dialog = SettingsDialog(self.settings, self._start_all, self._stop_all, self)
        if dialog.exec() != SettingsDialog.DialogCode.Accepted or dialog.result_settings is None:
            return
        self.client.send({"type": "update_settings", "settings": dialog.result_settings.to_dict()})

    def _send_command(self) -> None:
        server_id = self.server_list.current_id()
        command = self.command_input.text().strip()
        if not server_id or not command or not self._require_connection():
            return
        self.client.send({"type": "send_command", "id": server_id, "command": command})
        self._command_history.append(command)
        self._command_history = self._command_history[-50:]
        self._history_index = len(self._command_history)
        self.command_input.clear()

    def _open_logs(self) -> None:
        server_id = self.server_list.current_id()
        folder = self.app_root / "logs"
        if server_id and server_id in self.configs:
            named = folder / str(self.configs[server_id].get("log_folder") or "")
            if named.exists():
                folder = named
        folder.mkdir(parents=True, exist_ok=True)
        os.startfile(folder)  # type: ignore[attr-defined]

    def eventFilter(self, watched, event) -> bool:
        if watched is self.command_input and event.type() == QEvent.Type.KeyPress:
            if event.key() == Qt.Key.Key_Up and self._command_history:
                self._history_index = max(0, self._history_index - 1)
                self.command_input.setText(self._command_history[self._history_index])
                return True
            if event.key() == Qt.Key.Key_Down and self._command_history:
                self._history_index = min(len(self._command_history), self._history_index + 1)
                if self._history_index == len(self._command_history):
                    self.command_input.clear()
                else:
                    self.command_input.setText(self._command_history[self._history_index])
                return True
        return super().eventFilter(watched, event)

    def _require_connection(self) -> bool:
        if self.connected:
            return True
        QMessageBox.information(self, "MC Server Hub", "The supervisor is not connected yet.")
        return False

    def _confirm(self, text: str) -> bool:
        answer = QMessageBox.question(self, "MC Server Hub", text)
        return answer == QMessageBox.StandardButton.Yes

    def _tray_activated(self, reason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self._show_from_tray()

    def _show_from_tray(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def _request_quit(self) -> None:
        self._force_quit = True
        self.close()

    def closeEvent(self, event: QCloseEvent) -> None:
        if self.settings.minimize_to_tray and not self._force_quit:
            event.ignore()
            self.hide()
            self.tray.show()
            self.tray.showMessage(
                "MC Server Hub",
                "The window is in the tray. Servers keep their supervisor.",
                QSystemTrayIcon.MessageIcon.Information,
                2500,
            )
            return
        choice = self._close_choice()
        if choice is None:
            event.ignore()
            self._force_quit = False
            return
        if choice == "stop":
            self.statusBar().showMessage("Stopping servers...")
            self.client.send({"type": "shutdown", "stop_servers": True})
            self._wait_for_disconnect(self.settings.graceful_stop_timeout_seconds + 10)
        else:
            self.client.stop()
        event.accept()
        app = QApplication.instance()
        if app is not None:
            app.quit()

    def _close_choice(self) -> str | None:
        behavior = self.settings.close_behavior
        if behavior == "keep_running":
            return "keep"
        if behavior == "stop_all":
            if self.settings.confirm_before_stop and not self._confirm("Stop all servers and exit?"):
                return None
            return "stop"
        box = QMessageBox(self)
        box.setWindowTitle("Close MC Server Hub")
        box.setText("The servers are owned by a background supervisor.")
        box.setInformativeText(
            "Keep the supervisor running so the servers stay up, or stop every server and exit the supervisor."
        )
        keep = box.addButton("Keep servers running", QMessageBox.ButtonRole.AcceptRole)
        stop = box.addButton("Stop all servers", QMessageBox.ButtonRole.DestructiveRole)
        box.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
        box.exec()
        clicked = box.clickedButton()
        if clicked is keep:
            return "keep"
        if clicked is stop:
            return "stop"
        return None

    def _wait_for_disconnect(self, timeout: float) -> None:
        if not self.connected:
            return
        loop = QEventLoop(self)
        self.client.connection_changed.connect(lambda ok, _message: loop.quit() if not ok else None)
        QTimer.singleShot(int(timeout * 1000), loop.quit)
        loop.exec()


def run_gui() -> int:
    import ctypes
    import sys

    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("MC.ServerHub")
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setApplicationName("MC Server Hub")
    app.setQuitOnLastWindowClosed(False)
    window = MainWindow()
    window.show()
    return app.exec()
