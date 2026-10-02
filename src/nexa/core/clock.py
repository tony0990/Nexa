"""Time source abstraction.

No module in the data platform calls `datetime.now()` directly. Everything
takes a `Clock`, so tests can pin "now" and assert on overdue/today/this-week
filters deterministically.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Protocol

from .timezone import DEFAULT_TIMEZONE, UTC, to_local


class Clock(Protocol):
    def now_utc(self) -> datetime: ...

    def now_local(self) -> datetime: ...

    def today(self) -> date: ...


class SystemClock:
    """Real wall-clock time in the configured application timezone."""

    def __init__(self, tz_name: str = DEFAULT_TIMEZONE):
        self.tz_name = tz_name

    def now_utc(self) -> datetime:
        return datetime.now(UTC)

    def now_local(self) -> datetime:
        return to_local(self.now_utc(), self.tz_name)

    def today(self) -> date:
        return self.now_local().date()


class FixedClock:
    """A clock pinned to one instant, for tests and reproducible fixtures."""

    def __init__(self, moment: datetime, tz_name: str = DEFAULT_TIMEZONE):
        if moment.tzinfo is None:
            raise ValueError("FixedClock requires an aware datetime")
        self.tz_name = tz_name
        self._moment = moment.astimezone(UTC)

    def set(self, moment: datetime) -> None:
        if moment.tzinfo is None:
            raise ValueError("FixedClock requires an aware datetime")
        self._moment = moment.astimezone(UTC)

    def advance(self, **timedelta_kwargs: float) -> None:
        from datetime import timedelta

        self._moment = self._moment + timedelta(**timedelta_kwargs)

    def now_utc(self) -> datetime:
        return self._moment

    def now_local(self) -> datetime:
        return to_local(self._moment, self.tz_name)

    def today(self) -> date:
        return self.now_local().date()
