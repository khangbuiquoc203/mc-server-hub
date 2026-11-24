"""Per-server log files, an in-memory ring, and crash records."""

from __future__ import annotations

import json
from collections import deque
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path

from mc_server_hub.models.server_config import ServerConfig
from mc_server_hub.utils.format_utils import format_log_line


@dataclass
class LogRecord:
    timestamp: str
    server_id: str
    server_name: str
    message: str
    stream: str
    line: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


class LogManager:
    def __init__(self, logs_root: Path, retention_days: int, history_limit: int = 1000) -> None:
        self.logs_root = Path(logs_root)
        self.retention_days = retention_days
        self.logs_root.mkdir(parents=True, exist_ok=True)
        self.history: deque[LogRecord] = deque(maxlen=history_limit)
        self._handles: dict[str, tuple[str, object]] = {}
        self._recent: dict[str, deque[str]] = {}

    def set_retention_days(self, days: int) -> None:
        self.retention_days = days

    def write(self, config: ServerConfig, message: str, stream: str = "stdout") -> LogRecord:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        text = message.replace("\r", " ").replace("\n", " ")
        record = LogRecord(
            timestamp=timestamp,
            server_id=config.id,
            server_name=config.name,
            message=text,
            stream=stream,
            line=format_log_line(timestamp, config.name, text),
        )
        self.history.append(record)
        recent = self._recent.setdefault(config.id, deque(maxlen=200))
        recent.append(record.line)
        self._append_file(config, record.line)
        return record

    def recent_lines(self, server_id: str) -> list[str]:
        return list(self._recent.get(server_id, ()))

    def record_crash(
        self,
        config: ServerConfig,
        *,
        exit_code: int | None,
        root_pid: int | None,
        java_pid: int | None,
        restart_scheduled: bool,
        message: str,
    ) -> None:
        moment = datetime.now()
        entry = {
            "timestamp": moment.strftime("%Y-%m-%d %H:%M:%S"),
            "server_id": config.id,
            "server_name": config.name,
            "exit_code": exit_code,
            "root_pid": root_pid,
            "java_pid": java_pid,
            "restart_scheduled": restart_scheduled,
            "message": message,
        }
        self._append_history(entry)
        folder = self.logs_root / (config.log_folder or config.name)
        folder.mkdir(parents=True, exist_ok=True)
        crash_path = folder / f"crash-{moment.strftime('%Y%m%d-%H%M%S')}.log"
        body = [
            f"timestamp: {entry['timestamp']}",
            f"server: {config.name}",
            f"exit_code: {exit_code}",
            f"root_pid: {root_pid}",
            f"java_pid: {java_pid}",
            f"restart_scheduled: {restart_scheduled}",
            f"message: {message}",
            "",
            "----- recent log -----",
            *self.recent_lines(config.id),
            "",
        ]
        crash_path.write_text("\n".join(body), encoding="utf-8")

    def backlog(self, limit: int = 400) -> list[dict[str, str]]:
        records = list(self.history)[-limit:]
        return [record.to_dict() for record in records]

    def apply_retention(self) -> None:
        if self.retention_days <= 0 or not self.logs_root.exists():
            return
        cutoff = datetime.now() - timedelta(days=self.retention_days)
        for path in self.logs_root.rglob("*.log"):
            try:
                modified = datetime.fromtimestamp(path.stat().st_mtime)
            except OSError:
                continue
            if modified < cutoff:
                try:
                    path.unlink()
                except OSError:
                    pass

    def release(self, server_id: str) -> None:
        current = self._handles.pop(server_id, None)
        if current is not None:
            try:
                current[1].close()
            except Exception:
                pass

    def close(self) -> None:
        for _day, handle in list(self._handles.values()):
            try:
                handle.close()
            except Exception:
                pass
        self._handles.clear()

    def _append_file(self, config: ServerConfig, line: str) -> None:
        folder_name = config.log_folder or "server"
        day = datetime.now().strftime("%Y-%m-%d")
        current = self._handles.get(config.id)
        if current is None or current[0] != day:
            if current is not None:
                try:
                    current[1].close()
                except Exception:
                    pass
            folder = self.logs_root / folder_name
            folder.mkdir(parents=True, exist_ok=True)
            handle = (folder / f"{day}.log").open("a", encoding="utf-8", errors="replace")
            self._handles[config.id] = (day, handle)
        else:
            handle = current[1]
        handle.write(line + "\n")
        handle.flush()

    def _append_history(self, entry: dict) -> None:
        path = self.logs_root / "crash_history.json"
        items: list = []
        if path.exists():
            try:
                loaded = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(loaded, list):
                    items = loaded
            except (OSError, json.JSONDecodeError):
                items = []
        items.append(entry)
        items = items[-500:]
        temporary = path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(items, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        temporary.replace(path)
