"""Live state of a managed server. This is not the saved configuration."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ServerStatus(str, Enum):
    RUNNING = "RUNNING"
    STOPPED = "STOPPED"
    STARTING = "STARTING"
    STOPPING = "STOPPING"
    CRASHED = "CRASHED"
    RESTARTING = "RESTARTING"
    ERROR = "ERROR"


@dataclass
class ServerRuntime:
    server_id: str
    status: ServerStatus = ServerStatus.STOPPED
    root_pid: int | None = None
    java_pid: int | None = None
    tracked_pid: int | None = None
    primary_name: str = ""
    started_at: float | None = None
    exit_code: int | None = None
    restart_attempts: int = 0
    restart_deadline: float | None = None
    stop_requested: bool = False
    restart_requested: bool = False
    last_error: str = ""
    cpu_percent: float = 0.0
    memory_bytes: int = 0
    pause_seen: bool = False
    pause_enter_sent: bool = False
    pause_sent_at: float | None = None
    stop_requested_at: float | None = None
    last_crash_at: str | None = None

    def to_dict(self) -> dict:
        return {
            "server_id": self.server_id,
            "status": self.status.value,
            "root_pid": self.root_pid,
            "java_pid": self.java_pid,
            "tracked_pid": self.tracked_pid,
            "primary_name": self.primary_name,
            "started_at": self.started_at,
            "exit_code": self.exit_code,
            "restart_attempts": self.restart_attempts,
            "restart_deadline": self.restart_deadline,
            "last_error": self.last_error,
            "cpu_percent": round(self.cpu_percent, 1),
            "memory_bytes": self.memory_bytes,
            "last_crash_at": self.last_crash_at,
        }
