"""Health model the GUI reads to show worker healthy / stale / offline."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional

from nexa.scheduling.calculator import from_db, to_db
from nexa.scheduling.queue import ConnectionFactory
from .heartbeat import HEARTBEAT_KEY


class WorkerState(str, Enum):
    HEALTHY = "HEALTHY"
    STALE = "STALE"
    OFFLINE = "OFFLINE"


@dataclass
class WorkerHealth:
    state: WorkerState
    pid: Optional[int] = None
    last_beat_at: Optional[datetime] = None
    seconds_since_beat: Optional[float] = None
    last_run: dict = field(default_factory=dict)
    last_error: Optional[str] = None
    due_now: int = 0
    pending: int = 0
    retry_wait: int = 0
    failed: int = 0
    detail: str = ""


def check_worker_health(factory: ConnectionFactory, now: datetime,
                        healthy_within: timedelta = timedelta(seconds=60),
                        stale_within: timedelta = timedelta(minutes=3)) -> WorkerHealth:
    c = factory()
    try:
        row = c.execute("SELECT value_json FROM settings WHERE key=?", (HEARTBEAT_KEY,)).fetchone()
        counts = {r["status"]: r["n"] for r in c.execute(
            "SELECT status, COUNT(*) AS n FROM reminders GROUP BY status")}
        due_now = c.execute(
            "SELECT COUNT(*) AS n FROM reminders WHERE (status='PENDING' AND scheduled_at<=?) "
            "OR (status='RETRY_WAIT' AND next_attempt_at<=?)", (to_db(now), to_db(now))).fetchone()["n"]
    finally:
        c.close()
    h = WorkerHealth(WorkerState.OFFLINE, due_now=due_now, pending=counts.get("PENDING", 0),
                     retry_wait=counts.get("RETRY_WAIT", 0), failed=counts.get("FAILED", 0))
    if row is None:
        h.detail = "no heartbeat recorded"
        return h
    hb = json.loads(row["value_json"])
    h.pid, h.last_run, h.last_error = hb.get("pid"), hb.get("last_run", {}), hb.get("last_error")
    h.last_beat_at = from_db(hb.get("last_beat_at"))
    if h.last_beat_at is not None:
        h.seconds_since_beat = (now - h.last_beat_at).total_seconds()
    if hb.get("state") == "stopped":
        h.detail = "worker stopped"
    elif h.last_beat_at is None:
        h.detail = "invalid heartbeat"
    elif now - h.last_beat_at <= healthy_within:
        h.state = WorkerState.HEALTHY
    elif now - h.last_beat_at <= stale_within:
        h.state, h.detail = WorkerState.STALE, "heartbeat is late"
    else:
        h.detail = "heartbeat expired"
    return h
