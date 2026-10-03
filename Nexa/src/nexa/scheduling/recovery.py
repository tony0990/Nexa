"""Missed-reminder recovery.

If Windows was unavailable at the scheduled time:
    scheduled_at <= now AND now - scheduled_at <= recovery_window
-> send immediately and tag the delivery as late recovery.
Older than the window -> not sent (marked FAILED: MISSED_RECOVERY_WINDOW_EXPIRED).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Mapping, Optional

DEFAULT_RECOVERY_HOURS = 24          # setting: missed_reminder_recovery_hours
DEFAULT_LATE_GRACE = timedelta(minutes=2)   # normal polling delay is not "late"
MISSED_EXPIRED_ERROR = "MISSED_RECOVERY_WINDOW_EXPIRED"


class DueClass(str, Enum):
    NOT_DUE = "NOT_DUE"
    ON_TIME = "ON_TIME"
    LATE_RECOVERY = "LATE_RECOVERY"
    EXPIRED = "EXPIRED"


@dataclass(frozen=True)
class RecoveryPolicy:
    recovery_window: timedelta = timedelta(hours=DEFAULT_RECOVERY_HOURS)
    late_grace: timedelta = DEFAULT_LATE_GRACE

    @classmethod
    def from_settings(cls, settings: Mapping[str, Any]) -> "RecoveryPolicy":
        hours = settings.get("missed_reminder_recovery_hours")
        try:
            hours = float(str(hours).strip('"')) if hours is not None else DEFAULT_RECOVERY_HOURS
        except ValueError:
            hours = DEFAULT_RECOVERY_HOURS
        return cls(recovery_window=timedelta(hours=hours))

    def classify(self, scheduled_at: datetime, now: datetime) -> DueClass:
        if scheduled_at > now:
            return DueClass.NOT_DUE
        lateness = now - scheduled_at
        if lateness <= self.late_grace:
            return DueClass.ON_TIME
        if lateness <= self.recovery_window:
            return DueClass.LATE_RECOVERY
        return DueClass.EXPIRED

    def lateness(self, scheduled_at: datetime, now: datetime) -> Optional[timedelta]:
        return max(now - scheduled_at, timedelta(0))
