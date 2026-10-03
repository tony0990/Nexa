"""WorkerService: claim -> build personalised email -> send -> record -> retry/recover."""
from __future__ import annotations

import json
import logging
import threading
from dataclasses import asdict, dataclass, field, replace
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Callable, Optional, Protocol

from nexa.contracts.email import (
    DeliveryKind,
    DeliveryTarget,
    EmailSender,
    RecipientResolver,
    RenderedEmail,
    SendResult,
    TargetType,
)
from nexa.contracts.meetings import ActionItem, EmailLanguage, Meeting
from nexa.contracts.people import Employee
from nexa.contracts.scheduling import Reminder
from nexa.reports.models import resolve_language
from nexa.scheduling.calculator import from_db, to_db
from nexa.scheduling.queue import ConnectionFactory, SqliteReminderQueue, emit_audit, transaction
from nexa.scheduling.recovery import MISSED_EXPIRED_ERROR, DueClass, RecoveryPolicy
from nexa.scheduling.retry import RetryPolicy
from nexa.scheduling.rules import parse_hhmm
from nexa.scheduling.states import ActionStatus, AuditNames, ReminderStatus as S, reminder_type_from_key

from .claim import ClaimCoordinator
from .heartbeat import Heartbeat

log = logging.getLogger("nexa.worker")
NO_RECIPIENTS = "NO_RECIPIENTS"


# ----------------------------------------------------------------- dependency protocols
class ReminderEmailBuilder(Protocol):          # Member 4: ReportService
    def build_reminder(self, employee: Employee, action: ActionItem, meeting: Optional[Meeting],
                       language: str) -> RenderedEmail: ...


class ActionLookup(Protocol):
    def get_action(self, action_id: int) -> Optional[ActionItem]: ...
    def get_meeting(self, meeting_id: Optional[int]) -> Optional[Meeting]: ...
    def get_reminder_targets(self, action: ActionItem) -> list[DeliveryTarget]: ...
    def get_setting(self, key: str, default: Any = None) -> Any: ...


class DeliveryRecorder(Protocol):
    def already_sent(self, reminder_id: int, employee_id: int) -> bool: ...
    def record(self, *, reminder: Reminder, action: ActionItem, employee: Employee,
               email: Optional[RenderedEmail], result: SendResult, language: str,
               attempted_at: datetime, late_recovery: bool) -> None: ...


# ----------------------------------------------------------------- SQLite adapters (read-only lookups / delivery log)
class SqliteActionLookup:
    def __init__(self, factory: ConnectionFactory):
        self.factory = factory

    def get_action(self, action_id: int) -> Optional[ActionItem]:
        c = self.factory()
        try:
            r = c.execute("SELECT * FROM action_items WHERE id=?", (action_id,)).fetchone()
        finally:
            c.close()
        if r is None:
            return None
        return ActionItem(
            id=r["id"], meeting_id=r["meeting_id"], task=r["task"] or "",
            owner_employee_id=r["owner_employee_id"], owner_raw_text=r["owner_raw_text"],
            raw_date_phrase=r["raw_date_phrase"],
            due_date=date.fromisoformat(str(r["due_date"])[:10]) if r["due_date"] else None,
            due_time=parse_hhmm(r["due_time"], time(0, 0)) if r["due_time"] else None,
            due_at=from_db(r["due_at"]), source_text=r["source_text"], confidence=r["confidence"],
            review_state=r["review_state"], status=r["status"], completed_at=from_db(r["completed_at"]))

    def get_meeting(self, meeting_id: Optional[int]) -> Optional[Meeting]:
        if meeting_id is None:
            return None
        c = self.factory()
        try:
            r = c.execute("SELECT * FROM meetings WHERE id=?", (meeting_id,)).fetchone()
        finally:
            c.close()
        return None if r is None else Meeting(id=r["id"], title=r["title"] or "",
                                              email_language=r["email_language"], status=r["status"])

    def get_reminder_targets(self, action: ActionItem) -> list[DeliveryTarget]:
        c = self.factory()
        try:
            rows = c.execute("SELECT * FROM delivery_targets WHERE delivery_kind='REMINDER' "
                             "AND action_item_id=?", (action.id,)).fetchall()
        finally:
            c.close()
        # Keyword arguments on purpose: the canonical DeliveryTarget leads with
        # id/meeting_id, so the positional form this once used silently bound
        # "REMINDER" to `id` and every reminder resolved to zero recipients.
        targets = [
            DeliveryTarget(
                delivery_kind=DeliveryKind.REMINDER.value,
                target_type=r["target_type"],
                target_id=r["target_id"],
                meeting_id=r["meeting_id"],
                action_item_id=r["action_item_id"],
            )
            for r in rows
        ]
        if not targets and action.owner_employee_id is not None:      # spec default: assigned employee
            targets = [
                DeliveryTarget(
                    delivery_kind=DeliveryKind.REMINDER.value,
                    target_type=TargetType.ASSIGNEE.value,
                    target_id=action.owner_employee_id,
                    meeting_id=action.meeting_id,
                    action_item_id=action.id,
                )
            ]
        return targets

    def get_setting(self, key: str, default: Any = None) -> Any:
        c = self.factory()
        try:
            r = c.execute("SELECT value_json FROM settings WHERE key=?", (key,)).fetchone()
        finally:
            c.close()
        if r is None:
            return default
        try:
            return json.loads(r["value_json"])
        except (TypeError, ValueError):
            return r["value_json"]


