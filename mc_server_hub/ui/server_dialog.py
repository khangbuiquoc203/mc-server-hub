"""Add or edit one server without touching its BAT file."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)

from mc_server_hub.models.app_settings import AppSettings
from mc_server_hub.models.server_config import ServerConfig


class ServerDialog(QDialog):
    def __init__(self, settings: AppSettings, existing: ServerConfig | None = None, parent=None) -> None:
        super().__init__(parent)
        self.settings = settings
        self.existing = existing
        self.result_config: ServerConfig | None = None
        self.setWindowTitle("Edit server" if existing else "Add server")
        self.resize(640, 420)

        self.name = QLineEdit(existing.name if existing else "")
        self.bat_path = QLineEdit(existing.bat_path if existing else "")
        self.working_directory = QLineEdit(existing.working_directory if existing else "")
        self.auto_restart = QCheckBox("Restart automatically after a crash")
        self.auto_restart.setChecked(existing.auto_restart if existing else True)
        self.unlimited = QCheckBox("Unlimited restart attempts")
        self.unlimited.setChecked(existing.unlimited_restarts if existing else False)
        self.auto_start = QCheckBox("Start when the supervisor launches")
        self.auto_start.setChecked(existing.auto_start if existing else False)

        self.delay = QSpinBox()
        self.delay.setRange(1, 3600)
        self.delay.setSuffix(" sec")
        self.delay.setValue(existing.restart_delay_seconds if existing else settings.default_restart_delay)
        self.attempts = QSpinBox()
        self.attempts.setRange(1, 1000)
        self.attempts.setValue(existing.max_restart_attempts if existing else settings.default_max_restart_attempts)
        self.unlimited.toggled.connect(self.attempts.setDisabled)
        self.attempts.setDisabled(self.unlimited.isChecked())

        form = QFormLayout()
        form.addRow("Display name", self.name)
        form.addRow("BAT file", self._browse_row(self.bat_path, self._browse_bat))
        form.addRow("Working directory", self._browse_row(self.working_directory, self._browse_dir))
        form.addRow("", self.auto_restart)
        form.addRow("Restart delay", self.delay)
        form.addRow("", self.unlimited)
        form.addRow("Maximum attempts", self.attempts)
        form.addRow("", self.auto_start)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def _browse_row(self, edit: QLineEdit, callback) -> QHBoxLayout:
        row = QHBoxLayout()
        button = QPushButton("Browse")
        button.clicked.connect(callback)
        row.addWidget(edit, 1)
        row.addWidget(button)
        return row

    def _browse_bat(self) -> None:
        path, _selected = QFileDialog.getOpenFileName(
            self,
            "Choose the server BAT file",
            self.bat_path.text(),
            "Batch files (*.bat *.cmd)",
        )
        if not path:
            return
        self.bat_path.setText(path)
        if not self.working_directory.text().strip():
            from pathlib import Path
            self.working_directory.setText(str(Path(path).parent))

    def _browse_dir(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Working directory", self.working_directory.text())
        if path:
            self.working_directory.setText(path)

    def _save(self) -> None:
        config = ServerConfig(
            id=self.existing.id if self.existing else "",
            name=self.name.text(),
            bat_path=self.bat_path.text(),
            working_directory=self.working_directory.text(),
            auto_restart=self.auto_restart.isChecked(),
            restart_delay_seconds=self.delay.value(),
            max_restart_attempts=self.attempts.value(),
            unlimited_restarts=self.unlimited.isChecked(),
            auto_start=self.auto_start.isChecked(),
            color=self.existing.color if self.existing else "",
            log_folder=self.existing.log_folder if self.existing else "",
        )
        error = config.validate()
        if error:
            QMessageBox.warning(self, "Check the server", error)
            return
        self.result_config = config
        self.accept()
