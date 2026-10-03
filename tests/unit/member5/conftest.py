import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "src"))
sys.path.insert(0, os.path.dirname(__file__))

from fakes import FakeBuilder, FakeEmailSender, FakeResolver, RecordingAudit  # noqa: E402
from nexa.contracts.people import Employee  # noqa: E402
from nexa.scheduling.calculator import to_db  # noqa: E402
from nexa.scheduling.queue import SqliteReminderQueue, connect  # noqa: E402
from nexa.worker.service import (SqliteActionLookup, SqliteDeliveryRecorder,  # noqa: E402
                                 WorkerDependencies, WorkerService)

# The real schema, from Member 1's migrations.
#
# This file used to hand-write its own CREATE TABLE statements "mirroring spec
# section 16". That is the trap this whole merge exists to catch: the hand-copy
# had no CHECK constraints and no foreign keys, so Member 5's SQL was being
# tested against a schema nobody ships. Running against the migrations is what
# makes these integration tests mean anything — it is how the lowercase
# `actor_type` and the `email_language="ENGLISH"` bugs below were found.


def apply_real_schema(db_path: str) -> None:
    """Migrate a fresh database using Member 1's `open_database`."""
    from nexa.core.config import NexaConfig
    from nexa.data.database import open_database

    path = Path(db_path)
    database = open_database(
        NexaConfig(data_dir=path.parent, database_filename=path.name)
    )
    database.close()


T0 = datetime(2026, 9, 6, 17, 0, tzinfo=timezone.utc)   # 20:00 Cairo (UTC+3 in September)


class Env:
    def __init__(self, path):
        self.path = str(path)
        apply_real_schema(self.path)
        self.factory = lambda: connect(self.path)
        self.now = T0
        self.audit = RecordingAudit()
        self.queue = SqliteReminderQueue(self.factory, clock=lambda: self.now, audit=self.audit)
        self.sender = FakeEmailSender()
        self.employees = [
            Employee(id=i, full_name=f"Emp {i}", email=f"emp{i}@x.eg") for i in range(1, 6)
        ]
        # The real schema enforces foreign keys, so the employees the resolver
        # hands back must actually exist: action_items.owner_employee_id
        # references employees(id). The hand-written schema had no FKs, so this
        # was never needed and the tests were correspondingly weaker.
        c = self.factory()
        try:
            for e in self.employees:
                c.execute(
                    "INSERT OR IGNORE INTO employees(id,full_name,full_name_norm,email,"
                    "active,created_at,updated_at) VALUES (?,?,?,?,1,?,?)",
                    (e.id, e.full_name, e.full_name.lower(), e.email,
                     to_db(self.now), to_db(self.now)))
        finally:
            c.close()

    def add_action(self, id=1, owner=1, status="PENDING", meeting_id=1, due_date="2026-09-07", due_time="15:00"):
        c = self.factory()
        c.execute(
            "INSERT OR IGNORE INTO meetings(id,title,email_language,created_at,updated_at) "
            "VALUES (?,?,?,?,?)",
            (meeting_id, "M", "EN", to_db(self.now), to_db(self.now)))
        c.execute(
            "INSERT INTO action_items(id,meeting_id,task,owner_employee_id,due_date,"
            "due_time,status,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?)",
            (id, meeting_id, f"Task {id}", owner, due_date, due_time, status,
             to_db(self.now), to_db(self.now)))
        c.close()

    def add_reminder(self, action_id, scheduled_at, status="PENDING", key=None):
        c = self.factory()
        cur = c.execute("INSERT INTO reminders(action_item_id,scheduled_at,status,attempt_count,idempotency_key,created_at,updated_at) VALUES (?,?,?,0,?,?,?)",
                        (action_id, to_db(scheduled_at), status, key or f"k{action_id}:{scheduled_at}:{status}", to_db(self.now), to_db(self.now)))
        c.close()
        return cur.lastrowid

    def row(self, rid):
        c = self.factory(); r = c.execute("SELECT * FROM reminders WHERE id=?", (rid,)).fetchone(); c.close(); return r

    def deps(self, sender=None, **kw):
        return WorkerDependencies(queue=self.queue, lookup=SqliteActionLookup(self.factory),
                                  recipient_resolver=FakeResolver(self.employees), email_builder=FakeBuilder(),
                                  email_sender=sender or self.sender, recorder=SqliteDeliveryRecorder(self.factory),
                                  audit=self.audit, clock=lambda: self.now, **kw)

    def worker(self, sender=None, **kw):
        return WorkerService(self.deps(sender), **kw)


@pytest.fixture
def env(tmp_path):
    return Env(tmp_path / "nexa.db")
