"""Action-item persistence.

`source_text` and `raw_date_phrase` are the original spoken evidence: this
repository writes them once and never rewrites them from the normalized
interpretation (Section 2.2).
"""

from __future__ import annotations

from datetime import date
from typing import Iterable, List, Optional, Sequence

from ...contracts.meetings import ActionItem, ActionStatus
from ...core.errors import ConflictError, NotFoundError
from ...core.timezone import combine_local, isoformat_utc
from ...core.validation import normalize_search_text
from ..models import date_to_db, row_to_action, time_to_db
from ..transactions import unit_of_work
from .base import BaseRepository

_COLUMNS = (
    "id, meeting_id, task, owner_employee_id, owner_raw_text, raw_date_phrase, "
    "due_date, due_time, due_at, source_text, confidence, review_state, status, "
    "completed_at, created_at, updated_at"
)


class ActionRepository(BaseRepository):
    # ------------------------------------------------------------------
    # writes
    # ------------------------------------------------------------------
    def create(self, action: ActionItem) -> ActionItem:
        now = self.now_str()
        with unit_of_work(self.db):
            self.db.execute(
                """
                INSERT INTO action_items (
                    meeting_id, task, owner_employee_id, owner_raw_text,
                    raw_date_phrase, due_date, due_time, due_at, source_text,
                    search_text, confidence, review_state, status, completed_at,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    action.meeting_id,
                    action.task,
                    action.owner_employee_id,
                    action.owner_raw_text,
                    action.raw_date_phrase,
                    date_to_db(action.due_date),
                    time_to_db(action.due_time),
                    self._due_at_value(action),
                    action.source_text,
                    self._search_text(action),
                    action.confidence,
                    action.review_state,
                    action.status,
                    isoformat_utc(action.completed_at, self.tz),
                    now,
                    now,
                ),
            )
            action_id = self._last_insert_id()
        return self.get_or_raise(action_id)

    def update(self, action: ActionItem) -> ActionItem:
        if action.id is None:
            raise ValueError("action.id is required for update")
        with unit_of_work(self.db):
            cursor = self.db.execute(
                """
                UPDATE action_items
                   SET meeting_id = ?, task = ?, owner_employee_id = ?,
                       owner_raw_text = ?, raw_date_phrase = ?, due_date = ?,
                       due_time = ?, due_at = ?, source_text = ?, search_text = ?,
                       confidence = ?, review_state = ?, status = ?,
                       completed_at = ?, updated_at = ?
                 WHERE id = ?
                """,
                (
                    action.meeting_id,
                    action.task,
                    action.owner_employee_id,
                    action.owner_raw_text,
                    action.raw_date_phrase,
                    date_to_db(action.due_date),
                    time_to_db(action.due_time),
                    self._due_at_value(action),
                    action.source_text,
                    self._search_text(action),
                    action.confidence,
                    action.review_state,
                    action.status,
                    isoformat_utc(action.completed_at, self.tz),
                    self.now_str(),
                    action.id,
                ),
            )
            if cursor.rowcount == 0:
                raise NotFoundError("action_item", action.id)
        return self.get_or_raise(action.id)

    def save(self, action: ActionItem) -> ActionItem:
        """Insert or update depending on whether the item already has an id."""
        return self.update(action) if action.id else self.create(action)

    def bulk_create(self, actions: Iterable[ActionItem]) -> List[ActionItem]:
        """Save a whole approved review screen atomically."""
        saved: List[ActionItem] = []
        with unit_of_work(self.db):
            for action in actions:
                saved.append(self.create(action))
        return saved

    def assign_owner(self, action_id: int, employee_id: Optional[int]) -> ActionItem:
        with unit_of_work(self.db):
            cursor = self.db.execute(
                "UPDATE action_items SET owner_employee_id = ?, updated_at = ? WHERE id = ?",
                (employee_id, self.now_str(), action_id),
            )
            if cursor.rowcount == 0:
                raise NotFoundError("action_item", action_id)
        return self.get_or_raise(action_id)

    def set_status(self, action_id: int, status: str) -> ActionItem:
        value = getattr(status, "value", status)
        with unit_of_work(self.db):
            current = self.get_or_raise(action_id)
            if current.status == ActionStatus.CANCELLED.value and value == ActionStatus.COMPLETED.value:
                raise ConflictError(
                    "a cancelled action item cannot be completed", code="invalid_transition"
                )
            completed_at = (
                self.now_str() if value == ActionStatus.COMPLETED.value else None
            )
            self.db.execute(
                "UPDATE action_items SET status = ?, completed_at = ?, updated_at = ? "
                "WHERE id = ?",
                (value, completed_at, self.now_str(), action_id),
            )
        return self.get_or_raise(action_id)

    def set_review_state(self, action_id: int, review_state: str) -> ActionItem:
        with unit_of_work(self.db):
            cursor = self.db.execute(
                "UPDATE action_items SET review_state = ?, updated_at = ? WHERE id = ?",
                (getattr(review_state, "value", review_state), self.now_str(), action_id),
            )
            if cursor.rowcount == 0:
                raise NotFoundError("action_item", action_id)
        return self.get_or_raise(action_id)

    def reschedule(
        self, action_id: int, due_date: Optional[date], due_time=None
    ) -> ActionItem:
        """Change the deadline. Member 5 recalculates reminders afterwards."""
        current = self.get_or_raise(action_id)
        updated = ActionItem(
            id=current.id,
            meeting_id=current.meeting_id,
            task=current.task,
            owner_employee_id=current.owner_employee_id,
            owner_raw_text=current.owner_raw_text,
            raw_date_phrase=current.raw_date_phrase,
            due_date=due_date,
            due_time=due_time,
            due_at=None,
            source_text=current.source_text,
            confidence=current.confidence,
            review_state=current.review_state,
            status=current.status,
            completed_at=current.completed_at,
        )
        return self.update(updated)

    def delete(self, action_id: int) -> None:
        with unit_of_work(self.db):
            cursor = self.db.execute("DELETE FROM action_items WHERE id = ?", (action_id,))
            if cursor.rowcount == 0:
                raise NotFoundError("action_item", action_id)

    def mark_overdue(self, as_of=None) -> int:
        """Flip past-due pending items to OVERDUE. Returns the number changed."""
        moment = as_of or self.clock.now_utc()
        cutoff = isoformat_utc(moment, self.tz)
        today = self.clock.today().isoformat()
        with unit_of_work(self.db):
            cursor = self.db.execute(
                """
                UPDATE action_items
                   SET status = 'OVERDUE', updated_at = ?
                 WHERE status = 'PENDING'
                   AND (
                        (due_at IS NOT NULL AND due_at < ?)
                     OR (due_at IS NULL AND due_date IS NOT NULL AND due_date < ?)
                   )
                """,
                (self.now_str(), cutoff, today),
            )
            return cursor.rowcount

    # ------------------------------------------------------------------
    # reads
    # ------------------------------------------------------------------
    def get(self, action_id: int) -> Optional[ActionItem]:
        row = self.db.query_one(f"SELECT {_COLUMNS} FROM action_items WHERE id = ?", (action_id,))
        return None if row is None else row_to_action(row)

    def get_or_raise(self, action_id: int) -> ActionItem:
        action = self.get(action_id)
        if action is None:
            raise NotFoundError("action_item", action_id)
        return action

    def for_meeting(self, meeting_id: int) -> List[ActionItem]:
        rows = self.db.query_all(
            f"SELECT {_COLUMNS} FROM action_items WHERE meeting_id = ? "
            "ORDER BY COALESCE(due_date, '9999-12-31'), id",
            (meeting_id,),
        )
        return [row_to_action(row) for row in rows]

    def for_owner(self, employee_id: int, *, pending_only: bool = False) -> List[ActionItem]:
        sql = f"SELECT {_COLUMNS} FROM action_items WHERE owner_employee_id = ?"
        if pending_only:
            sql += " AND status = 'PENDING'"
        sql += " ORDER BY COALESCE(due_date, '9999-12-31'), id"
        return [row_to_action(row) for row in self.db.query_all(sql, (employee_id,))]

    def count(self, *, status: Optional[str] = None) -> int:
        if status is None:
            return int(self.db.query_value("SELECT COUNT(*) FROM action_items", default=0))
        return int(
            self.db.query_value(
                "SELECT COUNT(*) FROM action_items WHERE status = ?",
                (getattr(status, "value", status),),
                default=0,
            )
        )

    def owner_ids_for_actions(self, action_ids: Sequence[int]) -> List[int]:
        """Owners of the given actions, for ASSIGNEE recipient resolution."""
        ids = [int(i) for i in action_ids]
        if not ids:
            return []
        placeholders = ",".join("?" * len(ids))
        rows = self.db.query_all(
            "SELECT DISTINCT owner_employee_id FROM action_items "
            f"WHERE id IN ({placeholders}) AND owner_employee_id IS NOT NULL",
            ids,
        )
        return [row["owner_employee_id"] for row in rows]

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------
    def _due_at_value(self, action: ActionItem) -> Optional[str]:
        """Resolve the UTC instant of a deadline.

        A date with no time means "time not specified": the instant stays NULL
        and only `due_date` is used for day-level filtering.
        """
        if action.due_at is not None:
            return isoformat_utc(action.due_at, self.tz)
        if action.due_date is not None and action.due_time is not None:
            return isoformat_utc(
                combine_local(action.due_date, action.due_time, self.tz), self.tz
            )
        return None

    @staticmethod
    def _search_text(action: ActionItem) -> str:
        """Task text, owner wording and the original evidence, all searchable."""
        parts = [
            action.task,
            action.owner_raw_text or "",
            action.source_text or "",
            action.raw_date_phrase or "",
        ]
        return normalize_search_text(" ".join(parts))
