"""Small display helpers for the server list."""

from __future__ import annotations


def format_bytes(num: int | float) -> str:
    value = float(num or 0)
    if value < 0:
        value = 0
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024.0 or unit == "TB":
            if unit == "B":
                return f"{int(value)} {unit}"
            return f"{value:.1f} {unit}"
        value /= 1024.0
    return f"{value:.1f} TB"


def format_duration(seconds: float | None) -> str:
    if seconds is None or seconds < 0:
        return "--:--:--"
    total = int(seconds)
    days, remainder = divmod(total, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, secs = divmod(remainder, 60)
    clock = f"{hours:02d}:{minutes:02d}:{secs:02d}"
    if days:
        return f"{days}d {clock}"
    return clock


def format_log_line(timestamp: str, server_name: str, message: str) -> str:
    return f"[{timestamp}] [{server_name}] {message}"
