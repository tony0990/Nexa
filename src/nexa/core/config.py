"""Application configuration and the default `settings` rows.

Configuration is filesystem/runtime wiring (where the database lives). The
`settings` table holds user-editable preferences; the defaults below are
inserted on first run and are the keys listed in Section 16.14.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional

from .timezone import DEFAULT_TIMEZONE

APP_NAME = "Nexa"

DEFAULT_SETTINGS: Dict[str, Any] = {
    "ui_language": "AR",
    "theme": "light",
    "timezone": DEFAULT_TIMEZONE,
    "default_email_language": "AR",
    "default_evening_reminder_time": "20:00",
    "default_morning_reminder_time": "08:00",
    "missed_reminder_recovery_hours": 12,
    "audio_retention_policy": "DELETE_AFTER_APPROVAL",
    "transcript_retention_policy": "KEEP",
    "gmail_sender_display_name": APP_NAME,
}


def default_data_dir() -> Path:
    """Where the database lives when nothing else is configured.

    Delegates to `nexa.core.paths.data_dir`, the single place that decides: portable
    `<install>/data` first, the per-user app-data folder only if that is not writable.
    """
    from .paths import data_dir

    return data_dir()


@dataclass
class NexaConfig:
    """Runtime wiring for the data platform."""

    data_dir: Path = field(default_factory=default_data_dir)
    database_filename: str = "nexa.db"
    migrations_dir: Optional[Path] = None
    backup_dir: Optional[Path] = None
    timezone: str = DEFAULT_TIMEZONE
    busy_timeout_ms: int = 10_000
    journal_mode: str = "WAL"
    max_backups: int = 10

    def __post_init__(self) -> None:
        self.data_dir = Path(self.data_dir)
        if self.migrations_dir is None:
            self.migrations_dir = repo_migrations_dir()
        else:
            self.migrations_dir = Path(self.migrations_dir)
        if self.backup_dir is None:
            self.backup_dir = self.data_dir / "backups"
        else:
            self.backup_dir = Path(self.backup_dir)

    @property
    def database_path(self) -> Path:
        return self.data_dir / self.database_filename

    def ensure_directories(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        assert self.backup_dir is not None
        self.backup_dir.mkdir(parents=True, exist_ok=True)

    @classmethod
    def for_test(cls, tmp_dir: Path) -> "NexaConfig":
        """Config pointing at a throwaway directory."""
        return cls(data_dir=Path(tmp_dir))

    @classmethod
    def in_memory(cls) -> "NexaConfig":
        """Config for an in-memory database (unit tests)."""
        cfg = cls(data_dir=Path("."), database_filename=":memory:")
        return cfg


def repo_migrations_dir() -> Path:
    """Locate the `migrations/` folder shipped next to the source tree."""
    from .paths import resource_dir

    return resource_dir() / "migrations"
