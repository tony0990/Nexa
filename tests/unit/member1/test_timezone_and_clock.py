"""Africa/Cairo handling and the clock abstraction.

The expected UTC offset is read from the timezone itself rather than
hard-coded: Egypt observes DST again since 2023, and a machine without the
`tzdata` package falls back to a fixed +02:00. These tests must assert the
conversion logic, not one particular offset.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone

import pytest

from nexa.core.clock import FixedClock, SystemClock
from nexa.core.timezone import (
    DEFAULT_TIMEZONE,
    combine_local,
    day_bounds_utc,
    get_timezone,
    isoformat_utc,
    month_bounds,
    parse_utc,
    range_bounds_utc,
    to_local,
    to_utc,
    week_bounds,
)

CAIRO = get_timezone(DEFAULT_TIMEZONE)


def cairo_offset(moment: datetime) -> timedelta:
    return moment.replace(tzinfo=CAIRO).utcoffset() or timedelta(0)


class TestConversions:
    def test_naive_datetime_is_local_not_utc(self):
        # 15:00 typed into the UI means 15:00 in Cairo, not 15:00 UTC.
        local = datetime(2026, 9, 20, 15, 0)
        result = to_utc(local)
        assert result.tzinfo == timezone.utc
        assert result == (local - cairo_offset(local)).replace(tzinfo=timezone.utc)

    def test_cairo_is_ahead_of_utc(self):
        assert cairo_offset(datetime(2026, 9, 20, 15, 0)) >= timedelta(hours=2)

    def test_aware_datetime_is_respected(self):
        moment = datetime(2026, 9, 20, 12, 0, tzinfo=timezone.utc)
        assert to_utc(moment) == moment

    def test_round_trip(self):
        moment = datetime(2026, 9, 20, 15, 30)
        assert to_local(to_utc(moment)).replace(tzinfo=None) == moment

    def test_isoformat_and_parse_round_trip(self):
        moment = datetime(2026, 9, 20, 12, 0, tzinfo=timezone.utc)
        assert parse_utc(isoformat_utc(moment)) == moment

    def test_parse_accepts_z_suffix(self):
        assert parse_utc("2026-09-20T12:00:00Z") == datetime(
            2026, 9, 20, 12, 0, tzinfo=timezone.utc
        )

    def test_parse_none(self):
        assert parse_utc(None) is None
        assert parse_utc("") is None

    def test_combine_local_builds_cairo_time(self):
        moment = combine_local(date(2026, 9, 20), time(15, 0))
        assert moment.hour == 15
        assert to_local(to_utc(moment)).hour == 15


class TestDayBounds:
    def test_day_bounds_are_half_open_and_cover_24_hours(self):
        start, end = day_bounds_utc(date(2026, 9, 20))
        assert end - start == timedelta(days=1)
        assert to_local(start).date() == date(2026, 9, 20)
        assert to_local(start).hour == 0
        assert to_local(end).date() == date(2026, 9, 21)

    def test_range_bounds_cover_both_ends(self):
        start, end = range_bounds_utc(date(2026, 9, 20), date(2026, 9, 21))
        assert end - start == timedelta(days=2)


class TestWeekAndMonth:
    def test_week_starts_on_sunday_by_default(self):
        # 20 Sep 2026 is a Sunday: the start of the Egyptian working week.
        first, last = week_bounds(date(2026, 9, 20))
        assert first == date(2026, 9, 20)
        assert last == date(2026, 9, 26)

    def test_midweek_day_maps_to_the_same_week(self):
        first, last = week_bounds(date(2026, 9, 23))
        assert (first, last) == (date(2026, 9, 20), date(2026, 9, 26))

    def test_week_can_start_on_monday(self):
        first, _ = week_bounds(date(2026, 9, 23), week_starts_on=0)
        assert first == date(2026, 9, 21)

    def test_month_bounds(self):
        assert month_bounds(date(2026, 9, 15)) == (date(2026, 9, 1), date(2026, 9, 30))

    def test_month_bounds_december_rolls_over(self):
        assert month_bounds(date(2026, 12, 5)) == (date(2026, 12, 1), date(2026, 12, 31))

    def test_month_bounds_february_leap_year(self):
        assert month_bounds(date(2028, 2, 10)) == (date(2028, 2, 1), date(2028, 2, 29))


class TestClocks:
    def test_fixed_clock_is_stable(self, clock: FixedClock):
        assert clock.now_utc() == clock.now_utc()
        assert clock.today() == date(2026, 9, 20)

    def test_fixed_clock_local_time_is_cairo(self, clock: FixedClock):
        expected = clock.now_utc().astimezone(CAIRO)
        assert clock.now_local() == expected
        assert clock.now_local().hour >= 10  # 08:00 UTC, Cairo is +2 or +3

    def test_fixed_clock_advances(self, clock: FixedClock):
        before = clock.now_utc()
        clock.advance(hours=25)
        assert clock.today() == date(2026, 9, 21)
        assert (clock.now_utc() - before).total_seconds() == 25 * 3600

    def test_fixed_clock_rejects_naive_datetime(self):
        with pytest.raises(ValueError):
            FixedClock(datetime(2026, 9, 20, 12, 0))

    def test_system_clock_is_timezone_aware(self):
        assert SystemClock().now_utc().tzinfo is not None
        assert SystemClock().now_local().tzinfo is not None

    def test_get_timezone_always_returns_something_usable(self):
        # Without the tzdata package (common on a bare Windows machine) the
        # helper must still return a working tzinfo instead of raising.
        tz = get_timezone("Definitely/NotAZone")
        assert datetime(2026, 9, 20, 12, 0, tzinfo=tz).utcoffset() is not None
