"""Shared people domain models and service contracts (Section 17 kickoff)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Protocol, Sequence


@dataclass(frozen=True)
class Employee:
    """A person Nexa can address in a report or a reminder."""

    id: Optional[int] = None
    full_name: str = ""
    email: str = ""
    department: Optional[str] = None
    job_title: Optional[str] = None
    active: bool = True
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    role_ids: tuple[int, ...] = field(default=())


@dataclass(frozen=True)
class Role:
    """A named group of employees, used for recipient targeting."""

    id: Optional[int] = None
    name: str = ""
    description: Optional[str] = None
    active: bool = True
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class PeopleService(Protocol):
    def create_employee(self, employee: Employee) -> Employee: ...

    def update_employee(self, employee_id: int, **changes: object) -> Employee: ...

    def deactivate_employee(self, employee_id: int) -> Employee: ...

    def reactivate_employee(self, employee_id: int) -> Employee: ...

    def assign_role(self, employee_id: int, role_id: int) -> None: ...

    def remove_role(self, employee_id: int, role_id: int) -> None: ...

    def role_members(self, role_id: int) -> Sequence[Employee]: ...


class EmployeeRepository(Protocol):
    def get(self, employee_id: int) -> Optional[Employee]: ...

    def list_active(self) -> Sequence[Employee]: ...
