"""Shared repository plumbing."""

from __future__ import annotations

from typing import Optional

from ...core.clock import Clock, SystemClock
from ...core.timezone import isoformat_utc
from ..database import Database


def is_unique_violation(exc: BaseException, *columns: str) -> bool:
    """True when `exc` is a UNIQUE violation touching one of `columns`.

    SQLite reports the *column* ("UNIQUE constraint failed: roles.name_norm"),
    not the index name, so callers must match on `table.column`.
    """
    message = str(exc)
    if "UNIQUE constraint failed" not in message:
        return False
    if not columns:
        return True
    return any(column in message for column in columns)


class BaseRepository:
    """Common constructor and timestamp handling for every repository."""

    def __init__(self, database: Database, clock: Optional[Clock] = None):
        self.db = database
        self.clock = clock or SystemClock(database.config.timezone)

    @property
    def tz(self) -> str:
        return self.db.config.timezone

    def now_str(self) -> str:
        """Current instant as a stored UTC timestamp."""
        return isoformat_utc(self.clock.now_utc(), self.tz) or ""

    def _last_insert_id(self) -> int:
        return int(self.db.query_value("SELECT last_insert_rowid()"))
