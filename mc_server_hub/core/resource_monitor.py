"""CPU and RSS samples for one known PID.

psutil remembers the previous CPU timestamp on the process object, so the
same object has to be reused. A new object is created only when the PID changes.
"""

from __future__ import annotations

import psutil


class ResourceMonitor:
    def __init__(self) -> None:
        self._processes: dict[int, psutil.Process] = {}

    def sample(self, pid: int | None) -> tuple[float, int]:
        if not pid:
            return 0.0, 0
        process = self._processes.get(pid)
        if process is None:
            try:
                process = psutil.Process(pid)
                process.cpu_percent(interval=None)
            except (psutil.Error, OSError):
                self._processes.pop(pid, None)
                return 0.0, 0
            self._processes[pid] = process
            return 0.0, _memory_bytes(process)
        try:
            cpu = float(process.cpu_percent(interval=None))
            return cpu, _memory_bytes(process)
        except (psutil.Error, OSError):
            self._processes.pop(pid, None)
            return 0.0, 0

    def forget(self, pid: int | None) -> None:
        if pid:
            self._processes.pop(pid, None)


def _memory_bytes(process: psutil.Process) -> int:
    total = 0
    try:
        total += int(process.memory_info().rss)
    except (psutil.Error, OSError):
        return 0
    try:
        children = process.children(recursive=True)
    except (psutil.Error, OSError):
        return total
    for child in children:
        try:
            total += int(child.memory_info().rss)
        except (psutil.Error, OSError):
            continue
    return total
