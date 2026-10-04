import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from nexa.ui.app import run

if __name__ == "__main__":
    raise SystemExit(run())
