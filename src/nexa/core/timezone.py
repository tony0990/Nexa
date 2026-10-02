"""Timezone handling for Nexa.

Rules for the whole application:

* Everything is stored in UTC as an ISO-8601 string ending in `+00:00`.
* Everything shown to a human, and every reminder decision, uses the
  application timezone (`Africa/Cairo` by default).
* A naive datetime coming from the UI or a fixture is interpreted as local
  application time, never as UTC.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from typing import Optional, Tuple

try:  # pragma: no cover - platform dependent
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover - Python < 3.9
    ZoneInfo = None  # type: ignore[assignment]

DEFAULT_TIMEZONE = "Africa/Cairo"
UTC = timezone.utc


def get_timezone(name: str = DEFAULT_TIMEZONE):
    """Return a tzinfo for `name`, falling back to a fixed +02:00 offset.

    Windows machines without `tzdata` installed cannot load the IANA database.
    Cairo is UTC+02:00 (Egypt reintroduced DST in 2023, so the fallback is an
    approximation used only to keep the app running; `tzdata` is the supported
    configuration and is listed in requirements for packaging).
    """
    if ZoneInfo is not None:
        try:
            return ZoneInfo(name)
        except Exception:
            pass
    return timezone(timedelta(hours=2), name)


def has_iana_timezone(name: str = DEFAULT_TIMEZONE) -> bool:
    """True when the real IANA rules (including DST) are available.

    The first-run check surfaces this: on a machine where it is False, Cairo
    summer time is not applied and reminders would be an hour off, so the
    packaged build must ship `tzdata`.
    """
    if ZoneInfo is None:
        return False
    try:
        ZoneInfo(name)
    except Exception:
        return False
    return True


def to_utc(value: datetime, tz_name: str = DEFAULT_TIMEZONE) -> datetime:
    """Convert any datetime to an aware UTC datetime."""
    if value.tzinfo is None:
        value = value.replace(tzinfo=get_timezone(tz_name))
    return value.astimezone(UTC)


def to_local(value: datetime, tz_name: str = DEFAULT_TIMEZONE) -> datetime:
    """Convert any datetime to the application timezone."""
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(get_timezone(tz_name))


def combine_local(
    day: date, at: Optional[time], tz_name: str = DEFAULT_TIMEZONE
) -> datetime:
    """Build a local aware datetime from a date and an optional time.

    A missing time means "time not specified" (Section 2.1) and is treated as
    the end of the working day only by callers that need a concrete instant;
    here it simply becomes midnight local time.
    """
    return datetime.combine(day, at or time(0, 0), tzinfo=get_timezone(tz_name))


def start_of_day(day: date, tz_name: str = DEFAULT_TIMEZONE) -> datetime:
    return combine_local(day, time(0, 0), tz_name)


def end_of_day(day: date, tz_name: str = DEFAULT_TIMEZONE) -> datetime:
    """Exclusive upper bound: midnight at the start of the next day."""
    return combine_local(day + timedelta(days=1), time(0, 0), tz_name)


def day_bounds_utc(day: date, tz_name: str = DEFAULT_TIMEZONE) -> Tuple[datetime, datetime]:
    """Half-open `[start, end)` UTC bounds covering one local calendar day."""
    return to_utc(start_of_day(day, tz_name)), to_utc(end_of_day(day, tz_name))


def range_bounds_utc(
    first_day: date, last_day: date, tz_name: str = DEFAULT_TIMEZONE
) -> Tuple[datetime, datetime]:
    """Half-open UTC bounds covering the inclusive local day range."""
    return to_utc(start_of_day(first_day, tz_name)), to_utc(end_of_day(last_day, tz_name))


def week_bounds(day: date, week_starts_on: int = 6) -> Tuple[date, date]:
    """Inclusive first/last day of the week containing `day`.

    `week_starts_on` uses `date.weekday()` numbering (Mon=0 .. Sun=6). The
    default is Sunday, which is the working week in Egypt.
    """
    delta = (day.weekday() - week_starts_on) % 7
    first = day - timedelta(days=delta)
    return first, first + timedelta(days=6)


def month_bounds(day: date) -> Tuple[date, date]:
    """Inclusive first/last day of the month containing `day`."""
    first = day.replace(day=1)
    if first.month == 12:
        next_first = first.replace(year=first.year + 1, month=1)
    else:
        next_first = first.replace(month=first.month + 1)
    return first, next_first - timedelta(days=1)


def isoformat_utc(value: Optional[datetime], tz_name: str = DEFAULT_TIMEZONE) -> Optional[str]:
    """Serialize a datetime for storage."""
    if value is None:
        return None
    return to_utc(value, tz_name).isoformat()


def parse_utc(value: Optional[str]) -> Optional[datetime]:
    """Parse a stored timestamp back into an aware UTC datetime."""
    if value is None or value == "":
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)
