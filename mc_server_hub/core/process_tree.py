"""Identify the server process that belongs to one BAT tree.

Resource numbers come only from this tree. Another java.exe on the machine
is never treated as this server.
"""

from __future__ import annotations

from dataclasses import dataclass

import psutil


_WRAPPERS = {
    "cmd.exe",
    "conhost.exe",
    "openconsole.exe",
    "mcserverhub.exe",
}
_JAVA = {"java.exe", "javaw.exe", "java"}


@dataclass(frozen=True)
class TreeInfo:
    root_alive: bool
    primary_pid: int | None
    primary_name: str
    is_java: bool


def pid_alive(pid: int | None) -> bool:
    if not pid:
        return False
    try:
        process = psutil.Process(pid)
        return process.is_running() and process.status() != psutil.STATUS_ZOMBIE
    except (psutil.Error, OSError):
        return False


def inspect_process_tree(root_pid: int) -> TreeInfo:
    try:
        root = psutil.Process(root_pid)
        if not root.is_running() or root.status() == psutil.STATUS_ZOMBIE:
            return TreeInfo(False, None, "", False)
    except (psutil.Error, OSError):
        return TreeInfo(False, None, "", False)

    try:
        descendants = root.children(recursive=True)
    except (psutil.Error, OSError):
        descendants = []

    java_processes: list[psutil.Process] = []
    other_processes: list[psutil.Process] = []
    for process in descendants:
        try:
            name = process.name().lower()
        except (psutil.Error, OSError):
            continue
        if name in _WRAPPERS:
            continue
        if name in _JAVA:
            java_processes.append(process)
        else:
            other_processes.append(process)

    chosen: psutil.Process | None = None
    is_java = False
    if java_processes:
        chosen = _prefer_server_java(java_processes, root_pid)
        is_java = chosen is not None
    elif other_processes:
        chosen = _prefer_direct_child(other_processes, root_pid)

    if chosen is None:
        return TreeInfo(True, None, "", False)
    try:
        return TreeInfo(True, int(chosen.pid), chosen.name(), is_java)
    except (psutil.Error, OSError):
        return TreeInfo(True, None, "", False)


def kill_process_tree(pid: int) -> None:
    """Last-resort kill when the process was not placed in a job."""
    try:
        root = psutil.Process(pid)
    except (psutil.Error, OSError):
        return
    try:
        processes = root.children(recursive=True)
    except (psutil.Error, OSError):
        processes = []
    processes.append(root)
    for process in processes:
        try:
            process.kill()
        except (psutil.Error, OSError):
            pass
    try:
        psutil.wait_procs(processes, timeout=3)
    except (psutil.Error, OSError):
        pass


def descendant_pids(root_pid: int) -> list[int]:
    try:
        root = psutil.Process(root_pid)
        children = root.children(recursive=True)
    except (psutil.Error, OSError):
        return []
    pids: list[int] = []
    for process in children:
        try:
            pids.append(int(process.pid))
        except (psutil.Error, OSError):
            continue
    return pids


def _prefer_direct_child(processes: list[psutil.Process], root_pid: int) -> psutil.Process | None:
    direct: list[psutil.Process] = []
    for process in processes:
        try:
            if process.ppid() == root_pid:
                direct.append(process)
        except (psutil.Error, OSError):
            continue
    pool = direct or processes
    return pool[0] if pool else None


def _prefer_server_java(processes: list[psutil.Process], root_pid: int) -> psutil.Process | None:
    direct = _direct_children(processes, root_pid)
    pool = direct or processes
    for process in pool:
        try:
            command = " ".join(process.cmdline()).lower()
        except (psutil.Error, OSError):
            continue
        if "-jar" in command or "server.jar" in command:
            return process
    return pool[0] if pool else None


def _direct_children(processes: list[psutil.Process], root_pid: int) -> list[psutil.Process]:
    direct: list[psutil.Process] = []
    for process in processes:
        try:
            if process.ppid() == root_pid:
                direct.append(process)
        except (psutil.Error, OSError):
            continue
    return direct
