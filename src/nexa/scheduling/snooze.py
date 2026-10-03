"""Snooze: moves a reminder occurrence, never the task deadline.

Options: 30 minutes | 1 hour | 3 hours | Tomorrow morning | Custom date/time
The original reminder becomes SNOOZED (kept for history); a new PENDING occurrence
is created at the new time. `action_items` is never touched.
"""
from __future__ import annotations

from datetime import datetime, time, timedelta
from enum import Enum
from typing import Any, Optional

from .calculator import CAIRO, UTC, ensure_aware, local_combine, to_db
from .queue import SqliteReminderQueue, emit_audit, transaction
from .states import ActionStatus, AuditNames, ReminderStatus as S, ReminderType
from nexa.contracts.scheduling import Reminder


class SnoozeError(Exception):
    pass


class ReminderNotSnoozable(SnoozeError):
    pass


class InvalidSnoozeTime(SnoozeError):
    pass


class SnoozeOption(str, Enum):
    MINUTES_30 = "30_MINUTES"
    HOUR_1 = "1_HOUR"
    HOURS_3 = "3_HOURS"
    TOMORROW_MORNING = "TOMORROW_MORNING"
    CUSTOM = "CUSTOM"


def resolve_snooze_time(option: SnoozeOption, now: datetime, *,
                        morning_time: time = time(8, 0),
                        custom: Optional[datetime] = None) -> datetime:
    now = ensure_aware(now, UTC)
    option = SnoozeOption(option)
    if option == SnoozeOption.MINUTES_30:
        return now + timedelta(minutes=30)
    if option == SnoozeOption.HOUR_1:
        return now + timedelta(hours=1)
    if option == SnoozeOption.HOURS_3:
        return now + timedelta(hours=3)
    if option == SnoozeOption.TOMORROW_MORNING:
        tomorrow = now.astimezone(CAIRO).date() + timedelta(days=1)
        return local_combine(tomorrow, morning_time).astimezone(UTC)
    if custom is None:
        raise InvalidSnoozeTime("custom date/time required")
    return ensure_aware(custom).astimezone(UTC)


def snooze_reminder(queue: SqliteReminderQueue, reminder_id: int, new_time: datetime, *,
                    actor_type: str = "user", actor_id: Optional[str] = "admin",
                    now: Optional[datetime] = None, audit: Any = None) -> Reminder:
    audit = audit if audit is not None else queue.audit
    now = ensure_aware(now or queue.clock(), UTC)
    new_time = ensure_aware(new_time).astimezone(UTC).replace(second=0, microsecond=0)
    if new_time <= now:
        raise InvalidSnoozeTime("snooze time must be in the future")

    with transaction(queue.factory) as c:
        old = queue.get(reminder_id, c)
        if old is None:
            raise ReminderNotSnoozable(f"reminder {reminder_id} not found")
        if S(old.status) not in (S.PENDING, S.RETRY_WAIT):
            raise ReminderNotSnoozable(f"reminder {reminder_id} is {S(old.status).value}")
        action = c.execute("SELECT status, due_at, due_date, due_time FROM action_items WHERE id=?",
                           (old.action_item_id,)).fetchone()
        if action is None or action["status"] in (ActionStatus.COMPLETED, ActionStatus.CANCELLED):
            raise ReminderNotSnoozable("task is completed or cancelled")
        if not queue.transition(reminder_id, [S.PENDING, S.RETRY_WAIT], S.SNOOZED, now, conn=c):
            raise ReminderNotSnoozable("reminder was claimed by the worker")
        new = queue.insert_reminder(c, old.action_item_id, ReminderType.SNOOZE, new_time, now,
                                    extra_key=f"from{reminder_id}")
    emit_audit(audit, AuditNames.REMINDER_SNOOZE, "reminder", reminder_id,
               actor_type=actor_type, actor_id=actor_id,
               old={"scheduled_at": to_db(old.scheduled_at)},
               new={"scheduled_at": to_db(new_time), "new_reminder_id": new.id},
               metadata={"action_item_id": old.action_item_id, "deadline_changed": False})
    return new
