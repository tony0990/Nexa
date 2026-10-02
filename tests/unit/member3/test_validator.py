import pytest
from datetime import datetime
from nexa.dates.reference_time import CAIRO_TZ
from nexa.dates.validator import validate_resolved_date

def test_past_date_validation():
    ref_dt = datetime(2026, 9, 24, 12, 0, tzinfo=CAIRO_TZ)
    past_dt = datetime(2026, 9, 20, 12, 0, tzinfo=CAIRO_TZ)

    is_valid, reason = validate_resolved_date(past_dt, ref_dt)
    assert is_valid is False
    assert reason == "Date is in the past"

def test_timezone_validation():
    ref_dt = datetime(2026, 9, 24, 12, 0, tzinfo=CAIRO_TZ)
    # Naive datetime
    naive_dt = datetime(2026, 9, 25, 12, 0)

    is_valid, reason = validate_resolved_date(naive_dt, ref_dt)
    assert is_valid is False
    assert reason == "Naive datetime provided"
