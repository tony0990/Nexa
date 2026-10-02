"""Employee persistence."""

from __future__ import annotations

from typing import Dict, Iterable, List, Optional, Sequence

from ...contracts.people import Employee
from ...core.errors import ConflictError, NotFoundError
from ...core.validation import normalize_email, normalize_search_text
from ..models import row_to_employee
from ..transactions import unit_of_work
from .base import BaseRepository, is_unique_violation

_COLUMNS = (
    "id, full_name, email, department, job_title, active, created_at, updated_at"
)


def _search_text(employee: Employee) -> str:
    """Everything an employee can be found by, folded into one column."""
    parts = [
        employee.full_name,
        employee.email,
        employee.department or "",
        employee.job_title or "",
    ]
    return normalize_search_text(" ".join(parts))


class EmployeeRepository(BaseRepository):
    # ------------------------------------------------------------------
    # writes
    # ------------------------------------------------------------------
    def create(self, employee: Employee) -> Employee:
        now = self.now_str()
        email = normalize_email(employee.email)
        with unit_of_work(self.db):
            try:
                self.db.execute(
                    """
                    INSERT INTO employees (
                        full_name, full_name_norm, email, department, job_title,
                        search_text, active, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        employee.full_name,
                        normalize_search_text(employee.full_name),
                        email,
                        employee.department,
                        employee.job_title,
                        _search_text(employee),
                        1 if employee.active else 0,
                        now,
                        now,
                    ),
                )
            except Exception as exc:  # DatabaseError wraps IntegrityError
                if is_unique_violation(exc, "employees.email"):
                    raise ConflictError(
                        f"an employee with the email {email} already exists",
                        code="duplicate_email",
                    ) from exc
                raise
            new_id = self._last_insert_id()
        return self.get_or_raise(new_id)

    def update(self, employee: Employee) -> Employee:
        if employee.id is None:
            raise ValueError("employee.id is required for update")
        now = self.now_str()
        email = normalize_email(employee.email)
        with unit_of_work(self.db):
            try:
                cursor = self.db.execute(
                    """
                    UPDATE employees
                       SET full_name = ?, full_name_norm = ?, email = ?,
                           department = ?, job_title = ?, search_text = ?,
                           active = ?, updated_at = ?
                     WHERE id = ?
                    """,
                    (
                        employee.full_name,
                        normalize_search_text(employee.full_name),
                        email,
                        employee.department,
                        employee.job_title,
                        _search_text(employee),
                        1 if employee.active else 0,
                        now,
                        employee.id,
                    ),
                )
            except Exception as exc:
                if is_unique_violation(exc, "employees.email"):
                    raise ConflictError(
                        f"an employee with the email {email} already exists",
                        code="duplicate_email",
                    ) from exc
                raise
            if cursor.rowcount == 0:
                raise NotFoundError("employee", employee.id)
        return self.get_or_raise(employee.id)

    def set_active(self, employee_id: int, active: bool) -> Employee:
        with unit_of_work(self.db):
            cursor = self.db.execute(
                "UPDATE employees SET active = ?, updated_at = ? WHERE id = ?",
                (1 if active else 0, self.now_str(), employee_id),
            )
            if cursor.rowcount == 0:
                raise NotFoundError("employee", employee_id)
        return self.get_or_raise(employee_id)

    def delete(self, employee_id: int) -> None:
        """Hard delete. Prefer `set_active(False)`: deactivation keeps history.

        Used by fixtures and by the demo-database reset script.
        """
        with unit_of_work(self.db):
            cursor = self.db.execute("DELETE FROM employees WHERE id = ?", (employee_id,))
            if cursor.rowcount == 0:
                raise NotFoundError("employee", employee_id)

    def bulk_create(self, employees: Iterable[Employee]) -> int:
        """Insert many employees in one transaction (fixtures, imports)."""
        now = self.now_str()
        rows = [
            (
                employee.full_name,
                normalize_search_text(employee.full_name),
                normalize_email(employee.email),
                employee.department,
                employee.job_title,
                _search_text(employee),
                1 if employee.active else 0,
                now,
                now,
            )
            for employee in employees
        ]
        with unit_of_work(self.db):
            self.db.executemany(
                """
                INSERT INTO employees (
                    full_name, full_name_norm, email, department, job_title,
                    search_text, active, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                rows,
            )
        return len(rows)

    # ------------------------------------------------------------------
    # reads
    # ------------------------------------------------------------------
    def get(self, employee_id: int) -> Optional[Employee]:
        row = self.db.query_one(
            f"SELECT {_COLUMNS} FROM employees WHERE id = ?", (employee_id,)
        )
        if row is None:
            return None
        return row_to_employee(row, self.role_ids_for(employee_id))

    def get_or_raise(self, employee_id: int) -> Employee:
        employee = self.get(employee_id)
        if employee is None:
            raise NotFoundError("employee", employee_id)
        return employee

    def get_by_email(self, email: str) -> Optional[Employee]:
        row = self.db.query_one(
            f"SELECT {_COLUMNS} FROM employees WHERE email = ?", (normalize_email(email),)
        )
        return None if row is None else row_to_employee(row, self.role_ids_for(row["id"]))

    def get_many(self, employee_ids: Sequence[int]) -> List[Employee]:
        """Fetch several employees, preserving the requested order."""
        ids = [int(i) for i in employee_ids]
        if not ids:
            return []
        placeholders = ",".join("?" * len(ids))
        rows = self.db.query_all(
            f"SELECT {_COLUMNS} FROM employees WHERE id IN ({placeholders})", ids
        )
        by_id = {row["id"]: row for row in rows}
        role_map = self.role_ids_for_many(ids)
        return [
            row_to_employee(by_id[i], role_map.get(i, ()))
            for i in ids
            if i in by_id
        ]

    def list_all(self, *, active_only: bool = False) -> List[Employee]:
        sql = f"SELECT {_COLUMNS} FROM employees"
        if active_only:
            sql += " WHERE active = 1"
        sql += " ORDER BY full_name_norm"
        rows = self.db.query_all(sql)
        role_map = self.role_ids_for_many([row["id"] for row in rows])
        return [row_to_employee(row, role_map.get(row["id"], ())) for row in rows]

    def list_active(self) -> List[Employee]:
        return self.list_all(active_only=True)

    def count(self, *, active_only: bool = False) -> int:
        sql = "SELECT COUNT(*) FROM employees"
        if active_only:
            sql += " WHERE active = 1"
        return int(self.db.query_value(sql, default=0))

    def departments(self) -> List[str]:
        rows = self.db.query_all(
            "SELECT DISTINCT department FROM employees "
            "WHERE department IS NOT NULL AND department <> '' ORDER BY department"
        )
        return [row["department"] for row in rows]

    # ------------------------------------------------------------------
    # role membership
    # ------------------------------------------------------------------
    def role_ids_for(self, employee_id: int) -> List[int]:
        rows = self.db.query_all(
            "SELECT role_id FROM employee_roles WHERE employee_id = ? ORDER BY role_id",
            (employee_id,),
        )
        return [row["role_id"] for row in rows]

    def role_ids_for_many(self, employee_ids: Sequence[int]) -> Dict[int, tuple]:
        ids = [int(i) for i in employee_ids]
        if not ids:
            return {}
        placeholders = ",".join("?" * len(ids))
        rows = self.db.query_all(
            "SELECT employee_id, role_id FROM employee_roles "
            f"WHERE employee_id IN ({placeholders}) ORDER BY employee_id, role_id",
            ids,
        )
        result: Dict[int, list] = {}
        for row in rows:
            result.setdefault(row["employee_id"], []).append(row["role_id"])
        return {key: tuple(value) for key, value in result.items()}

    def exists(self, employee_id: int) -> bool:
        return self.db.query_one("SELECT 1 FROM employees WHERE id = ?", (employee_id,)) is not None

    def rebuild_search_text(self) -> int:
        """Recompute normalized columns for every row.

        Needed after changing the normalization rules, and by the migration
        path for databases written before a rule change.
        """
        rows = self.db.query_all(f"SELECT {_COLUMNS} FROM employees")
        updates = []
        for row in rows:
            employee = row_to_employee(row)
            updates.append(
                (
                    normalize_search_text(employee.full_name),
                    _search_text(employee),
                    employee.id,
                )
            )
        with unit_of_work(self.db):
            self.db.executemany(
                "UPDATE employees SET full_name_norm = ?, search_text = ? WHERE id = ?",
                updates,
            )
        return len(updates)
