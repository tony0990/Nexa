"""Append-only audit storage.

There is intentionally no update or delete method here, and migration 001
adds triggers that abort UPDATE/DELETE on `audit_events`, so the append-only
rule survives someone opening the database with a SQLite browser.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import List, Optional

from ...contracts.audit import AuditEvent
from ...core.timezone import isoformat_utc, range_bounds_utc
from ..models import json_to_db, row_to_audit_event
from ..transactions import unit_of_work
from .base import BaseRepository

_COLUMNS = (
    "id, actor_type, actor_id, event_type, entity_type, entity_id, "
    "old_value_json, new_value_json, metadata_json, created_at"
)


class AuditRepository(BaseRepository):
    def append(self, event: AuditEvent) -> AuditEvent:
        created_at = isoformat_utc(event.created_at, self.tz) or self.now_str()
        with unit_of_work(self.db):
            self.db.execute(
                """
                INSERT INTO audit_events (
                    actor_type, actor_id, event_type, entity_type, entity_id,
                    old_value_json, new_value_json, metadata_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    getattr(event.actor_type, "value", event.actor_type),
                    event.actor_id,
                    event.event_type,
                    event.entity_type,
                    None if event.entity_id is None else str(event.entity_id),
                    json_to_db(event.old_value),
                    json_to_db(event.new_value),
                    json_to_db(event.metadata),
                    created_at,
                ),
            )
            event_id = self._last_insert_id()
        row = self.db.query_one(f"SELECT {_COLUMNS} FROM audit_events WHERE id = ?", (event_id,))
        return row_to_audit_event(row)

    def get(self, event_id: int) -> Optional[AuditEvent]:
        row = self.db.query_one(f"SELECT {_COLUMNS} FROM audit_events WHERE id = ?", (event_id,))
        return None if row is None else row_to_audit_event(row)

    def by_entity(
        self, entity_type: str, entity_id: object, *, limit: int = 500
    ) -> List[AuditEvent]:
        rows = self.db.query_all(
            f"SELECT {_COLUMNS} FROM audit_events "
            "WHERE entity_type = ? AND entity_id = ? "
            "ORDER BY created_at, id LIMIT ?",
            (entity_type, str(entity_id), limit),
        )
        return [row_to_audit_event(row) for row in rows]

    def by_date_range(
        self, first_day: date, last_day: date, *, limit: int = 1000
    ) -> List[AuditEvent]:
        """Events in an inclusive local-day range."""
        start, end = range_bounds_utc(first_day, last_day, self.tz)
        rows = self.db.query_all(
            f"SELECT {_COLUMNS} FROM audit_events WHERE created_at >= ? AND created_at < ? "
            "ORDER BY created_at, id LIMIT ?",
            (start.isoformat(), end.isoformat(), limit),
        )
        return [row_to_audit_event(row) for row in rows]

    def by_actor(
        self,
        actor_type: Optional[str] = None,
        actor_id: Optional[str] = None,
        *,
        limit: int = 500,
    ) -> List[AuditEvent]:
        sql = f"SELECT {_COLUMNS} FROM audit_events WHERE 1 = 1"
        params: list = []
        if actor_type is not None:
            sql += " AND actor_type = ?"
            params.append(getattr(actor_type, "value", actor_type))
        if actor_id is not None:
            sql += " AND actor_id = ?"
            params.append(str(actor_id))
        sql += " ORDER BY created_at DESC, id DESC LIMIT ?"
        params.append(limit)
        return [row_to_audit_event(row) for row in self.db.query_all(sql, params)]

    def by_event_type(self, event_type: str, *, limit: int = 500) -> List[AuditEvent]:
        rows = self.db.query_all(
            f"SELECT {_COLUMNS} FROM audit_events WHERE event_type = ? "
            "ORDER BY created_at DESC, id DESC LIMIT ?",
            (event_type, limit),
        )
        return [row_to_audit_event(row) for row in rows]

    def recent(self, limit: int = 100) -> List[AuditEvent]:
        rows = self.db.query_all(
            f"SELECT {_COLUMNS} FROM audit_events ORDER BY created_at DESC, id DESC LIMIT ?",
            (limit,),
        )
        return [row_to_audit_event(row) for row in rows]

    def since(self, moment: datetime, *, limit: int = 1000) -> List[AuditEvent]:
        rows = self.db.query_all(
            f"SELECT {_COLUMNS} FROM audit_events WHERE created_at >= ? "
            "ORDER BY created_at, id LIMIT ?",
            (isoformat_utc(moment, self.tz), limit),
        )
        return [row_to_audit_event(row) for row in rows]

    def count(self) -> int:
        return int(self.db.query_value("SELECT COUNT(*) FROM audit_events", default=0))
