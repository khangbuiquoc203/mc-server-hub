"""Windows process tests: real BAT files, pause, commands, crash, and restart."""

from __future__ import annotations

import sys
import tempfile
import textwrap
import time
import unittest
from pathlib import Path

import psutil

from mc_server_hub.core.server_manager import ServerManager
from mc_server_hub.models.app_settings import AppSettings
from mc_server_hub.models.server_config import ServerConfig
from mc_server_hub.models.server_runtime import ServerStatus


def _wait(manager: ServerManager, predicate, timeout: float = 20.0):
    logs: list[dict] = []
    deadline = time.time() + timeout
    while time.time() < deadline:
        manager.tick()
        logs.extend(manager.drain_logs())
        if predicate():
            return logs
        time.sleep(0.05)
    manager.tick()
    logs.extend(manager.drain_logs())
    return logs


def _messages(logs: list[dict], server_id: str | None = None) -> str:
    lines = []
    for entry in logs:
        if server_id and entry.get("server_id") != server_id:
            continue
        lines.append(entry.get("line", ""))
    return "\n".join(lines)


class LifecycleTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temporary = tempfile.TemporaryDirectory()
        self.root = Path(self._temporary.name)
        self.work = self.root / "server files"
        self.work.mkdir()
        self.script = self.work / "fake_server.py"
        self.script.write_text(
            textwrap.dedent(
                """
                import sys
                print("READY", flush=True)
                for line in sys.stdin:
                    line = line.strip()
                    if not line:
                        continue
                    print(f"ECHO:{line}", flush=True)
                    if line == "stop":
                        break
                    if line == "crash":
                        raise SystemExit(3)
                print("BYE", flush=True)
                """
            ).strip()
            + "\n",
            encoding="utf-8",
        )
        self.manager = ServerManager(self.root)
        self.manager.update_settings(
            AppSettings(
                graceful_stop_timeout_seconds=8,
                startup_grace_seconds=8,
                stable_uptime_reset_seconds=3600,
                log_retention_days=0,
            )
        )

    def tearDown(self) -> None:
        self.manager.shutdown()
        self._temporary.cleanup()

    def _server(self, name: str, body: str, **overrides) -> str:
        bat = self.work / f"{name}.bat"
        normalized = body.replace("\r\n", "\n").replace("\n", "\r\n")
        bat.write_text(normalized, encoding="ascii")
        config = ServerConfig(
            id="",
            name=name,
            bat_path=str(bat),
            working_directory=str(self.work),
            auto_restart=overrides.pop("auto_restart", False),
            restart_delay_seconds=overrides.pop("restart_delay_seconds", 1),
            max_restart_attempts=overrides.pop("max_restart_attempts", 3),
            unlimited_restarts=overrides.pop("unlimited_restarts", False),
        )
        ok, message = self.manager.add_server(config)
        self.assertTrue(ok, message)
        return config.id

    def _python_bat(self, name: str, **overrides) -> str:
        body = f'@echo off\r\n"{sys.executable}" -u "{self.script}"\r\npause\r\n'
        return self._server(name, body, **overrides)

    def test_two_servers_keep_commands_and_logs_separate(self) -> None:
        alpha = self._python_bat("ALPHA")
        beta = self._python_bat("BETA")
        self.manager.start_server(alpha)
        self.manager.start_server(beta)
        logs = _wait(
            self.manager,
            lambda: self._running(alpha) and self._running(beta) and self._saw(alpha, "READY") and self._saw(beta, "READY"),
        )
        ok, message = self.manager.send_command(alpha, "token-alpha")
        self.assertTrue(ok, message)
        ok, message = self.manager.send_command(beta, "token-beta")
        self.assertTrue(ok, message)
        logs.extend(_wait(self.manager, lambda: self._saw(alpha, "ECHO:token-alpha") and self._saw(beta, "ECHO:token-beta")))
        alpha_text = _messages(logs, alpha)
        beta_text = _messages(logs, beta)
        self.assertIn("ECHO:token-alpha", alpha_text, alpha_text)
        self.assertNotIn("ECHO:token-alpha", beta_text, beta_text)
        self.assertIn("ECHO:token-beta", beta_text, beta_text)
        self.assertNotIn("ECHO:token-beta", alpha_text, alpha_text)
        self.assertIn("[ALPHA]", alpha_text)

    def test_user_stop_does_not_restart(self) -> None:
        server_id = self._python_bat("STOPME", auto_restart=True, restart_delay_seconds=1)
        self.manager.start_server(server_id)
        _wait(self.manager, lambda: self._running(server_id) and self._saw(server_id, "READY"))
        self.manager.stop_server(server_id)
        logs = _wait(self.manager, lambda: self.manager.runtimes[server_id].status == ServerStatus.STOPPED)
        self.assertEqual(self.manager.runtimes[server_id].status, ServerStatus.STOPPED, _messages(logs))
        time.sleep(2.2)
        self.manager.tick()
        self.assertEqual(self.manager.runtimes[server_id].status, ServerStatus.STOPPED)
        self.assertFalse(self.manager.processes.is_running(server_id))
        self.assertEqual(self.manager.runtimes[server_id].restart_attempts, 0)

    def test_pause_only_bat_is_released_and_marked_crashed(self) -> None:
        server_id = self._server("PAUSED", "@echo off\r\necho BEFORE_PAUSE\r\npause\r\necho AFTER_PAUSE\r\n", auto_restart=False)
        self.manager.start_server(server_id)
        logs = _wait(
            self.manager,
            lambda: self.manager.runtimes[server_id].status == ServerStatus.CRASHED
            and not self.manager.processes.is_running(server_id),
            timeout=15,
        )
        text = _messages(logs, server_id)
        self.assertIn("BEFORE_PAUSE", text, text)
        self.assertIn("Pause prompt detected", text, text)
        self.assertFalse(self.manager.processes.is_running(server_id))

    def test_killed_child_restarts_until_the_limit(self) -> None:
        server_id = self._python_bat("CRASH", auto_restart=True, restart_delay_seconds=1, max_restart_attempts=1)
        self.manager.start_server(server_id)
        logs = _wait(self.manager, lambda: self._running(server_id) and self._child_pid(server_id) is not None)
        self._kill(self._child_pid(server_id))
        logs.extend(
            _wait(
                self.manager,
                lambda: self.manager.runtimes[server_id].restart_attempts >= 1 and self._running(server_id),
            )
        )
        self._kill(self._child_pid(server_id))
        logs.extend(_wait(self.manager, lambda: self.manager.runtimes[server_id].status == ServerStatus.ERROR))
        runtime = self.manager.runtimes[server_id]
        self.assertEqual(runtime.status, ServerStatus.ERROR, _messages(logs))
        self.assertFalse(self.manager.processes.is_running(server_id))
        self.assertGreaterEqual(runtime.restart_attempts, 1)
        self.assertTrue((self.root / "logs" / "crash_history.json").exists())

    def test_job_close_kills_the_tree_when_assignment_works(self) -> None:
        server_id = self._server(
            "SLEEPER",
            "@echo off\r\nping -n 30 127.0.0.1 >nul\r\n",
            auto_restart=False,
        )
        self.manager.start_server(server_id)
        logs = _wait(self.manager, lambda: self.manager.processes.is_running(server_id), timeout=10)
        process = self.manager.processes.get(server_id)
        self.assertIsNotNone(process, _messages(logs))
        assert process is not None
        if not process.job_assigned or process.job is None:
            self.skipTest("This parent process did not allow a nested Windows job.")
        pid = process.pid
        process.job.close()
        process.job = None
        process.job_assigned = False
        deadline = time.time() + 8
        while time.time() < deadline and self._pid_alive(pid):
            time.sleep(0.1)
        self.assertFalse(self._pid_alive(pid), "Job handle close left the BAT process running.")

    def _running(self, server_id: str) -> bool:
        runtime = self.manager.runtimes[server_id]
        return runtime.status == ServerStatus.RUNNING and self.manager.processes.is_running(server_id)

    def _saw(self, server_id: str, text: str) -> bool:
        return any(text in record.message and record.server_id == server_id for record in self.manager.log_manager.history)

    def _child_pid(self, server_id: str) -> int | None:
        runtime = self.manager.runtimes[server_id]
        if runtime.tracked_pid and runtime.tracked_pid != runtime.root_pid:
            return runtime.tracked_pid
        return None

    def _kill(self, pid: int | None) -> None:
        self.assertIsNotNone(pid)
        assert pid is not None
        psutil.Process(pid).kill()

    def _pid_alive(self, pid: int) -> bool:
        return psutil.pid_exists(pid)
