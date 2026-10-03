"""The real seams between Members 1, 4 and 5 — no fakes on either side.

Each member's own suite passes against doubles for the dependencies they do not
own, which is exactly what Section 17 intends and is what let them work in
parallel. It also means nobody's suite ever exercised the actual joins. This
module does:

* Member 1's real migrated SQLite database, not a hand-written schema
* Member 4's real `ReportService` as the worker's `ReminderEmailBuilder`
* Member 5's real `WorkerService`, queue and SQLite adapters
* Member 1's real `RecipientResolver`, `PeopleService` and `AuditService`

The only double is the Gmail transport itself (`FakeEmailSender`), because the
alternative is mailing people during a test run. It still builds real MIME.

Three of these tests would have failed before the merge was reconciled:
`DeliveryTarget` was being built positionally against a field order that no
longer existed, `SendResult.retryable` did not exist, and the audit vocabulary
was split in two.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

import pytest

from nexa.audit import event_types
from nexa.audit.service import Actor, AuditService
from nexa.contracts.email import DeliveryKind, DeliveryTarget, TargetType
from nexa.contracts.meetings import ActionItem, EmailLanguage, Meeting
from nexa.core.clock import FixedClock
from nexa.core.config import NexaConfig
from nexa.data.database import open_database
from nexa.email import FakeEmailSender
from nexa.people.service import PeopleService
from nexa.reports import ReportService
from nexa.scheduling.calculator import to_db
from nexa.scheduling.queue import SqliteReminderQueue, connect
from nexa.scheduling.states import AuditNames, ReminderStatus
from nexa.worker.service import (
    SqliteActionLookup,
    SqliteDeliveryRecorder,
    WorkerDependencies,
    WorkerService,
)

# 20:00 Cairo on Sunday 6 September 2026 — the default evening reminder slot.
NOW = datetime(2026, 9, 6, 17, 0, tzinfo=timezone.utc)


class Stack:
    """Every member's real component, wired together over one database."""

    def __init__(self, tmp_path: Path):
        self.config = NexaConfig(data_dir=tmp_path / "data")
        self.db = open_database(self.config)          # Member 1 migrates
        self.clock = FixedClock(NOW)
        self.now = NOW
        self.audit = AuditService(self.db, self.clock, default_actor=Actor.user("admin"))
        self.people = PeopleService(self.db, self.clock, self.audit, actor=Actor.user("admin"))

        self.path = str(self.config.database_path)
        self.factory = lambda: connect(self.path)
        self.queue = SqliteReminderQueue(
            self.factory, clock=lambda: self.now, audit=self.audit
        )
        self.sender = FakeEmailSender(from_email="nexa@example.com", from_name="Nexa")
        self.reports = ReportService(clock=self.clock)   # Member 4, for real

    def close(self) -> None:
        self.db.close()

    # ------------------------------------------------------------ seeding
    def add_employee(self, name: str, email: str):
        return self.people.create_employee(name, email)

    def add_meeting(self, language: str = EmailLanguage.EN.value) -> int:
        stamp = to_db(self.now)
        with self.db.connect() as _:
            pass
        self.db.execute(
            "INSERT INTO meetings (title, title_norm, status, email_language, "
            "created_at, updated_at) VALUES (?,?,?,?,?,?)",
            ("Digital Transformation Weekly", "digital transformation weekly",
             "APPROVED", language, stamp, stamp),
        )
        self.db.connect().commit()
        return int(self.db.query_value("SELECT MAX(id) FROM meetings"))

    def add_action(self, meeting_id: int, owner_id: int, task: str, due: date) -> int:
        stamp = to_db(self.now)
        self.db.execute(
            "INSERT INTO action_items (meeting_id, task, owner_employee_id, due_date, "
            "due_time, source_text, review_state, status, created_at, updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?)",
            (meeting_id, task, owner_id, due.isoformat(), "15:00",
             "الـpresentation Thursday الساعة three", "APPROVED", "PENDING",
             stamp, stamp),
        )
        self.db.connect().commit()
        return int(self.db.query_value("SELECT MAX(id) FROM action_items"))

    def action(self, action_id: int) -> ActionItem:
        return SqliteActionLookup(self.factory).get_action(action_id)

    def worker(self, **kw) -> WorkerService:
        return WorkerService(
            WorkerDependencies(
                queue=self.queue,
                lookup=SqliteActionLookup(self.factory),
                recipient_resolver=self.resolver(),
                # Member 4's real report renderer, not a stub.
                email_builder=self.reports,
                email_sender=self.sender,
                recorder=SqliteDeliveryRecorder(self.factory),
                audit=self.audit,
                clock=lambda: self.now,
            ),
            **kw,
        )

    def schedule(self, action_id: int):
        """Create this action's reminders through Member 5's public API.

        `schedule_for_action` is what the review screen calls on approval, so
        using it here exercises the rule engine and the idempotency key rather
        than hand-inserting a row the real system would never produce.
        """
        from nexa.scheduling.service import ReminderService

        reminders = ReminderService(self.queue, audit=self.audit).schedule_for_action(
            self.action(action_id)
        )
        assert reminders, "the policy produced no reminders for this action"
        # The one due now is the 20:00-previous-day reminder.
        due = [r for r in reminders if r.scheduled_at <= NOW]
        return (due or reminders)[0]

    def resolver(self):
        from nexa.people.recipient_resolver import RecipientResolver

        return RecipientResolver(self.db, self.clock)


