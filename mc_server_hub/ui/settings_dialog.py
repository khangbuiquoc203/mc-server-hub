"""Application settings. Start-all and stop-all live here as well as on the toolbar."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)

from mc_server_hub.models.app_settings import AppSettings


class SettingsDialog(QDialog):
    def __init__(self, settings: AppSettings, on_start_all, on_stop_all, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.resize(480, 460)
        self.result_settings: AppSettings | None = None

        self.theme = QComboBox()
        self.theme.addItem("Dark", "dark")
        self.theme.addItem("Light", "light")
        index = self.theme.findData(settings.theme)
        self.theme.setCurrentIndex(index if index >= 0 else 0)

        self.delay = QSpinBox()
        self.delay.setRange(1, 3600)
        self.delay.setSuffix(" sec")
        self.delay.setValue(settings.default_restart_delay)
        self.attempts = QSpinBox()
        self.attempts.setRange(1, 1000)
        self.attempts.setValue(settings.default_max_restart_attempts)
        self.retention = QSpinBox()
        self.retention.setRange(0, 3650)
        self.retention.setSpecialValueText("Keep all")
        self.retention.setSuffix(" days")
        self.retention.setValue(settings.log_retention_days)
        self.confirm_stop = QCheckBox("Ask before stopping a server")
        self.confirm_stop.setChecked(settings.confirm_before_stop)
        self.tray = QCheckBox("Closing the window minimizes to the tray")
        self.tray.setChecked(settings.minimize_to_tray)
        self.close_behavior = QComboBox()
        self.close_behavior.addItem("Ask what to do with running servers", "ask")
        self.close_behavior.addItem("Keep servers running", "keep_running")
        self.close_behavior.addItem("Stop all servers", "stop_all")
        behavior_index = self.close_behavior.findData(settings.close_behavior)
        self.close_behavior.setCurrentIndex(behavior_index if behavior_index >= 0 else 0)

        form = QFormLayout()
        form.addRow("Theme", self.theme)
        form.addRow("Default restart delay", self.delay)
        form.addRow("Default maximum attempts", self.attempts)
        form.addRow("Log retention", self.retention)
        form.addRow("", self.confirm_stop)
        form.addRow("", self.tray)
        form.addRow("Quit behavior", self.close_behavior)

        actions = QHBoxLayout()
        start_all = QPushButton("Start all servers")
        stop_all = QPushButton("Stop all servers")
        stop_all.setObjectName("Danger")
        start_all.clicked.connect(on_start_all)
        stop_all.clicked.connect(on_stop_all)
        actions.addWidget(start_all)
        actions.addWidget(stop_all)
        actions.addStretch(1)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addLayout(actions)
        layout.addStretch(1)
        layout.addWidget(buttons)

    def _save(self) -> None:
        self.result_settings = AppSettings(
            theme=str(self.theme.currentData()),
            default_restart_delay=self.delay.value(),
            default_max_restart_attempts=self.attempts.value(),
            log_retention_days=self.retention.value(),
            confirm_before_stop=self.confirm_stop.isChecked(),
            minimize_to_tray=self.tray.isChecked(),
            close_behavior=str(self.close_behavior.currentData()),
        ).normalized()
        self.accept()
