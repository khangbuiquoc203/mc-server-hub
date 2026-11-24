"""Background process owner.

The window is a client. This process owns the consoles, crash detection, and
restart schedule. Closing the window leaves this process — and the servers —
running. Closing this process closes the job handles and the server trees die
with it, so a server is never left without an owner after a real shutdown.
"""

from __future__ import annotations

import json
import msvcrt
import os
import socket
import time
import traceback
from pathlib import Path
from typing import Any

import psutil

from mc_server_hub.core.server_manager import ServerManager
from mc_server_hub.models.app_settings import AppSettings
from mc_server_hub.models.server_config import ServerConfig
from mc_server_hub.utils.path_utils import get_app_root


_TOKEN_MISMATCH = "Supervisor token was rejected."


class Supervisor:
    def __init__(self, app_root: Path) -> None:
        self.app_root = Path(app_root)
        self.data_dir = self.app_root / "data"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.info_path = self.data_dir / "supervisor.json"
        self.lock_path = self.data_dir / "supervisor.lock"
        self.log_path = self.app_root / "logs" / "supervisor.log"
        self.manager = ServerManager(self.app_root)
        self._lock_file = None
        self._server: socket.socket | None = None
        self._clients: list[_Client] = []
        self._token = os.urandom(16).hex()
        self._running = True

    def run(self) -> None:
        self._acquire_lock()
        try:
            self._listen()
            self._write_info()
            self._log("Supervisor listening.")
            for warning in self.manager.config_manager.warnings:
                self._log(warning)
            self.manager.start_auto_servers()
            while self._running:
                self._pump(0.05)
                self.manager.tick()
                self._publish()
            self._stop_servers_and_exit()
        finally:
            self._cleanup()

    def _pump(self, timeout: float) -> None:
        import select

        if self._server is None:
            return
        readable = [self._server]
        writable = []
        for client in self._clients:
            readable.append(client.sock)
            if client.outgoing:
                writable.append(client.sock)
        try:
            ready_read, ready_write, _ = select.select(readable, writable, [], timeout)
        except (OSError, ValueError):
            return
        if self._server in ready_read:
            self._accept()
        for client in list(self._clients):
            if client.sock in ready_read:
                self._read_client(client)
            if client.sock in ready_write:
                self._flush(client)
        self._drop_unauthed()

    def _accept(self) -> None:
        assert self._server is not None
        try:
            sock, _address = self._server.accept()
        except OSError:
            return
        sock.setblocking(False)
        try:
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        except OSError:
            pass
        self._clients.append(_Client(sock))

    def _read_client(self, client: "_Client") -> None:
        try:
            data = client.sock.recv(65536)
        except (BlockingIOError, TimeoutError):
            return
        except OSError:
            self._drop(client)
            return
        if not data:
            self._drop(client)
            return
        client.incoming.extend(data)
        if len(client.incoming) > 2_000_000:
            self._drop(client)
            return
        while b"\n" in client.incoming:
            raw_buffer = bytes(client.incoming)
            raw, _, rest = raw_buffer.partition(b"\n")
            client.incoming = bytearray(rest)
            self._handle_line(client, raw)

    def _handle_line(self, client: "_Client", raw: bytes) -> None:
        try:
            message = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._send(client, {"type": "error", "message": "Invalid message."})
            return
        if not isinstance(message, dict):
            return
        if not client.authed:
            if message.get("type") == "hello" and _same_token(message.get("token", ""), self._token):
                client.authed = True
                self._send(client, self.manager.snapshot(include_logs=True))
            else:
                self._send(client, {"type": "error", "message": _TOKEN_MISMATCH})
                self._drop(client)
            return
        try:
            self._dispatch(client, message)
        except Exception as exc:
            self._log(traceback.format_exc())
            self._send(client, {"type": "ack", "action": message.get("type", ""), "ok": False, "message": str(exc)})

    def _dispatch(self, client: "_Client", message: dict[str, Any]) -> None:
        kind = message.get("type")
        if kind == "hello":
            self._send(client, self.manager.snapshot(include_logs=True))
            return
        if kind == "add_server":
            ok, text = self.manager.add_server(ServerConfig.from_dict(message.get("config", {})))
            self._ack(client, kind, ok, text)
            self._broadcast(self.manager.snapshot(include_logs=False))
            return
        if kind == "update_server":
            ok, text = self.manager.update_server(ServerConfig.from_dict(message.get("config", {})))
            self._ack(client, kind, ok, text)
            self._broadcast(self.manager.snapshot(include_logs=False))
            return
        if kind == "remove_server":
            ok, text = self.manager.remove_server(str(message.get("id", "")))
            self._ack(client, kind, ok, text)
            self._broadcast(self.manager.snapshot(include_logs=False))
            return
        if kind == "start_server":
            ok, text = self.manager.start_server(str(message.get("id", "")), reset_attempts=True)
            self._ack(client, kind, ok, text)
            return
        if kind == "stop_server":
            ok, text = self.manager.stop_server(str(message.get("id", "")))
            self._ack(client, kind, ok, text)
            return
        if kind == "restart_server":
            ok, text = self.manager.restart_server(str(message.get("id", "")))
            self._ack(client, kind, ok, text)
            return
        if kind == "send_command":
            ok, text = self.manager.send_command(str(message.get("id", "")), str(message.get("command", "")))
            self._ack(client, kind, ok, text, server_id=str(message.get("id", "")))
            return
        if kind == "start_all":
            self.manager.start_all()
            self._ack(client, kind, True, "")
            return
        if kind == "stop_all":
            self.manager.stop_all()
            self._ack(client, kind, True, "")
            return
        if kind == "update_settings":
            self.manager.update_settings(AppSettings.from_dict(message.get("settings", {})))
            self._ack(client, kind, True, "")
            self._broadcast(self.manager.snapshot(include_logs=False))
            return
        if kind == "shutdown":
            if not message.get("stop_servers", True):
                self._ack(
                    client,
                    kind,
                    False,
                    "The supervisor stays running so the servers are not abandoned.",
                )
                return
            self._ack(client, kind, True, "Stopping servers and exiting.")
            self._running = False
            return
        self._send(client, {"type": "error", "message": f"Unknown command: {kind}"})

    def _publish(self) -> None:
        logs = self.manager.drain_logs()
        if logs:
            self._broadcast({"type": "logs", "entries": logs})
        for runtime in self.manager.drain_runtime_updates():
            self._broadcast({"type": "runtime", "runtime": runtime})

    def _stop_servers_and_exit(self) -> None:
        self.manager.stop_all()
        deadline = time.time() + self.manager.settings.graceful_stop_timeout_seconds + 5
        while time.time() < deadline:
            self.manager.tick()
            self._publish()
            self._pump(0.05)
            running = any(self.manager.processes.is_running(server_id) for server_id in self.manager.configs)
            pending = bool(self.manager.scheduler.pending_ids())
            if not running and not pending:
                break
        self.manager.shutdown()
        self._broadcast({"type": "bye"})
        self._pump(0.1)

    def _listen(self) -> None:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        sock.bind(("127.0.0.1", 0))
        sock.listen(8)
        sock.setblocking(False)
        self._server = sock

    def _write_info(self) -> None:
        assert self._server is not None
        payload = {
            "pid": os.getpid(),
            "port": int(self._server.getsockname()[1]),
            "token": self._token,
            "started_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        temporary = self.info_path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        temporary.replace(self.info_path)

    def _acquire_lock(self) -> None:
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        handle = open(self.lock_path, "a+b")
        try:
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError as exc:
            handle.close()
            raise RuntimeError("Another MC Server Hub supervisor is already running.") from exc
        self._lock_file = handle

    def _cleanup(self) -> None:
        for client in list(self._clients):
            self._drop(client)
        if self._server is not None:
            try:
                self._server.close()
            except OSError:
                pass
            self._server = None
        try:
            if self.info_path.exists():
                self.info_path.unlink()
        except OSError:
            pass
        if self._lock_file is not None:
            try:
                self._lock_file.seek(0)
                msvcrt.locking(self._lock_file.fileno(), msvcrt.LK_UNLCK, 1)
            except OSError:
                pass
            self._lock_file.close()
            self._lock_file = None
        self._log("Supervisor stopped.")

    def _ack(self, client: "_Client", action: str, ok: bool, message: str, server_id: str = "") -> None:
        self._send(client, {"type": "ack", "action": action, "ok": ok, "message": message, "server_id": server_id})

    def _broadcast(self, message: dict) -> None:
        for client in list(self._clients):
            if client.authed:
                self._send(client, message)

    def _send(self, client: "_Client", message: dict) -> None:
        try:
            blob = (json.dumps(message, ensure_ascii=False) + "\n").encode("utf-8")
        except (TypeError, ValueError):
            return
        client.outgoing.extend(blob)
        if len(client.outgoing) > 8_000_000:
            self._drop(client)
            return
        self._flush(client)

    def _flush(self, client: "_Client") -> None:
        while client.outgoing:
            try:
                sent = client.sock.send(client.outgoing)
            except (BlockingIOError, TimeoutError):
                return
            except OSError:
                self._drop(client)
                return
            if sent <= 0:
                self._drop(client)
                return
            del client.outgoing[:sent]

    def _drop(self, client: "_Client") -> None:
        if client in self._clients:
            self._clients.remove(client)
        try:
            client.sock.close()
        except OSError:
            pass

    def _drop_unauthed(self) -> None:
        now = time.monotonic()
        for client in list(self._clients):
            if not client.authed and now - client.connected_at > 5:
                self._drop(client)

    def _log(self, message: str) -> None:
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {message}\n"
        try:
            with self.log_path.open("a", encoding="utf-8", errors="replace") as handle:
                handle.write(line)
        except OSError:
            pass


class _Client:
    def __init__(self, sock: socket.socket) -> None:
        self.sock = sock
        self.incoming = bytearray()
        self.outgoing = bytearray()
        self.authed = False
        self.connected_at = time.monotonic()


def _same_token(left: object, right: str) -> bool:
    import hmac
    if not isinstance(left, str) or len(left) != len(right):
        return False
    return hmac.compare_digest(left, right)


def read_supervisor_info(app_root: Path) -> dict | None:
    path = Path(app_root) / "data" / "supervisor.json"
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    if not isinstance(payload.get("port"), int) or not isinstance(payload.get("token"), str):
        return None
    return payload


def supervisor_pid_alive(info: dict) -> bool:
    pid = info.get("pid")
    if not isinstance(pid, int):
        return False
    try:
        process = psutil.Process(pid)
        if not process.is_running():
            return False
        command = " ".join(process.cmdline()).lower()
    except (psutil.Error, OSError):
        return False
    return "--supervisor" in command


def run_supervisor() -> None:
    app_root = get_app_root()
    try:
        Supervisor(app_root).run()
    except Exception:
        log_path = app_root / "logs" / "supervisor.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8", errors="replace") as handle:
            handle.write(traceback.format_exc() + "\n")
        raise
