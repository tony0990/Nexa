"""Search facade used by the UI (Section 21.3).

`global_search` is the top search bar: one query, results grouped into
Employees / Meetings / Tasks exactly as Section 31 describes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from ..contracts.meetings import ActionItem, Meeting
from ..contracts.people import Employee
from ..core.clock import Clock, SystemClock
from ..data.database import Database
from .employee_search import EmployeeSearch
from .filters import EmployeeFilters, MeetingFilters, TaskFilters, clamp_limit
from .meeting_search import MeetingSearch
from .task_search import TaskRow, TaskSearch

DEFAULT_GROUP_LIMIT = 20


@dataclass
class GlobalSearchResults:
    query: str = ""
    employees: List[Employee] = field(default_factory=list)
    meetings: List[Meeting] = field(default_factory=list)
    tasks: List[ActionItem] = field(default_factory=list)
    employee_total: int = 0
    meeting_total: int = 0
    task_total: int = 0

    @property
    def total(self) -> int:
        return self.employee_total + self.meeting_total + self.task_total

    @property
    def is_empty(self) -> bool:
        return self.total == 0

    def group_counts(self) -> dict:
        """Counts for the group headers: `Employees (3)`, `Meetings (2)`, ..."""
        return {
            "employees": self.employee_total,
            "meetings": self.meeting_total,
            "tasks": self.task_total,
        }


class SearchService:
    def __init__(self, database: Database, clock: Optional[Clock] = None):
        self.db = database
        self.clock = clock or SystemClock(database.config.timezone)
        self.employees = EmployeeSearch(database, self.clock)
        self.meetings = MeetingSearch(database, self.clock)
        self.tasks = TaskSearch(database, self.clock)

    # ------------------------------------------------------------------
    # category searches
    # ------------------------------------------------------------------
    def search_employees(
        self, query: Optional[str] = None, filters: Optional[EmployeeFilters] = None
    ) -> List[Employee]:
        return self.employees.search(query, filters)

    def search_meetings(
        self, query: Optional[str] = None, filters: Optional[MeetingFilters] = None
    ) -> List[Meeting]:
        return self.meetings.search(query, filters)

    def search_tasks(
        self, query: Optional[str] = None, filters: Optional[TaskFilters] = None
    ) -> List[ActionItem]:
        return self.tasks.search(query, filters)

    def search_task_rows(
        self, query: Optional[str] = None, filters: Optional[TaskFilters] = None
    ) -> List[TaskRow]:
        return self.tasks.search_rows(query, filters)

    # ------------------------------------------------------------------
    # global search
    # ------------------------------------------------------------------
    def global_search(
        self, query: str, *, limit_per_group: int = DEFAULT_GROUP_LIMIT
    ) -> GlobalSearchResults:
        limit = clamp_limit(limit_per_group)
        if not query or not query.strip():
            return GlobalSearchResults(query=query or "")

        return GlobalSearchResults(
            query=query,
            employees=self.employees.search(query, EmployeeFilters(limit=limit)),
            meetings=self.meetings.search(query, MeetingFilters(limit=limit)),
            tasks=self.tasks.search(query, TaskFilters(limit=limit)),
            employee_total=self.employees.count(query),
            meeting_total=self.meetings.count(query),
            task_total=self.tasks.count(query),
        )

    # ------------------------------------------------------------------
    # counters
    # ------------------------------------------------------------------
    def count_tasks(
        self, query: Optional[str] = None, filters: Optional[TaskFilters] = None
    ) -> int:
        return self.tasks.count(query, filters)

    def task_status_counts(self, filters: Optional[TaskFilters] = None) -> dict:
        return self.tasks.count_by_status(filters)
