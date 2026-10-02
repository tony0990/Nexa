"""Employee and role validation rules."""

from __future__ import annotations

from typing import Optional

from ..contracts.people import Employee, Role
from ..core.errors import ValidationError
from ..core.validation import (
    MAX_NAME_LENGTH,
    clean_text,
    normalize_email,
    require_text,
    validate_email,
    validate_full_name,
)

MAX_DEPARTMENT_LENGTH = 120
MAX_JOB_TITLE_LENGTH = 120
MAX_ROLE_NAME_LENGTH = 80
MAX_DESCRIPTION_LENGTH = 500


def validate_employee(employee: Employee) -> Employee:
    """Return a cleaned copy, or raise `ValidationError`.

    Cleaning is part of validation on purpose: what gets stored is exactly
    what was validated, so the repository never has to re-trim anything.
    """
    full_name = validate_full_name(employee.full_name)
    email = validate_email(employee.email)
    department = _optional(employee.department, "department", MAX_DEPARTMENT_LENGTH)
    job_title = _optional(employee.job_title, "job_title", MAX_JOB_TITLE_LENGTH)

    return Employee(
        id=employee.id,
        full_name=full_name,
        email=email,
        department=department,
        job_title=job_title,
        active=bool(employee.active),
        created_at=employee.created_at,
        updated_at=employee.updated_at,
        role_ids=employee.role_ids,
    )


def validate_role(role: Role) -> Role:
    name = require_text(role.name, "name", max_length=MAX_ROLE_NAME_LENGTH)
    description = _optional(role.description, "description", MAX_DESCRIPTION_LENGTH)
    return Role(
        id=role.id,
        name=name,
        description=description,
        active=bool(role.active),
        created_at=role.created_at,
        updated_at=role.updated_at,
    )


def validate_employee_changes(changes: dict) -> dict:
    """Validate a partial update (only the fields actually being changed)."""
    allowed = {"full_name", "email", "department", "job_title", "active"}
    unknown = set(changes) - allowed
    if unknown:
        raise ValidationError(
            f"unknown employee fields: {', '.join(sorted(unknown))}",
            field=sorted(unknown)[0],
            code="unknown_field",
        )

    cleaned = {}
    if "full_name" in changes:
        cleaned["full_name"] = validate_full_name(changes["full_name"])
    if "email" in changes:
        cleaned["email"] = validate_email(changes["email"])
    if "department" in changes:
        cleaned["department"] = _optional(
            changes["department"], "department", MAX_DEPARTMENT_LENGTH
        )
    if "job_title" in changes:
        cleaned["job_title"] = _optional(
            changes["job_title"], "job_title", MAX_JOB_TITLE_LENGTH
        )
    if "active" in changes:
        cleaned["active"] = bool(changes["active"])
    return cleaned


def is_duplicate_email(existing: Optional[Employee], employee_id: Optional[int]) -> bool:
    """True when `existing` is a different employee holding the same address."""
    return existing is not None and existing.id != employee_id


def _optional(value: Optional[str], field: str, max_length: int) -> Optional[str]:
    text = clean_text(value)
    if text is None:
        return None
    if len(text) > max_length:
        raise ValidationError(
            f"{field} must be at most {max_length} characters",
            field=field,
            code="too_long",
        )
    return text


__all__ = [
    "MAX_DEPARTMENT_LENGTH",
    "MAX_DESCRIPTION_LENGTH",
    "MAX_JOB_TITLE_LENGTH",
    "MAX_NAME_LENGTH",
    "MAX_ROLE_NAME_LENGTH",
    "is_duplicate_email",
    "normalize_email",
    "validate_employee",
    "validate_employee_changes",
    "validate_role",
]
