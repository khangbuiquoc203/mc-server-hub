"""Decide what a process exit means. Idle consoles are not crashes."""

from __future__ import annotations

from dataclasses import dataclass

from mc_server_hub.models.server_runtime import ServerStatus


@dataclass(frozen=True)
class ExitDecision:
    status: ServerStatus
    should_restart: bool
    reason: str


def decide_exit(
    *,
    user_stop: bool,
    auto_restart: bool,
    attempts: int,
    max_attempts: int,
    unlimited: bool,
) -> ExitDecision:
    """Classify an unexpected process-tree exit.

    ``attempts`` is how many automatic restarts have already been consumed.
    A user stop never restarts, even when auto restart is enabled.
    """
    if user_stop:
        return ExitDecision(ServerStatus.STOPPED, False, "Stopped by user.")
    if not auto_restart:
        return ExitDecision(ServerStatus.CRASHED, False, "Auto restart is disabled.")
    if unlimited or attempts < max_attempts:
        limit = "unlimited" if unlimited else str(max_attempts)
        return ExitDecision(
            ServerStatus.RESTARTING,
            True,
            f"Scheduled auto restart ({attempts + 1}/{limit}).",
        )
    return ExitDecision(
        ServerStatus.ERROR,
        False,
        "Restart limit reached; auto restart stopped.",
    )
