"""Application settings shared by the window and the supervisor."""

from __future__ import annotations

from dataclasses import asdict, dataclass, fields


@dataclass
class AppSettings:
    theme: str = "dark"
    default_restart_delay: int = 5
    default_max_restart_attempts: int = 3
    log_retention_days: int = 14
    confirm_before_stop: bool = True
    minimize_to_tray: bool = False
    close_behavior: str = "ask"
    max_console_lines: int = 5000
    stable_uptime_reset_seconds: int = 120
    graceful_stop_timeout_seconds: int = 45
    startup_grace_seconds: int = 30

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict | None) -> AppSettings:
        if not isinstance(data, dict):
            return cls()
        known = {item.name for item in fields(cls)}
        values = {key: value for key, value in data.items() if key in known}
        settings = cls(**values)
        settings.normalized()
        return settings

    def normalized(self) -> AppSettings:
        if self.theme not in {"dark", "light"}:
            self.theme = "dark"
        if self.close_behavior not in {"ask", "keep_running", "stop_all"}:
            self.close_behavior = "ask"
        self.default_restart_delay = _clamp(self.default_restart_delay, 1, 3600, 5)
        self.default_max_restart_attempts = _clamp(self.default_max_restart_attempts, 1, 1000, 3)
        self.log_retention_days = _clamp(self.log_retention_days, 0, 3650, 14)
        self.max_console_lines = _clamp(self.max_console_lines, 500, 20000, 5000)
        self.stable_uptime_reset_seconds = _clamp(self.stable_uptime_reset_seconds, 10, 86400, 120)
        self.graceful_stop_timeout_seconds = _clamp(self.graceful_stop_timeout_seconds, 3, 600, 45)
        self.startup_grace_seconds = _clamp(self.startup_grace_seconds, 3, 300, 30)
        self.confirm_before_stop = bool(self.confirm_before_stop)
        self.minimize_to_tray = bool(self.minimize_to_tray)
        return self


def _clamp(value: object, low: int, high: int, default: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    return max(low, min(high, number))
