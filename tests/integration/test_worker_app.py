"""`NexaWorker.exe`'s composition root — the one place all members meet.

`apps/nexa_worker.py:build_dependencies` had never been executed. It carried a
note to "adjust constructor arguments to their final signatures", and every one
of them was wrong, so the first real invocation died. These tests run it.

What it got wrong, each of which is a test below:

* the database was never migrated, so a worker starting before the GUI had ever
  run crashed with `no such table: settings`
* `AuditService` and `RecipientResolver` were handed a raw connection factory
  instead of Member 1's `Database` and a `Clock`
* `EmailService` was passed where the `EmailSender` protocol is required — it
  returns a `DeliveryAttempt`, not a `SendResult`
* `--status` raised `sqlite3.OperationalError` on an un-migrated file, which the
  GUI polls and has to render
"""

from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKER_APP = REPO_ROOT / "apps" / "nexa_worker.py"


def run_worker(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(WORKER_APP), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
        cwd=str(REPO_ROOT),
    )


def test_help_works_without_a_database():
    result = run_worker("--help")
    assert result.returncode == 0
    assert "NexaWorker" in result.stdout


def test_status_on_a_missing_database_is_reported_not_raised(tmp_path):
    result = run_worker("--db", str(tmp_path / "nope.db"), "--status")
    assert result.returncode == 0
    assert json.loads(result.stdout)["state"] == "NO_DATABASE"
    assert "Traceback" not in result.stderr


def test_status_on_an_unmigrated_database_is_reported_not_raised(tmp_path):
    """The GUI polls --status; a traceback is not something it can render."""
    path = tmp_path / "empty.db"
    sqlite3.connect(path).close()          # a real file with no schema
    result = run_worker("--db", str(path), "--status")
    assert result.returncode == 0
    assert json.loads(result.stdout)["state"] == "NOT_MIGRATED"
    assert "Traceback" not in result.stderr


def test_a_fresh_database_is_created_and_migrated(tmp_path):
    """Section 3.2's loop starts with "Open SQLite database".

    The worker is allowed to be the first process to touch the file, so it has
    to migrate rather than assume the GUI has run.
    """
    path = tmp_path / "data" / "nexa.db"
    result = run_worker("--db", str(path), "--once")

    assert path.is_file(), result.stderr
    connection = sqlite3.connect(path)
    try:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
    finally:
        connection.close()
    # The tables the worker itself reads, plus the migration bookkeeping.
    assert {"settings", "reminders", "action_items", "schema_migrations"} <= tables
    assert "no such table" not in (result.stdout + result.stderr)


def test_missing_gmail_is_a_clear_message_not_a_traceback(tmp_path):
    """A worker that cannot send should say so the way Settings does."""
    result = run_worker("--db", str(tmp_path / "data" / "nexa.db"), "--once")
    combined = result.stdout + result.stderr
    assert "Traceback" not in combined, combined
    assert "Gmail is not connected" in combined
    assert "setup_gmail.py connect" in combined


def test_startup_status_does_not_need_a_database():
    result = run_worker("--startup-status")
    assert result.returncode == 0
    assert result.stdout.strip() in {"enabled", "disabled"}


# ------------------------------------------------- the composition root itself
@pytest.fixture
def worker_app():
    """Import `apps/nexa_worker.py` as a module."""
    import importlib.util

    spec = importlib.util.spec_from_file_location("nexa_worker_app", WORKER_APP)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_build_dependencies_wires_every_members_real_service(
    tmp_path, worker_app, monkeypatch
):
    """The whole point: this function must actually construct.

    Only the Gmail sender is substituted, because the real one needs an OAuth
    credential. Everything else — Member 1's database, audit and resolver,
    Member 4's ReportService, Member 5's queue and adapters — is real.
    """
    from nexa.audit.service import AuditService
    from nexa.email import FakeEmailSender
    from nexa.people.recipient_resolver import RecipientResolver
    from nexa.reports.service import ReportService
    from nexa.worker.runner import WorkerConfig

    monkeypatch.setattr(worker_app, "_email_sender", lambda: FakeEmailSender())

    config = WorkerConfig(db_path=str(tmp_path / "data" / "nexa.db"))
    deps = worker_app.build_dependencies(config)

    # Each slot holds the real type, not a factory or the wrong service.
    assert isinstance(deps.audit, AuditService)
    assert isinstance(deps.recipient_resolver, RecipientResolver)
    assert isinstance(deps.email_builder, ReportService)
    # email_sender must satisfy EmailSender: send(rendered) -> SendResult.
    assert hasattr(deps.email_sender, "send")
    assert deps.queue is not None
    assert deps.recorder is not None


def test_the_wired_worker_can_run_a_pass(tmp_path, worker_app, monkeypatch):
    """Composition is not enough — the assembled worker has to execute."""
    from datetime import datetime, timezone

    from nexa.email import FakeEmailSender
    from nexa.worker.runner import WorkerConfig
    from nexa.worker.service import WorkerService

    monkeypatch.setattr(worker_app, "_email_sender", lambda: FakeEmailSender())
    config = WorkerConfig(db_path=str(tmp_path / "data" / "nexa.db"))
    worker = WorkerService(worker_app.build_dependencies(config))

    summary = worker.run_once(datetime.now(timezone.utc))
    # An empty queue: no work, and crucially no exception.
    assert summary.claimed == 0
    assert summary.sent == 0


def test_email_service_is_not_used_as_the_sender(worker_app):
    """`EmailService.send` returns a DeliveryAttempt, not a SendResult.

    Passing it where the `EmailSender` protocol is expected type-checks fine at
    runtime and then breaks on `result.ok`, which is why this is pinned.
    """
    import inspect

    from nexa.email import EmailService

    source = inspect.getsource(worker_app.build_dependencies)
    assert "email_sender=_email_sender()" in source
    # The orchestrator returns an attempt, confirming it is the wrong shape.
    assert "DeliveryAttempt" in inspect.getsource(EmailService.send)
