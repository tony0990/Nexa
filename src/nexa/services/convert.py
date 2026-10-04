"""Mapping between the domain contracts (Members 1-5) and the UI's display DTOs.

Member 6's screens work in display strings — `due_display="Mon 07 Sep 2026 15:00"`,
`email_language="ENGLISH"`, `audio_source="mic+computer"` — because they were
built against fakes. The domain stores real values: UTC datetimes, `EN`/`AR`, and
`MICROPHONE`/`COMPUTER`/`BOTH`. Every translation between the two lives here, in
pure functions with no Qt and no database, so they can be tested exhaustively.

Two rules this module exists to enforce:

* **A display string is never the source of truth.** `due_display` is what the
  admin reads and may retype. The machine value rides alongside it
  (`due_iso`/`due_time`) and is only replaced when the text was actually edited.
* **Month and weekday names are fixed English.** `strftime("%a %b")` follows the
  Windows locale, so on an Arabic system a date would render in Arabic and then
  fail to parse back. The UI's Arabic translation is a separate, deliberate layer.
"""

from __future__ import annotations

import re
from datetime import date, datetime, time
from typing import Optional, Tuple

from nexa.core.timezone import DEFAULT_TIMEZONE, combine_local, to_local, to_utc

UI_SOURCE_TO_DB = {"mic": "MICROPHONE", "computer": "COMPUTER", "mic+computer": "BOTH"}
DB_SOURCE_TO_UI = {v: k for k, v in UI_SOURCE_TO_DB.items()}

UI_LANG_TO_DB = {"ENGLISH": "EN", "ARABIC": "AR", "BILINGUAL": "BILINGUAL"}
DB_LANG_TO_UI = {v: k for k, v in UI_LANG_TO_DB.items()}

_WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")

NO_DUE = "Time not specified"
UNASSIGNED = "Unassigned"

WHEN_FORMAT = "%Y-%m-%d %H:%M"


def to_db_source(value: str) -> str:
    """UI audio source -> `MICROPHONE|COMPUTER|BOTH` (accepts a DB value as-is)."""
    return UI_SOURCE_TO_DB.get(value, value if value in DB_SOURCE_TO_UI else "MICROPHONE")


def to_ui_source(value: str) -> str:
    return DB_SOURCE_TO_UI.get(value, "mic")


def to_db_language(value: Optional[str]) -> str:
    """UI language -> `AR|EN|BILINGUAL`; anything unknown becomes Arabic."""
    text = (value or "").strip().upper()
    if text in UI_LANG_TO_DB:
        return UI_LANG_TO_DB[text]
    return text if text in DB_LANG_TO_UI else "AR"


def to_ui_language(value: Optional[str]) -> str:
    return DB_LANG_TO_UI.get((value or "").strip().upper(), "ENGLISH")


# --------------------------------------------------------------------- display
def fmt_date(day: date) -> str:
    return f"{_WEEKDAYS[day.weekday()]} {day.day:02d} {_MONTHS[day.month - 1]} {day.year}"


def fmt_local(moment: Optional[datetime], tz_name: str = DEFAULT_TIMEZONE) -> str:
    """A UTC (or aware) datetime as local `Mon 07 Sep 2026 15:00`, or `""`."""
    if moment is None:
        return ""
    local = to_local(moment, tz_name)
    return f"{fmt_date(local.date())} {local:%H:%M}"


def fmt_due(
    due_date: Optional[date],
    due_time: Optional[time] = None,
    due_at: Optional[datetime] = None,
    tz_name: str = DEFAULT_TIMEZONE,
) -> str:
    """The deadline as the admin reads it. Empty means "no date was resolved".

    `due_at` wins when present because it is the instant the scheduler uses; the
    date is then taken from its *local* day so a late-evening UTC value does not
    show the wrong weekday.
    """
    if due_at is not None:
        return fmt_local(due_at, tz_name)
    if due_date is None:
        return ""
    if due_time is None:
        return fmt_date(due_date)
    return f"{fmt_date(due_date)} {due_time:%H:%M}"


