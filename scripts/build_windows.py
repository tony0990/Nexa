"""Build the Nexa Windows package: dist/Nexa/{Nexa.exe, NexaWorker.exe, resources, models, data, logs}.

Usage:
    python scripts/build_windows.py                      # build Nexa.exe + assemble layout
    python scripts/build_windows.py --worker dist/NexaWorker.exe
    python scripts/build_windows.py --layout-only        # only (re)assemble folders/resources

NexaWorker.exe is built by Member 5. If --worker is not given, the script looks for
dist/NexaWorker.exe and dist/NexaWorker/NexaWorker.exe and warns if it is missing.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
ENTRY = ROOT / "apps" / "nexa_desktop.py"
VERSION = ROOT / "scripts" / "nexa_version.txt"
ICON = ROOT / "resources" / "icons" / "nexa.ico"
DIST = ROOT / "dist"

# Section 43 of the plan: the logical package layout.
PACKAGE_DIRS = [
    "resources/email_templates",
    "resources/translations",
    "resources/themes",
    "resources/icons",
    "models/whisper",
    "models/llm",
    "data",
    "logs",
]


def data_arg(src: Path, dest: str) -> str:
    sep = ";" if sys.platform == "win32" else ":"
    return f"{src}{sep}{dest}"


def pyinstaller_command() -> list[str]:
    cmd = [
        sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--windowed",
        "--name", "Nexa", "--paths", str(SRC), "--version-file", str(VERSION),
    ]
    for name in ("en.json", "ar.json"):
        cmd += ["--add-data", data_arg(SRC / "nexa" / "i18n" / name, "nexa/i18n")]
    for name in ("light.qss", "dark.qss"):
        cmd += ["--add-data", data_arg(SRC / "nexa" / "themes" / name, "nexa/themes")]
    cmd += ["--icon", str(ICON), str(ENTRY)]
    return cmd


def find_worker(explicit: Path | None, dist: Path = DIST) -> Path | None:
    candidates = [explicit] if explicit else [dist / "NexaWorker.exe", dist / "NexaWorker" / "NexaWorker.exe"]
    return next((c for c in candidates if c and c.is_file()), None)


def _copy_tree(src: Path, dst: Path) -> None:
    if src.is_dir():
        shutil.copytree(src, dst, dirs_exist_ok=True)


def assemble_layout(package: Path, root: Path = ROOT, worker: Path | None = None) -> list[str]:
    """Create the package folders, copy resources and the worker. Returns warnings."""
    warnings: list[str] = []
    for rel in PACKAGE_DIRS:
        (package / rel).mkdir(parents=True, exist_ok=True)
    _copy_tree(root / "resources" / "icons", package / "resources" / "icons")
    _copy_tree(root / "resources" / "email_templates", package / "resources" / "email_templates")
    _copy_tree(root / "src" / "nexa" / "i18n", package / "resources" / "translations")
    _copy_tree(root / "src" / "nexa" / "themes", package / "resources" / "themes")
    for stray in list((package / "resources" / "translations").glob("*.py")) + list(
        (package / "resources" / "themes").glob("*.py")
    ):
        stray.unlink()
    shutil.rmtree(package / "resources" / "translations" / "__pycache__", ignore_errors=True)
    shutil.rmtree(package / "resources" / "themes" / "__pycache__", ignore_errors=True)
    if worker:
        shutil.copy2(worker, package / "NexaWorker.exe")
    else:
        warnings.append("NexaWorker.exe not found: package is UI-only until Member 5's worker is added.")
    for models in ("whisper", "llm"):
        if not any((package / "models" / models).iterdir()):
            warnings.append(f"models/{models} is empty: run scripts/download_models.py before the demo.")
    return warnings


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the Nexa Windows package")
    parser.add_argument("--worker", type=Path, help="path to NexaWorker.exe (built by Member 5)")
    parser.add_argument("--layout-only", action="store_true", help="skip PyInstaller, only assemble the folders")
    args = parser.parse_args()

    if not args.layout_only:
        if not ICON.exists():
            subprocess.run([sys.executable, str(ROOT / "scripts" / "make_icon.py")], check=True)
        subprocess.run(pyinstaller_command(), cwd=ROOT, check=True)

    package = DIST / "Nexa"
    warnings = assemble_layout(package, ROOT, find_worker(args.worker))
    print(f"Build complete: {package}")
    for warning in warnings:
        print(f"  warning: {warning}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