@pytest.fixture
def stack(tmp_path):
    instance = Stack(tmp_path)
    yield instance
    instance.close()


@pytest.fixture
def scheduled(stack):
    """One employee with one approved action and one due reminder."""
    employee = stack.add_employee("أحمد حسن", "ahmed@example.com")
    meeting_id = stack.add_meeting(EmailLanguage.EN.value)
    action_id = stack.add_action(meeting_id, employee.id, "Database Integration",
                                date(2026, 9, 7))
    reminder = stack.schedule(action_id)
    return stack, employee, meeting_id, action_id, reminder


# ----------------------------------------------- Member 4's renderer in the worker
def test_worker_sends_a_real_member4_reminder(scheduled):
    """The whole chain: queue -> resolve -> render -> send -> record."""
    stack, employee, _, _, reminder = scheduled

    summary = stack.worker().run_once(NOW)

    assert summary.sent == 1, summary
    assert len(stack.sender.sent) == 1
    message = stack.sender.sent[0].message
    # Rendered by Member 4's English lexicon, not by a stub.
    assert message.to_email == employee.email
    assert message.subject == "[Nexa Reminder] Database Integration — Due Tomorrow"
    assert "This is a reminder that your assigned action item" in message.text_body
    assert message.html_body.strip().startswith("<!DOCTYPE html>")
    assert message.language == EmailLanguage.EN.value


def test_arabic_meeting_produces_an_arabic_reminder(stack):
    """The meeting's email_language reaches Member 4's renderer intact."""
    employee = stack.add_employee("ندى مصطفى", "nada@example.com")
    meeting_id = stack.add_meeting(EmailLanguage.AR.value)
    action_id = stack.add_action(meeting_id, employee.id, "إرسال تقرير الحضور",
                                date(2026, 9, 7))
    stack.schedule(action_id)

    assert stack.worker().run_once(NOW).sent == 1
    message = stack.sender.sent[0].message
    assert message.language == EmailLanguage.AR.value
    assert "نود تذكيركم" in message.text_body
    assert 'dir="rtl"' in message.html_body


