"""Central log view. The widget only keeps a bounded number of lines."""

from __future__ import annotations

from collections import deque
from pathlib import Path

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QColor, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from mc_server_hub.ui.theme import console_font


class ConsolePanel(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.records: deque[dict] = deque(maxlen=5000)
        self.colors: dict[str, str] = {}
        self._server_filter = ""
        self._search = ""

        toolbar = QHBoxLayout()
        toolbar.setContentsMargins(8, 6, 8, 6)
        toolbar.addWidget(QLabel("View"))
        self.filter = QComboBox()
        self.filter.setMinimumWidth(180)
        self.filter.addItem("All servers", "")
        self.filter.currentIndexChanged.connect(self._filter_changed)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search log")
        self.search.setClearButtonEnabled(True)
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(150)
        self._search_timer.timeout.connect(self._apply_search)
        self.search.textChanged.connect(lambda _text: self._search_timer.start())
        self.autoscroll = QCheckBox("Auto-scroll")
        self.autoscroll.setChecked(True)
        clear_button = QPushButton("Clear view")
        export_button = QPushButton("Export")
        clear_button.clicked.connect(self.clear_view)
        export_button.clicked.connect(self.export_view)
        toolbar.addWidget(self.filter)
        toolbar.addWidget(self.search, 1)
        toolbar.addWidget(self.autoscroll)
        toolbar.addWidget(clear_button)
        toolbar.addWidget(export_button)

        self.view = QPlainTextEdit()
        self.view.setReadOnly(True)
        self.view.setUndoRedoEnabled(False)
        self.view.setMaximumBlockCount(5000)
        self.view.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        self.view.setFont(console_font())
        self._timestamp_format = self._format("#808080")
        self._message_format = self._format("#D4D4D4")
        self._system_format = self._format("#D7BA7D")
        self._error_format = self._format("#F14C4C")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addLayout(toolbar)
        layout.addWidget(self.view, 1)

    def set_limit(self, limit: int) -> None:
        if limit == self.records.maxlen:
            return
        self.records = deque(self.records, maxlen=limit)
        self.view.setMaximumBlockCount(limit)
        self.rebuild()

    def set_colors(self, colors: dict[str, str]) -> None:
        self.colors = colors

    def set_servers(self, servers: list[tuple[str, str]]) -> None:
        current = self.filter.currentData()
        self.filter.blockSignals(True)
        self.filter.clear()
        self.filter.addItem("All servers", "")
        for server_id, name in servers:
            self.filter.addItem(name, server_id)
        index = self.filter.findData(current)
        self.filter.setCurrentIndex(index if index >= 0 else 0)
        self.filter.blockSignals(False)
        new_filter = str(self.filter.currentData() or "")
        if new_filter != self._server_filter:
            self._server_filter = new_filter
            self.rebuild()

    def add_entries(self, entries: list[dict]) -> None:
        if not entries:
            return
        self.records.extend(entries)
        self._append(entries)

    def replace(self, entries: list[dict]) -> None:
        self.records.clear()
        self.records.extend(entries)
        self.rebuild()

    def clear_view(self) -> None:
        self.records.clear()
        self.view.clear()

    def export_view(self) -> None:
        path, _selected = QFileDialog.getSaveFileName(
            self,
            "Export console",
            "mc-server-hub.log",
            "Log files (*.log);;Text files (*.txt)",
        )
        if not path:
            return
        Path(path).write_text(self.view.toPlainText(), encoding="utf-8")

    def rebuild(self) -> None:
        self.view.clear()
        self._append(list(self.records))

    def _filter_changed(self) -> None:
        self._server_filter = str(self.filter.currentData() or "")
        self.rebuild()

    def _apply_search(self) -> None:
        self._search = self.search.text().strip().lower()
        self.rebuild()

    def _append(self, entries: list[dict]) -> None:
        visible = [entry for entry in entries if self._matches(entry)]
        if not visible:
            return
        cursor = self.view.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self.view.setUpdatesEnabled(False)
        try:
            for entry in visible:
                self._insert(cursor, entry)
        finally:
            self.view.setUpdatesEnabled(True)
        if self.autoscroll.isChecked():
            self.view.moveCursor(QTextCursor.MoveOperation.End)
            self.view.ensureCursorVisible()

    def _insert(self, cursor: QTextCursor, entry: dict) -> None:
        timestamp = str(entry.get("timestamp", ""))
        name = str(entry.get("server_name", ""))
        message = str(entry.get("message", ""))
        cursor.insertText(f"[{timestamp}] ", self._timestamp_format)
        name_format = self._format(self.colors.get(str(entry.get("server_id", "")), "#4FC1FF"))
        cursor.insertText(f"[{name}] ", name_format)
        cursor.insertText(message + "\n", self._message_format_for(entry))

    def _matches(self, entry: dict) -> bool:
        if self._server_filter and str(entry.get("server_id", "")) != self._server_filter:
            return False
        if self._search and self._search not in str(entry.get("line", "")).lower():
            return False
        return True

    def _message_format_for(self, entry: dict) -> QTextCharFormat:
        message = str(entry.get("message", ""))
        stream = str(entry.get("stream", "stdout"))
        if stream == "system":
            return self._system_format
        upper = message.upper()
        if "ERROR" in upper or "EXCEPTION" in upper:
            return self._error_format
        return self._message_format

    def _format(self, color: str) -> QTextCharFormat:
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(color))
        return fmt
