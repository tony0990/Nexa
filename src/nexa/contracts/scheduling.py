"""Shared reminder/scheduling contracts (owned end-to-end by Member 5)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time
from enum import Enum
from typing import Optional, Protocol, Sequence, runtime_checkable


class ReminderStatus(str, Enum):
    PENDING = "PENDING"
    CLAIMED = "CLAIMED"
    SENDING = "SENDING"
    SENT = "SENT"
    RETRY_WAIT = "RETRY_WAIT"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    SNOOZED = "SNOOZED"
    SKIPPED_COMPLETED = "SKIPPED_COMPLETED"


class ReminderRuleType(str, Enum):
    PREVIOUS_DAY_FIXED = "PREVIOUS_DAY_FIXED"
    EVENT_DAY_FIXED = "EVENT_DAY_FIXED"
    OFFSET_BEFORE = "OFFSET_BEFORE"


@dataclass(frozen=True)
class ReminderRule:
    id: Optional[int] = None
    action_item_id: Optional[int] = None
    rule_type: str = ReminderRuleType.EVENT_DAY_FIXED.value
    offset_minutes: Optional[int] = None
    fixed_local_time: Optional[time] = None
    enabled: bool = True
    created_at: Optional[datetime] = None


@dataclass(frozen=True)
class Reminder:
    id: Optional[int] = None
    action_item_id: Optional[int] = None
    scheduled_at: Optional[datetime] = None
    status: str = ReminderStatus.PENDING.value
    attempt_count: int = 0
    next_attempt_at: Optional[datetime] = None
    claimed_at: Optional[datetime] = None
    sent_at: Optional[datetime] = None
    last_error: Optional[str] = None
    idempotency_key: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


@runtime_checkable
class ReminderQueue(Protocol):
    def enqueue_for_action(self, action: object) -> Sequence[Reminder]: ...

    def claim_due(self, now: datetime, limit: int) -> Sequence[Reminder]: ...
