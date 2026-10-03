"""English deadline phrases must resolve forward (§39.2's "English dates").

Two defects, both of which produced a *plausible* date rather than an error:

1. `PREFER_DATES_FROM` was unset, so dateparser resolved a bare weekday to the
   nearest one in either direction. "by Friday" said on a Thursday came back as
   the Friday six days earlier — a deadline already in the past, which means a
   reminder that never fires and an action item overdue the moment it is
   approved.
2. dateparser returns `None` for "next Monday". It handles a bare "Monday" and
   "next week", but not the combination, so the single most ordinary English
   deadline phrasing silently produced no date at all.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from nexa.dates.english_rules import resolve_english_phrase
from nexa.dates.normalizer import normalize_date_phrase
from nexa.dates.reference_time import CAIRO_TZ

# Thursday 24 September 2026, 12:00 Cairo. A Thursday so that "next Thursday"
# exercises the same-weekday case.
REF = datetime(2026, 9, 24, 12, 0, tzinfo=CAIRO_TZ)


def day(phrase: str):
    resolved, _ = resolve_english_phrase(phrase, REF)
    return None if resolved is None else resolved.date()


# ------------------------------------------------- 1. deadlines point forward
@pytest.mark.parametrize("phrase", ["Friday", "by Friday", "on Friday", "friday"])
def test_a_bare_weekday_resolves_forward(phrase):
    resolved = day(phrase)
    assert resolved is not None
    assert resolved > REF.date(), f"{phrase!r} resolved into the past"
    assert resolved.weekday() == 4


def test_by_friday_is_tomorrow_not_last_week():
    """The exact regression: Thursday + "by Friday" is one day ahead."""
    assert day("by Friday").isoformat() == "2026-09-25"


@pytest.mark.parametrize(
    "phrase",
    ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
)
def test_no_bare_weekday_ever_resolves_backwards(phrase):
    assert day(phrase) >= REF.date()


def test_a_bare_calendar_date_resolves_forward():
    """March is behind us in September, so a bare "March 5" means next year."""
    assert day("March 5").year == 2027


def test_an_explicit_past_phrase_still_resolves_backwards():
    """PREFER_DATES_FROM must not rewrite history.

    "yesterday" is unambiguous about direction; forcing it forward would be
    inventing information. The validator flags it instead.
    """
    assert day("yesterday") < REF.date()
    assert day("two days ago") < REF.date()


def test_a_past_phrase_is_kept_and_flagged_not_discarded():
    result = normalize_date_phrase("yesterday", REF)
    assert result.resolved_datetime is not None
    assert result.is_ambiguous is True
    assert result.ambiguity_reason == "Date is in the past"


# ------------------------------------------- 2. "next <weekday>" must resolve
@pytest.mark.parametrize(
    "phrase,expected",
    [
        ("next Monday", "2026-10-05"),
        ("next Thursday", "2026-10-01"),
        ("next Friday", "2026-10-02"),
        ("by next Thu", "2026-10-01"),
        ("next tuesday", "2026-10-06"),   # upcoming Tue is 09-29, +7
    ],
)
def test_next_weekday_resolves(phrase, expected):
    assert day(phrase).isoformat() == expected


@pytest.mark.parametrize(
    "phrase,expected",
    [
        ("this Friday", "2026-09-25"),
        ("coming Sunday", "2026-09-27"),
        ("upcoming Monday", "2026-09-28"),
    ],
)
def test_this_and_coming_weekday_resolve_to_the_upcoming_one(phrase, expected):
    assert day(phrase).isoformat() == expected


def test_next_weekday_is_a_week_past_the_upcoming_one():
    assert (day("next Monday") - day("Monday")).days == 7


def test_this_weekday_on_that_weekday_means_the_coming_one():
    """Said on a Thursday, "this Thursday" is not today."""
    assert day("this Thursday") > REF.date()
    assert day("this Thursday").weekday() == 3


def test_next_weekday_on_that_weekday_skips_a_full_week():
    assert day("next Thursday").isoformat() == "2026-10-01"


def test_abbreviations_resolve():
    assert day("next Mon").weekday() == 0
    assert day("this Wed").weekday() == 2


def test_a_qualified_weekday_inside_a_sentence_still_matches():
    assert day("please finish it by next Monday at the latest").isoformat() == "2026-10-05"


# ----------------------------------------------------------- unchanged paths
def test_plain_relative_phrases_still_work():
    assert day("tomorrow").isoformat() == "2026-09-25"
    assert day("next week") is not None


def test_an_unparseable_phrase_yields_nothing():
    assert day("sometime soonish maybe") is None


def test_an_empty_phrase_is_safe():
    assert resolve_english_phrase("", REF) == (None, False)
    assert resolve_english_phrase(None, REF) == (None, False)


def test_resolution_is_cairo_aware():
    resolved, _ = resolve_english_phrase("by Friday", REF)
    assert resolved.tzinfo is not None
    assert resolved.utcoffset() == REF.utcoffset()
