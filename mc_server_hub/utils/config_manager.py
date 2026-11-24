"""Load and save JSON configuration beside the application."""

from __future__ import annotations

import json
from pathlib import Path

from mc_server_hub.models.app_settings import AppSettings
from mc_server_hub.models.server_config import ServerConfig


class ConfigError(RuntimeError):
    """A configuration file could not be read or written."""


class ConfigManager:
    def __init__(self, app_root: Path) -> None:
        self.app_root = Path(app_root)
        self.config_dir = self.app_root / "config"
        self.servers_path = self.config_dir / "servers.json"
        self.settings_path = self.config_dir / "settings.json"
        self.warnings: list[str] = []
        self.config_dir.mkdir(parents=True, exist_ok=True)

    def load_servers(self) -> list[ServerConfig]:
        payload = self._read_json(self.servers_path, {"servers": []})
        raw_servers = payload.get("servers", []) if isinstance(payload, dict) else []
        if not isinstance(raw_servers, list):
            raise ConfigError(f"{self.servers_path} does not contain a server list.")
        configs: list[ServerConfig] = []
        for item in raw_servers:
            if isinstance(item, dict):
                configs.append(ServerConfig.from_dict(item))
        return configs

    def save_servers(self, configs: list[ServerConfig]) -> None:
        payload = {"servers": [config.to_dict() for config in configs]}
        self._write_json(self.servers_path, payload)

    def load_settings(self) -> AppSettings:
        payload = self._read_json(self.settings_path, AppSettings().to_dict())
        return AppSettings.from_dict(payload if isinstance(payload, dict) else {})

    def save_settings(self, settings: AppSettings) -> None:
        settings.normalized()
        self._write_json(self.settings_path, settings.to_dict())

    def _read_json(self, path: Path, default: dict) -> dict:
        if not path.exists():
            self._write_json(path, default)
            return json.loads(json.dumps(default))
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            broken = path.with_suffix(path.suffix + ".bad")
            try:
                path.replace(broken)
            except OSError:
                pass
            self._write_json(path, default)
            self.warnings.append(f"{path.name} was invalid and was moved aside: {exc}")
            return json.loads(json.dumps(default))

    def _write_json(self, path: Path, payload: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        text = json.dumps(payload, indent=2, ensure_ascii=False)
        temporary.write_text(text + "\n", encoding="utf-8")
        temporary.replace(path)
