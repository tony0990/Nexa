"""Employee search: name, email, department, job title, role (Section 6.4)."""

from __future__ import annotations

from typing import List, Optional

from ..contracts.people import Employee
from ..core.clock import Clock, SystemClock
from ..core.validation import like_pattern, normalize_search_text
from ..data.database import Database
from ..data.models import row_to_employee
from ..data.repositories.employees import EmployeeRepository
from .filters import Conditions, EmployeeFilters, clamp_limit

_COLUMNS = (
    "e.id AS id, e.full_name AS full_name, e.email AS email, "
    "e.department AS department, e.job_title AS job_title, e.active AS active, "
    "e.created_at AS created_at, e.updated_at AS updated_at"
)


class EmployeeSearch:
    def __init__(self, database: Database, clock: Optional[Clock] = None):
        self.db = database
        self.clock = clock or SystemClock(database.config.timezone)
        self.employees = EmployeeRepository(database, self.clock)

    def search(
        self, query: Optional[str] = None, filters: Optional[EmployeeFilters] = None
    ) -> List[Employee]:
        active_filters = filters or EmployeeFilters()
        conditions = Conditions()

        if query and normalize_search_text(query):
            pattern = like_pattern(query)
            # search_text already contains name, email, department and title;
            # the role branch is a separate EXISTS so role names match too.
            conditions.add(
                "(e.search_text LIKE ? ESCAPE '\\' OR EXISTS ("
                "  SELECT 1 FROM employee_roles er JOIN roles r ON r.id = er.role_id"
                "   WHERE er.employee_id = e.id AND r.name_norm LIKE ? ESCAPE '\\'))",
                pattern,
                pattern,
            )

        active_filters.build(conditions)

        sql = (
            f"SELECT {_COLUMNS} FROM employees e"
            + conditions.where()
            + active_filters.order_by()
            + " LIMIT ?"
        )
        params = list(conditions.params) + [clamp_limit(active_filters.limit)]
        rows = self.db.query_all(sql, params)

        role_map = self.employees.role_ids_for_many([row["id"] for row in rows])
        return [row_to_employee(row, role_map.get(row["id"], ())) for row in rows]

    def count(
        self, query: Optional[str] = None, filters: Optional[EmployeeFilters] = None
    ) -> int:
        active_filters = filters or EmployeeFilters()
        conditions = Conditions()
        if query and normalize_search_text(query):
            pattern = like_pattern(query)
            conditions.add(
                "(e.search_text LIKE ? ESCAPE '\\' OR EXISTS ("
                "  SELECT 1 FROM employee_roles er JOIN roles r ON r.id = er.role_id"
                "   WHERE er.employee_id = e.id AND r.name_norm LIKE ? ESCAPE '\\'))",
                pattern,
                pattern,
            )
        active_filters.build(conditions)
        sql = "SELECT COUNT(*) FROM employees e" + conditions.where()
        return int(self.db.query_value(sql, list(conditions.params), default=0))

    def suggest(self, prefix: str, limit: int = 10) -> List[Employee]:
        """Name-prefix lookup for the assignee picker."""
        normalized = normalize_search_text(prefix)
        if not normalized:
            return []
        escaped = normalized.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        rows = self.db.query_all(
            f"SELECT {_COLUMNS} FROM employees e "
            "WHERE e.active = 1 AND e.full_name_norm LIKE ? ESCAPE '\\' "
            "ORDER BY e.full_name_norm LIMIT ?",
            (f"{escaped}%", clamp_limit(limit)),
        )
        return [row_to_employee(row) for row in rows]
