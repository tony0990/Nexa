"""Worker heartbeat stored in `settings` (key `worker.heartbeat`) so the GUI can show status."""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Callable, Optional

from nexa.scheduling.calculator import to_db
from nexa.scheduling.queue import ConnectionFactory, transaction

HEARTBEAT_KEY = "worker.heartbeat"
VERSION = "1.0"


class Heartbeat:
    def __init__(self, factory: ConnectionFactory,
                 clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
                 key: str = HEARTBEAT_KEY):
        self.factory, self.clock, self.key = factory, clock, key
        self.started_at = clock()

    def _write(self, payload: dict) -> None:
        now = self.clock()
        payload.update(pid=os.getpid(), started_at=to_db(self.started_at),
                       last_beat_at=to_db(now), version=VERSION)
        with transaction(self.factory) as c:
            c.execute(
                "INSERT INTO settings(key, value_json, updated_at) VALUES (?,?,?) "
                "ON CONFLICT(key) DO UPDATE SET value_json=excluded.value_json, "
                "updated_at=excluded.updated_at",
                (self.key, json.dumps(payload), to_db(now)))

    def beat(self, last_run: Optional[dict] = None, error: Optional[str] = None) -> None:
        self._write({"state": "running", "last_run": last_run or {}, "last_error": error})

    def stopped(self) -> None:
        self._write({"state": "stopped", "last_run": {}, "last_error": None})
