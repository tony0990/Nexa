"""Spoken clock times in Egyptian Arabic, English and code-switched speech.

`dates/time_of_day.py` was a skeleton that nothing called, so no extracted action
ever received a time of day. It also had an ordering bug: the cultural-band
check ("الصبح" -> 08:00) ran *before* the hour was parsed, so "الساعة عشرة
الصبح" (ten in the morning) came back as 08:00.

This module is the real parser. It returns `(time, needs_review)`:

* `needs_review` is True whenever the hour had to be *guessed* from a cultural
  band rather than stated — "العصر" alone is "afternoon", not 16:00 exactly. That
  is Section 2.1 again: show uncertainty, never invent precision.
* A bare hour with no am/pm ("الساعة three", "at 3") is resolved to the
  working-day reading (1-6 -> afternoon) and flagged, because it is genuinely
  ambiguous and a wrong guess sends a reminder twelve hours off.

Everything is matched on text folded through `normalize_search_text`, so
`الساعه`/`الساعة`, `تلاته`/`تلاتة` and Arabic-Indic digits all land on one form.
"""

from __future__ import annotations

import re
from datetime import time
from typing import Optional, Tuple

from nexa.core.validation import normalize_search_text

# Egyptian + MSA number words for 1-12, normalized the same way the phrase is.
# Longest first so "اتناشر" is tried before "اتنين"-like prefixes.
_HOUR_WORDS = {
    "واحده": 1, "واحد": 1, "one": 1,
    "اتنين": 2, "اثنين": 2, "ثنتين": 2, "two": 2,
    "تلاته": 3, "ثلاثه": 3, "three": 3,
    "اربعه": 4, "اربع": 4, "four": 4,
    "خمسه": 5, "خمس": 5, "five": 5,
    "سته": 6, "ست": 6, "six": 6,
    "سبعه": 7, "سبع": 7, "seven": 7,
    "تمانيه": 8, "ثمانيه": 8, "تمنيه": 8, "eight": 8,
    "تسعه": 9, "تسع": 9, "nine": 9,
    "عشره": 10, "عشر": 10, "ten": 10,
    "حداشر": 11, "احدعشر": 11, "حدعشر": 11, "eleven": 11,
    "اتناشر": 12, "اثناعشر": 12, "twelve": 12,
}
_WORDS_BY_LENGTH = sorted(_HOUR_WORDS, key=len, reverse=True)

# Period markers -> (is_pm, is_exact). "exact" means the speaker said enough to
# fix am/pm; the cultural bands below are approximations.
_PM_WORDS = ("مساء", "بالليل", "الليل", "العصر", "العشاء", "pm", "p.m")
_AM_WORDS = ("صباحا", "الصبح", "الفجر", "am", "a.m", "الصباح")
_NOON = ("الضهر", "الظهر", "noon", "midday")
_MIDNIGHT = ("منتصف الليل", "midnight")

# Defaults when only a band was spoken: "after lunch", "in the evening"...
_BANDS = (
    ("العصر", time(16, 0)),
    ("الضهر", time(12, 0)),
    ("الظهر", time(12, 0)),
    ("بالليل", time(21, 0)),
    ("الليل", time(21, 0)),
    ("المغرب", time(18, 0)),
    ("الصبح", time(9, 0)),
    ("الصباح", time(9, 0)),
    ("morning", time(9, 0)),
    ("afternoon", time(15, 0)),
    ("evening", time(18, 0)),
    ("tonight", time(20, 0)),
    ("noon", time(12, 0)),
    ("midnight", time(0, 0)),
    ("eod", time(17, 0)),
    ("end of day", time(17, 0)),
    ("close of business", time(17, 0)),
    ("اخر اليوم", time(17, 0)),
)

_DIGIT_TIME = re.compile(r"(?<!\d)(\d{1,2})(?:[:.](\d{2}))?(?!\d)")
_EXPLICIT_24H = re.compile(r"(?<!\d)([01]?\d|2[0-3]):([0-5]\d)(?!\d)")


def _has(text: str, words) -> bool:
    return any(w in text for w in words)


def _period(text: str) -> Optional[bool]:
    """True = pm, False = am, None = not stated."""
    if _has(text, _PM_WORDS):
        return True
    if _has(text, _AM_WORDS):
        return False
    return None


def _apply_period(hour: int, minute: int, text: str) -> Tuple[time, bool]:
    """Place an hour 1-12 on the 24h clock. Returns (time, guessed)."""
    pm = _period(text)
    if pm is None and _has(text, _NOON) and hour in (11, 12, 1, 2):
        pm = hour != 11
    if pm is True:
        hour = hour if hour == 12 else hour + 12
        return time(hour % 24, minute), False
    if pm is False:
        hour = 0 if hour == 12 else hour
        return time(hour, minute), False
    # Not stated. 13-23 is already unambiguous 24h.
    if hour >= 13:
        return time(hour % 24, minute), False
    # Working-day reading: 1-6 is the afternoon, 7-11 the morning, 12 noon.
    if 1 <= hour <= 6:
        return time(hour + 12, minute), True
    return time(hour, minute), True


