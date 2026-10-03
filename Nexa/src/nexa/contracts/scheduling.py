from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Protocol


@dataclass
class Reminder:
    id: int
    action_item_id: int
    scheduled_at: datetime                 # timezone-aware (UTC)
    status: str = "PENDING"
    attempt_count: int = 0
    next_attempt_at: Optional[datetime] = None
    claimed_at: Optional[datetime] = None
    sent_at: Optional[datetime] = None
    last_error: Optional[str] = None
    idempotency_key: str = ""
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class ReminderQueue(Protocol):
    def enqueue_for_action(self, action) -> list[Reminder]: ...
    def claim_due(self, now: datetime, limit: int) -> list[Reminder]: ...
