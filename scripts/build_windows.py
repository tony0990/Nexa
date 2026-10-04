"""Build the Windows package: dist/Nexa/{Nexa.exe, NexaWorker.exe, ...}.

    python scripts/build_windows.py                 # full build, then self-verify
    python scripts/build_windows.py --no-cuda       # CPU-only build, ~2 GB smaller
    python scripts/build_windows.py --no-models     # do not copy the Whisper model
    python scripts/build_windows.py --skip-verify   # build only
    python scripts/build_windows.py --verify-only   # re-run the self-test on dist/

Replaces the earlier script, which packaged only the UI: it left out the
migrations, email templates, ASR libraries, CUDA DLLs and the worker.

1. `Nexa.spec` builds BOTH executables into one shared bundle.
2. Model weights are copied beside the exe (core/paths.py looks in <install>/models).
3. `Nexa.exe --selftest` runs from inside the finished build, which catches a data
   file that was not bundled or a DLL that is not found - unit tests cannot.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / "Nexa.spec"
ICON = ROOT / "resources" / "icons" / "nexa.ico"
DIST = ROOT / "dist"
BUILD = ROOT / "build" / "pyinstaller"
PACKAGE = DIST / "Nexa"


def run_pyinstaller(bundle_cuda: bool) -> None:
    if not ICON.exists():
        subprocess.run([sys.executable, str(ROOT / "scripts" / "make_icon.py")], check=True)
    env = dict(os.environ, NEXA_BUNDLE_CUDA="1" if bundle_cuda else "0")
    subprocess.run(
        [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
         "--distpath", str(DIST), "--workpath", str(BUILD), str(SPEC)],
        cwd=ROOT, env=env, check=True,
    )


def copy_models() -> list:
    source = ROOT / "models"
    if not (source / "whisper").is_dir() or not any((source / "whisper").iterdir()):
        return ["no Whisper model in models/whisper: run scripts/download_models.py --asr whisper-medium"]
    shutil.copytree(source, PACKAGE / "models", dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns(".cache", "*.lock", "*.incomplete"))
    return []


def verify() -> bool:
    # A default Windows console is cp1252 and cannot print Arabic check details.
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace")
    exe = PACKAGE / "Nexa.exe"
    if not exe.is_file():
        print(f"cannot verify: {exe} does not exist")
        return False
    data = PACKAGE / "data"
    report = data / "selftest.json"
    report.unlink(missing_ok=True)
    result = subprocess.run([str(exe), "--selftest", "--data-dir", str(data)], timeout=900)
    if not report.is_file():
        print("the self-test wrote no report; exit code", result.returncode)
        return False
    summary = json.loads(report.read_text(encoding="utf-8"))
    for check in summary["checks"]:
        first = str(check["detail"]).splitlines()[0] if check["detail"] else ""
        print(f"  [{check['status']}] {check['name']}: {first[:150]}")
    print("self-test:", "PASSED" if summary["ok"] else "FAILED")
    return bool(summary["ok"])


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the Nexa Windows package")
    parser.add_argument("--no-cuda", action="store_true")
    parser.add_argument("--no-models", action="store_true")
    parser.add_argument("--skip-verify", action="store_true")
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()

    if not args.verify_only:
        run_pyinstaller(bundle_cuda=not args.no_cuda)
        for folder in ("data", "logs"):
            (PACKAGE / folder).mkdir(parents=True, exist_ok=True)
        warnings = [] if args.no_models else copy_models()
        size = sum(f.stat().st_size for f in PACKAGE.rglob("*") if f.is_file()) / 1e9
        print(f"\nBuilt {PACKAGE}  ({size:.2f} GB)")
        for warning in warnings:
            print(f"  warning: {warning}")
    if args.skip_verify:
        return 0
    return 0 if verify() else 1


if __name__ == "__main__":
    raise SystemExit(main())
