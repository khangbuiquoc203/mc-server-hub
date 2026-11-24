"""Own server configs, process lifetime, crash decisions, and restarts."""

from __future__ import annotations

import time
import uuid
from pathlib import Path

from mc_server_hub.core.console_buffer import contains_pause_prompt
from mc_server_hub.core.crash_detector import decide_exit
from mc_server_hub.core.log_manager import LogManager
from mc_server_hub.core.process_manager import ProcessManager, ProcessStartError
from mc_server_hub.core.process_tree import inspect_process_tree, pid_alive
from mc_server_hub.core.resource_monitor import ResourceMonitor
from mc_server_hub.core.restart_scheduler import RestartScheduler
from mc_server_hub.models.app_settings import AppSettings
from mc_server_hub.models.server_config import SERVER_COLORS, ServerConfig
from mc_server_hub.models.server_runtime import ServerRuntime, ServerStatus
from mc_server_hub.utils.config_manager import ConfigManager
from mc_server_hub.utils.path_utils import unique_log_folder


_INTENTIONAL_STOPS = {"stop", "end"}


class ServerManager:
    def __init__(self, app_root: Path) -> None:
        self.app_root = Path(app_root)
        self.config_manager = ConfigManager(self.app_root)
        self.settings = self.config_manager.load_settings()
        self.log_manager = LogManager(self.app_root / "logs", self.settings.log_retention_days)
        self.log_manager.apply_retention()
        self.processes = ProcessManager()
        self.scheduler = RestartScheduler()
        self.resources = ResourceMonitor()
        self.configs: dict[str, ServerConfig] = {}
        self.runtimes: dict[str, ServerRuntime] = {}
        self._logs: list[dict] = []
        self._dirty: set[str] = set()
        self._signatures: dict[str, tuple] = {}
        self._last_resource_sample = 0.0
        self.load()

    def load(self) -> None:
        self.configs.clear()
        self.runtimes.clear()
        for config in self.config_manager.load_servers():
            config.normalized()
            self._ensure_log_folder(config)
            self.configs[config.id] = config
            self.runtimes[config.id] = ServerRuntime(server_id=config.id)
            self._dirty.add(config.id)

    def start_auto_servers(self) -> None:
        for server_id, config in list(self.configs.items()):
            if config.auto_start:
                self.start_server(server_id, reset_attempts=False)

    def tick(self) -> None:
        for server_id in list(self.configs):
            try:
                self._tick_server(server_id)
            except Exception as exc:
                config = self.configs.get(server_id)
                runtime = self.runtimes.get(server_id)
                if config is not None and runtime is not None:
                    runtime.last_error = str(exc)
                    self._emit(config, f"Monitor error: {exc}", "system")
                    self._mark(server_id)
        self._fire_restarts()
        self._sample_resources()

    def add_server(self, config: ServerConfig) -> tuple[bool, str]:
        config.normalized()
        if not config.id:
            config.id = uuid.uuid4().hex
        if config.id in self.configs:
            return False, "That server id already exists."
        if not config.color:
            config.color = SERVER_COLORS[len(self.configs) % len(SERVER_COLORS)]
        self._ensure_log_folder(config)
        error = config.validate()
        if error:
            return False, error
        self.configs[config.id] = config
        self.runtimes[config.id] = ServerRuntime(server_id=config.id)
        self._save_servers()
        self._mark(config.id)
        return True, ""

    def update_server(self, config: ServerConfig) -> tuple[bool, str]:
        current = self.configs.get(config.id)
        if current is None:
            return False, "Server was not found."
        config.normalized()
        config.log_folder = current.log_folder
        if not config.color:
            config.color = current.color
        error = config.validate()
        if error:
            return False, error
        self.configs[config.id] = config
        self._save_servers()
        self._mark(config.id)
        return True, ""

    def remove_server(self, server_id: str) -> tuple[bool, str]:
        config = self.configs.get(server_id)
        if config is None:
            return False, "Server was not found."
        runtime = self.runtimes[server_id]
        runtime.stop_requested = True
        runtime.restart_requested = False
        self.scheduler.cancel(server_id)
        self.processes.discard(server_id)
        self.resources.forget(runtime.tracked_pid)
        self.resources.forget(runtime.java_pid)
        self.resources.forget(runtime.root_pid)
        self.log_manager.release(server_id)
        self.configs.pop(server_id, None)
        self.runtimes.pop(server_id, None)
        self._signatures.pop(server_id, None)
        self._dirty.discard(server_id)
        self._save_servers()
        return True, ""

    def start_server(self, server_id: str, *, reset_attempts: bool = True) -> tuple[bool, str]:
        config = self.configs.get(server_id)
        runtime = self.runtimes.get(server_id)
        if config is None or runtime is None:
            return False, "Server was not found."
        if self.processes.is_running(server_id):
            return False, "Server is already running."
        self.scheduler.cancel(server_id)
        runtime.restart_deadline = None
        error = config.validate()
        if error:
            runtime.status = ServerStatus.ERROR
            runtime.last_error = error
            self._emit(config, f"Failed to start: {error}", "system")
            self._mark(server_id)
            return False, error
        try:
            process = self.processes.start(server_id, config.bat_path, config.working_directory)
        except ProcessStartError as exc:
            runtime.status = ServerStatus.ERROR
            runtime.last_error = str(exc)
            self._emit(config, f"Failed to start: {exc}", "system")
            self._mark(server_id)
            return False, str(exc)
        if reset_attempts:
            runtime.restart_attempts = 0
        runtime.status = ServerStatus.STARTING
        runtime.root_pid = process.pid
        runtime.java_pid = None
        runtime.tracked_pid = None
        runtime.primary_name = ""
        runtime.started_at = time.time()
        runtime.exit_code = None
        runtime.stop_requested = False
        runtime.restart_requested = False
        runtime.pause_seen = False
        runtime.pause_enter_sent = False
        runtime.pause_sent_at = None
        runtime.stop_requested_at = None
        runtime.last_error = ""
        runtime.cpu_percent = 0.0
        runtime.memory_bytes = 0
        self._emit(config, f"Starting {config.bat_path}", "system")
        self._emit(config, f"Process started (PID {process.pid}).", "system")
        if not process.job_assigned:
            self._emit(
                config,
                "Process could not be placed in a Windows job. Shutdown will kill the process tree directly.",
                "system",
            )
        self._mark(server_id)
        return True, ""

    def stop_server(self, server_id: str) -> tuple[bool, str]:
        config = self.configs.get(server_id)
        runtime = self.runtimes.get(server_id)
        if config is None or runtime is None:
            return False, "Server was not found."
        self.scheduler.cancel(server_id)
        runtime.restart_deadline = None
        runtime.restart_requested = False
        if not self.processes.is_running(server_id):
            runtime.stop_requested = False
            runtime.status = ServerStatus.STOPPED
            runtime.last_error = ""
            self._mark(server_id)
            return True, "Server is not running."
        runtime.stop_requested = True
        runtime.status = ServerStatus.STOPPING
        runtime.stop_requested_at = time.monotonic()
        self._emit(config, "Stop requested by user.", "system")
        self._write_stdin(config, "stop")
        self._mark(server_id)
        return True, ""

    def restart_server(self, server_id: str) -> tuple[bool, str]:
        config = self.configs.get(server_id)
        runtime = self.runtimes.get(server_id)
        if config is None or runtime is None:
            return False, "Server was not found."
        runtime.restart_attempts = 0
        if not self.processes.is_running(server_id):
            return self.start_server(server_id, reset_attempts=True)
        self.scheduler.cancel(server_id)
        runtime.restart_deadline = None
        runtime.restart_requested = True
        runtime.stop_requested = False
        runtime.status = ServerStatus.STOPPING
        runtime.stop_requested_at = time.monotonic()
        self._emit(config, "Restart requested by user.", "system")
        self._write_stdin(config, "stop")
        self._mark(server_id)
        return True, ""

    def send_command(self, server_id: str, command: str) -> tuple[bool, str]:
        config = self.configs.get(server_id)
        runtime = self.runtimes.get(server_id)
        if config is None or runtime is None:
            return False, "Server was not found."
        text = command.strip()
        if not text:
            return False, "Command is empty."
        if len(text) > 2000:
            return False, "Command is too long."
        if text.lower() in _INTENTIONAL_STOPS:
            return self.stop_server(server_id)
        if not self.processes.is_running(server_id):
            return False, "Server is not running. Start it before sending a command."
        if runtime.status not in {ServerStatus.RUNNING, ServerStatus.STARTING, ServerStatus.STOPPING}:
            return False, f"Server is {runtime.status.value} and cannot take a command."
        ok, message = self._write_stdin(config, text)
        return ok, message

    def start_all(self) -> None:
        for server_id in list(self.configs):
            runtime = self.runtimes[server_id]
            if runtime.status in {ServerStatus.STOPPED, ServerStatus.CRASHED, ServerStatus.ERROR}:
                self.start_server(server_id, reset_attempts=True)

    def stop_all(self) -> None:
        for server_id in list(self.configs):
            if self.processes.is_running(server_id) or self.scheduler.deadline(server_id):
                self.stop_server(server_id)

    def update_settings(self, settings: AppSettings) -> None:
        settings.normalized()
        self.settings = settings
        self.config_manager.save_settings(settings)
        self.log_manager.set_retention_days(settings.log_retention_days)
        self.log_manager.apply_retention()

    def shutdown(self) -> None:
        for runtime in self.runtimes.values():
            runtime.stop_requested = True
            runtime.restart_requested = False
        self.scheduler = RestartScheduler()
        self.processes.shutdown_all()
        for runtime in self.runtimes.values():
            runtime.status = ServerStatus.STOPPED
            runtime.root_pid = None
            runtime.java_pid = None
            runtime.tracked_pid = None
            runtime.restart_deadline = None
        self.log_manager.close()

    def drain_logs(self) -> list[dict]:
        logs = self._logs
        self._logs = []
        return logs

    def drain_runtime_updates(self) -> list[dict]:
        updates: list[dict] = []
        for server_id in list(self._dirty):
            runtime = self.runtimes.get(server_id)
            self._dirty.discard(server_id)
            if runtime is None:
                continue
            signature = _signature(runtime)
            if self._signatures.get(server_id) == signature:
                continue
            self._signatures[server_id] = signature
            updates.append(runtime.to_dict())
        return updates

    def snapshot(self, *, include_logs: bool) -> dict:
        return {
            "type": "snapshot",
            "configs": [config.to_dict() for config in self.configs.values()],
            "runtimes": [runtime.to_dict() for runtime in self.runtimes.values()],
            "settings": self.settings.to_dict(),
            "logs": self.log_manager.backlog() if include_logs else None,
            "warnings": list(self.config_manager.warnings),
        }

    def _tick_server(self, server_id: str) -> None:
        config = self.configs[server_id]
        runtime = self.runtimes[server_id]
        deadline = self.scheduler.deadline(server_id)
        if runtime.restart_deadline != deadline:
            runtime.restart_deadline = deadline
            self._mark(server_id)
        process = self.processes.get(server_id)
        if process is None:
            if runtime.status in {ServerStatus.STARTING, ServerStatus.RUNNING, ServerStatus.STOPPING}:
                runtime.status = ServerStatus.CRASHED if not runtime.stop_requested else ServerStatus.STOPPED
                runtime.last_error = "Process handle disappeared."
                self._emit(config, "Process handle disappeared.", "system")
                self._mark(server_id)
            return

        for line in process.poll_output():
            if contains_pause_prompt(line):
                runtime.pause_seen = True
            self._emit(config, line, "stdout")
        process.capture_new_children()

        if not process.is_running():
            for line in process.poll_output():
                self._emit(config, line, "stdout")
            self._finalize(config, runtime, process)
            return

        if runtime.stop_requested or runtime.restart_requested or runtime.status == ServerStatus.STOPPING:
            self._tick_stopping(config, runtime, process)
            return
        if runtime.status in {ServerStatus.STARTING, ServerStatus.RUNNING}:
            self._tick_running(config, runtime, process)

    def _tick_running(self, config: ServerConfig, runtime: ServerRuntime, process) -> None:
        tree = inspect_process_tree(process.pid)
        now = time.monotonic()
        if runtime.tracked_pid and not pid_alive(runtime.tracked_pid):
            self._release_pause(config, runtime, process, primary_gone=True)
            if not process.is_running():
                self._finalize(config, runtime, process)
                return
            if runtime.pause_enter_sent and runtime.pause_sent_at and now - runtime.pause_sent_at > 3:
                self._emit(config, "BAT process stayed open after the server exited. Terminating it.", "system")
                process.terminate()
                self._finalize(config, runtime, process)
            return

        if tree.primary_pid and runtime.tracked_pid is None:
            runtime.tracked_pid = tree.primary_pid
            runtime.primary_name = tree.primary_name
            runtime.java_pid = tree.primary_pid if tree.is_java else None
            runtime.status = ServerStatus.RUNNING
            kind = "Java" if tree.is_java else tree.primary_name
            self._emit(config, f"Server process detected ({kind} PID {tree.primary_pid}).", "system")
            self._mark(config.id)
            return

        if runtime.tracked_pid and pid_alive(runtime.tracked_pid):
            if runtime.status != ServerStatus.RUNNING:
                runtime.status = ServerStatus.RUNNING
                self._mark(config.id)
            self._maybe_clear_attempts(config, runtime)
            return

        if runtime.pause_seen:
            self._release_pause(config, runtime, process, primary_gone=False)
            if runtime.pause_enter_sent and runtime.pause_sent_at and now - runtime.pause_sent_at > 3:
                if process.is_running():
                    process.terminate()
                    self._finalize(config, runtime, process)
            return

        started = runtime.started_at or time.time()
        if time.time() - started < self.settings.startup_grace_seconds:
            if runtime.status != ServerStatus.STARTING:
                runtime.status = ServerStatus.STARTING
                self._mark(config.id)
            return

        runtime.tracked_pid = process.pid
        runtime.primary_name = "cmd.exe"
        runtime.status = ServerStatus.RUNNING
        self._emit(config, "No child server process appeared. Monitoring the BAT process itself.", "system")
        self._mark(config.id)

    def _tick_stopping(self, config: ServerConfig, runtime: ServerRuntime, process) -> None:
        now = time.monotonic()
        requested_at = runtime.stop_requested_at or now
        primary_alive = bool(runtime.tracked_pid and pid_alive(runtime.tracked_pid) and runtime.tracked_pid != process.pid)
        if primary_alive:
            if now - requested_at > self.settings.graceful_stop_timeout_seconds:
                self._emit(config, "Graceful stop timed out. Terminating the process tree.", "system")
                process.terminate()
                self._finalize(config, runtime, process)
            return
        self._release_pause(config, runtime, process, primary_gone=True)
        if not process.is_running():
            self._finalize(config, runtime, process)
            return
        if runtime.pause_enter_sent and runtime.pause_sent_at and now - runtime.pause_sent_at > 3:
            process.terminate()
            self._finalize(config, runtime, process)
            return
        if now - requested_at > self.settings.graceful_stop_timeout_seconds:
            self._emit(config, "Stop timed out. Terminating the process tree.", "system")
            process.terminate()
            self._finalize(config, runtime, process)

    def _finalize(self, config: ServerConfig, runtime: ServerRuntime, process) -> None:
        exit_code = process.exit_code()
        root_pid = runtime.root_pid
        java_pid = runtime.java_pid
        user_stop = runtime.stop_requested
        manual_restart = runtime.restart_requested and not runtime.stop_requested
        self.resources.forget(runtime.tracked_pid)
        self.resources.forget(runtime.java_pid)
        self.resources.forget(runtime.root_pid)
        self.processes.discard(config.id)

        runtime.root_pid = None
        runtime.java_pid = None
        runtime.tracked_pid = None
        runtime.primary_name = ""
        runtime.exit_code = exit_code
        runtime.cpu_percent = 0.0
        runtime.memory_bytes = 0
        runtime.pause_seen = False
        runtime.pause_enter_sent = False
        runtime.pause_sent_at = None
        runtime.started_at = None
        code_text = "unknown" if exit_code is None else str(exit_code)
        self._emit(config, f"Process exited with code {code_text}.", "system")

        if manual_restart:
            runtime.restart_requested = False
            runtime.stop_requested = False
            self._emit(config, "Starting again after the requested restart.", "system")
            self._mark(config.id)
            self.start_server(config.id, reset_attempts=True)
            return

        decision = decide_exit(
            user_stop=user_stop,
            auto_restart=config.auto_restart,
            attempts=runtime.restart_attempts,
            max_attempts=config.max_restart_attempts,
            unlimited=config.unlimited_restarts,
        )
        runtime.stop_requested = False
        runtime.restart_requested = False
        runtime.status = decision.status
        runtime.last_error = "" if decision.status == ServerStatus.STOPPED else decision.reason
        if decision.status != ServerStatus.STOPPED:
            runtime.last_crash_at = time.strftime("%Y-%m-%d %H:%M:%S")
            self.log_manager.record_crash(
                config,
                exit_code=exit_code,
                root_pid=root_pid,
                java_pid=java_pid,
                restart_scheduled=decision.should_restart,
                message=decision.reason,
            )
        if decision.should_restart:
            runtime.restart_attempts += 1
            runtime.restart_deadline = self.scheduler.schedule(config.id, config.restart_delay_seconds)
            limit = "unlimited" if config.unlimited_restarts else str(config.max_restart_attempts)
            self._emit(
                config,
                f"Crash detected. Restart {runtime.restart_attempts}/{limit} in {config.restart_delay_seconds}s.",
                "system",
            )
        else:
            self.scheduler.cancel(config.id)
            runtime.restart_deadline = None
            self._emit(config, decision.reason, "system")
        self._mark(config.id)

    def _release_pause(self, config: ServerConfig, runtime: ServerRuntime, process, *, primary_gone: bool) -> None:
        if runtime.pause_enter_sent or not process.is_running():
            return
        if not runtime.pause_seen and not primary_gone:
            return
        try:
            process.write("\r\n")
        except ProcessStartError as exc:
            self._emit(config, f"Could not send Enter to the pause prompt: {exc}", "system")
            return
        runtime.pause_enter_sent = True
        runtime.pause_sent_at = time.monotonic()
        if runtime.pause_seen:
            self._emit(config, "Pause prompt detected. Sending Enter so the BAT process can exit.", "system")
        else:
            self._emit(
                config,
                "Server process ended while the BAT is still open. Sending Enter to release pause.",
                "system",
            )

    def _maybe_clear_attempts(self, config: ServerConfig, runtime: ServerRuntime) -> None:
        if runtime.restart_attempts <= 0 or not runtime.started_at:
            return
        if time.time() - runtime.started_at < self.settings.stable_uptime_reset_seconds:
            return
        runtime.restart_attempts = 0
        self._emit(
            config,
            "Server stayed up. The automatic restart counter was reset.",
            "system",
        )
        self._mark(config.id)

    def _fire_restarts(self) -> None:
        for server_id in self.scheduler.pop_due():
            config = self.configs.get(server_id)
            runtime = self.runtimes.get(server_id)
            if config is None or runtime is None or runtime.stop_requested:
                continue
            if self.processes.is_running(server_id):
                continue
            self._emit(config, "Auto restart is starting the server.", "system")
            self.start_server(server_id, reset_attempts=False)

    def _sample_resources(self) -> None:
        now = time.monotonic()
        if now - self._last_resource_sample < 2.0:
            return
        self._last_resource_sample = now
        for server_id, runtime in self.runtimes.items():
            if runtime.status not in {ServerStatus.RUNNING, ServerStatus.STARTING, ServerStatus.STOPPING}:
                if runtime.cpu_percent or runtime.memory_bytes:
                    runtime.cpu_percent = 0.0
                    runtime.memory_bytes = 0
                    self._mark(server_id)
                continue
            pid = _sample_pid(runtime)
            cpu, memory = self.resources.sample(pid)
            runtime.cpu_percent = cpu
            runtime.memory_bytes = memory
            self._mark(server_id)

    def _write_stdin(self, config: ServerConfig, command: str) -> tuple[bool, str]:
        process = self.processes.get(config.id)
        if process is None or not process.is_running():
            return False, "Server process is not running, so the command was not sent."
        try:
            process.write(command + "\r\n")
        except ProcessStartError as exc:
            self._emit(config, str(exc), "system")
            return False, str(exc)
        self._emit(config, f"> {command}", "system")
        return True, ""

    def _emit(self, config: ServerConfig, message: str, stream: str) -> None:
        text = str(message).strip()
        if not text:
            return
        record = self.log_manager.write(config, text, stream)
        self._logs.append(record.to_dict())

    def _mark(self, server_id: str) -> None:
        self._dirty.add(server_id)

    def _save_servers(self) -> None:
        self.config_manager.save_servers(list(self.configs.values()))

    def _ensure_log_folder(self, config: ServerConfig) -> None:
        if config.log_folder:
            return
        used = {item.log_folder for item in self.configs.values() if item.id != config.id}
        config.log_folder = unique_log_folder(config.name, config.id, used)


def _sample_pid(runtime: ServerRuntime) -> int | None:
    if runtime.java_pid and pid_alive(runtime.java_pid):
        return runtime.java_pid
    if runtime.tracked_pid and pid_alive(runtime.tracked_pid):
        return runtime.tracked_pid
    if runtime.root_pid and pid_alive(runtime.root_pid):
        return runtime.root_pid
    return None


def _signature(runtime: ServerRuntime) -> tuple:
    return (
        runtime.status.value,
        runtime.root_pid,
        runtime.java_pid,
        runtime.tracked_pid,
        runtime.primary_name,
        runtime.started_at,
        runtime.exit_code,
        runtime.restart_attempts,
        runtime.restart_deadline,
        runtime.last_error,
        runtime.last_crash_at,
        int(runtime.cpu_percent),
        runtime.memory_bytes // (1024 * 1024),
    )