class SqliteDeliveryRecorder:
    """Writes `email_deliveries` rows (Member 1 owns the table; Member 4 supplies the SendResult)."""

    def __init__(self, factory: ConnectionFactory):
        self.factory = factory

    def already_sent(self, reminder_id: int, employee_id: int) -> bool:
        c = self.factory()
        try:
            return c.execute("SELECT 1 FROM email_deliveries WHERE reminder_id=? AND "
                             "recipient_employee_id=? AND status='SENT' LIMIT 1",
                             (reminder_id, employee_id)).fetchone() is not None
        finally:
            c.close()

    def record(self, *, reminder, action, employee, email, result, language, attempted_at,
               late_recovery) -> None:
        ok = bool(result.ok)
        with transaction(self.factory) as c:
            c.execute(
                "INSERT INTO email_deliveries(meeting_id, action_item_id, reminder_id, "
                "recipient_employee_id, recipient_email, subject, language, status, "
                "gmail_message_id, attempted_at, sent_at, error_message) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (action.meeting_id, action.id, reminder.id, employee.id, employee.email,
                 # email_deliveries.subject is NOT NULL DEFAULT '': a delivery
                 # can be recorded with no rendered email (the build failed, or
                 # there were no recipients), and passing None there crashes the
                 # insert instead of logging the failure.
                 (email.subject if email else "") or "",
                 language, "SENT" if ok else "FAILED",
                 result.gmail_message_id if ok else None, to_db(attempted_at),
                 to_db(attempted_at) if ok else None,
                 None if ok else (result.error_message or "send failed")))


# ----------------------------------------------------------------- service
@dataclass
class WorkerDependencies:
    queue: SqliteReminderQueue
    lookup: ActionLookup
    recipient_resolver: RecipientResolver
    email_builder: ReminderEmailBuilder
    email_sender: EmailSender
    recorder: DeliveryRecorder
    audit: Any = None
    retry_policy: RetryPolicy = field(default_factory=RetryPolicy)
    recovery_policy: RecoveryPolicy = field(default_factory=RecoveryPolicy)
    clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc)


@dataclass
class RunSummary:
    claimed: int = 0
    sent: int = 0
    late_recovered: int = 0
    retry_scheduled: int = 0
    failed: int = 0
    skipped_completed: int = 0
    cancelled: int = 0
    lost_claims: int = 0
    released: int = 0
    abandoned_recovered: int = 0

    def as_dict(self) -> dict:
        return asdict(self)


