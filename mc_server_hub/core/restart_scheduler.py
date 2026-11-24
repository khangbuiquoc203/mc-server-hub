"""Per-server restart deadlines. The caller ticks this; it does not sleep."""

from __future__ import annotations

import time


class RestartScheduler:
    def __init__(self) -> None:
        self._due_monotonic: dict[str, float] = {}
        self._due_wall: dict[str, float] = {}

    def schedule(self, server_id: str, delay_seconds: float) -> float:
        delay = max(1.0, float(delay_seconds))
        self._due_monotonic[server_id] = time.monotonic() + delay
        deadline = time.time() + delay
        self._due_wall[server_id] = deadline
        return deadline

    def cancel(self, server_id: str) -> None:
        self._due_monotonic.pop(server_id, None)
        self._due_wall.pop(server_id, None)

    def deadline(self, server_id: str) -> float | None:
        return self._due_wall.get(server_id)

    def pop_due(self) -> list[str]:
        now = time.monotonic()
        ready = [server_id for server_id, due in self._due_monotonic.items() if due <= now]
        for server_id in ready:
            self.cancel(server_id)
        return ready

    def pending_ids(self) -> list[str]:
        return list(self._due_monotonic)
