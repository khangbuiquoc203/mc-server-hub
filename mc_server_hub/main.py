"""Desktop entry point and the detached supervisor entry point."""

from __future__ import annotations

import sys
from pathlib import Path


if not getattr(sys, "frozen", False):
    _ROOT = Path(__file__).resolve().parents[1]
    if str(_ROOT) not in sys.path:
        sys.path.insert(0, str(_ROOT))


def main() -> int:
    if "--supervisor" in sys.argv:
        from mc_server_hub.core.supervisor import run_supervisor

        run_supervisor()
        return 0
    from mc_server_hub.ui.main_window import run_gui

    return run_gui()


if __name__ == "__main__":
    raise SystemExit(main())