class WorkerService:
    def __init__(self, deps: WorkerDependencies, *, poll_interval: float = 10.0, batch_size: int = 50,
                 stale_claim_after: timedelta = timedelta(minutes=5),
                 heartbeat: Optional[Heartbeat] = None):
        self.d = deps
        self.poll_interval = poll_interval
        self.batch_size = batch_size
        self.heartbeat = heartbeat
        self.claims = ClaimCoordinator(deps.queue, deps.retry_policy, stale_claim_after)
        self._stop = threading.Event()

    # ---- lifecycle
    def stop(self) -> None:
        """Graceful shutdown: finish the reminder in flight, release the rest, exit the loop."""
        self._stop.set()

    def run_forever(self) -> None:
        emit_audit(self.d.audit, AuditNames.WORKER_START, "worker", None)
        try:
            while not self._stop.is_set():
                error, summary = None, RunSummary()
                try:
                    summary = self.run_once(self.d.clock())
                except Exception as exc:                      # never let the loop die
                    log.exception("worker pass failed")
                    error = f"{type(exc).__name__}: {exc}"
                if self.heartbeat:
                    try:
                        self.heartbeat.beat(summary.as_dict(), error)
                    except Exception:
                        log.exception("heartbeat failed")
                self._stop.wait(self.poll_interval)
        finally:
            if self.heartbeat:
                try:
                    self.heartbeat.stopped()
                except Exception:
                    log.exception("final heartbeat failed")
            emit_audit(self.d.audit, AuditNames.WORKER_STOP, "worker", None)

    def run_once(self, now: Optional[datetime] = None) -> RunSummary:
        now = now or self.d.clock()
        s = RunSummary()
        ab = self.claims.recover_abandoned(now)
        s.abandoned_recovered = len(ab.released) + len(ab.retried) + len(ab.failed)
        while not self._stop.is_set():
            batch = self.claims.claim_batch(now, self.batch_size)
            if not batch:
                break
            s.claimed += len(batch)
            for i, reminder in enumerate(batch):
                if self._stop.is_set():
                    s.released += self.claims.release([r.id for r in batch[i:]], now)
                    return s
                self._process(reminder, now, s)
        return s

    # ---- one reminder
    def _process(self, reminder: Reminder, now: datetime, s: RunSummary) -> None:
        q, lookup = self.d.queue, self.d.lookup
        action = lookup.get_action(reminder.action_item_id)
        if action is None:
            if q.transition(reminder.id, [S.CLAIMED], S.FAILED, now, last_error="ACTION_NOT_FOUND"):
                s.failed += 1
                emit_audit(self.d.audit, AuditNames.REMINDER_FAIL, "reminder", reminder.id,
                           metadata={"error": "ACTION_NOT_FOUND"})
            return
        if action.status == ActionStatus.COMPLETED:
            if q.transition(reminder.id, [S.CLAIMED], S.SKIPPED_COMPLETED, now, last_error="ACTION_COMPLETED"):
                s.skipped_completed += 1
                emit_audit(self.d.audit, AuditNames.REMINDER_SKIP_COMPLETED, "reminder", reminder.id)
            return
        if action.status == ActionStatus.CANCELLED:
            if q.transition(reminder.id, [S.CLAIMED], S.CANCELLED, now, last_error="ACTION_CANCELLED"):
                s.cancelled += 1
                emit_audit(self.d.audit, AuditNames.REMINDER_CANCEL, "reminder", reminder.id,
                           metadata={"reason": "ACTION_CANCELLED"})
            return

        late = False
        if reminder.attempt_count == 0:                      # missed-reminder recovery (first attempt only)
            cls = self.d.recovery_policy.classify(reminder.scheduled_at, now)
            if cls == DueClass.EXPIRED:
                if q.transition(reminder.id, [S.CLAIMED], S.FAILED, now, last_error=MISSED_EXPIRED_ERROR):
                    s.failed += 1
                    emit_audit(self.d.audit, AuditNames.REMINDER_FAIL, "reminder", reminder.id,
                               metadata={"error": MISSED_EXPIRED_ERROR})
                return
            late = cls == DueClass.LATE_RECOVERY

        # CLAIMED -> SENDING (fails if completion/cancel/reschedule won the race)
        if not q.transition(reminder.id, [S.CLAIMED], S.SENDING, now, increment_attempt=True):
            s.lost_claims += 1
            return
        attempt = reminder.attempt_count + 1

        meeting = lookup.get_meeting(action.meeting_id)
        # "ENGLISH" was not a storable value: email_deliveries.language is
        # CHECK (language IN ('AR','EN','BILINGUAL')), so this fallback made
        # every delivery insert fail whenever the setting row was missing.
        # DEFAULT_SETTINGS["default_email_language"] is "AR"; resolve_language
        # also maps anything stale onto a real mode rather than raising.
        language = resolve_language(
            (meeting.email_language if meeting else None)
            or lookup.get_setting("default_email_language", EmailLanguage.AR.value)
        )
        employees = self._recipients(lookup.get_reminder_targets(action))
        if not employees:
            q.transition(reminder.id, [S.SENDING], S.FAILED, now, last_error=NO_RECIPIENTS)
            s.failed += 1
            emit_audit(self.d.audit, AuditNames.REMINDER_FAIL, "reminder", reminder.id,
                       metadata={"error": NO_RECIPIENTS})
            return

        delivered, retryable_errors, permanent_errors = 0, [], []
        for emp in employees:
            if self.d.recorder.already_sent(reminder.id, emp.id):      # duplicate-send protection
                delivered += 1
                continue
            email, result = None, None
            if not emp.email:
                result = SendResult(False, error=f"employee {emp.id} has no email", retryable=False)
            else:
                try:
                    email = self.d.email_builder.build_reminder(emp, action, meeting, language)
                    if not email.to_email:
                        # The canonical RenderedEmail is frozen and addresses
                        # one recipient; replace rather than mutate.
                        email = replace(email, to_email=emp.email)
                    result = self.d.email_sender.send(email)
                except Exception as exc:
                    result = SendResult(
                        ok=False,
                        error_message=f"{type(exc).__name__}: {exc}",
                        retryable=True,
                    )
            try:
                self.d.recorder.record(reminder=reminder, action=action, employee=emp, email=email,
                                       result=result, language=language, attempted_at=now,
                                       late_recovery=late)
            except Exception:
                log.exception("delivery record failed for reminder %s", reminder.id)
            if result.ok:
                delivered += 1
            elif result.retryable:
                retryable_errors.append(f"{emp.id}: {result.error_message}")
            else:
                permanent_errors.append(f"{emp.id}: {result.error_message}")

        if retryable_errors:
            nxt = self.d.retry_policy.next_attempt(attempt, now)
            err = "; ".join(retryable_errors + permanent_errors)[:900]
            if nxt is None:
                q.transition(reminder.id, [S.SENDING], S.FAILED, now, last_error=err)
                s.failed += 1
                emit_audit(self.d.audit, AuditNames.REMINDER_FAIL, "reminder", reminder.id,
                           metadata={"error": err, "attempts": attempt})
            else:
                q.transition(reminder.id, [S.SENDING], S.RETRY_WAIT, now, next_attempt_at=nxt, last_error=err)
                s.retry_scheduled += 1
                emit_audit(self.d.audit, AuditNames.REMINDER_RETRY, "reminder", reminder.id,
                           metadata={"error": err, "attempt": attempt, "next_attempt_at": to_db(nxt)})
        elif delivered == 0:
            err = "; ".join(permanent_errors)[:900]
            q.transition(reminder.id, [S.SENDING], S.FAILED, now, last_error=err)
            s.failed += 1
            emit_audit(self.d.audit, AuditNames.REMINDER_FAIL, "reminder", reminder.id,
                       metadata={"error": err})
        else:
            note = ("PARTIAL: " + "; ".join(permanent_errors)[:880]) if permanent_errors else None
            q.transition(reminder.id, [S.SENDING], S.SENT, now, sent_at=now, last_error=note)
            s.sent += 1
            meta = {"recipients": delivered, "attempt": attempt, "late_recovery": late}
            if late:
                s.late_recovered += 1
                meta["late_by_seconds"] = int((now - reminder.scheduled_at).total_seconds())
                emit_audit(self.d.audit, AuditNames.REMINDER_LATE_RECOVERY, "reminder", reminder.id,
                           metadata=meta)
            emit_audit(self.d.audit, AuditNames.REMINDER_SEND, "reminder", reminder.id, metadata=meta)

    def _recipients(self, targets: list[DeliveryTarget]) -> list[Employee]:
        if not targets:
            return []
        seen, out = set(), []
        for e in self.d.recipient_resolver.resolve(targets):
            k = (e.id, (e.email or "").lower())
            if e.id in seen or k in seen:
                continue
            seen.add(e.id), seen.add(k)
            out.append(e)
        return out
