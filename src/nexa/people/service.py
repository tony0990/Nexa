"""Employee and role administration.

This is the public surface other members use; nobody outside `nexa.data`
touches the employee tables directly. Every mutation is validated, wrapped in
one transaction with its audit row, and returns the stored entity.
"""

from __future__ import annotations

from typing import List, Optional, Sequence

from ..audit import event_types
from ..audit.service import Actor, AuditService
from ..contracts.people import Employee, Role
from ..core.clock import Clock, SystemClock
from ..core.errors import ConflictError, NotFoundError
from ..data.database import Database
from ..data.models import employee_snapshot, role_snapshot
from ..data.repositories.employees import EmployeeRepository
from ..data.repositories.roles import RoleRepository
from ..data.transactions import unit_of_work
from .validators import (
    is_duplicate_email,
    validate_employee,
    validate_employee_changes,
    validate_role,
)


class PeopleService:
    def __init__(
        self,
        database: Database,
        clock: Optional[Clock] = None,
        audit: Optional[AuditService] = None,
        *,
        actor: Optional[Actor] = None,
    ):
        self.db = database
        self.clock = clock or SystemClock(database.config.timezone)
        self.employees = EmployeeRepository(database, self.clock)
        self.roles = RoleRepository(database, self.clock)
        self.audit = audit or AuditService(database, self.clock)
        self.actor = actor or Actor.user()

    # ==================================================================
    # employees
    # ==================================================================
    def create_employee(
        self,
        full_name: str,
        email: str,
        *,
        department: Optional[str] = None,
        job_title: Optional[str] = None,
        active: bool = True,
        role_ids: Sequence[int] = (),
        actor: Optional[Actor] = None,
    ) -> Employee:
        candidate = validate_employee(
            Employee(
                full_name=full_name,
                email=email,
                department=department,
                job_title=job_title,
                active=active,
            )
        )
        with unit_of_work(self.db):
            existing = self.employees.get_by_email(candidate.email)
            if is_duplicate_email(existing, None):
                raise ConflictError(
                    f"an employee with the email {candidate.email} already exists",
                    code="duplicate_email",
                )
            created = self.employees.create(candidate)
            for role_id in dict.fromkeys(role_ids):
                self.roles.assign(created.id, int(role_id))
            self.audit.log(
                event_types.EMPLOYEE_CREATED,
                event_types.ENTITY_EMPLOYEE,
                created.id,
                new_value=employee_snapshot(created),
                actor=actor or self.actor,
            )
        return self.employees.get_or_raise(created.id)

    def update_employee(
        self, employee_id: int, *, actor: Optional[Actor] = None, **changes: object
    ) -> Employee:
        """Partial update: only the fields passed in are touched."""
        cleaned = validate_employee_changes(changes)
        with unit_of_work(self.db):
            current = self.employees.get_or_raise(employee_id)
            if not cleaned:
                return current

            if "email" in cleaned:
                existing = self.employees.get_by_email(str(cleaned["email"]))
                if is_duplicate_email(existing, employee_id):
                    raise ConflictError(
                        f"an employee with the email {cleaned['email']} already exists",
                        code="duplicate_email",
                    )

            updated = validate_employee(
                Employee(
                    id=current.id,
                    full_name=str(cleaned.get("full_name", current.full_name)),
                    email=str(cleaned.get("email", current.email)),
                    department=cleaned.get("department", current.department),  # type: ignore[arg-type]
                    job_title=cleaned.get("job_title", current.job_title),  # type: ignore[arg-type]
                    active=bool(cleaned.get("active", current.active)),
                )
            )
            saved = self.employees.update(updated)
            self.audit.log_change(
                event_types.EMPLOYEE_UPDATED,
                event_types.ENTITY_EMPLOYEE,
                employee_id,
                employee_snapshot(current),
                employee_snapshot(saved),
                actor=actor or self.actor,
            )
        return self.employees.get_or_raise(employee_id)

    def deactivate_employee(self, employee_id: int, *, actor: Optional[Actor] = None) -> Employee:
        """Deactivate rather than delete: history and past reports stay intact.

        A deactivated employee is excluded from every recipient resolution.
        """
        with unit_of_work(self.db):
            current = self.employees.get_or_raise(employee_id)
            if not current.active:
                return current
            saved = self.employees.set_active(employee_id, False)
            self.audit.log(
                event_types.EMPLOYEE_DEACTIVATED,
                event_types.ENTITY_EMPLOYEE,
                employee_id,
                old_value={"active": True},
                new_value={"active": False},
                actor=actor or self.actor,
            )
        return saved

    def reactivate_employee(self, employee_id: int, *, actor: Optional[Actor] = None) -> Employee:
        with unit_of_work(self.db):
            current = self.employees.get_or_raise(employee_id)
            if current.active:
                return current
            saved = self.employees.set_active(employee_id, True)
            self.audit.log(
                event_types.EMPLOYEE_REACTIVATED,
                event_types.ENTITY_EMPLOYEE,
                employee_id,
                old_value={"active": False},
                new_value={"active": True},
                actor=actor or self.actor,
            )
        return saved

    def get_employee(self, employee_id: int) -> Employee:
        return self.employees.get_or_raise(employee_id)

    def find_by_email(self, email: str) -> Optional[Employee]:
        return self.employees.get_by_email(email)

    def list_employees(self, *, active_only: bool = False) -> List[Employee]:
        return self.employees.list_all(active_only=active_only)

    def departments(self) -> List[str]:
        return self.employees.departments()

    # ==================================================================
    # roles
    # ==================================================================
    def create_role(
        self,
        name: str,
        description: Optional[str] = None,
        *,
        active: bool = True,
        actor: Optional[Actor] = None,
    ) -> Role:
        candidate = validate_role(Role(name=name, description=description, active=active))
        with unit_of_work(self.db):
            if self.roles.get_by_name(candidate.name) is not None:
                raise ConflictError(
                    f"a role named {candidate.name!r} already exists", code="duplicate_role"
                )
            created = self.roles.create(candidate)
            self.audit.log(
                event_types.ROLE_CREATED,
                event_types.ENTITY_ROLE,
                created.id,
                new_value=role_snapshot(created),
                actor=actor or self.actor,
            )
        return created

    def update_role(
        self,
        role_id: int,
        *,
        name: Optional[str] = None,
        description: Optional[str] = None,
        active: Optional[bool] = None,
        actor: Optional[Actor] = None,
    ) -> Role:
        with unit_of_work(self.db):
            current = self.roles.get_or_raise(role_id)
            candidate = validate_role(
                Role(
                    id=role_id,
                    name=name if name is not None else current.name,
                    description=description if description is not None else current.description,
                    active=current.active if active is None else bool(active),
                )
            )
            clash = self.roles.get_by_name(candidate.name)
            if clash is not None and clash.id != role_id:
                raise ConflictError(
                    f"a role named {candidate.name!r} already exists", code="duplicate_role"
                )
            saved = self.roles.update(candidate)
            self.audit.log_change(
                event_types.ROLE_UPDATED,
                event_types.ENTITY_ROLE,
                role_id,
                role_snapshot(current),
                role_snapshot(saved),
                actor=actor or self.actor,
            )
        return saved

    def delete_role(self, role_id: int, *, actor: Optional[Actor] = None) -> None:
        with unit_of_work(self.db):
            current = self.roles.get_or_raise(role_id)
            self.roles.delete(role_id)
            self.audit.log(
                event_types.ROLE_DELETED,
                event_types.ENTITY_ROLE,
                role_id,
                old_value=role_snapshot(current),
                actor=actor or self.actor,
            )

    def get_role(self, role_id: int) -> Role:
        return self.roles.get_or_raise(role_id)

    def list_roles(self, *, active_only: bool = False) -> List[Role]:
        return self.roles.list_all(active_only=active_only)

    # ==================================================================
    # assignment
    # ==================================================================
    def assign_role(
        self, employee_id: int, role_id: int, *, actor: Optional[Actor] = None
    ) -> bool:
        """Assign a role. Returns False when it was already assigned."""
        with unit_of_work(self.db):
            assigned = self.roles.assign(employee_id, role_id)
            if assigned:
                self.audit.log(
                    event_types.ROLE_ASSIGNED,
                    event_types.ENTITY_EMPLOYEE,
                    employee_id,
                    new_value={"role_id": role_id},
                    actor=actor or self.actor,
                )
            return assigned

    def remove_role(
        self, employee_id: int, role_id: int, *, actor: Optional[Actor] = None
    ) -> bool:
        with unit_of_work(self.db):
            removed = self.roles.unassign(employee_id, role_id)
            if removed:
                self.audit.log(
                    event_types.ROLE_UNASSIGNED,
                    event_types.ENTITY_EMPLOYEE,
                    employee_id,
                    old_value={"role_id": role_id},
                    actor=actor or self.actor,
                )
            return removed

    def set_roles(
        self, employee_id: int, role_ids: Sequence[int], *, actor: Optional[Actor] = None
    ) -> List[Role]:
        """Make the employee's roles exactly `role_ids`."""
        wanted = {int(role_id) for role_id in role_ids}
        with unit_of_work(self.db):
            if not self.employees.exists(employee_id):
                raise NotFoundError("employee", employee_id)
            current = {role.id for role in self.roles.roles_for_employee(employee_id)}
            for role_id in sorted(wanted - current):
                self.assign_role(employee_id, role_id, actor=actor)
            for role_id in sorted(current - wanted):
                self.remove_role(employee_id, role_id, actor=actor)
        return self.roles.roles_for_employee(employee_id)

    def role_members(self, role_id: int, *, active_only: bool = True) -> List[Employee]:
        """The role membership query."""
        self.roles.get_or_raise(role_id)
        return self.roles.members(role_id, active_only=active_only)

    def roles_for_employee(self, employee_id: int) -> List[Role]:
        return self.roles.roles_for_employee(employee_id)
