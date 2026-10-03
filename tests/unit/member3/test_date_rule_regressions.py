"""Regressions for three bugs that all failed *silently*.

Each of these produced a plausible-looking wrong answer rather than an error,
which is the expensive kind in a deadline system:

1. `بعد بكرة` ("the day after tomorrow") resolved to tomorrow, because the
   shorter `بكرة` was tested first and is a substring of it.
2. `الأحد` ("Sunday") resolved to nothing, because the lookup table only held
   the colloquial `الحد` spelling and matched raw text.
3. A past date was resolved correctly and then thrown away, leaving the review
   screen with "no date" instead of "this date is in the past".
"""

from __future__ import annotations

from datetime import datetime

import pytest

from nexa.dates.egyptian_rules import WEEKDAYS, resolve_egyptian_phrase
from nexa.dates.normalizer import normalize_date_phrase
from nexa.dates.reference_time import CAIRO_TZ

# Thursday 24 September 2026, 12:00 Cairo — a Thursday so that "next Thursday"
# exercises the same-weekday case.
REF = datetime(2026, 9, 24, 12, 0, tzinfo=CAIRO_TZ)


def _day(phrase: str):
    resolved, _ = resolve_egyptian_phrase(phrase, REF)
    return None if resolved is None else resolved.date()


# ------------------------------------------- 1. longest phrase must win first
@pytest.mark.parametrize(
    "phrase,expected_day",
    [
        ("النهاردة", 24),
        ("بكرة", 25),
        ("بعد بكرة", 26),
        ("امبارح", 23),
        ("أول امبارح", 22),
    ],
)
def test_relative_days(phrase, expected_day):
    assert _day(phrase).day == expected_day


def test_day_after_tomorrow_is_not_tomorrow():
    """`بكرة` is a substring of `بعد بكرة`; shortest-first gets this wrong."""
    assert _day("بعد بكرة") != _day("بكرة")
    assert (_day("بعد بكرة") - _day("بكرة")).days == 1


def test_longer_weekday_names_are_not_shadowed():
    """`الاربع` is a substring of `الاربعاء`, and they are different days."""
    assert _day("الأربعاء").weekday() == 2
    assert _day("الاربع").weekday() == 2


# ---------------------------------------- 2. spelling variants must all match
@pytest.mark.parametrize("phrase", ["الأحد", "الاحد", "الحد", "الأحد ده"])
def test_sunday_spellings_all_resolve(phrase):
    """Transcription is not consistent about the alef-hamza."""
    resolved = _day(phrase)
    assert resolved is not None, f"{phrase!r} resolved to nothing"
    assert resolved.weekday() == 6


@pytest.mark.parametrize(
    "phrase,weekday",
    [
        ("الاثنين", 0), ("الإثنين", 0), ("الاتنين", 0),
        ("الثلاثاء", 1), ("التلات", 1),
        ("الأربعاء", 2),
        ("الخميس", 3),
        ("الجمعة", 4), ("الجمعه", 4),
        ("السبت", 5),
        ("الأحد", 6),
    ],
)
def test_every_weekday_resolves(phrase, weekday):
    assert _day(phrase).weekday() == weekday


def test_lookup_keys_are_stored_normalized():
    """A raw-text key would never match normalized input — a silent miss."""
    from nexa.core.validation import normalize_search_text

    for key in WEEKDAYS:
        assert key == normalize_search_text(key)


def test_diacritics_do_not_break_matching():
    assert _day("الخَميس").weekday() == 3


# ---------------------------------- next / this weekday
def test_next_weekday_from_the_same_weekday_is_a_week_later():
    """Reference is a Thursday; `الخميس الجاي` must not be today."""
    assert _day("الخميس الجاي").day == 1   # 1 October
    assert _day("الخميس").day == 24        # today


def test_this_weekday_is_the_upcoming_one():
    assert _day("الأحد ده").day == 27


def test_next_always_adds_a_week():
    assert (_day("الأحد الجاي") - _day("الأحد")).days == 7


# ----------------------- 3. a failed validation must not erase the resolution
def test_past_date_is_kept_and_flagged():
    """Section 2.1: show uncertainty, do not discard it.

    `امبارح` is not ambiguous — the date is known. Only its suitability as a
    deadline is in question, and that is the reviewer's call.
    """
    result = normalize_date_phrase("امبارح", REF)
    assert result.resolved_datetime is not None
    assert result.resolved_datetime.date().day == 23
    assert result.is_ambiguous is True
    assert result.ambiguity_reason == "Date is in the past"


def test_a_truly_unresolvable_phrase_still_yields_nothing():
    result = normalize_date_phrase("مش فاكر امتى بالظبط", REF)
    assert result.resolved_datetime is None
    assert result.is_ambiguous is True


def test_fuzzy_ranges_resolve_and_stay_ambiguous():
    for phrase, weekday in (("آخر الأسبوع", 3), ("أول الأسبوع", 6)):
        result = normalize_date_phrase(phrase, REF)
        assert result.resolved_datetime is not None
        assert result.resolved_datetime.weekday() == weekday
        assert result.is_ambiguous is True


def test_week_range_is_not_mistaken_for_a_weekday():
    """`الأسبوع` must not match `السبت` or any other weekday entry."""
    result = normalize_date_phrase("آخر الأسبوع", REF)
    assert result.is_ambiguous is True
    assert result.resolved_datetime.weekday() == 3


def test_empty_and_blank_phrases_are_safe():
    assert resolve_egyptian_phrase("", REF) == (None, False)
    assert resolve_egyptian_phrase("   ", REF) == (None, False)
