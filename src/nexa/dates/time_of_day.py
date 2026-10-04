"""Compatibility shim: the real parser lives in `nexa.dates.clock_time`.

This module was a skeleton that nothing called, and it evaluated the
cultural-band check before parsing the hour, so "الساعة عشرة الصبح" (ten in the
morning) returned 08:00. Kept so existing imports keep working.
"""

from __future__ import annotations

from datetime import time
from typing import Optional, Tuple

from nexa.dates.clock_time import parse_clock_time


def parse_arabic_time(phrase: str) -> Tuple[Optional[time], bool]:
    """Returns (time | None, needs_review). See `parse_clock_time`."""
    return parse_clock_time(phrase)
