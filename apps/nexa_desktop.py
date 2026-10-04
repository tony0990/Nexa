"""`Nexa.exe` entry point (PyInstaller target).

    Nexa.exe                  the app
    Nexa.exe --demo           the UI over fake services
    Nexa.exe --selftest       headless self-check of this build
"""

import sys
from pathlib import Path

if not getattr(sys, "frozen", False):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from nexa.ui.app import run  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(run())
