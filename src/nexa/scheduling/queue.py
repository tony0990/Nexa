"""SQLite reminder queue - the source of truth for reminder state.

All state changes are conditional UPDATEs (`WHERE id=? AND status IN (...)`) inside
BEGIN IMMEDIATE transactions, so two workers/loops can never act on the same reminder.
"""
from __future__ import annotations

import logging
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Iterable, Optional, Sequence

from nexa.contracts.audit import ActorType, AuditEvent
from nexa.contracts.meetings import ActionItem
from nexa.contracts.scheduling import Reminder

from .calculator import PlannedReminder, calculate_reminders, from_db, to_db
from .rules import ReminderPolicy
from .states import (
    AuditNames,
    ReminderStatus as S,
    ReminderType,
    assert_transition,
    make_idempotency_key,
)

log = logging.getLogger("nexa.scheduling.queue")
ConnectionFactory = Callable[[], sqlite3.Connection]

_ACTIVE_FOR_KEY = (S.PENDING, S.CLAIMED, S.SENDING, S.SENT, S.RETRY_WAIT)
_SETTABLE = {"claimed_at", "sent_at", "next_attempt_at", "last_error", "scheduled_at"}


def connect(db_path: str) -> sqlite3.Connection:
    """Connection tuned for a DB shared by Nexa.exe and NexaWorker.exe."""
    conn = sqlite3.connect(db_path, timeout=30, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


@contextmanager
def transaction(factory: ConnectionFactory, conn: Optional[sqlite3.Connection] = None):
    """Open a BEGIN IMMEDIATE transaction, or join the caller's connection."""
    if conn is not None:
        yield conn
        return
    c = factory()
    try:
        c.execute("BEGIN IMMEDIATE")
        yield c
        c.execute("COMMIT")
    except BaseException:
        try:
            c.execute("ROLLBACK")
        except sqlite3.Error:
            pass
        raise
    finally:
        c.close()


def emit_audit(audit: Any, event_type: str, entity_type: str, entity_id: Optional[int],
               *, actor_type: str = ActorType.SYSTEM.value, actor_id: Optional[str] = None,
               old: Optional[dict] = None, new: Optional[dict] = None,
               metadata: Optional[dict] = None) -> None:
    """Record via the AuditService contract; audit failures never break scheduling."""
    if audit is None:
        return
    try:
        audit.record(AuditEvent(actor_type=actor_type, actor_id=actor_id, event_type=event_type,
                                entity_type=entity_type, entity_id=entity_id,
                                old_value=old, new_value=new, metadata=metadata or {}))
    except Exception:  # pragma: no cover
        log.exception("audit record failed for %s", event_type)


def row_to_reminder(r: sqlite3.Row) -> Reminder:
    return Reminder(
        id=r["id"], action_item_id=r["action_item_id"],
        scheduled_at=from_db(r["scheduled_at"]), status=S(r["status"]),
        attempt_count=r["attempt_count"] or 0,
        next_attempt_at=from_db(r["next_attempt_at"]), claimed_at=from_db(r["claimed_at"]),
        sent_at=from_db(r["sent_at"]), last_error=r["last_error"],
        idempotency_key=r["idempotency_key"] or "",
        created_at=from_db(r["created_at"]), updated_at=from_db(r["updated_at"]),
    )


def _now() -> datetime:
    return datetime.now(timezone.utc)


class SqliteReminderQueue:
    """Implements the `ReminderQueue` contract on top of SQLite."""

    def __init__(self, connection_factory: ConnectionFactory,
                 policy: Optional[ReminderPolicy] = None,
                 clock: Callable[[], datetime] = _now, audit: Any = None):
        self.factory = connection_factory
        self.policy = policy or ReminderPolicy.default()
        self.clock = clock
        self.audit = audit

    # ------------------------------------------------------------ contract
    def enqueue_for_action(self, action: ActionItem) -> list[Reminder]:
        now = self.clock()
        planned = calculate_reminders(action.due_date, action.due_time, action.due_at,
                                      self.policy, now)
        with transaction(self.factory) as c:
            self.replace_rules(c, action.id, self.policy, now)
            created: list[Reminder] = []
            all_rows = self.insert_planned(c, action.id, planned, now, created_out=created)
        self.audit_created(created)
        return all_rows

    def audit_created(self, reminders: Sequence[Reminder], *, actor_type: str = ActorType.SYSTEM.value,
                      actor_id: Optional[str] = None) -> None:
        for r in reminders:
            emit_audit(self.audit, AuditNames.REMINDER_CREATE, "reminder", r.id,
                       actor_type=actor_type, actor_id=actor_id,
                       new={"action_item_id": r.action_item_id,
                            "scheduled_at": to_db(r.scheduled_at), "status": S(r.status).value})

    def claim_due(self, now: datetime, limit: int) -> list[Reminder]:
        """Atomically claim up to `limit` due reminders (PENDING or due RETRY_WAIT)."""
        ts = to_db(now)
        with transaction(self.factory) as c:
            ids = [r["id"] for r in c.execute(
                "SELECT id FROM reminders WHERE "
                "(status='PENDING' AND scheduled_at<=?) OR "
                "(status='RETRY_WAIT' AND next_attempt_at<=?) "
                "ORDER BY scheduled_at, id LIMIT ?", (ts, ts, limit)).fetchall()]
            claimed: list[int] = []
            for rid in ids:
                cur = c.execute(
                    "UPDATE reminders SET status='CLAIMED', claimed_at=?, updated_at=? "
                    "WHERE id=? AND status IN ('PENDING','RETRY_WAIT')", (ts, ts, rid))
                if cur.rowcount == 1:
                    claimed.append(rid)
            return [self._get(c, rid) for rid in claimed]

    # ------------------------------------------------------------ writes
    def replace_rules(self, c: sqlite3.Connection, action_id: int,
                      policy: ReminderPolicy, now: datetime) -> None:
        c.execute("DELETE FROM reminder_rules WHERE action_item_id=?", (action_id,))
        for rule in policy.rules:
            c.execute(
                "INSERT INTO reminder_rules(action_item_id, rule_type, offset_minutes, "
                "fixed_local_time, enabled, created_at) VALUES (?,?,?,?,?,?)",
                (action_id, rule.rule_type, rule.offset_minutes,
                 rule.fixed_local_time.strftime("%H:%M") if rule.fixed_local_time else None,
                 1 if rule.enabled else 0, to_db(now)))

    def insert_planned(self, c: sqlite3.Connection, action_id: int,
                       planned: Sequence[PlannedReminder], now: datetime,
                       *, extra_key: Optional[str] = None,
                       created_out: Optional[list] = None) -> list[Reminder]:
        """Returns every matching reminder; newly inserted ones are also appended to `created_out`."""
        out: list[Reminder] = []
        for p in planned:
            out.append(self._insert_one(c, action_id, p.reminder_type, p.scheduled_at, now,
                                        extra_key, created_out))
        return out

    def insert_reminder(self, c: sqlite3.Connection, action_id: int, reminder_type: ReminderType,
                        scheduled_at: datetime, now: datetime,
                        extra_key: Optional[str] = None) -> Reminder:
        return self._insert_one(c, action_id, reminder_type, scheduled_at, now, extra_key, None)

    def _insert_one(self, c, action_id, rtype, scheduled_at, now, extra_key, created_out) -> Reminder:
        base = make_idempotency_key(action_id, rtype, scheduled_at, extra_key)
        key, n = base, 0
        while True:
            row = c.execute("SELECT id, status FROM reminders WHERE idempotency_key=?",
                            (key,)).fetchone()
            if row is None:
                break
            if S(row["status"]) in _ACTIVE_FOR_KEY:
                return self._get(c, row["id"])      # idempotent: already scheduled/sent
            n += 1                                   # cancelled/failed/snoozed earlier -> new generation
            key = f"{base}#{n}"
        ts = to_db(now)
        cur = c.execute(
            "INSERT INTO reminders(action_item_id, scheduled_at, status, attempt_count, "
            "next_attempt_at, claimed_at, sent_at, last_error, idempotency_key, created_at, "
            "updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (action_id, to_db(scheduled_at), S.PENDING.value, 0, None, None, None, None,
             key, ts, ts))
        rem = self._get(c, cur.lastrowid)       # audit is emitted AFTER commit by callers
        if created_out is not None:
            created_out.append(rem)
        return rem

    def transition(self, reminder_id: int, from_states: Iterable[S], to_state: S,
                   now: Optional[datetime] = None, *, conn: Optional[sqlite3.Connection] = None,
                   increment_attempt: bool = False, **fields) -> bool:
        """Conditional state change. Returns False when another actor got there first."""
        from_states = [S(s) for s in from_states]
        for s in from_states:
            assert_transition(s, S(to_state))
        bad = set(fields) - _SETTABLE
        if bad:
            raise ValueError(f"cannot set {bad}")
        now = now or self.clock()
        sets, params = ["status=?", "updated_at=?"], [S(to_state).value, to_db(now)]
        if increment_attempt:
            sets.append("attempt_count=attempt_count+1")
        for k, v in fields.items():
            sets.append(f"{k}=?")
            params.append(to_db(v) if isinstance(v, datetime) else v)
        ph = ",".join("?" * len(from_states))
        params += [reminder_id] + [s.value for s in from_states]
        with transaction(self.factory, conn) as c:
            cur = c.execute(f"UPDATE reminders SET {', '.join(sets)} "
                            f"WHERE id=? AND status IN ({ph})", params)
            return cur.rowcount == 1

    def claim_one(self, reminder_id: int, now: Optional[datetime] = None) -> bool:
        """UPDATE reminders SET status='CLAIMED' WHERE id=? AND status='PENDING'."""
        now = now or self.clock()
        return self.transition(reminder_id, [S.PENDING], S.CLAIMED, now, claimed_at=now)

    def release_claims(self, reminder_ids: Iterable[int], now: Optional[datetime] = None) -> int:
        n = 0
        for rid in reminder_ids:
            if self.transition(rid, [S.CLAIMED], S.PENDING, now, claimed_at=None):
                n += 1
        return n

    def cancel_unsent_for_action(self, c: sqlite3.Connection, action_id: int, to_state: S,
                                 now: datetime, *, reason: str) -> list[int]:
        """Unsent (PENDING/RETRY_WAIT/CLAIMED) -> to_state. Sent history is preserved."""
        ids = [r["id"] for r in c.execute(
            "SELECT id FROM reminders WHERE action_item_id=? AND status IN "
            "('PENDING','RETRY_WAIT','CLAIMED')", (action_id,)).fetchall()]
        done = []
        for rid in ids:
            cur = c.execute(
                "UPDATE reminders SET status=?, last_error=?, updated_at=? WHERE id=? "
                "AND status IN ('PENDING','RETRY_WAIT','CLAIMED')",
                (S(to_state).value, reason, to_db(now), rid))
            if cur.rowcount == 1:
                done.append(rid)
        return done

    def cancel_for_action(self, action_id: int, *, reason: str = "CANCELLED_BY_USER") -> list[int]:
        now = self.clock()
        with transaction(self.factory) as c:
            return self.cancel_unsent_for_action(c, action_id, S.CANCELLED, now, reason=reason)

    # ------------------------------------------------------------ reads
    def _get(self, c: sqlite3.Connection, reminder_id: int) -> Optional[Reminder]:
        r = c.execute("SELECT * FROM reminders WHERE id=?", (reminder_id,)).fetchone()
        return row_to_reminder(r) if r else None

    def get(self, reminder_id: int, conn: Optional[sqlite3.Connection] = None) -> Optional[Reminder]:
        if conn is not None:
            return self._get(conn, reminder_id)
        c = self.factory()
        try:
            return self._get(c, reminder_id)
        finally:
            c.close()

    def list_for_action(self, action_id: int, statuses: Optional[Iterable[S]] = None) -> list[Reminder]:
        c = self.factory()
        try:
            sql, params = "SELECT * FROM reminders WHERE action_item_id=?", [action_id]
            if statuses:
                st = [S(s).value for s in statuses]
                sql += f" AND status IN ({','.join('?' * len(st))})"
                params += st
            return [row_to_reminder(r) for r in c.execute(sql + " ORDER BY scheduled_at, id", params)]
        finally:
            c.close()

    def find_stale(self, status: S, older_than: datetime) -> list[Reminder]:
        """CLAIMED -> by claimed_at; SENDING -> by updated_at."""
        col = "claimed_at" if S(status) == S.CLAIMED else "updated_at"
        c = self.factory()
        try:
            return [row_to_reminder(r) for r in c.execute(
                f"SELECT * FROM reminders WHERE status=? AND {col}<=? ORDER BY id",
                (S(status).value, to_db(older_than)))]
        finally:
            c.close()

    def count_by_status(self) -> dict[str, int]:
        c = self.factory()
        try:
            return {r["status"]: r["n"] for r in c.execute(
                "SELECT status, COUNT(*) AS n FROM reminders GROUP BY status")}
        finally:
            c.close()
