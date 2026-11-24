"""Client side of the local supervisor connection."""

from __future__ import annotations

import json
import socket
import subprocess
import threading
import time
from pathlib import Path
from queue import Empty, Queue
from typing import Callable

from mc_server_hub.core.supervisor import read_supervisor_info, supervisor_pid_alive
from mc_server_hub.utils.path_utils import supervisor_command


DETACHED_PROCESS = 0x00000008
CREATE_NEW_PROCESS_GROUP = 0x00000200
CREATE_NO_WINDOW = 0x08000000
CREATE_BREAKAWAY_FROM_JOB = 0x01000000


class SupervisorClient:
    """Speaks JSON lines to the supervisor. Callbacks run on the client thread."""

    def __init__(self) -> None:
        self.on_logs: Callable[[list], None] = lambda _entries: None
        self.on_runtime: Callable[[dict], None] = lambda _runtime: None
        self.on_snapshot: Callable[[dict], None] = lambda _payload: None
        self.on_ack: Callable[[dict], None] = lambda _payload: None
        self.on_connection: Callable[[bool, str], None] = lambda _ok, _message: None
        self._out: Queue[dict | None] = Queue()
        self._thread: threading.Thread | None = None
        self._running = False

    def start(self, app_root: Path) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._running = True
        self._thread = threading.Thread(target=self._run, args=(Path(app_root),), name="mc-hub-client", daemon=True)
        self._thread.start()

    def send(self, message: dict) -> None:
        self._out.put(message)

    def stop(self) -> None:
        self._running = False
        self._out.put(None)

    def _run(self, app_root: Path) -> None:
        while self._running:
            try:
                info = ensure_supervisor(app_root)
                self._session(info)
            except Exception as exc:
                if self._running:
                    self.on_connection(False, f"Supervisor unavailable: {exc}")
            else:
                self.on_connection(False, "Disconnected from the supervisor.")
            if self._running:
                time.sleep(1.0)

    def _session(self, info: dict) -> None:
        sock = socket.create_connection(("127.0.0.1", int(info["port"])), timeout=3)
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        sock.settimeout(0.2)
        try:
            self._write(sock, {"type": "hello", "token": info["token"]})
            buffer = b""
            announced = False
            while self._running:
                self._drain_outgoing(sock)
                try:
                    chunk = sock.recv(65536)
                except socket.timeout:
                    continue
                if not chunk:
                    break
                buffer += chunk
                if len(buffer) > 8_000_000:
                    raise ConnectionError("Supervisor sent too much data.")
                while b"\n" in buffer:
                    raw, buffer = buffer.split(b"\n", 1)
                    if not raw:
                        continue
                    message = json.loads(raw.decode("utf-8"))
                    if not announced and message.get("type") == "snapshot":
                        announced = True
                        self.on_connection(True, "Connected to the local supervisor.")
                    self._dispatch(message)
                    if message.get("type") == "bye":
                        self._running = False
                        return
        finally:
            try:
                sock.close()
            except OSError:
                pass

    def _drain_outgoing(self, sock: socket.socket) -> None:
        while True:
            try:
                message = self._out.get_nowait()
            except Empty:
                return
            if message is None:
                self._running = False
                return
            self._write(sock, message)

    def _dispatch(self, message: dict) -> None:
        kind = message.get("type")
        if kind == "logs":
            entries = message.get("entries", [])
            if isinstance(entries, list) and entries:
                self.on_logs(entries)
        elif kind == "runtime":
            runtime = message.get("runtime", {})
            if isinstance(runtime, dict):
                self.on_runtime(runtime)
        elif kind == "snapshot":
            self.on_snapshot(message)
        elif kind == "ack":
            self.on_ack(message)
        elif kind == "error":
            self.on_ack({"type": "ack", "action": "error", "ok": False, "message": message.get("message", "")})

    def _write(self, sock: socket.socket, message: dict) -> None:
        sock.sendall((json.dumps(message, ensure_ascii=False) + "\n").encode("utf-8"))


def ensure_supervisor(app_root: Path, timeout: float = 20.0) -> dict:
    """Connect to the existing supervisor, or start one detached process."""
    deadline = time.time() + timeout
    launched = False
    last_error = "Supervisor did not become ready."
    while time.time() < deadline:
        info = read_supervisor_info(app_root)
        if info and supervisor_pid_alive(info) and _port_open(int(info["port"])):
            return info
        if not launched:
            try:
                launch_supervisor(app_root)
                launched = True
            except OSError as exc:
                last_error = str(exc)
        time.sleep(0.15)
    raise TimeoutError(last_error)


def launch_supervisor(app_root: Path) -> None:
    command = supervisor_command(app_root)
    log_path = Path(app_root) / "logs" / "supervisor-process.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_handle = open(log_path, "a", encoding="utf-8", errors="replace")
    flags = DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW | CREATE_BREAKAWAY_FROM_JOB
    try:
        try:
            subprocess.Popen(
                command,
                cwd=str(app_root),
                creationflags=flags,
                stdin=subprocess.DEVNULL,
                stdout=log_handle,
                stderr=log_handle,
                close_fds=True,
            )
        except OSError:
            subprocess.Popen(
                command,
                cwd=str(app_root),
                creationflags=DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW,
                stdin=subprocess.DEVNULL,
                stdout=log_handle,
                stderr=log_handle,
                close_fds=True,
            )
    finally:
        log_handle.close()


def _port_open(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.3):
            return True
    except OSError:
        return False
