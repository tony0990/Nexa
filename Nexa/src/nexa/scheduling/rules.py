"""Reminder rule engine configuration.

Default policy (Africa/Cairo):
    Reminder A: previous day 20:00
    Reminder B: event day   08:00
Smart early-event rule (section 33 of the spec):
    if event_time <= 09:00:
        reminder = max(earliest_reasonable_time, event_time - 2 hours)
    else:
        reminder = 08:00
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import time, timedelta
from typing import Any, Mapping, Optional

PREVIOUS_DAY = "PREVIOUS_DAY"
EVENT_DAY = "EVENT_DAY"
OFFSET_BEFORE = "OFFSET_BEFORE"
RULE_TYPES = (PREVIOUS_DAY, EVENT_DAY, OFFSET_BEFORE)


def parse_hhmm(value: Any, default: time) -> time:
    """Accepts 'HH:MM', 'HH:MM:SS', datetime.time or a JSON-ish '\"20:00\"' string."""
    if value is None:
        return default
    if isinstance(value, time):
        return value.replace(second=0, microsecond=0, tzinfo=None)
    text = str(value).strip().strip('"').strip("'")
    try:
        parts = [int(p) for p in text.split(":")]
        return time(parts[0], parts[1] if len(parts) > 1 else 0)
    except (ValueError, IndexError):
        return default


@dataclass(frozen=True)
class ReminderRule:
    rule_type: str
    fixed_local_time: Optional[time] = None   # PREVIOUS_DAY / EVENT_DAY
    offset_minutes: Optional[int] = None      # OFFSET_BEFORE
    enabled: bool = True

    def __post_init__(self):
        if self.rule_type not in RULE_TYPES:
            raise ValueError(f"unknown rule_type {self.rule_type!r}")
        if self.rule_type in (PREVIOUS_DAY, EVENT_DAY) and self.fixed_local_time is None:
            raise ValueError(f"{self.rule_type} needs fixed_local_time")
        if self.rule_type == OFFSET_BEFORE and not self.offset_minutes:
            raise ValueError("OFFSET_BEFORE needs offset_minutes")


@dataclass(frozen=True)
class ReminderPolicy:
    rules: tuple[ReminderRule, ...]
    smart_early_event: bool = True
    early_event_threshold: time = time(9, 0)
    early_event_lead: timedelta = timedelta(hours=2)
    earliest_reasonable_time: time = time(6, 0)

    @classmethod
    def default(cls) -> "ReminderPolicy":
        return cls(rules=(
            ReminderRule(PREVIOUS_DAY, fixed_local_time=time(20, 0)),
            ReminderRule(EVENT_DAY, fixed_local_time=time(8, 0)),
        ))

    @classmethod
    def from_settings(cls, settings: Mapping[str, Any]) -> "ReminderPolicy":
        """Build from the Settings keys (values may be raw or JSON-decoded)."""
        evening = parse_hhmm(settings.get("default_evening_reminder_time"), time(20, 0))
        morning = parse_hhmm(settings.get("default_morning_reminder_time"), time(8, 0))
        lead = settings.get("early_event_lead_minutes")
        smart = settings.get("smart_early_event_enabled")
        return cls(
            rules=(
                ReminderRule(PREVIOUS_DAY, fixed_local_time=evening),
                ReminderRule(EVENT_DAY, fixed_local_time=morning),
            ),
            smart_early_event=True if smart is None else bool(smart),
            early_event_threshold=parse_hhmm(settings.get("early_event_threshold"), time(9, 0)),
            early_event_lead=timedelta(minutes=int(lead)) if lead is not None else timedelta(hours=2),
            earliest_reasonable_time=parse_hhmm(settings.get("earliest_reasonable_time"), time(6, 0)),
        )

    def enabled_rules(self) -> tuple[ReminderRule, ...]:
        return tuple(r for r in self.rules if r.enabled)
