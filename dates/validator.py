from datetime import datetime
from typing import Tuple, Optional
from dates.reference_time import CAIRO_TZ

def validate_resolved_date(resolved: datetime, ref_dt: datetime) -> Tuple[bool, Optional[str]]:
    """
    Performs sanity checks on a resolved datetime (§7.4).
    Returns (is_valid, error_reason).
    """
    if not resolved:
        return False, "No date provided"

    # Ensure TZ awareness
    if resolved.tzinfo is None:
        return False, "Naive datetime provided"

    # 1. Past date check
    # Deadlines should generally not be in the past relative to the meeting
    if resolved < ref_dt.replace(hour=0, minute=0, second=0, microsecond=0):
        return False, "Date is in the past"

    # 2. TZ check
    if resolved.tzinfo != CAIRO_TZ:
        return False, "Wrong timezone"

    return True, None
