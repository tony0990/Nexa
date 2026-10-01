import pytest
from datetime import datetime
from dates.reference_time import CAIRO_TZ
from dates.normalizer import normalize_date_phrase

def test_egyptian_relative_days():
    # Mock reference: Thursday 2026-09-24 (Cairo)
    ref_dt = datetime(2026, 9, 24, 12, 0, tzinfo=CAIRO_TZ)

    cases = [
        ("النهاردة", 2026, 9, 24),
        ("بكرة", 2026, 9, 25),
        ("بعد بكرة", 2026, 9, 26),
        ("امبارح", 2026, 9, 23),
    ]

    for phrase, y, m, d in cases:
        res = normalize_date_phrase(phrase, ref_dt)
        assert res.resolved_datetime.year == y
        assert res.resolved_datetime.month == m
        assert res.resolved_datetime.day == d

def test_egyptian_weekdays():
    ref_dt = datetime(2026, 9, 24, 12, 0, tzinfo=CAIRO_TZ) # Thursday

    cases = [
        ("الخميس الجاي", 2026, 10, 1), # Next Thursday
        ("الأحد ده", 2026, 9, 27),    # This Sunday
    ]

    for phrase, y, m, d in cases:
        res = normalize_date_phrase(phrase, ref_dt)
        assert res.resolved_datetime.year == y
        assert res.resolved_datetime.month == m
        assert res.resolved_datetime.day == d

def test_egyptian_fuzzy_ranges():
    ref_dt = datetime(2026, 9, 24, 12, 0, tzinfo=CAIRO_TZ)

    cases = [
        ("آخر الأسبوع", True),
        ("أول الأسبوع", True),
    ]

    for phrase, expected_ambiguous in cases:
        res = normalize_date_phrase(phrase, ref_dt)
        assert res.is_ambiguous == expected_ambiguous
