import datetime
from zoneinfo import ZoneInfo

# The mandate requires Africa/Cairo awareness everywhere.
CAIRO_TZ = ZoneInfo("Africa/Cairo")

def get_reference_datetime(dt: datetime.datetime = None) -> datetime.datetime:
    """
    Returns the reference datetime for relative date resolution.
    In production, this would come from the meeting metadata (Member 2).
    For now, it defaults to 'now' in Cairo time.
    """
    if dt:
        return dt.astimezone(CAIRO_TZ)
    return datetime.datetime.now(CAIRO_TZ)

def ensure_cairo_tz(dt: datetime.datetime) -> datetime.datetime:
    """Ensures a datetime object is aware of Africa/Cairo timezone."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=CAIRO_TZ)
    return dt.astimezone(CAIRO_TZ)