def test_bilingual_meeting_produces_a_paired_reminder(stack):
    """BILINGUAL survives the DB CHECK (migration 004) and the worker."""
    employee = stack.add_employee("Sarah Ali", "sarah@example.com")
    meeting_id = stack.add_meeting(EmailLanguage.BILINGUAL.value)
    action_id = stack.add_action(meeting_id, employee.id, "Database Integration",
                                date(2026, 9, 7))
    stack.schedule(action_id)

    assert stack.worker().run_once(NOW).sent == 1
    message = stack.sender.sent[0].message
    assert message.language == EmailLanguage.BILINGUAL.value
    assert "This is a reminder" in message.text_body
    assert "نود تذكيركم" in message.text_body
    # And the delivery row stored it, which needs the widened CHECK.
    assert stack.db.query_value(
        "SELECT language FROM email_deliveries ORDER BY id DESC LIMIT 1"
    ) == EmailLanguage.BILINGUAL.value


# ----------------------------------------- Member 1's resolver in the worker
def test_recipients_come_from_member1s_resolver(scheduled):
    """The ASSIGNEE default target resolves through the real resolver.

    This is the test that fails when `DeliveryTarget` is built positionally:
    the canonical field order starts with id/meeting_id, so "REMINDER" bound to
    `id`, `target_type` stayed "ALL", and the resolver returned nobody.
    """
    stack, employee, _, _, _ = scheduled
    assert stack.worker().run_once(NOW).sent == 1
    assert stack.sender.sent[0].message.to_email == employee.email


def test_an_explicit_delivery_target_is_honoured(stack):
    """A stored EMPLOYEE target overrides the assignee default."""
    owner = stack.add_employee("Owner Person", "owner@example.com")
    other = stack.add_employee("Target Person", "target@example.com")
    meeting_id = stack.add_meeting()
    action_id = stack.add_action(meeting_id, owner.id, "Review the contract",
                                date(2026, 9, 7))
    stack.db.execute(
        "INSERT INTO delivery_targets (meeting_id, action_item_id, delivery_kind, "
        "target_type, target_id, created_at) VALUES (?,?,?,?,?,?)",
        (meeting_id, action_id, DeliveryKind.REMINDER.value,
         TargetType.EMPLOYEE.value, other.id, to_db(stack.now)),
    )
    stack.db.connect().commit()
    stack.schedule(action_id)

    assert stack.worker().run_once(NOW).sent == 1
    assert stack.sender.sent[0].message.to_email == other.email


def test_a_deactivated_employee_is_not_mailed(stack):
    """Member 1's resolver drops unsendable employees; the worker must not send."""
    employee = stack.add_employee("Retired Person", "retired@example.com")
    stack.people.deactivate_employee(employee.id)
    meeting_id = stack.add_meeting()
    action_id = stack.add_action(meeting_id, employee.id, "Old task", date(2026, 9, 7))
    reminder = stack.schedule(action_id)

    summary = stack.worker().run_once(NOW)
    assert summary.sent == 0
    assert stack.sender.sent == []
    row = stack.db.query_one("SELECT status, last_error FROM reminders WHERE id = ?",
                             (reminder.id,))
    assert row["status"] == ReminderStatus.FAILED.value
    assert row["last_error"] == "NO_RECIPIENTS"


# ---------------------------------------- Member 4's retry classification
def test_a_retryable_failure_schedules_a_retry(scheduled):
    """`SendResult.retryable` is the Member 4 -> Member 5 retry contract.

    Before the merge was reconciled, the canonical SendResult had no
    `retryable` field at all, so the worker could not tell a rate limit from a
    revoked token.
    """
    stack, _, _, _, reminder = scheduled
    stack.sender.fail_next = 1
    stack.sender.retryable = True

    summary = stack.worker().run_once(NOW)
    assert summary.retry_scheduled == 1
    assert summary.failed == 0
    row = stack.db.query_one("SELECT status, next_attempt_at FROM reminders WHERE id = ?",
                             (reminder.id,))
    assert row["status"] == ReminderStatus.RETRY_WAIT.value
    assert row["next_attempt_at"] is not None


def test_a_permanent_failure_does_not_retry(scheduled):
    stack, _, _, _, reminder = scheduled
    stack.sender.fail_next = 1
    stack.sender.retryable = False

    summary = stack.worker().run_once(NOW)
    assert summary.retry_scheduled == 0
    assert summary.failed == 1
    assert stack.db.query_value(
        "SELECT status FROM reminders WHERE id = ?", (reminder.id,)
    ) == ReminderStatus.FAILED.value


