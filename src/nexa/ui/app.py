"""Application entry: builds the Qt app, the services and the main window.

    Nexa.exe                 the real app (database, microphone, speech model)
    Nexa.exe --demo          the same UI over Member 6's fake services
    Nexa.exe --selftest      headless check that this build can actually work
    Nexa.exe --data-dir X    keep the database, outbox and recordings in X

Real services are the default. `--demo` exists for screenshots and for trying the
UI on a machine with no microphone or model.
"""

from __future__ import annotations

import argparse
import logging
import subprocess
import sys
import traceback
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QMessageBox

from nexa.core import paths
from nexa.ui.main_window import MainWindow

log = logging.getLogger("nexa.app")


def create_app() -> QApplication:
    app = QApplication.instance() or QApplication(sys.argv[:1])
    app.setApplicationName("Nexa")
    app.setOrganizationName("Nexa")
    icon = _icon_path()
    if icon is not None:
        app.setWindowIcon(QIcon(str(icon)))
    return app


def _icon_path() -> Optional[Path]:
    for base in (paths.resource_dir(), paths.install_dir()):
        candidate = base / "resources" / "icons" / "nexa.ico"
        if candidate.is_file():
            return candidate
    return None


def setup_logging(data_dir: Path) -> Path:
    """Log to a rotating file: a windowed exe has no console to print to."""
    log_dir = data_dir / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    target = log_dir / "nexa.log"
    handler = RotatingFileHandler(target, maxBytes=2_000_000, backupCount=5, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(handler)
    # With no console (--windowed) sys.stderr/stdout are None; libraries write to them.
    if sys.stderr is None:
        sys.stderr = open(log_dir / "stderr.log", "a", encoding="utf-8")  # noqa: SIM115
    if sys.stdout is None:
        sys.stdout = open(log_dir / "stdout.log", "a", encoding="utf-8")  # noqa: SIM115
    return target


def install_crash_handler(parent_hint=None) -> None:
    """Log any uncaught exception and tell the user, instead of vanishing."""

    def hook(exc_type, exc, tb):
        text = "".join(traceback.format_exception(exc_type, exc, tb))
        logging.getLogger("nexa.crash").error("uncaught exception:\n%s", text)
        try:
            QMessageBox.critical(
                parent_hint, "Nexa",
                f"Something went wrong:\n\n{exc_type.__name__}: {exc}\n\nDetails were saved to the log file.",
            )
        except Exception:  # noqa: BLE001 - the dialog itself must not mask the real error
            pass

    sys.excepthook = hook


def build_real_services(data_dir: Path):
    """The real container (a clear failure is handled by the caller)."""
    from nexa.services.real import RealServiceContainer

    return RealServiceContainer(data_dir)


def ensure_worker(services, data_dir: Path) -> Optional[subprocess.Popen]:
    """Start NexaWorker in the background if no healthy worker is running.

    Reminders are the worker's job and must fire with the window closed (§3), so the
    app starts it rather than hoping the admin did. Two workers cannot double-send:
    the worker holds a single-instance lock and claims reminders atomically.
    """
    try:
        if services.worker_online:
            return None
    except Exception:  # noqa: BLE001
        pass
    db = str(data_dir / "nexa.db")
    log_dir = str(data_dir / "logs")
    if paths.is_frozen():
        exe = paths.install_dir() / "NexaWorker.exe"
        if not exe.is_file():
            log.warning("NexaWorker.exe not found next to Nexa.exe; reminders will not be sent")
            return None
        command = [str(exe), "--db", db, "--log-dir", log_dir, "--background"]
    else:
        script = paths.install_dir() / "apps" / "nexa_worker.py"
        command = [sys.executable, str(script), "--db", db, "--log-dir", log_dir, "--background"]
    flags = 0
    if sys.platform == "win32":
        flags = subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS
    try:
        return subprocess.Popen(
            command, creationflags=flags, stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True,
        )
    except OSError:
        log.exception("could not start the worker")
        return None


def parse_args(argv=None):
    parser = argparse.ArgumentParser(prog="Nexa", description="Nexa meeting assistant")
    parser.add_argument("--demo", action="store_true", help="use fake services (no microphone or model)")
    parser.add_argument("--selftest", action="store_true", help="headless check of this build, then exit")
    parser.add_argument("--data-dir", type=Path, help="where to keep the database, outbox and recordings")
    parser.add_argument("--no-worker", action="store_true", help="do not start NexaWorker in the background")
    return parser.parse_known_args(argv)[0]


def run(argv=None) -> int:
    args = parse_args(argv)
    data_dir = args.data_dir or paths.data_dir()
    data_dir.mkdir(parents=True, exist_ok=True)
    setup_logging(data_dir)
    log.info("starting Nexa (frozen=%s, data=%s)", paths.is_frozen(), data_dir)

    if args.selftest:
        from nexa.ui.selftest import run_selftest

        return run_selftest(data_dir)

    app = create_app()
    install_crash_handler()

    if args.demo:
        from nexa.services.fakes import FakeServiceContainer

        services = FakeServiceContainer()
    else:
        try:
            services = build_real_services(data_dir)
        except Exception as exc:  # noqa: BLE001
            log.exception("could not start the real services")
            QMessageBox.critical(
                None, "Nexa",
                f"Nexa could not start its services:\n\n{type(exc).__name__}: {exc}\n\n"
                f"Details: {data_dir / 'logs' / 'nexa.log'}",
            )
            return 1
        if not args.no_worker:
            ensure_worker(services, data_dir)

    window = MainWindow(services=services)
    window.show()
    code = app.exec()
    close = getattr(services, "close", None)
    if callable(close):
        close()
    return code