def _minutes_modifier(text: str) -> Optional[int]:
    """`ونص` +30, `وربع` +15, `الا ربع` -15, `الا تلت` -20, `وتلت` +20."""
    if "الا ربع" in text:
        return -15
    if "الا تلت" in text:
        return -20
    if "ونص" in text or "ونصف" in text or "و نص" in text:
        return 30
    if "وربع" in text or "و ربع" in text:
        return 15
    if "وتلت" in text or "و تلت" in text:
        return 20
    return None


def parse_clock_time(phrase: Optional[str]) -> Tuple[Optional[time], bool]:
    """Parse a spoken clock time. Returns `(time | None, needs_review)`.

    >>> parse_clock_time("الساعة 10 الصبح")
    (datetime.time(10, 0), False)
    >>> parse_clock_time("تلاتة ونص")
    (datetime.time(15, 30), True)
    >>> parse_clock_time("at 3:30 pm")
    (datetime.time(15, 30), False)
    >>> parse_clock_time("العصر")
    (datetime.time(16, 0), True)
    """
    if not phrase or not phrase.strip():
        return None, False
    text = normalize_search_text(phrase)

    # 1. Unambiguous 24-hour "15:30".
    match = _EXPLICIT_24H.search(text)
    if match and int(match.group(1)) >= 13:
        return time(int(match.group(1)), int(match.group(2))), False

    # 2. Midnight / noon words stand alone.
    if _has(text, _MIDNIGHT):
        return time(0, 0), False

    # 3. A digit hour: "10", "3:30", "3.30 pm".
    digit = _DIGIT_TIME.search(text)
    if digit:
        hour = int(digit.group(1))
        minute = int(digit.group(2)) if digit.group(2) else 0
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            adj = _minutes_modifier(text)
            if adj is not None and not digit.group(2):
                hour, minute = _shift(hour, adj)
            result, guessed = _apply_period(hour, minute, text)
            return result, guessed

    # 4. A number word: "تلاتة ونص", "الساعة عشرة بالليل", "three".
    for word in _WORDS_BY_LENGTH:
        if re.search(rf"(?<![^\W\d_]){re.escape(word)}(?![^\W\d_])", text):
            hour = _HOUR_WORDS[word]
            minute = 0
            adj = _minutes_modifier(text)
            if adj is not None:
                hour, minute = _shift(hour, adj)
            result, guessed = _apply_period(hour, minute, text)
            return result, guessed

    # 5. Only a cultural band: "العصر", "in the evening". Approximate by nature.
    for band, default in _BANDS:
        if band in text:
            return default, True

    return None, False


def _shift(hour: int, minutes: int) -> Tuple[int, int]:
    """Apply a +/- minute modifier, wrapping the hour: 3 الا ربع -> 2:45."""
    total = hour * 60 + minutes
    total %= 12 * 60 if hour <= 12 else 24 * 60
    h, m = divmod(total, 60)
    return (h if h else 12) if hour <= 12 else h, m


def find_time_phrase(text: str) -> Optional[str]:
    """The span of `text` that reads as a clock time, as spoken, or None.

    Used by the extractor so `raw_time_phrase` is the user's own words and the
    parser above then interprets it — the same split Section 2.2 requires for
    dates: the spoken form is evidence, the computed value is separate.
    """
    patterns = (
        # الساعة 10 الصبح / الساعة تلاتة ونص / الساعة 3 ونص
        r"(?:الساعة|الساعه|الساعة)\s+[^\s،,.؟?!]+(?:\s+(?:ونص|ونصف|وربع|وتلت|الا\s+ربع|الا\s+تلت))?"
        r"(?:\s+(?:الصبح|صباحا|الصباح|مساء|بالليل|العصر|الضهر|الظهر|المغرب))?",
        # at 3 pm / at 3:30 / 3 pm / 15:30
        # (?![A-Za-z]) rather than \b: "3 p.m." ends in a full stop, and there is
        # no word boundary between "." and a following space, so \b made the
        # match backtrack to "3 p" and strand ".m." in the task text.
        # The final dot is consumed only when it belongs to "p.m." itself; "3 PM."
        # must leave its sentence-ending full stop alone.
        r"\b(?:at\s+)?\d{1,2}(?::\d{2})?\s*(?:a\.m\.|p\.m\.|a\.m|p\.m|am|pm)(?![A-Za-z])",
        r"\bat\s+\d{1,2}(?::\d{2})?\b",
        r"\b(?:[01]?\d|2[0-3]):[0-5]\d\b",
        r"\bat\s+(?:one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve)\b",
        r"\b(?:end of (?:the )?day|eod|close of business|noon|midnight|tonight)\b",
        r"(?:العصر|الضهر|الظهر|بالليل|المغرب|الصبح|الصباح|صباحا|مساء|اخر اليوم|آخر اليوم)",
        r"\b(?:in the )?(?:morning|afternoon|evening)\b",
    )
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return match.group(0).strip()
    return None
