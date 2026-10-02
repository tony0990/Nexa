"""Task search: task text, owner, meeting, date, status, evidence (Section 6.4).

Evidence text is searchable on purpose: an admin who remembers the sentence
that was said ("قبل يوم الاتنين") can find the task it produced.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from ..contracts.meetings import ActionItem
from ..core.clock import Clock, SystemClock
from ..core.validation import like_pattern, normalize_search_text
from ..data.database import Database
from ..data.models import row_to_action
from .filters import Conditions, TaskFilters, clamp_limit

_COLUMNS = (
    "a.id AS id, a.meeting_id AS meeting_id, a.task AS task, "
    "a.owner_employee_id AS owner_employee_id, a.owner_raw_text AS owner_raw_text, "
    "a.raw_date_phrase AS raw_date_phrase, a.due_date AS due_date, "
    "a.due_time AS due_time, a.due_at AS due_at, a.source_text AS source_text, "
    "a.confidence AS confidence, a.review_state AS review_state, a.status AS status, "
    "a.completed_at AS completed_at, a.created_at AS created_at, a.updated_at AS updated_at"
)

_MATCH = """(
    a.search_text LIKE ? ESCAPE '\\'
 OR EXISTS (SELECT 1 FROM employees e
             WHERE e.id = a.owner_employee_id AND e.search_text LIKE ? ESCAPE '\\')
 OR EXISTS (SELECT 1 FROM meetings m
             WHERE m.id = a.meeting_id AND m.title_norm LIKE ? ESCAPE '\\')
)"""


@dataclass(frozen=True)
class TaskRow:
    """An action item with the display fields the list view needs.

    Returned by `search_rows` so the UI does not have to issue one extra
    query per row for the owner name and meeting title.
    """

    action: ActionItem
    owner_name: Optional[str]
    meeting_title: Optional[str]


class TaskSearch:
    def __init__(self, database: Database, clock: Optional[Clock] = None):
        self.db = database
        self.clock = clock or SystemClock(database.config.timezone)

    def search(
        self, query: Optional[str] = None, filters: Optional[TaskFilters] = None
    ) -> List[ActionItem]:
        active_filters = filters or TaskFilters()
        conditions = self._conditions(query, active_filters)
        sql = (
            f"SELECT {_COLUMNS} FROM action_items a"
            + conditions.where()
            + active_filters.order_by()
            + " LIMIT ?"
        )
        params = list(conditions.params) + [clamp_limit(active_filters.limit)]
        return [row_to_action(row) for row in self.db.query_all(sql, params)]

    def search_rows(
        self, query: Optional[str] = None, filters: Optional[TaskFilters] = None
    ) -> List[TaskRow]:
        """Same query, joined with owner name and meeting title for display."""
        active_filters = filters or TaskFilters()
        conditions = self._conditions(query, active_filters)
        sql = (
            f"SELECT {_COLUMNS}, e.full_name AS owner_name, m.title AS meeting_title "
            "FROM action_items a "
            "LEFT JOIN employees e ON e.id = a.owner_employee_id "
            "LEFT JOIN meetings m ON m.id = a.meeting_id"
            + conditions.where()
            + active_filters.order_by()
            + " LIMIT ?"
        )
        params = list(conditions.params) + [clamp_limit(active_filters.limit)]
        return [
            TaskRow(
                action=row_to_action(row),
                owner_name=row["owner_name"],
                meeting_title=row["meeting_title"],
            )
            for row in self.db.query_all(sql, params)
        ]

    def count(
        self, query: Optional[str] = None, filters: Optional[TaskFilters] = None
    ) -> int:
        conditions = self._conditions(query, filters or TaskFilters())
        sql = "SELECT COUNT(*) FROM action_items a" + conditions.where()
        return int(self.db.query_value(sql, list(conditions.params), default=0))

    def count_by_status(self, filters: Optional[TaskFilters] = None) -> dict:
        """Dashboard counters, one query instead of four."""
        conditions = self._conditions(None, filters or TaskFilters())
        sql = (
            "SELECT a.status AS status, COUNT(*) AS total FROM action_items a"
            + conditions.where()
            + " GROUP BY a.status"
        )
        return {row["status"]: row["total"] for row in self.db.query_all(sql, list(conditions.params))}

    def _conditions(self, query: Optional[str], filters: TaskFilters) -> Conditions:
        conditions = Conditions()
        if query and normalize_search_text(query):
            pattern = like_pattern(query)
            conditions.add(_MATCH, pattern, pattern, pattern)
        filters.build(self.clock, conditions)
        return conditions
