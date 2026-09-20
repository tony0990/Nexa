"""Transaction helper.

Every write path in the data layer runs inside `unit_of_work`. Nesting is
supported with SAVEPOINTs, so a service method that calls another service
method still commits or rolls back as one unit — which is what makes
"approve the meeting, save 9 actions, write 9 audit rows" atomic.
"""

from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from typing import Iterator, Optional

from ..core.errors import DatabaseError
from .database import Database

_state = threading.local()


def _depth() -> int:
    return getattr(_state, "depth", 0)


def _set_depth(value: int) -> None:
    _state.depth = value


def in_transaction() -> bool:
    return _depth() > 0


@contextmanager
def unit_of_work(database: Database, *, immediate: bool = True) -> Iterator[sqlite3.Connection]:
    """Run a block atomically.

    `immediate` issues `BEGIN IMMEDIATE`, taking the write lock up front so two
    processes (UI and worker) fail fast instead of halfway through.
    """
    connection = database.connect()
    depth = _depth()

    savepoint: Optional[str] = None
    try:
        if depth == 0:
            connection.execute("BEGIN IMMEDIATE" if immediate else "BEGIN")
        else:
            savepoint = f"nexa_sp_{depth}"
            connection.execute(f"SAVEPOINT {savepoint}")
        _set_depth(depth + 1)

        yield connection

        if savepoint is not None:
            connection.execute(f"RELEASE {savepoint}")
        else:
            connection.execute("COMMIT")
    except BaseException as exc:
        try:
            if savepoint is not None:
                connection.execute(f"ROLLBACK TO {savepoint}")
                connection.execute(f"RELEASE {savepoint}")
            else:
                connection.execute("ROLLBACK")
        except sqlite3.Error:  # pragma: no cover - nothing to roll back
            pass
        if isinstance(exc, sqlite3.Error):
            raise DatabaseError(str(exc)) from exc
        raise
    finally:
        _set_depth(depth)
