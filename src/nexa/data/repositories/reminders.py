"""Reminder persistence.

Storage primitives only. The scheduling *policy* (when to create occurrences,
retry backoff, missed-reminder recovery) belongs to Member 5; this repository
gives that worker a safe, idempotent place to keep its state.
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from ...contracts.scheduling import Reminder, ReminderRule, ReminderStatus
from ...core.errors import NotFoundError
from ...core.timezone import isoformat_utc
from ..models import row_to_reminder, row_to_reminder_rule, time_to_db
from ..transactions import unit_of_work
from .base import BaseRepository

_COLUMNS = (
    "id, action_item_id, scheduled_at, status, attempt_count, next_attempt_at, "
    "claimed_at, sent_at, last_error, idempotency_key, created_at, updated_at"
)
_RULE_COLUMNS = (
    "id, action_item_id, rule_type, offset_minutes, fixed_local_time, enabled, created_at"
)

# Occurrences that have not been delivered yet and can still be cancelled.
OPEN_STATUSES = (
    ReminderStatus.PENDING.value,
    ReminderStatus.CLAIMED.value,
    ReminderStatus.RETRY_WAIT.value,
    ReminderStatus.SNOOZED.value,
)


class ReminderRepository(BaseRepository):
    # ------------------------------------------------------------------
    # reminders
    # ------------------------------------------------------------------
    def create(self, reminder: Reminder) -> Reminder:
        now = self.now_str()
        with unit_of_work(self.db):
            self.db.execute(
                """
                INSERT INTO reminders (
                    action_item_id, scheduled_at, status, attempt_count,
                    next_attempt_at, claimed_at, sent_at, last_error,
                    idempotency_key, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    reminder.action_item_id,
                    isoformat_utc(reminder.scheduled_at, self.tz),
                    reminder.status,
                    reminder.attempt_count,
                    isoformat_utc(reminder.next_attempt_at, self.tz),
                    isoformat_utc(reminder.claimed_at, self.tz),
                    isoformat_utc(reminder.sent_at, self.tz),
                    reminder.last_error,
                    reminder.idempotency_key,
                    now,
                    now,
                ),
            )
            reminder_id = self._last_insert_id()
        return self.get_or_raise(reminder_id)

    def update_status(
        self,
        reminder_id: int,
        status: str,
        *,
        last_error: Optional[str] = None,
        sent_at: Optional[datetime] = None,
        next_attempt_at: Optional[datetime] = None,
        increment_attempt: bool = False,
    ) -> Reminder:
        with unit_of_work(self.db):
            cursor = self.db.execute(
                """
                UPDATE reminders
                   SET status = ?,
                       last_error = ?,
                       sent_at = COALESCE(?, sent_at),
                       next_attempt_at = ?,
                       attempt_count = attempt_count + ?,
                       updated_at = ?
                 WHERE id = ?
                """,
                (
                    getattr(status, "value", status),
                    last_error,
                    isoformat_utc(sent_at, self.tz),
                    isoformat_utc(next_attempt_at, self.tz),
                    1 if increment_attempt else 0,
                    self.now_str(),
                    reminder_id,
                ),
            )
            if cursor.rowcount == 0:
                raise NotFoundError("reminder", reminder_id)
        return self.get_or_raise(reminder_id)

    def reschedule(self, reminder_id: int, scheduled_at: datetime, *, status: str = ReminderStatus.SNOOZED.value) -> Reminder:
        """Move one occurrence (snooze). The task deadline is untouched."""
        with unit_of_work(self.db):
            cursor = self.db.execute(
                "UPDATE reminders SET scheduled_at = ?, status = ?, updated_at = ? WHERE id = ?",
                (
                    isoformat_utc(scheduled_at, self.tz),
                    getattr(status, "value", status),
                    self.now_str(),
                    reminder_id,
                ),
            )
            if cursor.rowcount == 0:
                raise NotFoundError("reminder", reminder_id)
        return self.get_or_raise(reminder_id)

    def cancel_open_for_action(
        self, action_item_id: int, *, status: str = ReminderStatus.CANCELLED.value
    ) -> int:
        """Close every not-yet-sent occurrence for an action item.

        Used when a task is completed (`SKIPPED_COMPLETED`), cancelled, or
        rescheduled (`CANCELLED`, then Member 5 creates fresh occurrences).
        """
        placeholders = ",".join("?" * len(OPEN_STATUSES))
        with unit_of_work(self.db):
            cursor = self.db.execute(
                f"""
                UPDATE reminders
                   SET status = ?, updated_at = ?
                 WHERE action_item_id = ? AND status IN ({placeholders})
                """,
                (
                    getattr(status, "value", status),
                    self.now_str(),
                    action_item_id,
                    *OPEN_STATUSES,
                ),
            )
            return cursor.rowcount

    def get(self, reminder_id: int) -> Optional[Reminder]:
        row = self.db.query_one(f"SELECT {_COLUMNS} FROM reminders WHERE id = ?", (reminder_id,))
        return None if row is None else row_to_reminder(row)

    def get_or_raise(self, reminder_id: int) -> Reminder:
        reminder = self.get(reminder_id)
        if reminder is None:
            raise NotFoundError("reminder", reminder_id)
        return reminder

    def get_by_idempotency_key(self, key: str) -> Optional[Reminder]:
        row = self.db.query_one(
            f"SELECT {_COLUMNS} FROM reminders WHERE idempotency_key = ?", (key,)
        )
        return None if row is None else row_to_reminder(row)

    def for_action(self, action_item_id: int) -> List[Reminder]:
        rows = self.db.query_all(
            f"SELECT {_COLUMNS} FROM reminders WHERE action_item_id = ? ORDER BY scheduled_at",
            (action_item_id,),
        )
        return [row_to_reminder(row) for row in rows]

    def due(self, now: datetime, limit: int = 100) -> List[Reminder]:
        """Pending occurrences whose time has arrived, oldest first."""
        rows = self.db.query_all(
            f"""
            SELECT {_COLUMNS} FROM reminders
             WHERE status IN ('PENDING', 'RETRY_WAIT', 'SNOOZED')
               AND scheduled_at <= ?
               AND (next_attempt_at IS NULL OR next_attempt_at <= ?)
             ORDER BY scheduled_at
             LIMIT ?
            """,
            (isoformat_utc(now, self.tz), isoformat_utc(now, self.tz), limit),
        )
        return [row_to_reminder(row) for row in rows]

    def count(self, *, status: Optional[str] = None) -> int:
        if status is None:
            return int(self.db.query_value("SELECT COUNT(*) FROM reminders", default=0))
        return int(
            self.db.query_value(
                "SELECT COUNT(*) FROM reminders WHERE status = ?",
                (getattr(status, "value", status),),
                default=0,
            )
        )

    def action_ids_with_open_reminders(self) -> List[int]:
        """Action items that still have a live reminder (the Snoozed filter)."""
        placeholders = ",".join("?" * len(OPEN_STATUSES))
        rows = self.db.query_all(
            f"SELECT DISTINCT action_item_id FROM reminders WHERE status IN ({placeholders})",
            OPEN_STATUSES,
        )
        return [row["action_item_id"] for row in rows]

    # ------------------------------------------------------------------
    # reminder rules
    # ------------------------------------------------------------------
    def add_rule(self, rule: ReminderRule) -> ReminderRule:
        with unit_of_work(self.db):
            self.db.execute(
                """
                INSERT INTO reminder_rules (
                    action_item_id, rule_type, offset_minutes, fixed_local_time,
                    enabled, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    rule.action_item_id,
                    getattr(rule.rule_type, "value", rule.rule_type),
                    rule.offset_minutes,
                    time_to_db(rule.fixed_local_time),
                    1 if rule.enabled else 0,
                    self.now_str(),
                ),
            )
            rule_id = self._last_insert_id()
        row = self.db.query_one(
            f"SELECT {_RULE_COLUMNS} FROM reminder_rules WHERE id = ?", (rule_id,)
        )
        return row_to_reminder_rule(row)

    def rules_for_action(self, action_item_id: int) -> List[ReminderRule]:
        rows = self.db.query_all(
            f"SELECT {_RULE_COLUMNS} FROM reminder_rules WHERE action_item_id = ? ORDER BY id",
            (action_item_id,),
        )
        return [row_to_reminder_rule(row) for row in rows]

    def set_rule_enabled(self, rule_id: int, enabled: bool) -> None:
        with unit_of_work(self.db):
            cursor = self.db.execute(
                "UPDATE reminder_rules SET enabled = ? WHERE id = ?",
                (1 if enabled else 0, rule_id),
            )
            if cursor.rowcount == 0:
                raise NotFoundError("reminder_rule", rule_id)
