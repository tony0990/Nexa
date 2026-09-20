"""Role persistence and employee<->role assignment."""

from __future__ import annotations

from typing import List, Optional

from ...contracts.people import Employee, Role
from ...core.errors import ConflictError, NotFoundError
from ...core.validation import normalize_search_text
from ..models import row_to_employee, row_to_role
from ..transactions import unit_of_work
from .base import BaseRepository, is_unique_violation

_COLUMNS = "id, name, description, active, created_at, updated_at"
_EMPLOYEE_COLUMNS = (
    "e.id AS id, e.full_name AS full_name, e.email AS email, "
    "e.department AS department, e.job_title AS job_title, e.active AS active, "
    "e.created_at AS created_at, e.updated_at AS updated_at"
)


class RoleRepository(BaseRepository):
    # ------------------------------------------------------------------
    # role CRUD
    # ------------------------------------------------------------------
    def create(self, role: Role) -> Role:
        now = self.now_str()
        with unit_of_work(self.db):
            try:
                self.db.execute(
                    """
                    INSERT INTO roles (name, name_norm, description, active,
                                       created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        role.name,
                        normalize_search_text(role.name),
                        role.description,
                        1 if role.active else 0,
                        now,
                        now,
                    ),
                )
            except Exception as exc:
                if is_unique_violation(exc, "roles.name_norm"):
                    raise ConflictError(
                        f"a role named {role.name!r} already exists", code="duplicate_role"
                    ) from exc
                raise
            new_id = self._last_insert_id()
        return self.get_or_raise(new_id)

    def update(self, role: Role) -> Role:
        if role.id is None:
            raise ValueError("role.id is required for update")
        with unit_of_work(self.db):
            try:
                cursor = self.db.execute(
                    """
                    UPDATE roles
                       SET name = ?, name_norm = ?, description = ?, active = ?,
                           updated_at = ?
                     WHERE id = ?
                    """,
                    (
                        role.name,
                        normalize_search_text(role.name),
                        role.description,
                        1 if role.active else 0,
                        self.now_str(),
                        role.id,
                    ),
                )
            except Exception as exc:
                if is_unique_violation(exc, "roles.name_norm"):
                    raise ConflictError(
                        f"a role named {role.name!r} already exists", code="duplicate_role"
                    ) from exc
                raise
            if cursor.rowcount == 0:
                raise NotFoundError("role", role.id)
        return self.get_or_raise(role.id)

    def delete(self, role_id: int) -> None:
        """Delete a role; assignments cascade away with it."""
        with unit_of_work(self.db):
            cursor = self.db.execute("DELETE FROM roles WHERE id = ?", (role_id,))
            if cursor.rowcount == 0:
                raise NotFoundError("role", role_id)

    # ------------------------------------------------------------------
    # reads
    # ------------------------------------------------------------------
    def get(self, role_id: int) -> Optional[Role]:
        row = self.db.query_one(f"SELECT {_COLUMNS} FROM roles WHERE id = ?", (role_id,))
        return None if row is None else row_to_role(row)

    def get_or_raise(self, role_id: int) -> Role:
        role = self.get(role_id)
        if role is None:
            raise NotFoundError("role", role_id)
        return role

    def get_by_name(self, name: str) -> Optional[Role]:
        row = self.db.query_one(
            f"SELECT {_COLUMNS} FROM roles WHERE name_norm = ?",
            (normalize_search_text(name),),
        )
        return None if row is None else row_to_role(row)

    def list_all(self, *, active_only: bool = False) -> List[Role]:
        sql = f"SELECT {_COLUMNS} FROM roles"
        if active_only:
            sql += " WHERE active = 1"
        sql += " ORDER BY name_norm"
        return [row_to_role(row) for row in self.db.query_all(sql)]

    def search(self, pattern: str) -> List[Role]:
        rows = self.db.query_all(
            f"SELECT {_COLUMNS} FROM roles WHERE name_norm LIKE ? ESCAPE '\\' "
            "ORDER BY name_norm",
            (pattern,),
        )
        return [row_to_role(row) for row in rows]

    # ------------------------------------------------------------------
    # assignment
    # ------------------------------------------------------------------
    def assign(self, employee_id: int, role_id: int) -> bool:
        """Assign a role. Returns False when the assignment already existed."""
        if not self._employee_exists(employee_id):
            raise NotFoundError("employee", employee_id)
        if self.get(role_id) is None:
            raise NotFoundError("role", role_id)
        with unit_of_work(self.db):
            cursor = self.db.execute(
                "INSERT OR IGNORE INTO employee_roles (employee_id, role_id, created_at) "
                "VALUES (?, ?, ?)",
                (employee_id, role_id, self.now_str()),
            )
            return cursor.rowcount > 0

    def unassign(self, employee_id: int, role_id: int) -> bool:
        """Remove an assignment. Returns False when there was nothing to remove."""
        with unit_of_work(self.db):
            cursor = self.db.execute(
                "DELETE FROM employee_roles WHERE employee_id = ? AND role_id = ?",
                (employee_id, role_id),
            )
            return cursor.rowcount > 0

    def members(self, role_id: int, *, active_only: bool = True) -> List[Employee]:
        """Employees holding a role (the role membership query)."""
        sql = (
            f"SELECT {_EMPLOYEE_COLUMNS} FROM employee_roles er "
            "JOIN employees e ON e.id = er.employee_id "
            "WHERE er.role_id = ?"
        )
        if active_only:
            sql += " AND e.active = 1"
        sql += " ORDER BY e.full_name_norm"
        return [row_to_employee(row) for row in self.db.query_all(sql, (role_id,))]

    def member_ids(self, role_id: int, *, active_only: bool = True) -> List[int]:
        sql = (
            "SELECT er.employee_id AS employee_id FROM employee_roles er "
            "JOIN employees e ON e.id = er.employee_id WHERE er.role_id = ?"
        )
        if active_only:
            sql += " AND e.active = 1"
        return [row["employee_id"] for row in self.db.query_all(sql, (role_id,))]

    def roles_for_employee(self, employee_id: int) -> List[Role]:
        rows = self.db.query_all(
            "SELECT r.id AS id, r.name AS name, r.description AS description, "
            "r.active AS active, r.created_at AS created_at, r.updated_at AS updated_at "
            "FROM employee_roles er JOIN roles r ON r.id = er.role_id "
            "WHERE er.employee_id = ? ORDER BY r.name_norm",
            (employee_id,),
        )
        return [row_to_role(row) for row in rows]

    def member_count(self, role_id: int, *, active_only: bool = True) -> int:
        sql = (
            "SELECT COUNT(*) FROM employee_roles er "
            "JOIN employees e ON e.id = er.employee_id WHERE er.role_id = ?"
        )
        if active_only:
            sql += " AND e.active = 1"
        return int(self.db.query_value(sql, (role_id,), default=0))

    def _employee_exists(self, employee_id: int) -> bool:
        return (
            self.db.query_one("SELECT 1 FROM employees WHERE id = ?", (employee_id,))
            is not None
        )
