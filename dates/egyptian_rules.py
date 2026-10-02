import datetime
from datetime import timedelta
from typing import Optional, Tuple, Union
from dates.reference_time import get_reference_datetime

"""
Egyptian Arabic expression lookup table (§7.2).
Implemented as a series of regex patterns and resolution functions.
"""

def resolve_egyptian_phrase(phrase: str, ref_dt: datetime.datetime) -> Tuple[Optional[datetime.datetime], bool]:
    """
    Tries to resolve an Egyptian Arabic date phrase.
    Returns (resolved_datetime, is_ambiguous).
    """
    phrase = phrase.strip()

    # 1. Immediate relative days
    # النهاردة (Today)
    if "النهاردة" in phrase:
        return ref_dt.replace(hour=0, minute=0, second=0, microsecond=0), False

    # بكرة (Tomorrow)
    if "بكرة" in phrase:
        resolved = ref_dt + timedelta(days=1)
        return resolved.replace(hour=0, minute=0, second=0, microsecond=0), False

    # بعد بكرة (Day after tomorrow)
    if "بعد بكرة" in phrase:
        resolved = ref_dt + timedelta(days=2)
        return resolved.replace(hour=0, minute=0, second=0, microsecond=0), False

    # امبارح (Yesterday) - Validator should flag this if used as deadline
    if "امبارح" in phrase:
        resolved = ref_dt - timedelta(days=1)
        return resolved.replace(hour=0, minute=0, second=0, microsecond=0), False

    # 2. Relative weekdays
    # Patterns like 'الخميس الجاي' or 'الأحد ده'
    weekdays = {
        "الحد": 6, # Sunday (Python calendar: Mon=0, Sun=6)
        "الاثنين": 0, "الاتنين": 0,
        "الثلاثاء": 1, "التلات": 1,
        "الاربعاء": 2, "الاربع": 2,
        "الخميس": 3,
        "الجمعة": 4,
        "السبت": 5
    }

    # Check for 'الـ[weekday]'
    for day_name, day_val in weekdays.items():
        if day_name in phrase:
            # Calculate distance to that weekday
            current_weekday = ref_dt.weekday()
            days_ahead = day_val - current_weekday

            # For 'this' (ده), if we are already past the day this week,
            # it usually refers to the same day next week in colloquial Egyptian.
            # But per plan §7.2, "ده" = this occurrence.
            if days_ahead < 0:
                days_ahead += 7

            # 'الجاي' (Next) always means the occurrence AFTER the one this week.
            if "الجاي" in phrase or "اللي جاي" in phrase:
                if days_ahead == 0:
                    days_ahead = 7
                else:
                    # If the day is tomorrow (days_ahead=1), 'next' usually means +7
                    # To be safe and deterministic: 'الجاي' always adds 7 if we are
                    # already looking at the "upcoming" one.
                    days_ahead += 7

            resolved = ref_dt + timedelta(days=days_ahead)
            return resolved.replace(hour=0, minute=0, second=0, microsecond=0), False

    # 3. Fuzzy ranges (§7.2, §7.3)
    # آخر الأسبوع -> Thu-Fri (Egyptian week)
    if "آخر الأسبوع" in phrase:
        # Resolve to Thu (day 3)
        current_weekday = ref_dt.weekday()
        days_to_thu = 3 - current_weekday
        if days_to_thu < 0: days_to_thu += 7
        resolved = ref_dt + timedelta(days=days_to_thu)
        return resolved.replace(hour=0, minute=0, second=0, microsecond=0), True

    # أول الأسبوع -> Sun-Mon (Egyptian week)
    if "أول الأسبوع" in phrase:
        # Resolve to Sun (day 6)
        current_weekday = ref_dt.weekday()
        days_to_sun = 6 - current_weekday
        if days_to_sun < 0: days_to_sun += 7
        resolved = ref_dt + timedelta(days=days_to_sun)
        return resolved.replace(hour=0, minute=0, second=0, microsecond=0), True

    return None, False