def test_an_invalid_address_is_classified_permanent(stack):
    """The fake builds real MIME, so a bad address fails the way Gmail would."""
    employee = stack.add_employee("Bad Address", "bad@example.com")
    meeting_id = stack.add_meeting()
    action_id = stack.add_action(meeting_id, employee.id, "Task", date(2026, 9, 7))
    # Corrupt the stored address behind the service's validation.
    stack.db.execute("UPDATE employees SET email = 'not-an-email' WHERE id = ?",
                     (employee.id,))
    stack.db.connect().commit()
    stack.schedule(action_id)

    summary = stack.worker().run_once(NOW)
    assert summary.sent == 0
    assert summary.retry_scheduled == 0, "a malformed address must not be retried forever"


# ----------------------------------------- Member 1's delivery log and audit
def test_the_delivery_is_recorded_in_member1s_table(scheduled):
    stack, employee, meeting_id, action_id, reminder = scheduled
    stack.worker().run_once(NOW)

    row = stack.db.query_one(
        "SELECT * FROM email_deliveries WHERE reminder_id = ?", (reminder.id,)
    )
    assert row["status"] == "SENT"
    assert row["recipient_email"] == employee.email
    assert row["recipient_employee_id"] == employee.id
    assert row["meeting_id"] == meeting_id
    assert row["action_item_id"] == action_id
    assert row["gmail_message_id"]
    assert row["language"] == EmailLanguage.EN.value
    assert row["subject"]


def test_worker_audit_events_land_in_member1s_trail(scheduled):
    """Audit names must be Member 1's, or the trail screen cannot find them."""
    stack, _, _, _, reminder = scheduled
    stack.worker().run_once(NOW)

    recorded = {
        row["event_type"]
        for row in stack.db.query_all("SELECT event_type FROM audit_events")
    }
    assert AuditNames.REMINDER_SEND in recorded
    assert event_types.REMINDER_SENT in recorded          # the same string
    assert AuditNames.REMINDER_SEND == event_types.REMINDER_SENT

    history = stack.audit.history("reminder", reminder.id)
    assert any(event.event_type == event_types.REMINDER_SENT for event in history)


def test_every_audit_name_the_worker_uses_is_canonical():
    """A name outside Member 1's vocabulary would be invisible to the UI."""
    used = {v for k, v in vars(AuditNames).items() if k.isupper()}
    assert used <= set(event_types.ALL_EVENT_TYPES)


def test_actor_type_satisfies_the_audit_check_constraint(scheduled):
    """audit_events.actor_type is CHECK (actor_type IN ('USER','SYSTEM','WORKER')).

    The worker defaulted to lowercase "system", which would have failed the
    insert on every event it emitted.
    """
    stack, _, _, _, _ = scheduled
    stack.worker().run_once(NOW)
    actors = {
        row["actor_type"]
        for row in stack.db.query_all("SELECT actor_type FROM audit_events")
    }
    assert actors
    assert actors <= {"USER", "SYSTEM", "WORKER"}


# ------------------------------------------------------------- idempotency
def test_a_second_run_does_not_resend(scheduled):
    stack, _, _, _, _ = scheduled
    assert stack.worker().run_once(NOW).sent == 1
    assert stack.worker().run_once(NOW).sent == 0
    assert len(stack.sender.sent) == 1


def test_a_completed_action_is_never_reminded(stack):
    employee = stack.add_employee("Done Person", "done@example.com")
    meeting_id = stack.add_meeting()
    action_id = stack.add_action(meeting_id, employee.id, "Already done",
                                date(2026, 9, 7))
    stack.schedule(action_id)
    stack.db.execute("UPDATE action_items SET status = 'COMPLETED' WHERE id = ?",
                     (action_id,))
    stack.db.connect().commit()

    summary = stack.worker().run_once(NOW)
    assert summary.skipped_completed == 1
    assert stack.sender.sent == []
