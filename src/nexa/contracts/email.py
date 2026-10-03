"""Shared delivery-target and email contracts (sending is Member 4's work)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional, Protocol, Sequence, runtime_checkable


class DeliveryKind(str, Enum):
    REPORT = "REPORT"
    REMINDER = "REMINDER"


class TargetType(str, Enum):
    ALL = "ALL"
    MEETING_PARTICIPANTS = "MEETING_PARTICIPANTS"
    ROLE = "ROLE"
    EMPLOYEE = "EMPLOYEE"
    ASSIGNEE = "ASSIGNEE"


class DeliveryStatus(str, Enum):
    PENDING = "PENDING"
    SENDING = "SENDING"
    SENT = "SENT"
    FAILED = "FAILED"


@dataclass(frozen=True)
class DeliveryTarget:
    """An abstract recipient selection, resolved to employees by Member 1.

    `target_id` means: role id for ROLE, employee id for EMPLOYEE, and is
    unused for ALL / MEETING_PARTICIPANTS / ASSIGNEE, which are resolved from
    `meeting_id` / `action_item_id`.
    """

    id: Optional[int] = None
    meeting_id: Optional[int] = None
    action_item_id: Optional[int] = None
    delivery_kind: str = DeliveryKind.REPORT.value
    target_type: str = TargetType.ALL.value
    target_id: Optional[int] = None
    created_at: Optional[datetime] = None


@dataclass(frozen=True)
class EmailDelivery:
    id: Optional[int] = None
    meeting_id: Optional[int] = None
    action_item_id: Optional[int] = None
    reminder_id: Optional[int] = None
    recipient_employee_id: Optional[int] = None
    recipient_email: str = ""
    subject: str = ""
    language: str = "AR"
    status: str = DeliveryStatus.PENDING.value
    gmail_message_id: Optional[str] = None
    attempted_at: Optional[datetime] = None
    sent_at: Optional[datetime] = None
    error_message: Optional[str] = None


@dataclass(frozen=True)
class RenderedEmail:
    to_email: str = ""
    to_name: str = ""
    subject: str = ""
    html_body: str = ""
    text_body: str = ""
    language: str = "AR"


@dataclass(frozen=True)
class SendResult:
    """The outcome of one send attempt.

    `retryable` is the retry contract between Member 4 and Member 5: Section
    24.1 makes "retryable vs permanent errors" Member 4's job, and this is the
    only channel to the worker's retry policy. It defaults to True because a
    retried reminder is recoverable and a dropped one is not — see
    `nexa.email.errors.classify_status`. It is meaningless when `ok` is True.
    """

    ok: bool = False
    gmail_message_id: Optional[str] = None
    error_message: Optional[str] = None
    retryable: bool = True


@runtime_checkable
class RecipientResolver(Protocol):
    def resolve(self, targets: Sequence[DeliveryTarget]) -> Sequence[object]: ...


@runtime_checkable
class EmailSender(Protocol):
    def send(self, message: RenderedEmail) -> SendResult: ...
