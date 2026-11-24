"""Persisted configuration for one Minecraft server."""

from __future__ import annotations

from dataclasses import asdict, dataclass, fields
from pathlib import Path
import uuid


SERVER_COLORS = [
    "#4FC1FF",
    "#6CC66C",
    "#D7BA7D",
    "#C586C0",
    "#F14C4C",
    "#4EC9B0",
    "#CE9178",
    "#9CDCFE",
    "#DCDCAA",
    "#B5CEA8",
    "#D16969",
    "#569CD6",
]


@dataclass
class ServerConfig:
    """User-owned settings for a server started from an existing BAT file."""

    id: str
    name: str
    bat_path: str
    working_directory: str
    auto_restart: bool = True
    restart_delay_seconds: int = 5
    max_restart_attempts: int = 3
    unlimited_restarts: bool = False
    auto_start: bool = False
    color: str = SERVER_COLORS[0]
    log_folder: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> ServerConfig:
        known = {item.name for item in fields(cls)}
        values = {key: value for key, value in data.items() if key in known}
        if not values.get("id"):
            values["id"] = uuid.uuid4().hex
        return cls(**values)

    def normalized(self) -> ServerConfig:
        """Return a copy with absolute paths and a usable working directory."""
        bat = str(Path(self.bat_path).expanduser())
        work = self.working_directory.strip()
        if not work:
            work = str(Path(bat).parent)
        work = str(Path(work).expanduser())
        self.bat_path = bat
        self.working_directory = work
        self.name = self.name.strip()
        self.restart_delay_seconds = int(self.restart_delay_seconds)
        self.max_restart_attempts = int(self.max_restart_attempts)
        return self

    def validate(self) -> str | None:
        """Return an error message, or None when the config can be started."""
        self.normalized()
        if not self.name:
            return "Server name is required."
        if any(char in self.name for char in "\r\n\t"):
            return "Server name cannot contain line breaks."
        suffix = Path(self.bat_path).suffix.lower()
        if suffix not in {".bat", ".cmd"}:
            return "Choose a .bat or .cmd file."
        if '"' in self.bat_path or '"' in self.working_directory:
            return "Paths cannot contain double quotes."
        if not Path(self.bat_path).is_file():
            return f"BAT file does not exist: {self.bat_path}"
        if not Path(self.working_directory).is_dir():
            return f"Working directory does not exist: {self.working_directory}"
        if self.restart_delay_seconds < 1 or self.restart_delay_seconds > 3600:
            return "Restart delay must be between 1 and 3600 seconds."
        if not self.unlimited_restarts and self.max_restart_attempts < 1:
            return "Maximum restart attempts must be at least 1, or choose unlimited."
        if self.max_restart_attempts > 1000:
            return "Maximum restart attempts is too large."
        return None
