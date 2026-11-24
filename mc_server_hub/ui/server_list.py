"""Sidebar rows for every configured server."""

from __future__ import annotations

import time

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QLabel, QListWidget, QListWidgetItem, QVBoxLayout, QWidget

from mc_server_hub.utils.format_utils import format_bytes, format_duration


_STATUS_COLOR = {
    "RUNNING": "#6CC66C",
    "STOPPED": "#8A8A8A",
    "STARTING": "#D7BA7D",
    "STOPPING": "#D7BA7D",
    "CRASHED": "#F14C4C",
    "RESTARTING": "#C586C0",
    "ERROR": "#F14C4C",
}


class ServerRow(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(2)
        self.name = QLabel()
        self.name.setObjectName("RowName")
        self.status = QLabel()
        self.status.setObjectName("RowMeta")
        self.meta = QLabel()
        self.meta.setObjectName("RowMeta")
        layout.addWidget(self.name)
        layout.addWidget(self.status)
        layout.addWidget(self.meta)
        self.runtime: dict = {}

    def apply(self, config: dict, runtime: dict) -> None:
        self.runtime = runtime
        self.name.setText(config.get("name", "Server"))
        self.name.setStyleSheet(f"color: {config.get('color', '#4FC1FF')};")
        self._paint_clock()

    def _paint_clock(self) -> None:
        runtime = self.runtime
        status = str(runtime.get("status", "STOPPED"))
        color = _STATUS_COLOR.get(status, "#D4D4D4")
        deadline = runtime.get("restart_deadline")
        if status == "RESTARTING" and isinstance(deadline, (int, float)):
            remaining = max(0, int(deadline - time.time()))
            status_text = f"{status}  ·  {remaining}s"
        else:
            status_text = status
        pid = runtime.get("java_pid") or runtime.get("root_pid") or "-"
        self.status.setText(f"●  {status_text}   PID {pid}")
        self.status.setStyleSheet(f"color: {color};")
        started = runtime.get("started_at")
        uptime = None
        if isinstance(started, (int, float)) and status in {"RUNNING", "STARTING", "STOPPING"}:
            uptime = time.time() - started
        attempts = runtime.get("restart_attempts", 0)
        error = runtime.get("last_error") or ""
        meta = (
            f"Up {format_duration(uptime)}   "
            f"RAM {format_bytes(runtime.get('memory_bytes') or 0)}   "
            f"CPU {float(runtime.get('cpu_percent') or 0):.0f}%"
        )
        if attempts:
            meta += f"   Restarts {attempts}"
        if error and status in {"ERROR", "CRASHED", "RESTARTING"}:
            meta += f"\n{error}"
        self.meta.setText(meta)


class ServerList(QWidget):
    selected = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.empty = QLabel("No servers yet.\nAdd one to get started.")
        self.empty.setObjectName("Muted")
        self.empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty.setContentsMargins(12, 24, 12, 12)
        self.list = QListWidget()
        self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.list.currentItemChanged.connect(self._emit_selected)
        layout.addWidget(self.empty)
        layout.addWidget(self.list, 1)
        self._rows: dict[str, tuple[QListWidgetItem, ServerRow]] = {}

    def sync(self, configs: dict[str, dict], runtimes: dict[str, dict]) -> None:
        selected = self.current_id()
        for server_id in list(self._rows):
            if server_id not in configs:
                item, _row = self._rows.pop(server_id)
                self.list.takeItem(self.list.row(item))
        for server_id, config in configs.items():
            runtime = runtimes.get(server_id, {"server_id": server_id, "status": "STOPPED"})
            if server_id not in self._rows:
                item = QListWidgetItem()
                row = ServerRow()
                item.setData(Qt.ItemDataRole.UserRole, server_id)
                item.setSizeHint(row.sizeHint())
                self.list.addItem(item)
                self.list.setItemWidget(item, row)
                self._rows[server_id] = (item, row)
            item, row = self._rows[server_id]
            row.apply(config, runtime)
            item.setSizeHint(row.sizeHint())
        self.empty.setVisible(not configs)
        self.list.setVisible(bool(configs))
        if selected and selected in self._rows:
            self.list.setCurrentItem(self._rows[selected][0])
        elif self.list.currentItem() is None and self.list.count():
            self.list.setCurrentRow(0)

    def update_one(self, config: dict | None, runtime: dict) -> None:
        server_id = runtime.get("server_id")
        if not server_id or server_id not in self._rows or config is None:
            return
        item, row = self._rows[server_id]
        row.apply(config, runtime)
        item.setSizeHint(row.sizeHint())

    def refresh_clocks(self) -> None:
        for item, row in self._rows.values():
            row._paint_clock()
            item.setSizeHint(row.sizeHint())

    def current_id(self) -> str:
        item = self.list.currentItem()
        if item is None:
            return ""
        return str(item.data(Qt.ItemDataRole.UserRole) or "")

    def _emit_selected(self, current, _previous) -> None:
        if current is None:
            return
        server_id = str(current.data(Qt.ItemDataRole.UserRole) or "")
        if server_id:
            self.selected.emit(server_id)
