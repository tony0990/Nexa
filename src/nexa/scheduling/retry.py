"""Retry policy.

Attempt 1: immediately
Attempt 2: +1 minute
Attempt 3: +5 minutes
Attempt 4: +15 minutes
Attempt 5: +30 minutes
Then: FAILED
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional


@dataclass(frozen=True)
class RetryPolicy:
    delays: tuple[timedelta, ...] = (
        timedelta(minutes=1),
        timedelta(minutes=5),
        timedelta(minutes=15),
        timedelta(minutes=30),
    )

    @property
    def max_attempts(self) -> int:
        return len(self.delays) + 1

    def next_attempt(self, attempt_number: int, now: datetime) -> Optional[datetime]:
        """`attempt_number` = number of attempts already made (1-based) that failed.
        Returns when the next attempt may run, or None when the reminder must FAIL."""
        if attempt_number < 1:
            return now
        if attempt_number > len(self.delays):
            return None
        return now + self.delays[attempt_number - 1]

    def has_attempts_left(self, attempt_number: int) -> bool:
        return attempt_number < self.max_attempts
