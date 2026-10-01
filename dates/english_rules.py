import dateparser
from datetime import datetime
from typing import Optional, Tuple
from dates.reference_time import CAIRO_TZ

def resolve_english_phrase(phrase: str, ref_dt: datetime) -> Tuple[Optional[datetime], bool]:
    """
    Wraps dateparser to resolve English relative dates.
    Ensures Africa/Cairo timezone and reference_datetime base.
    """
    settings = {
        "RELATIVE_BASE": ref_dt,
        "TIMEZONE": "Africa/Cairo",
        "RETURN_AS_TIMEZONE_AWARE": True,
    }

    try:
        resolved = dateparser.parse(phrase, settings=settings)
        if resolved:
            # Ensure it's Cairo aware
            resolved = resolved.astimezone(CAIRO_TZ)
            return resolved, False
    except Exception:
        pass

    return None, False
