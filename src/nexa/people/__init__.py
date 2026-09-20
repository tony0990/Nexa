"""Employees, roles and recipient resolution."""

from .recipient_resolver import (
    RecipientResolver,
    ResolutionResult,
    SkippedRecipient,
)
from .service import PeopleService

__all__ = [
    "PeopleService",
    "RecipientResolver",
    "ResolutionResult",
    "SkippedRecipient",
]
