import datetime
from datetime import timedelta
from typing import Optional, Tuple

from nexa.core.validation import normalize_search_text

"""
Egyptian Arabic expression lookup table (§7.2).
Implemented as a series of regex patterns and resolution functions.

Two rules keep this table honest:

* **Match on normalized text.** Every phrase and every key below is folded
  through Member 1's `normalize_search_text`, which strips tashkeel and unifies
  the alef/ya/ta-marbuta forms. A speaker writing `الأحد`, `الاحد` or `الحد`
  means the same Sunday, and transcription output is not consistent about which
  it produces. Matching raw text means every spelling has to be enumerated by
  hand, and the one that was missed fails silently — it returns no date at all.
* **Longest phrase first.** Several entries contain each other as substrings:
  `بعد بكرة` contains `بكرة`, and `الاربعاء` contains `الاربع`. Checking the
  shorter one first silently resolves "the day after tomorrow" to tomorrow,
  which is a wrong deadline rather than a visible error.
"""


def _norm(value: str) -> str:
    """Fold a phrase for matching (tashkeel, alef/ya/ta-marbuta, digits)."""
    return normalize_search_text(value)


# Relative-day offsets, keyed by normalized phrase.
RELATIVE_DAYS = {
    _norm("النهاردة"): 0,       # today
    _norm("اليوم"): 0,
    _norm("بكرة"): 1,           # tomorrow
    _norm("غدا"): 1,
    _norm("بعد بكرة"): 2,       # the day after tomorrow
    _norm("امبارح"): -1,        # yesterday
    _norm("إمبارح"): -1,
    _norm("البارحة"): -1,
    _norm("أول امبارح"): -2,    # the day before yesterday
}

# Longest first, so `بعد بكرة` is tested before `بكرة`.
_RELATIVE_DAYS_BY_LENGTH = sorted(RELATIVE_DAYS.items(), key=lambda kv: -len(kv[0]))

# Python's calendar numbering: Monday = 0 ... Sunday = 6.
WEEKDAYS = {
    _norm("الأحد"): 6,
    _norm("الحد"): 6,
    _norm("الاثنين"): 0,
    _norm("الاتنين"): 0,
    _norm("التنين"): 0,
    _norm("الثلاثاء"): 1,
    _norm("التلاتاء"): 1,
    _norm("التلات"): 1,
    _norm("الأربعاء"): 2,
    _norm("الاربع"): 2,
    _norm("الخميس"): 3,
    _norm("الجمعة"): 4,
    _norm("السبت"): 5,
}

_WEEKDAYS_BY_LENGTH = sorted(WEEKDAYS.items(), key=lambda kv: -len(kv[0]))

# "next" markers — `الجاي` / `اللي جاي` / `القادم`.
_NEXT_MARKERS = tuple(
    _norm(marker) for marker in ("الجاي", "اللي جاي", "القادم", "الجاية")
)

# Fuzzy week ranges (§7.2, §7.3). The Egyptian working week runs Sunday to
# Thursday, so "end of the week" lands on Thursday and "start" on Sunday.
_END_OF_WEEK = tuple(_norm(p) for p in ("آخر الأسبوع", "نهاية الأسبوع"))
_START_OF_WEEK = tuple(_norm(p) for p in ("أول الأسبوع", "بداية الأسبوع"))

_END_OF_WEEK_WEEKDAY = 3    # Thursday
_START_OF_WEEK_WEEKDAY = 6  # Sunday


def _midnight(moment: datetime.datetime) -> datetime.datetime:
    return moment.replace(hour=0, minute=0, second=0, microsecond=0)


def _upcoming_weekday(
    ref_dt: datetime.datetime, target: int, *, force_next: bool
) -> datetime.datetime:
    """The upcoming `target` weekday, or the one after it when `force_next`.

    `days_ahead == 0` means the reference day itself, so `الجاي` on that day
    means the same weekday next week and never today.
    """
    days_ahead = (target - ref_dt.weekday()) % 7
    if force_next:
        days_ahead += 7
    return _midnight(ref_dt + timedelta(days=days_ahead))


def resolve_egyptian_phrase(
    phrase: str, ref_dt: datetime.datetime
) -> Tuple[Optional[datetime.datetime], bool]:
    """
    Tries to resolve an Egyptian Arabic date phrase.
    Returns (resolved_datetime, is_ambiguous).
    """
    if not phrase:
        return None, False

    normalized = _norm(phrase)
    if not normalized:
        return None, False

    # 1. Fuzzy week ranges, before weekday names: "آخر الأسبوع" denotes a range
    #    and must not be mistaken for one specific day.
    for marker in _END_OF_WEEK:
        if marker in normalized:
            return (
                _upcoming_weekday(ref_dt, _END_OF_WEEK_WEEKDAY, force_next=False),
                True,
            )
    for marker in _START_OF_WEEK:
        if marker in normalized:
            return (
                _upcoming_weekday(ref_dt, _START_OF_WEEK_WEEKDAY, force_next=False),
                True,
            )

    # 2. Immediate relative days, longest phrase first.
    for marker, offset in _RELATIVE_DAYS_BY_LENGTH:
        if marker in normalized:
            return _midnight(ref_dt + timedelta(days=offset)), False

    # 3. Relative weekdays, longest name first so `الاربعاء` is not shadowed
    #    by `الاربع`.
    for day_name, day_val in _WEEKDAYS_BY_LENGTH:
        if day_name in normalized:
            force_next = any(marker in normalized for marker in _NEXT_MARKERS)
            return _upcoming_weekday(ref_dt, day_val, force_next=force_next), False

    return None, False
