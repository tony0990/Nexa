import os
import sys
from datetime import datetime, timedelta, timezone

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "src"))
sys.path.insert(0, os.path.dirname(__file__))

from fakes import FakeBuilder, FakeEmailSender, FakeResolver, RecordingAudit  # noqa: E402
from nexa.contracts.people import Employee  # noqa: E402
from nexa.scheduling.calculator import to_db  # noqa: E402
from nexa.scheduling.queue import SqliteReminderQueue, connect  # noqa: E402
from nexa.worker.service import (SqliteActionLookup, SqliteDeliveryRecorder,  # noqa: E402
                                 WorkerDependencies, WorkerService)

# Mirrors spec section 16 (Member 1 owns the real migrations).
SCHEMA = """
CREATE TABLE employees(id INTEGER PRIMARY KEY, full_name TEXT, email TEXT, department TEXT, job_title TEXT, active INTEGER DEFAULT 1, created_at TEXT, updated_at TEXT);
CREATE TABLE meetings(id INTEGER PRIMARY KEY, title TEXT, template_id INTEGER, started_at TEXT, ended_at TEXT, audio_source TEXT, status TEXT, email_language TEXT, created_at TEXT, updated_at TEXT);
CREATE TABLE action_items(id INTEGER PRIMARY KEY, meeting_id INTEGER, task TEXT, owner_employee_id INTEGER, owner_raw_text TEXT, raw_date_phrase TEXT, due_date TEXT, due_time TEXT, due_at TEXT, source_text TEXT, confidence REAL, review_state TEXT, status TEXT DEFAULT 'PENDING', completed_at TEXT, created_at TEXT, updated_at TEXT);
CREATE TABLE reminder_rules(id INTEGER PRIMARY KEY, action_item_id INTEGER, rule_type TEXT, offset_minutes INTEGER, fixed_local_time TEXT, enabled INTEGER, created_at TEXT);
CREATE TABLE reminders(id INTEGER PRIMARY KEY, action_item_id INTEGER, scheduled_at TEXT, status TEXT, attempt_count INTEGER DEFAULT 0, next_attempt_at TEXT, claimed_at TEXT, sent_at TEXT, last_error TEXT, idempotency_key TEXT, created_at TEXT, updated_at TEXT);
CREATE TABLE delivery_targets(id INTEGER PRIMARY KEY, meeting_id INTEGER, action_item_id INTEGER, delivery_kind TEXT, target_type TEXT, target_id INTEGER, created_at TEXT);
CREATE TABLE email_deliveries(id INTEGER PRIMARY KEY, meeting_id INTEGER, action_item_id INTEGER, reminder_id INTEGER, recipient_employee_id INTEGER, recipient_email TEXT, subject TEXT, language TEXT, status TEXT, gmail_message_id TEXT, attempted_at TEXT, sent_at TEXT, error_message TEXT);
CREATE TABLE settings(key TEXT PRIMARY KEY, value_json TEXT, updated_at TEXT);
"""

T0 = datetime(2026, 9, 6, 17, 0, tzinfo=timezone.utc)   # 20:00 Cairo (UTC+3 in September)


class Env:
    def __init__(self, path):
        self.path = str(path)
        self.factory = lambda: connect(self.path)
        c = self.factory(); c.executescript(SCHEMA); c.close()
        self.now = T0
        self.audit = RecordingAudit()
        self.queue = SqliteReminderQueue(self.factory, clock=lambda: self.now, audit=self.audit)
        self.sender = FakeEmailSender()
        self.employees = [Employee(i, f"Emp {i}", f"emp{i}@x.eg") for i in range(1, 6)]

    def add_action(self, id=1, owner=1, status="PENDING", meeting_id=1, due_date="2026-09-07", due_time="15:00"):
        c = self.factory()
        c.execute("INSERT OR IGNORE INTO meetings(id,title,email_language) VALUES (?,?,?)", (meeting_id, "M", "ENGLISH"))
        c.execute("INSERT INTO action_items(id,meeting_id,task,owner_employee_id,due_date,due_time,status) VALUES (?,?,?,?,?,?,?)",
                  (id, meeting_id, f"Task {id}", owner, due_date, due_time, status))
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