def due_for_listing(
    due_date: Optional[date], due_time: Optional[time], due_at: Optional[datetime]
) -> str:
    """`fmt_due`, but with the placeholder a table needs for an empty cell."""
    return fmt_due(due_date, due_time, due_at) or NO_DUE


def iso_day(
    due_date: Optional[date], due_at: Optional[datetime], tz_name: str = DEFAULT_TIMEZONE
) -> str:
    if due_at is not None:
        return to_local(due_at, tz_name).date().isoformat()
    return due_date.isoformat() if due_date else ""


# --------------------------------------------------------------------- parsing
_DISPLAY_RE = re.compile(
    r"^(?:[A-Za-z]{3}\s+)?(?P<d>\d{1,2})\s+(?P<m>[A-Za-z]{3})\s+(?P<y>\d{4})(?:\s+(?P<h>\d{1,2}):(?P<mi>\d{2}))?$"
)


def parse_when(text: str) -> Optional[datetime]:
    """`2026-09-10 16:00`-style text as a naive local datetime (UI snooze/reschedule)."""
    value = (text or "").strip()
    for fmt in (WHEN_FORMAT, "%Y-%m-%dT%H:%M", "%d/%m/%Y %H:%M"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return None


def to_aware_utc(naive_local: datetime, tz_name: str = DEFAULT_TIMEZONE) -> datetime:
    """A naive Cairo wall-clock time as an aware UTC instant."""
    return to_utc(naive_local, tz_name)


def parse_due_text(
    text: str, reference: datetime
) -> Tuple[Optional[date], Optional[time]]:
    """Read a deadline the admin typed back into `(date, time)`.

    Tried in order, so the cheapest exact forms win and free text is the fallback:

    1. what `fmt_due` itself produces ("Mon 07 Sep 2026 15:00")
    2. ISO-ish ("2026-09-10 16:00", "2026-09-10")
    3. natural language, through Member 3's deterministic resolvers — so
       "next Friday 3 pm" and "الخميس الجاي الساعة تلاتة" work too

    Returns `(None, None)` for text that cannot be read; the caller must treat that
    as "no deadline" and flag it, never invent one (§2.1).
    """
    value = (text or "").strip()
    if not value or value in (NO_DUE, "—", "-"):
        return None, None

    match = _DISPLAY_RE.match(value)
    if match and match.group("m").title() in _MONTHS:
        month = _MONTHS.index(match.group("m").title()) + 1
        try:
            day = date(int(match.group("y")), month, int(match.group("d")))
        except ValueError:
            day = None
        if day is not None:
            at = time(int(match.group("h")), int(match.group("mi"))) if match.group("h") else None
            return day, at

    when = parse_when(value)
    if when is not None:
        return when.date(), when.time()
    for fmt in ("%Y-%m-%d",):
        try:
            return datetime.strptime(value, fmt).date(), None
        except ValueError:
            pass

    # Natural language. Imported lazily: it pulls in dateparser.
    from nexa.dates.clock_time import find_time_phrase, parse_clock_time
    from nexa.dates.normalizer import normalize_date_phrase

    resolved = normalize_date_phrase(value, reference)
    day = resolved.resolved_datetime.date() if resolved.resolved_datetime else None
    spoken = find_time_phrase(value)
    at, _ = parse_clock_time(spoken) if spoken else (None, False)
    return day, at


def due_instant(
    day: Optional[date], at: Optional[time], tz_name: str = DEFAULT_TIMEZONE
) -> Optional[datetime]:
    """The aware UTC instant a deadline falls on, or None unless BOTH are known.

    `due_at` must stay empty for a date-only deadline. Member 5's calculator reads
    `due_date` + `due_time` and treats a missing time as "time not specified", which
    selects different reminder rules (previous-day evening and event-day morning,
    never an offset before the event). Filling `due_at` with a made-up time such as
    17:00 would turn "by Friday" into "Friday at 17:00" and move every reminder.
    """
    if day is None or at is None:
        return None
    return to_utc(combine_local(day, at, tz_name), tz_name)
