"""Dark and light styles inspired by a server panel, not a marketing page."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPixmap


def console_font() -> QFont:
    font = QFont("Cascadia Mono")
    font.setStyleHint(QFont.StyleHint.Monospace)
    if not font.exactMatch():
        font = QFont("Consolas")
        font.setStyleHint(QFont.StyleHint.Monospace)
    font.setPointSize(10)
    return font


def app_icon() -> QIcon:
    pixmap = QPixmap(64, 64)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor("#0E639C"))
    painter.drawRoundedRect(0, 0, 64, 64, 14, 14)
    painter.setPen(QColor("#F3F3F3"))
    font = QFont("Segoe UI", 18)
    font.setBold(True)
    painter.setFont(font)
    painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, "MC")
    painter.end()
    return QIcon(pixmap)


def stylesheet(theme: str) -> str:
    if theme == "light":
        return _LIGHT
    return _DARK


_DARK = """
* { font-family: "Segoe UI"; color: #D4D4D4; font-size: 13px; }
QMainWindow, QDialog, QWidget { background: #1E1E1E; }
QFrame#Header { background: #181818; border-bottom: 1px solid #2B2B2B; }
QFrame#Sidebar { background: #181818; border-right: 1px solid #2B2B2B; }
QFrame#Card { background: #252526; border: 1px solid #333333; border-radius: 8px; }
QLabel#Title { font-size: 18px; font-weight: 650; color: #F3F3F3; }
QLabel#Subtitle { color: #8A8A8A; font-size: 12px; }
QLabel#CardValue { font-size: 26px; font-weight: 700; }
QLabel#CardLabel { color: #9D9D9D; font-size: 12px; }
QLabel#Muted { color: #8A8A8A; }
QLabel#RowName { font-weight: 650; color: #F3F3F3; }
QLabel#RowMeta { color: #A0A0A0; font-size: 12px; }
QPlainTextEdit, QLineEdit, QSpinBox, QComboBox, QListWidget {
    background: #1E1E1E;
    border: 1px solid #3C3C3C;
    border-radius: 6px;
    padding: 4px 6px;
    selection-background-color: #094771;
}
QPlainTextEdit { background: #121212; border-radius: 0; padding: 8px; }
QListWidget { background: #181818; border: none; outline: none; }
QListWidget::item { border-bottom: 1px solid #2A2A2A; }
QListWidget::item:selected { background: #094771; }
QPushButton {
    background: #2D2D30;
    border: 1px solid #3C3C3C;
    border-radius: 6px;
    padding: 6px 12px;
}
QPushButton:hover { background: #3A3A3D; }
QPushButton:pressed { background: #094771; }
QPushButton:disabled { color: #666666; background: #252526; }
QPushButton#Primary { background: #0E639C; border-color: #1177BB; color: white; }
QPushButton#Danger { background: #5A1D1D; border-color: #8A2E2E; color: #F3C7C7; }
QCheckBox { spacing: 8px; }
QStatusBar { background: #007ACC; color: white; }
QStatusBar QLabel { color: white; }
QMenuBar { background: #181818; }
QMenuBar::item:selected, QMenu::item:selected { background: #094771; }
QMenu { background: #252526; border: 1px solid #3C3C3C; }
QScrollBar:vertical { background: #1E1E1E; width: 12px; margin: 0; }
QScrollBar::handle:vertical { background: #424242; min-height: 24px; border-radius: 4px; }
QScrollBar::add-line, QScrollBar::sub-line { height: 0; }
QToolTip { background: #252526; color: #D4D4D4; border: 1px solid #3C3C3C; }
QComboBox QAbstractItemView { background: #252526; selection-background-color: #094771; }
"""

_LIGHT = """
* { font-family: "Segoe UI"; color: #1F1F1F; font-size: 13px; }
QMainWindow, QDialog, QWidget { background: #F5F5F5; }
QFrame#Header { background: #FFFFFF; border-bottom: 1px solid #E0E0E0; }
QFrame#Sidebar { background: #FFFFFF; border-right: 1px solid #E0E0E0; }
QFrame#Card { background: #FFFFFF; border: 1px solid #E0E0E0; border-radius: 8px; }
QLabel#Title { font-size: 18px; font-weight: 650; color: #1F1F1F; }
QLabel#Subtitle { color: #666666; font-size: 12px; }
QLabel#CardValue { font-size: 26px; font-weight: 700; }
QLabel#CardLabel { color: #666666; font-size: 12px; }
QLabel#Muted { color: #666666; }
QLabel#RowName { font-weight: 650; color: #1F1F1F; }
QLabel#RowMeta { color: #555555; font-size: 12px; }
QPlainTextEdit, QLineEdit, QSpinBox, QComboBox, QListWidget {
    background: #FFFFFF;
    border: 1px solid #D0D0D0;
    border-radius: 6px;
    padding: 4px 6px;
    selection-background-color: #CCE4F7;
}
QPlainTextEdit { background: #FAFAFA; border-radius: 0; padding: 8px; }
QListWidget { background: #FFFFFF; border: none; }
QListWidget::item:selected { background: #CCE4F7; }
QPushButton {
    background: #FFFFFF;
    border: 1px solid #C8C8C8;
    border-radius: 6px;
    padding: 6px 12px;
}
QPushButton:hover { background: #F0F0F0; }
QPushButton#Primary { background: #0E639C; border-color: #0E639C; color: white; }
QPushButton#Danger { background: #FDECEC; border-color: #E0B4B4; color: #8A1F1F; }
QStatusBar { background: #0E639C; color: white; }
QStatusBar QLabel { color: white; }
QMenu { background: #FFFFFF; border: 1px solid #D0D0D0; }
QScrollBar:vertical { background: #F5F5F5; width: 12px; }
QScrollBar::handle:vertical { background: #C8C8C8; min-height: 24px; border-radius: 4px; }
QScrollBar::add-line, QScrollBar::sub-line { height: 0; }
"""
