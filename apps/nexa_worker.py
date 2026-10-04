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
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from nexa.scheduling.queue import SqliteReminderQueue, connect  # noqa: E402
from nexa.scheduling.recovery import RecoveryPolicy  # noqa: E402
from nexa.scheduling.rules import ReminderPolicy  # noqa: E402
from nexa.worker import windows_startup  # noqa: E402
from nexa.worker.health import check_worker_health  # noqa: E402
from nexa.worker.runner import EXIT_ERROR, EXIT_OK, WorkerConfig, run_worker  # noqa: E402
from nexa.worker.service import SqliteActionLookup, SqliteDeliveryRecorder, WorkerDependencies  # noqa: E402


def build_dependencies(config: WorkerConfig) -> WorkerDependencies:
    """Composition root (Integration E): every member's real service, wired.

    This was a sketch — "adjust constructor arguments to their final
    signatures" — and had never been run. Four things were wrong, all of which
    crashed on the first real invocation:

    * The database was never migrated, so a worker starting before the GUI had
      ever run died with `no such table: settings`. Section 3.2's loop begins
      with "Open SQLite database", and `NexaWorker.exe` is allowed to be the
      first process to touch it.
    * `AuditService(factory)` and `RecipientResolver(factory)` were passed a
      raw connection factory; Member 1's services take a `Database` and a
      `Clock`.
    * `EmailService` was passed as `email_sender`, but that slot needs the
      `EmailSender` protocol — `send(rendered) -> SendResult`. `EmailService`
      is the orchestrator and returns a `DeliveryAttempt`; the sender is
      `GmailSender` (or `FakeEmailSender`).

    The worker keeps two handles on the same file on purpose: Member 1's
    `Database` for its services, and the raw connection factory the queue needs
    for its `BEGIN IMMEDIATE` transactions. WAL makes that safe, and the two
    executables already share the file this way.
    """
    from nexa.audit.service import Actor, AuditService
    from nexa.core.clock import SystemClock
    from nexa.core.config import NexaConfig
    from nexa.data.database import open_database
    from nexa.email import GmailConnectionService
    from nexa.people.recipient_resolver import RecipientResolver
    from nexa.reports.service import ReportService

    db_path = Path(config.db_path)
    # Creates the file and applies every migration; a no-op once it exists.
    database = open_database(
        NexaConfig(data_dir=db_path.parent, database_filename=db_path.name)
    )
    clock = SystemClock(database.config.timezone)
    audit = AuditService(database, clock, default_actor=Actor.worker())

    factory = config.factory()
    lookup = SqliteActionLookup(factory)
    settings = {
        key: lookup.get_setting(key)
        for key in (
            "default_evening_reminder_time",
            "default_morning_reminder_time",
            "missed_reminder_recovery_hours",
        )
    }
    queue = SqliteReminderQueue(
        factory, ReminderPolicy.from_settings(settings), audit=audit
    )
    return WorkerDependencies(
        queue=queue,
        lookup=lookup,
        recipient_resolver=RecipientResolver(database, clock),
        email_builder=ReportService(clock=clock),
        email_sender=_email_sender(db_path.parent / "outbox"),
        audit=audit,
        recorder=SqliteDeliveryRecorder(factory),
        recovery_policy=RecoveryPolicy.from_settings(settings),
    )


def _email_sender(outbox_dir=None):
    """Gmail when connected, otherwise the local outbox folder.

    This used to exit with "Gmail is not connected", which made NexaWorker.exe
    unusable for anyone without a Google OAuth client — the normal state before
    the admin setup in Section 24.4 is done. Reminders are then written as real
    `.eml` files to the outbox instead of being lost, and the worker says so on
    stderr so nobody mistakes that for delivery. Connecting Gmail switches it over
    with no other change: both senders satisfy the same `EmailSender` protocol.
    """
    from nexa.email import GmailConnectionService, OutboxSender
    from nexa.email.errors import EmailError

    connection = GmailConnectionService()
    status = connection.status()
    if status.connected:
        try:
            return connection.sender()
        except EmailError as exc:
            print(f"Gmail sender unavailable ({exc}); using the outbox folder.", file=sys.stderr)
    else:
        print(
            f"Gmail is not connected ({status.summary}); reminders will be written to the "
            "outbox folder instead of being sent. To send for real: python scripts/setup_gmail.py connect",
            file=sys.stderr,
        )
    folder = Path(outbox_dir) if outbox_dir else Path(os.environ.get("NEXA_DATA_DIR", ".")) / "outbox"
    return OutboxSender(folder)


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
        if not os.path.isfile(a.db):
            print(json.dumps({"state": "NO_DATABASE", "db": a.db}, indent=2))
            return EXIT_OK
        try:
            h = check_worker_health(lambda: connect(a.db), datetime.now(timezone.utc))
        except sqlite3.OperationalError as exc:
            # An un-migrated file is a state to report, not a traceback: the
            # GUI polls --status and has to render something.
            print(json.dumps({"state": "NOT_MIGRATED", "db": a.db, "error": str(exc)},
                             indent=2))
            return EXIT_OK
        print(json.dumps(h.__dict__, default=str, indent=2))
        return EXIT_OK

    cfg = WorkerConfig(db_path=a.db, poll_interval=a.interval,
                       log_dir=a.log_dir or os.path.join(os.path.dirname(os.path.abspath(a.db)), "..", "logs"))
    return run_worker(cfg, deps_builder, once=a.once)


if __name__ == "__main__":
    sys.exit(main())
