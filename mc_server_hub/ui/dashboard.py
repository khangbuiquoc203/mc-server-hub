"""Top-of-window counts. These are summaries, not a second source of truth."""

from __future__ import annotations

from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget


class _Card(QFrame):
    def __init__(self, title: str, accent: str) -> None:
        super().__init__()
        self.setObjectName("Card")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(2)
        self.value = QLabel("0")
        self.value.setObjectName("CardValue")
        self.accent = accent
        self.value.setStyleSheet(f"color: {accent};")
        label = QLabel(title)
        label.setObjectName("CardLabel")
        layout.addWidget(self.value)
        layout.addWidget(label)

    def set_value(self, value: int) -> None:
        self.value.setText(str(value))
        self.value.setStyleSheet(f"color: {self.accent};")


class Dashboard(QWidget):
    def __init__(self) -> None:
        super().__init__()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 6)
        layout.setSpacing(10)
        self.total = _Card("Servers", "#4FC1FF")
        self.running = _Card("Running", "#6CC66C")
        self.stopped = _Card("Stopped", "#A0A0A0")
        self.trouble = _Card("Crash / restart", "#F14C4C")
        for card in (self.total, self.running, self.stopped, self.trouble):
            layout.addWidget(card)

    def set_counts(self, total: int, running: int, stopped: int, trouble: int) -> None:
        self.total.set_value(total)
        self.running.set_value(running)
        self.stopped.set_value(stopped)
        self.trouble.set_value(trouble)
