"""Start BAT files on a real Windows console and own their process tree.

pywinpty hosts the BAT in a ConPTY, so Java log lines stay unbuffered and
``pause`` can be released with Enter. The cmd process is placed in a Job
Object with JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE. Children created after that
join the job. Descendants that already exist are assigned explicitly.
"""

from __future__ import annotations

import codecs
import os
import socket
from dataclasses import dataclass

from winpty import PtyProcess

from mc_server_hub.core.console_buffer import LineAssembler, strip_ansi
from mc_server_hub.core.process_tree import descendant_pids, kill_process_tree
from mc_server_hub.core.win_job import WinJob, try_assign_pid


class ProcessStartError(RuntimeError):
    """The BAT file could not be launched."""


@dataclass
class ManagedProcess:
    server_id: str
    pty: PtyProcess
    pid: int
    job: WinJob | None
    job_assigned: bool
    assigned_pids: set[int]
    assembler: LineAssembler
    decoder: codecs.IncrementalDecoder
    eof: bool = False

    def poll_output(self) -> list[str]:
        raw = self._read_available()
        if not raw and not self.eof:
            return []
        text = self.decoder.decode(raw, final=self.eof)
        text = strip_ansi(text)
        lines = self.assembler.feed(text)
        if self.eof:
            lines.extend(self.assembler.flush())
        return [line for line in lines if line != ""]

    def write(self, text: str) -> None:
        if not self.is_running():
            raise ProcessStartError("Server process is not running.")
        try:
            self.pty.write(text)
        except Exception as exc:
            raise ProcessStartError(f"Could not write to the server console: {exc}") from exc

    def is_running(self) -> bool:
        try:
            return bool(self.pty.isalive())
        except Exception:
            return False

    def exit_code(self) -> int | None:
        if self.is_running():
            return None
        try:
            code = self.pty.exitstatus
        except Exception:
            return None
        if code is None:
            return None
        return int(code)

    def capture_new_children(self) -> None:
        if self.job is None:
            return
        if not self.job_assigned:
            if try_assign_pid(self.job, self.pid):
                self.job_assigned = True
                self.assigned_pids.add(self.pid)
        if not self.job_assigned:
            return
        for pid in descendant_pids(self.pid):
            if pid in self.assigned_pids:
                continue
            if try_assign_pid(self.job, pid):
                self.assigned_pids.add(pid)

    def terminate(self) -> None:
        if self.job is not None and self.job_assigned:
            self.job.terminate(1)
        if self.is_running():
            kill_process_tree(self.pid)

    def close(self) -> None:
        """Drop console handles. Closing the job kills anything still inside it."""
        try:
            self.pty.fileobj.close()
        except Exception:
            pass
        try:
            self.pty._server.close()
        except Exception:
            pass
        try:
            self.pty.closed = True
        except Exception:
            pass
        if self.job is not None:
            self.job.close()
            self.job = None

    def _read_available(self) -> bytes:
        chunks: list[bytes] = []
        while True:
            try:
                data = self.pty.fileobj.recv(65536)
            except (BlockingIOError, TimeoutError, socket.timeout):
                break
            except OSError as exc:
                winerror = getattr(exc, "winerror", None)
                if winerror in {10035, 10054, 10053} or exc.errno in {11, 10035}:
                    if winerror in {10054, 10053}:
                        self.eof = True
                    break
                self.eof = True
                break
            if data == b"0011Ignore":
                continue
            if not data:
                self.eof = True
                break
            chunks.append(data)
        return b"".join(chunks)


class ProcessManager:
    def __init__(self) -> None:
        self._processes: dict[str, ManagedProcess] = {}

    def start(self, server_id: str, bat_path: str, working_directory: str) -> ManagedProcess:
        if server_id in self._processes and self._processes[server_id].is_running():
            raise ProcessStartError("Server process is already running.")
        self.discard(server_id)
        if not os.path.isfile(bat_path):
            raise ProcessStartError(f"BAT file does not exist: {bat_path}")
        if not os.path.isdir(working_directory):
            raise ProcessStartError(f"Working directory does not exist: {working_directory}")
        if '"' in bat_path:
            raise ProcessStartError("BAT path cannot contain double quotes.")

        system_root = os.environ.get("SystemRoot", r"C:\Windows")
        cmd = os.path.join(system_root, "System32", "cmd.exe")
        try:
            pty = PtyProcess.spawn(
                [cmd, "/q", "/c", "call", bat_path],
                cwd=working_directory,
                dimensions=(32, 160),
            )
        except Exception as exc:
            raise ProcessStartError(f"Failed to start {bat_path}: {exc}") from exc

        if not getattr(pty, "pid", None):
            self._destroy_pty(pty)
            raise ProcessStartError("Console process did not return a PID.")
        try:
            pty.fileobj.setblocking(False)
        except Exception as exc:
            self._destroy_pty(pty)
            raise ProcessStartError(f"Failed to watch the console stream: {exc}") from exc

        job: WinJob | None
        try:
            job = WinJob()
        except OSError:
            job = None
        managed = ManagedProcess(
            server_id=server_id,
            pty=pty,
            pid=int(pty.pid),
            job=job,
            job_assigned=False,
            assigned_pids=set(),
            assembler=LineAssembler(),
            decoder=codecs.getincrementaldecoder("utf-8")("replace"),
        )
        managed.capture_new_children()
        self._processes[server_id] = managed
        return managed

    def get(self, server_id: str) -> ManagedProcess | None:
        return self._processes.get(server_id)

    def is_running(self, server_id: str) -> bool:
        process = self._processes.get(server_id)
        return bool(process and process.is_running())

    def discard(self, server_id: str) -> None:
        process = self._processes.pop(server_id, None)
        if process is not None:
            if process.is_running():
                process.terminate()
            process.close()

    def shutdown_all(self) -> None:
        for server_id in list(self._processes):
            self.discard(server_id)

    def _destroy_pty(self, pty: PtyProcess) -> None:
        try:
            if pty.isalive():
                kill_process_tree(int(pty.pid))
        except Exception:
            pass
        try:
            pty.fileobj.close()
            pty._server.close()
        except Exception:
            pass
