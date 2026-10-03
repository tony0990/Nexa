"""ReminderService - public interface of the scheduling subsystem (Member 5)."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from nexa.contracts.meetings import ActionItem
from nexa.contracts.scheduling import Reminder

from .calculator import calculate_reminders
from .queue import SqliteReminderQueue, emit_audit, transaction
from .reschedule import reschedule_action
from .rules import ReminderPolicy
from .snooze import snooze_reminder
from .states import AuditNames


class ReminderService:
    def __init__(self, queue: SqliteReminderQueue, audit: Any = None,
                 default_policy: Optional[ReminderPolicy] = None):
        self.queue = queue
        self.audit = audit if audit is not None else queue.audit
        self.default_policy = default_policy or queue.policy

    def schedule_for_action(self, action: ActionItem,
                            policy: Optional[ReminderPolicy] = None) -> list[Reminder]:
        """Approval of an action creates independent reminder records (one row each)."""
        policy = policy or self.default_policy
        now = self.queue.clock()
        planned = calculate_reminders(action.due_date, action.due_time, action.due_at, policy, now)
        with transaction(self.queue.factory) as c:
            self.queue.replace_rules(c, action.id, policy, now)
            created: list[Reminder] = []
            reminders = self.queue.insert_planned(c, action.id, planned, now, created_out=created)
        self.queue.audit_created(created, actor_type="user")
        return reminders

    def cancel_for_action(self, action_id: int, actor: Optional[str] = "admin") -> list[int]:
        ids = self.queue.cancel_for_action(action_id)
        for rid in ids:
            emit_audit(self.audit, AuditNames.REMINDER_CANCEL, "reminder", rid,
                       actor_type="user", actor_id=actor,
                       metadata={"action_item_id": action_id})
        return ids

    def snooze(self, reminder_id: int, new_time: datetime,
               actor: Optional[str] = "admin") -> Reminder:
        return snooze_reminder(self.queue, reminder_id, new_time, actor_id=actor, audit=self.audit)

    def reschedule_action(self, action_id: int, new_due_at: datetime, *,
                          time_specified: bool = True, actor: Optional[str] = "admin"
                          ) -> list[Reminder]:
        return reschedule_action(self.queue, action_id, new_due_at, policy=self.default_policy,
                                 time_specified=time_specified, actor_id=actor, audit=self.audit)
