"""Database backup helper.

Uses SQLite's online backup API rather than copying the file, so a backup is
consistent even while `Nexa.exe` and `NexaWorker.exe` are both connected.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from ..core.errors import DatabaseError, NexaError
from ..core.timezone import UTC
from .database import Database

BACKUP_SUFFIX = ".db"
BACKUP_PREFIX = "nexa-backup-"
TIMESTAMP_FORMAT = "%Y%m%d-%H%M%S"


@dataclass(frozen=True)
class BackupInfo:
    path: Path
    created_at: datetime
    size_bytes: int


class BackupService:
    def __init__(self, database: Database, backup_dir: Optional[Path] = None):
        self.db = database
        self.backup_dir = Path(backup_dir or database.config.backup_dir)

    def create(self, label: Optional[str] = None) -> BackupInfo:
        """Write a consistent snapshot and return where it landed."""
        if self.db.is_memory:
            raise NexaError("an in-memory database cannot be backed up to a file")

        self.backup_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(UTC).strftime(TIMESTAMP_FORMAT)
        suffix = f"-{_safe_label(label)}" if label else ""
        target = self.backup_dir / f"{BACKUP_PREFIX}{stamp}{suffix}{BACKUP_SUFFIX}"

        destination = sqlite3.connect(str(target))
        try:
            self.db.connect().backup(destination)
        except sqlite3.Error as exc:
            raise DatabaseError(f"backup failed: {exc}") from exc
        finally:
            destination.close()

        return BackupInfo(
            path=target,
            created_at=datetime.now(UTC),
            size_bytes=target.stat().st_size,
        )

    def list_backups(self) -> List[BackupInfo]:
        """Existing backups, newest first."""
        if not self.backup_dir.is_dir():
            return []
        infos = []
        for path in self.backup_dir.glob(f"{BACKUP_PREFIX}*{BACKUP_SUFFIX}"):
            stat = path.stat()
            infos.append(
                BackupInfo(
                    path=path,
                    created_at=datetime.fromtimestamp(stat.st_mtime, UTC),
                    size_bytes=stat.st_size,
                )
            )
        return sorted(infos, key=lambda info: info.created_at, reverse=True)

    def prune(self, keep: Optional[int] = None) -> List[Path]:
        """Delete all but the newest `keep` backups; return what was removed."""
        limit = keep if keep is not None else self.db.config.max_backups
        removed = []
        for info in self.list_backups()[limit:]:
            info.path.unlink(missing_ok=True)
            removed.append(info.path)
        return removed

    def restore(self, backup_path: Path) -> None:
        """Overwrite the live database with a backup.

        Destructive by nature: the caller (UI) must confirm with the user
        first. A safety copy of the current database is taken beforehand.
        """
        source_path = Path(backup_path)
        if not source_path.is_file():
            raise NexaError(f"backup not found: {source_path}")
        if self.db.is_memory:
            raise NexaError("an in-memory database cannot be restored into")

        self.create(label="pre-restore")

        source = sqlite3.connect(str(source_path))
        try:
            target = self.db.connect()
            source.backup(target)
        except sqlite3.Error as exc:
            raise DatabaseError(f"restore failed: {exc}") from exc
        finally:
            source.close()


def _safe_label(label: str) -> str:
    keep = [char if char.isalnum() or char in "-_" else "-" for char in label.strip()]
    return "".join(keep)[:40].strip("-") or "backup"
