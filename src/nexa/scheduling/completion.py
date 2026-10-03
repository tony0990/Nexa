"""Mark Complete.

1. action_items.status = COMPLETED  2. completed_at recorded  3. actor audited
4. future unsent reminders -> SKIPPED_COMPLETED (sent history preserved)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

from .calculator import to_db
from .queue import SqliteReminderQueue, emit_audit, transaction
from .states import ActionStatus, AuditNames, ReminderStatus as S


class CompletionError(Exception):
    pass


@dataclass
class CompletionResult:
    action_id: int
    completed_at: Optional[datetime]
    skipped_reminder_ids: list[int] = field(default_factory=list)
    already_completed: bool = False


class CompletionService:
    def __init__(self, queue: SqliteReminderQueue, audit: Any = None):
        self.queue = queue
        self.audit = audit if audit is not None else queue.audit

    def mark_complete(self, action_id: int, actor: Optional[str] = "admin",
                      actor_type: str = "user") -> CompletionResult:
        now = self.queue.clock()
        with transaction(self.queue.factory) as c:
            row = c.execute("SELECT status, completed_at FROM action_items WHERE id=?",
                            (action_id,)).fetchone()
            if row is None:
                raise CompletionError(f"action {action_id} not found")
            if row["status"] == ActionStatus.COMPLETED:
                return CompletionResult(action_id, None, [], already_completed=True)
            if row["status"] == ActionStatus.CANCELLED:
                raise CompletionError("cancelled actions cannot be completed")
            c.execute("UPDATE action_items SET status=?, completed_at=?, updated_at=? WHERE id=?",
                      (ActionStatus.COMPLETED, to_db(now), to_db(now), action_id))
            skipped = self.queue.cancel_unsent_for_action(
                c, action_id, S.SKIPPED_COMPLETED, now, reason="ACTION_COMPLETED")
        emit_audit(self.audit, AuditNames.ACTION_COMPLETE, "action_item", action_id,
                   actor_type=actor_type, actor_id=actor,
                   old={"status": row["status"]},
                   new={"status": ActionStatus.COMPLETED, "completed_at": to_db(now)},
                   metadata={"skipped_reminder_ids": skipped})
        for rid in skipped:
            emit_audit(self.audit, AuditNames.REMINDER_SKIP_COMPLETED, "reminder", rid,
                       actor_type=actor_type, actor_id=actor)
        return CompletionResult(action_id, now, skipped)
