"""Application settings (Section 16.14).

Values are stored as JSON so booleans, numbers and strings all round-trip.
`ensure_defaults` runs on first start and after an upgrade adds a new key.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from ...core.config import DEFAULT_SETTINGS
from ..models import json_from_db, json_to_db
from ..transactions import unit_of_work
from .base import BaseRepository


class SettingsRepository(BaseRepository):
    def get(self, key: str, default: Any = None) -> Any:
        row = self.db.query_one("SELECT value_json FROM settings WHERE key = ?", (key,))
        if row is None:
            return default
        return json_from_db(row["value_json"])

    def set(self, key: str, value: Any) -> Any:
        with unit_of_work(self.db):
            self.db.execute(
                """
                INSERT INTO settings (key, value_json, updated_at) VALUES (?, ?, ?)
                ON CONFLICT (key) DO UPDATE
                    SET value_json = excluded.value_json,
                        updated_at = excluded.updated_at
                """,
                (key, json_to_db(value), self.now_str()),
            )
        return value

    def all(self) -> Dict[str, Any]:
        rows = self.db.query_all("SELECT key, value_json FROM settings ORDER BY key")
        return {row["key"]: json_from_db(row["value_json"]) for row in rows}

    def ensure_defaults(self, overrides: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Insert missing default settings without touching existing values."""
        defaults = dict(DEFAULT_SETTINGS)
        if overrides:
            defaults.update(overrides)
        existing = set(self.all())
        now = self.now_str()
        missing = [
            (key, json_to_db(value), now)
            for key, value in defaults.items()
            if key not in existing
        ]
        if missing:
            with unit_of_work(self.db):
                self.db.executemany(
                    "INSERT INTO settings (key, value_json, updated_at) VALUES (?, ?, ?)",
                    missing,
                )
        return self.all()

    def delete(self, key: str) -> bool:
        with unit_of_work(self.db):
            cursor = self.db.execute("DELETE FROM settings WHERE key = ?", (key,))
            return cursor.rowcount > 0
