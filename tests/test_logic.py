"""Pure tests for crash policy, logs, config, and console line assembly."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from mc_server_hub.core.console_buffer import LineAssembler, contains_pause_prompt, strip_ansi
from mc_server_hub.core.crash_detector import decide_exit
from mc_server_hub.core.restart_scheduler import RestartScheduler
from mc_server_hub.models.server_runtime import ServerStatus
from mc_server_hub.utils.config_manager import ConfigManager
from mc_server_hub.utils.format_utils import format_bytes, format_duration, format_log_line


class CrashDecisionTests(unittest.TestCase):
    def test_user_stop_never_restarts(self) -> None:
        decision = decide_exit(
            user_stop=True,
            auto_restart=True,
            attempts=0,
            max_attempts=3,
            unlimited=False,
        )
        self.assertEqual(decision.status, ServerStatus.STOPPED)
        self.assertFalse(decision.should_restart)

    def test_disabled_auto_restart_stays_crashed(self) -> None:
        decision = decide_exit(
            user_stop=False,
            auto_restart=False,
            attempts=0,
            max_attempts=3,
            unlimited=False,
        )
        self.assertEqual(decision.status, ServerStatus.CRASHED)
        self.assertFalse(decision.should_restart)

    def test_restart_until_limit(self) -> None:
        allowed = decide_exit(
            user_stop=False,
            auto_restart=True,
            attempts=2,
            max_attempts=3,
            unlimited=False,
        )
        blocked = decide_exit(
            user_stop=False,
            auto_restart=True,
            attempts=3,
            max_attempts=3,
            unlimited=False,
        )
        self.assertTrue(allowed.should_restart)
        self.assertEqual(allowed.status, ServerStatus.RESTARTING)
        self.assertFalse(blocked.should_restart)
        self.assertEqual(blocked.status, ServerStatus.ERROR)

    def test_unlimited_keeps_restarting(self) -> None:
        decision = decide_exit(
            user_stop=False,
            auto_restart=True,
            attempts=50,
            max_attempts=1,
            unlimited=True,
        )
        self.assertTrue(decision.should_restart)


class ConsoleBufferTests(unittest.TestCase):
    def test_strips_conpty_controls_and_keeps_text(self) -> None:
        raw = "\x1b[1t\x1b[?9001h\x1b[?7hHELLO_WINPTY\r\n"
        lines = LineAssembler().feed(strip_ansi(raw))
        self.assertEqual(lines, ["HELLO_WINPTY"])

    def test_pause_prompt_without_newline_is_emitted(self) -> None:
        text = "Press any key to continue . . ."
        lines = LineAssembler().feed(text)
        self.assertTrue(lines)
        self.assertTrue(contains_pause_prompt(lines[0]))

    def test_log_format(self) -> None:
        self.assertEqual(
            format_log_line("2026-11-24 15:30:01", "SURVIVAL", "Done! For help, type \"help\""),
            "[2026-11-24 15:30:01] [SURVIVAL] Done! For help, type \"help\"",
        )


class FormatTests(unittest.TestCase):
    def test_bytes_and_duration(self) -> None:
        self.assertEqual(format_bytes(1536), "1.5 KB")
        self.assertEqual(format_duration(3661), "01:01:01")
        self.assertEqual(format_duration(90061), "1d 01:01:01")
        self.assertEqual(format_duration(None), "--:--:--")


class SchedulerTests(unittest.TestCase):
    def test_due_items_are_returned_once(self) -> None:
        scheduler = RestartScheduler()
        scheduler.schedule("alpha", 1)
        self.assertEqual(scheduler.pop_due(), [])
        self.assertIsNotNone(scheduler.deadline("alpha"))
        scheduler._due_monotonic["alpha"] = 0
        self.assertEqual(scheduler.pop_due(), ["alpha"])
        self.assertIsNone(scheduler.deadline("alpha"))
        scheduler.cancel("missing")


class ConfigTests(unittest.TestCase):
    def test_round_trip_and_corrupt_file(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manager = ConfigManager(root)
            from mc_server_hub.models.server_config import ServerConfig

            config = ServerConfig(
                id="abc",
                name="Survival",
                bat_path="C:/servers/start.bat",
                working_directory="C:/servers",
                auto_restart=True,
                restart_delay_seconds=5,
                max_restart_attempts=3,
            )
            manager.save_servers([config])
            loaded = manager.load_servers()
            self.assertEqual(loaded[0].name, "Survival")
            self.assertTrue((root / "config" / "servers.json").exists())

            path = root / "config" / "servers.json"
            path.write_text("{", encoding="utf-8")
            again = ConfigManager(root)
            recovered = again.load_servers()
            self.assertEqual(recovered, [])
            self.assertTrue(again.warnings)
            self.assertTrue((root / "config" / "servers.json.bad").exists())
            saved = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(saved["servers"], [])


if __name__ == "__main__":
    unittest.main()
