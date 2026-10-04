"""Schedule view-model: filtering plus validated snooze / reschedule logic.

Everything here is pure Python (no Qt) so it can be unit-tested headless.
Snooze only changes the *reminder* time; the task deadline is never touched.
"""

from __future__ import annotations

from datetime import datetime, timedelta

SNOOZE_KEYS = ("30m", "1h", "3h", "tomorrow", "custom")
WHEN_FORMAT = "%Y-%m-%d %H:%M"
_ACCEPTED = (WHEN_FORMAT, "%Y-%m-%dT%H:%M", "%d/%m/%Y %H:%M")


def cairo_now() -> datetime:
    """Naive 'now' in Africa/Cairo (falls back to local time if tzdata is missing)."""
    try:
        from zoneinfo import ZoneInfo

        return datetime.now(ZoneInfo("Africa/Cairo")).replace(tzinfo=None)
    except Exception:  # pragma: no cover - depends on platform tzdata
        return datetime.now()


def parse_when(text: str) -> datetime:
    value = (text or "").strip()
    for fmt in _ACCEPTED:
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    raise ValueError("invalid_datetime")


def _morning(morning: str) -> tuple[int, int]:
    try:
        hour, minute = (int(p) for p in morning.split(":"))
        if 0 <= hour < 24 and 0 <= minute < 60:
            return hour, minute
    except ValueError:
        pass
    return 8, 0


def snooze_target(option: str, now: datetime, custom_text: str = "", morning: str = "08:00") -> str:
    """Return the new reminder time as 'YYYY-MM-DD HH:MM'. Raises ValueError if invalid."""
    if option == "30m":
        target = now + timedelta(minutes=30)
    elif option == "1h":
        target = now + timedelta(hours=1)
    elif option == "3h":
        target = now + timedelta(hours=3)
    elif option == "tomorrow":
        hour, minute = _morning(morning)
        target = (now + timedelta(days=1)).replace(hour=hour, minute=minute, second=0, microsecond=0)
    elif option == "custom":
        target = parse_when(custom_text)
        if target <= now:
            raise ValueError("in_the_past")
    else:
        raise ValueError("unknown_option")
    return target.strftime(WHEN_FORMAT)


class ScheduleViewModel:
    def __init__(self, reminders) -> None:
        self.reminders = reminders
        self.filter_status = "all"

    def rows(self):
        filters = {}
        if self.filter_status == "unassigned":
            filters["owner"] = "Unassigned"
        elif self.filter_status != "all":
            filters["status"] = self.filter_status
        return self.reminders.list_actions(filters)

    def rows_for_iso(self, iso: str):
        return [row for row in self.rows() if getattr(row, "due_iso", "") == iso]

    def marked_dates(self) -> set[str]:
        return {row.due_iso for row in self.rows() if getattr(row, "due_iso", "")}

    def snooze(self, action_id: int, option: str, custom_text: str = "", morning: str = "08:00", now: datetime | None = None) -> str:
        target = snooze_target(option, now or cairo_now(), custom_text, morning)
        self.reminders.snooze(action_id, target)
        return target

    def reschedule(self, action_id: int, text: str, now: datetime | None = None) -> str:
        when = parse_when(text)
        if when <= (now or cairo_now()):
            raise ValueError("in_the_past")
        value = when.strftime(WHEN_FORMAT)
        self.reminders.reschedule_action(action_id, value)
        return value
