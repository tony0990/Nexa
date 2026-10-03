import re
from datetime import datetime, timedelta
from typing import Optional, Tuple

import dateparser

from nexa.dates.reference_time import CAIRO_TZ

# Python's calendar numbering: Monday = 0 ... Sunday = 6.
_WEEKDAYS = {
    "monday": 0, "mon": 0,
    "tuesday": 1, "tue": 1, "tues": 1,
    "wednesday": 2, "wed": 2,
    "thursday": 3, "thu": 3, "thurs": 3,
    "friday": 4, "fri": 4,
    "saturday": 5, "sat": 5,
    "sunday": 6, "sun": 6,
}

# `next Monday`, `this coming Friday`, `by next Thu` ... dateparser returns None
# for every one of these — it handles a bare "Monday" and "next week" but not
# "next Monday". §14 pairs dateparser with custom rules for exactly this, and a
# deadline phrased with "next" is too common to leave unresolved.
_QUALIFIED_WEEKDAY = re.compile(
    r"\b(?P<qualifier>next|this|coming|upcoming)\s+(?:week\s+)?"
    r"(?P<weekday>" + "|".join(sorted(_WEEKDAYS, key=len, reverse=True)) + r")\b",
    re.IGNORECASE,
)


def _qualified_weekday(phrase: str, ref_dt: datetime) -> Optional[datetime]:
    """Resolve `next <weekday>` / `this <weekday>` forward from the reference.

    Same semantics as the Egyptian table's `الجاي` / `ده`: "this Friday" is the
    upcoming one, and "next Friday" is the one after that — never today, which
    is what a speaker on a Friday saying "next Friday" means.
    """
    match = _QUALIFIED_WEEKDAY.search(phrase or "")
    if match is None:
        return None
    target = _WEEKDAYS[match.group("weekday").lower()]
    days_ahead = (target - ref_dt.weekday()) % 7
    if match.group("qualifier").lower() == "next":
        days_ahead += 7
    elif days_ahead == 0:
        # "this Monday" said on a Monday means the coming one, not today.
        days_ahead = 7
    resolved = ref_dt + timedelta(days=days_ahead)
    return resolved.replace(hour=0, minute=0, second=0, microsecond=0)


def resolve_english_phrase(phrase: str, ref_dt: datetime) -> Tuple[Optional[datetime], bool]:
    """
    Wraps dateparser to resolve English relative dates.
    Ensures Africa/Cairo timezone and reference_datetime base.
    """
    qualified = _qualified_weekday(phrase, ref_dt)
    if qualified is not None:
        return qualified.astimezone(CAIRO_TZ), False

    settings = {
        "RELATIVE_BASE": ref_dt,
        "TIMEZONE": "Africa/Cairo",
        "RETURN_AS_TIMEZONE_AWARE": True,
        # Deadlines point forward. Without this, dateparser resolves a bare
        # weekday to the nearest one in *either* direction, so "by Friday" said
        # on a Thursday came back as the Friday six days earlier — a deadline
        # already in the past, which means a reminder that never fires and an
        # action item that is overdue the moment it is approved.
        #
        # This only affects phrases that are ambiguous about direction, such as
        # "Friday" or "March 5". An explicitly past phrase ("yesterday", "two
        # days ago") still resolves backwards, which is what the validator
        # flags. It also matches the Egyptian table, whose weekday lookup has
        # always resolved forward.
        "PREFER_DATES_FROM": "future",
    }

    try:
        resolved = dateparser.parse(phrase, settings=settings)
        if resolved:
            # Ensure it's Cairo aware
            resolved = resolved.astimezone(CAIRO_TZ)
            return resolved, False
    except Exception:
        pass

    return None, False
