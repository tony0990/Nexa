"""Reschedule: new deadline => obsolete unsent reminders invalidated, new ones calculated."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from nexa.contracts.scheduling import Reminder

from .calculator import CAIRO, UTC, calculate_reminders, ensure_aware, to_db
from .queue import SqliteReminderQueue, emit_audit, transaction
from .rules import ReminderPolicy
from .states import ActionStatus, AuditNames, ReminderStatus as S


class RescheduleError(Exception):
    pass


def reschedule_action(queue: SqliteReminderQueue, action_id: int, new_due_at: datetime, *,
                      policy: Optional[ReminderPolicy] = None, time_specified: bool = True,
                      actor_type: str = "user", actor_id: Optional[str] = "admin",
                      audit: Any = None) -> list[Reminder]:
    audit = audit if audit is not None else queue.audit
    policy = policy or queue.policy
    now = queue.clock()
    local = ensure_aware(new_due_at).astimezone(CAIRO)
    due_date = local.date()
    due_time = local.timetz().replace(tzinfo=None) if time_specified else None

    with transaction(queue.factory) as c:
        row = c.execute("SELECT status, due_date, due_time, due_at FROM action_items WHERE id=?",
                        (action_id,)).fetchone()
        if row is None:
            raise RescheduleError(f"action {action_id} not found")
        if row["status"] in (ActionStatus.CANCELLED,):
            raise RescheduleError("cancelled actions cannot be rescheduled")
        old_value = {"due_date": row["due_date"], "due_time": row["due_time"], "due_at": row["due_at"]}
        new_status = ActionStatus.PENDING if row["status"] == ActionStatus.OVERDUE else row["status"]
        c.execute("UPDATE action_items SET due_date=?, due_time=?, due_at=?, status=?, updated_at=? "
                  "WHERE id=?",
                  (due_date.isoformat(), due_time.strftime("%H:%M") if due_time else None,
                   to_db(local), new_status, to_db(now), action_id))
        cancelled = queue.cancel_unsent_for_action(c, action_id, S.CANCELLED, now,
                                                   reason="OBSOLETE_AFTER_RESCHEDULE")
        new_reminders: list[Reminder] = []
        created: list[Reminder] = []
        if row["status"] != ActionStatus.COMPLETED:
            queue.replace_rules(c, action_id, policy, now)
            planned = calculate_reminders(due_date, due_time, local, policy, now)
            new_reminders = queue.insert_planned(c, action_id, planned, now, created_out=created)

    emit_audit(audit, AuditNames.ACTION_RESCHEDULE, "action_item", action_id,
               actor_type=actor_type, actor_id=actor_id, old=old_value,
               new={"due_date": due_date.isoformat(),
                    "due_time": due_time.strftime("%H:%M") if due_time else None},
               metadata={"cancelled_reminder_ids": cancelled,
                         "new_reminder_ids": [r.id for r in new_reminders]})
    queue.audit_created(created, actor_type=actor_type, actor_id=actor_id)
    for rid in cancelled:
        emit_audit(audit, AuditNames.REMINDER_CANCEL, "reminder", rid, actor_type=actor_type,
                   actor_id=actor_id, metadata={"reason": "OBSOLETE_AFTER_RESCHEDULE"})
    return new_reminders
