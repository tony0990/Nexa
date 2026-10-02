"""Error types shared by the whole data platform."""

from __future__ import annotations

from typing import Optional


class NexaError(Exception):
    """Base class for every error Nexa raises deliberately."""


class ValidationError(NexaError):
    """Input rejected before it reached the database.

    `field` lets the UI highlight the offending input; `code` is a stable
    machine-readable key so the UI can translate the message to Arabic or
    English instead of showing the English text.
    """

    def __init__(self, message: str, *, field: Optional[str] = None, code: str = "invalid"):
        super().__init__(message)
        self.message = message
        self.field = field
        self.code = code

    def __str__(self) -> str:  # pragma: no cover - trivial
        if self.field:
            return f"{self.field}: {self.message}"
        return self.message


class NotFoundError(NexaError):
    """A referenced entity does not exist."""

    def __init__(self, entity_type: str, entity_id: object):
        super().__init__(f"{entity_type} {entity_id!r} was not found")
        self.entity_type = entity_type
        self.entity_id = entity_id


class ConflictError(NexaError):
    """A uniqueness or state rule would be violated.

    Example: a second employee with the same email address, or completing an
    action item that is already cancelled.
    """

    def __init__(self, message: str, *, code: str = "conflict"):
        super().__init__(message)
        self.message = message
        self.code = code


class DatabaseError(NexaError):
    """SQLite reported a problem the application cannot recover from."""


class MigrationError(NexaError):
    """The schema could not be brought up to date."""
