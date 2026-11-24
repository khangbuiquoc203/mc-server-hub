"""Locations that stay next to the executable in a portable build."""

from __future__ import annotations

import re
import sys
from pathlib import Path


def get_app_root() -> Path:
    """Directory that owns config/ and logs/.

    PyInstaller onedir extracts libraries under ``_internal``. User data stays
    beside ``MCServerHub.exe`` so a copied folder remains portable.
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


def supervisor_command(app_root: Path) -> list[str]:
    """Command that starts the background process owner."""
    if getattr(sys, "frozen", False):
        return [sys.executable, "--supervisor"]
    return [sys.executable, "-m", "mc_server_hub.main", "--supervisor"]


def sanitize_folder_name(name: str) -> str:
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip().rstrip(". ")
    return (cleaned or "server")[:80]


def unique_log_folder(name: str, server_id: str, used: set[str]) -> str:
    base = sanitize_folder_name(name)
    if base not in used:
        return base
    return f"{base}_{server_id[:8]}"
