"""The window talks to a real local supervisor socket."""

from __future__ import annotations

import json
import socket
import tempfile
import threading
import time
import unittest
from pathlib import Path

from mc_server_hub.core.supervisor import Supervisor, read_supervisor_info


class SupervisorTests(unittest.TestCase):
    def test_add_server_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            work = root / "srv"
            work.mkdir()
            bat = work / "start.bat"
            bat.write_text("@echo off\r\necho HELLO\r\n", encoding="ascii")
            supervisor = Supervisor(root)
            thread = threading.Thread(target=supervisor.run, daemon=True)
            thread.start()
            try:
                info = self._wait_info(root)
                with socket.create_connection(("127.0.0.1", info["port"]), timeout=3) as sock:
                    sock.settimeout(3)
                    self._send(sock, {"type": "hello", "token": info["token"]})
                    hello = self._read_until(sock, "snapshot")
                    self.assertEqual(hello.get("configs"), [])
                    self._send(
                        sock,
                        {
                            "type": "add_server",
                            "config": {
                                "id": "",
                                "name": "Lobby",
                                "bat_path": str(bat),
                                "working_directory": str(work),
                                "auto_restart": False,
                                "restart_delay_seconds": 5,
                                "max_restart_attempts": 2,
                                "unlimited_restarts": False,
                                "auto_start": False,
                            },
                        },
                    )
                    snapshot = self._read_until(sock, "snapshot")
                    names = [item["name"] for item in snapshot.get("configs", [])]
                    self.assertEqual(names, ["Lobby"])
                    saved = json.loads((root / "config" / "servers.json").read_text(encoding="utf-8"))
                    self.assertEqual(saved["servers"][0]["name"], "Lobby")
                    self._send(sock, {"type": "shutdown", "stop_servers": True})
            finally:
                supervisor._running = False
                thread.join(10)
            self.assertFalse(thread.is_alive())

    def _wait_info(self, root: Path) -> dict:
        deadline = time.time() + 8
        while time.time() < deadline:
            info = read_supervisor_info(root)
            if info:
                return info
            time.sleep(0.05)
        self.fail("Supervisor did not write its port file.")

    def _send(self, sock: socket.socket, message: dict) -> None:
        sock.sendall((json.dumps(message) + "\n").encode("utf-8"))

    def _read_until(self, sock: socket.socket, kind: str) -> dict:
        buffer = b""
        deadline = time.time() + 8
        while time.time() < deadline:
            try:
                chunk = sock.recv(65536)
            except socket.timeout:
                continue
            if not chunk:
                break
            buffer += chunk
            while b"\n" in buffer:
                raw, buffer = buffer.split(b"\n", 1)
                if not raw:
                    continue
                message = json.loads(raw.decode("utf-8"))
                if message.get("type") == kind:
                    return message
        self.fail(f"Did not receive {kind}. Buffer: {buffer[:500]!r}")
