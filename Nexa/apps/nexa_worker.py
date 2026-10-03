"""NexaWorker.exe entry point (PyInstaller target). No GUI.

    NexaWorker.exe --db data\\nexa.db               # run forever
    NexaWorker.exe --once                           # one pass (testing)
    NexaWorker.exe --install-startup / --remove-startup / --startup-status
    NexaWorker.exe --status                         # health JSON for support/GUI
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from nexa.scheduling.queue import SqliteReminderQueue, connect  # noqa: E402
from nexa.scheduling.recovery import RecoveryPolicy  # noqa: E402
from nexa.scheduling.rules import ReminderPolicy  # noqa: E402
from nexa.worker import windows_startup  # noqa: E402
from nexa.worker.health import check_worker_health  # noqa: E402
from nexa.worker.runner import EXIT_ERROR, EXIT_OK, WorkerConfig, run_worker  # noqa: E402
from nexa.worker.service import SqliteActionLookup, SqliteDeliveryRecorder, WorkerDependencies  # noqa: E402


def build_dependencies(config: WorkerConfig) -> WorkerDependencies:
    """Composition root (Integration E). The four lines marked INTEGRATION use other members'
    PUBLIC services only; adjust constructor arguments to their final signatures."""
    factory = config.factory()
    lookup = SqliteActionLookup(factory)
    settings = {k: lookup.get_setting(k) for k in (
        "default_evening_reminder_time", "default_morning_reminder_time",
        "missed_reminder_recovery_hours")}
    try:
        from nexa.people.recipient_resolver import RecipientResolver      # INTEGRATION (Member 1)
        from nexa.reports.service import ReportService                    # INTEGRATION (Member 4)
        from nexa.email.service import EmailService                       # INTEGRATION (Member 4)
        from nexa.audit.service import AuditService                       # INTEGRATION (Member 1)
    except ImportError as exc:
        raise SystemExit(f"Integration modules missing ({exc}). "
                         "Wire Members 1/4 services here or build with fakes for tests.")
    audit = AuditService(factory)
    queue = SqliteReminderQueue(factory, ReminderPolicy.from_settings(settings), audit=audit)
    return WorkerDependencies(
        queue=queue, lookup=lookup, recipient_resolver=RecipientResolver(factory),
        email_builder=ReportService(), email_sender=EmailService(), audit=audit,
        recorder=SqliteDeliveryRecorder(factory),
        recovery_policy=RecoveryPolicy.from_settings(settings))


def main(argv=None, deps_builder=build_dependencies) -> int:
    default_db = os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])), "data", "nexa.db")
    p = argparse.ArgumentParser(prog="NexaWorker")
    p.add_argument("--db", default=os.environ.get("NEXA_DB", default_db))
    p.add_argument("--interval", type=float, default=10.0)
    p.add_argument("--log-dir", default=None)
    p.add_argument("--once", action="store_true")
    p.add_argument("--background", action="store_true", help="used by the Windows startup entry")
    p.add_argument("--install-startup", action="store_true")
    p.add_argument("--remove-startup", action="store_true")
    p.add_argument("--startup-status", action="store_true")
    p.add_argument("--status", action="store_true")
    a = p.parse_args(argv)

    if a.install_startup:
        print(windows_startup.enable_startup(sys.executable if getattr(sys, "frozen", False)
                                             else os.path.abspath(__file__), "--db", a.db, "--background"))
        return EXIT_OK
    if a.remove_startup:
        print("removed" if windows_startup.disable_startup() else "not registered")
        return EXIT_OK
    if a.startup_status:
        print("enabled" if windows_startup.is_enabled() else "disabled")
        return EXIT_OK
    if a.status:
        h = check_worker_health(lambda: connect(a.db), datetime.now(timezone.utc))
        print(json.dumps(h.__dict__, default=str, indent=2))
        return EXIT_OK

    cfg = WorkerConfig(db_path=a.db, poll_interval=a.interval,
                       log_dir=a.log_dir or os.path.join(os.path.dirname(os.path.abspath(a.db)), "..", "logs"))
    return run_worker(cfg, deps_builder, once=a.once)


if __name__ == "__main__":
    sys.exit(main())
