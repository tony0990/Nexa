"""Pure reminder-time calculation + timezone/DB datetime helpers (no I/O)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo

from .rules import EVENT_DAY, OFFSET_BEFORE, PREVIOUS_DAY, ReminderPolicy
from .states import ReminderType

UTC = timezone.utc
CAIRO = ZoneInfo("Africa/Cairo")
DB_FORMAT = "%Y-%m-%d %H:%M:%S"     # UTC, fixed width => lexicographic == chronological


def ensure_aware(dt: datetime, assume=CAIRO) -> datetime:
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=assume)


def to_db(dt: datetime) -> str:
    return ensure_aware(dt, UTC).astimezone(UTC).strftime(DB_FORMAT)


def from_db(value: Optional[str]) -> Optional[datetime]:
    if value is None or value == "":
        return None
    dt = datetime.fromisoformat(str(value))
    return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt.astimezone(UTC)


def local_combine(d: date, t: time) -> datetime:
    return datetime.combine(d, t.replace(tzinfo=None), tzinfo=CAIRO)


@dataclass(frozen=True)
class PlannedReminder:
    rule_type: str
    reminder_type: ReminderType
    scheduled_at: datetime          # aware, UTC

    @property
    def local(self) -> datetime:
        return self.scheduled_at.astimezone(CAIRO)


def resolve_event(
    due_date: Optional[date], due_time: Optional[time], due_at: Optional[datetime]
) -> Optional[tuple[datetime, bool]]:
    """Return (event_local, time_specified) or None when nothing is schedulable."""
    if due_date is not None:
        if due_time is not None:
            return local_combine(due_date, due_time), True
        return local_combine(due_date, time(0, 0)), False
    if due_at is not None:
        return ensure_aware(due_at).astimezone(CAIRO), True
    return None


def early_event_reminder(event_local: datetime, policy: ReminderPolicy) -> datetime:
    """max(earliest_reasonable_time, event - lead), never at/after the event."""
    floor = local_combine(event_local.date(), policy.earliest_reasonable_time)
    candidate = max(floor, event_local - policy.early_event_lead)
    if candidate >= event_local:
        candidate = event_local - policy.early_event_lead
    return candidate


def calculate_reminders(
    due_date: Optional[date],
    due_time: Optional[time],
    due_at: Optional[datetime],
    policy: ReminderPolicy,
    now: Optional[datetime] = None,
) -> list[PlannedReminder]:
    resolved = resolve_event(due_date, due_time, due_at)
    if resolved is None:
        return []
    event_local, time_specified = resolved
    event_day = event_local.date()
    candidates: list[tuple[str, ReminderType, datetime]] = []

    for rule in policy.enabled_rules():
        if rule.rule_type == PREVIOUS_DAY:
            when = local_combine(event_day - timedelta(days=1), rule.fixed_local_time)
            candidates.append((rule.rule_type, ReminderType.PREVIOUS_DAY, when))
        elif rule.rule_type == EVENT_DAY:
            fixed = local_combine(event_day, rule.fixed_local_time)
            early = (
                time_specified
                and policy.smart_early_event
                and (event_local.timetz().replace(tzinfo=None) <= policy.early_event_threshold
                     or fixed >= event_local)
            )
            if early:
                candidates.append((rule.rule_type, ReminderType.EARLY_EVENT,
                                   early_event_reminder(event_local, policy)))
            elif time_specified and fixed >= event_local:
                continue                      # smart rule disabled: never remind after the event
            else:
                candidates.append((rule.rule_type, ReminderType.EVENT_DAY, fixed))
        elif rule.rule_type == OFFSET_BEFORE and time_specified:
            when = event_local - timedelta(minutes=rule.offset_minutes)
            candidates.append((rule.rule_type, ReminderType.OFFSET_BEFORE, when))

    planned: dict[datetime, PlannedReminder] = {}
    for rule_type, rtype, when in candidates:
        utc = when.astimezone(UTC)
        if now is not None and utc < ensure_aware(now, UTC):
            continue                          # already in the past: nothing to schedule
        planned.setdefault(utc.replace(second=0, microsecond=0),
                           PlannedReminder(rule_type, rtype, utc.replace(second=0, microsecond=0)))
    return sorted(planned.values(), key=lambda p: p.scheduled_at)
