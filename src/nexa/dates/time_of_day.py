import re
from datetime import datetime, time
from typing import Optional, Tuple

def parse_arabic_time(phrase: str) -> Optional[Tuple[time, bool]]:
    """
    Parses Arabic fractional hours and 12h formats.
    Returns (time_object, needs_review).

    Examples:
    - 'تلاتة ونص' -> 03:30, False
    - 'تلاتة إلا ربع' -> 02:45, False
    - 'الساعة عشرة بالليل' -> 22:00, False
    - 'العصر' -> 16:00, True (Cultural band)
    """
    phrase = phrase.strip().lower()

    # Cultural bands (§7.3)
    bands = {
        "الصبح": time(8, 0),
        "العصر": time(16, 0),
        "بالليل": time(21, 0),
    }
    for band, default_time in bands.items():
        if band in phrase:
            return default_time, True

    # Basic fractional hour mapping
    hours = {
        "واحد": 1, "اتنين": 2, "تلاتة": 3, "اربعة": 4, "خمسة": 5,
        "ستة": 6, "سبعة": 7, "تمانية": 8, "تسعة": 9, "عشرة": 10,
        "حدعشر": 11, "اتناشر": 12
    }

    # This is a simplified implementation for the skeleton.
    # In full M1, this would be a robust regex-based parser.
    # Try to find an hour
    found_hour = None
    for word, hr in hours.items():
        if word in phrase:
            found_hour = hr
            break

    if found_hour is None:
        return None, False

    # Handle 'ونص' (and a half)
    if "ونص" in phrase:
        return time(found_hour, 30), False
    # Handle 'إلا ربع' (minus a quarter)
    if "إلا ربع" in phrase or "إلا ربع" in phrase:
        # Simple hour wrap for 'minus quarter'
        return time((found_hour - 1) % 24, 45), False

    return time(found_hour, 0), False
