"""SQLite connection management and the migration runner.

Design notes:

* One `Database` owns one connection per thread (`Nexa.exe` UI thread plus
  background work, and `NexaWorker.exe` in its own process). SQLite objects
  are not safe to share across threads.
* WAL is enabled so the worker process can read while the UI writes.
* Foreign keys are enforced per connection; SQLite defaults them off.
* Migrations are plain `.sql` files applied in filename order and recorded in
  `schema_migrations`, so "create the schema from an empty folder" and
  "upgrade an existing database" are the same code path.
"""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path
from typing import Iterable, List, Optional, Sequence, Tuple

from ..core.config import NexaConfig
from ..core.errors import DatabaseError, MigrationError
from ..core.validation import normalize_search_text

SCHEMA_MIGRATIONS_DDL = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version    TEXT PRIMARY KEY,
    applied_at TEXT NOT NULL
)
"""


class Database:
    """Owns the SQLite connection lifecycle for one process."""

    def __init__(self, config: Optional[NexaConfig] = None):
        self.config = config or NexaConfig()
        self._local = threading.local()
        self._shared_memory_conn: Optional[sqlite3.Connection] = None
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # connections
    # ------------------------------------------------------------------
    @property
    def is_memory(self) -> bool:
        return self.config.database_filename == ":memory:"

    def connect(self) -> sqlite3.Connection:
        """Return this thread's connection, opening it on first use."""
        existing = getattr(self._local, "connection", None)
        if existing is not None:
            return existing

        if self.is_memory:
            # An in-memory database dies with its connection, so tests share a
            # single one across threads and rely on the serialized threading
            # mode plus the transaction helper for safety.
            with self._lock:
                if self._shared_memory_conn is None:
                    self._shared_memory_conn = self._open(":memory:")
                connection = self._shared_memory_conn
        else:
            self.config.ensure_directories()
            connection = self._open(str(self.config.database_path))

        self._local.connection = connection
        return connection

    def _open(self, target: str) -> sqlite3.Connection:
        try:
            connection = sqlite3.connect(
                target,
                timeout=self.config.busy_timeout_ms / 1000,
                isolation_level=None,  # explicit transactions, see transactions.py
                check_same_thread=False,
                detect_types=0,
            )
        except sqlite3.Error as exc:  # pragma: no cover - environment dependent
            raise DatabaseError(f"could not open database {target}: {exc}") from exc

        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute(f"PRAGMA busy_timeout = {int(self.config.busy_timeout_ms)}")
        if not self.is_memory:
            connection.execute(f"PRAGMA journal_mode = {self.config.journal_mode}")
            connection.execute("PRAGMA synchronous = NORMAL")
        # Search normalization must behave identically in Python and in SQL,
        # so SQL calls the same Python function.
        connection.create_function("nexa_norm", 1, _norm_for_sql)
        return connection

    def close(self) -> None:
        """Close this thread's connection (and the shared in-memory one)."""
        connection = getattr(self._local, "connection", None)
        if connection is not None:
            if connection is not self._shared_memory_conn:
                connection.close()
            self._local.connection = None
        if self._shared_memory_conn is not None and threading.current_thread() is threading.main_thread():
            self._shared_memory_conn.close()
            self._shared_memory_conn = None

    def __enter__(self) -> "Database":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    # ------------------------------------------------------------------
    # convenience query helpers
    # ------------------------------------------------------------------
    def execute(self, sql: str, params: Sequence | dict = ()) -> sqlite3.Cursor:
        try:
            return self.connect().execute(sql, params)
        except sqlite3.Error as exc:
            raise DatabaseError(f"{exc} | sql={sql.strip()[:200]}") from exc

    def executemany(self, sql: str, seq_of_params: Iterable) -> sqlite3.Cursor:
        try:
            return self.connect().executemany(sql, seq_of_params)
        except sqlite3.Error as exc:
            raise DatabaseError(f"{exc} | sql={sql.strip()[:200]}") from exc

    def query_all(self, sql: str, params: Sequence | dict = ()) -> List[sqlite3.Row]:
        return list(self.execute(sql, params).fetchall())

    def query_one(self, sql: str, params: Sequence | dict = ()) -> Optional[sqlite3.Row]:
        return self.execute(sql, params).fetchone()

    def query_value(self, sql: str, params: Sequence | dict = (), default=None):
        row = self.query_one(sql, params)
        if row is None:
            return default
        return row[0]

    # ------------------------------------------------------------------
    # migrations
    # ------------------------------------------------------------------
    def migrate(self, migrations_dir: Optional[Path] = None) -> List[str]:
        """Apply every pending migration; return the versions applied.

        Safe to call on every start: already-applied files are skipped, and
        each file runs inside its own transaction, so a failing migration
        leaves the database on the last good version.
        """
        directory = Path(migrations_dir or self.config.migrations_dir)
        if not directory.is_dir():
            raise MigrationError(f"migrations directory not found: {directory}")

        connection = self.connect()
        connection.execute(SCHEMA_MIGRATIONS_DDL)

        applied = {row["version"] for row in connection.execute("SELECT version FROM schema_migrations")}
        newly_applied: List[str] = []

        for path in sorted(directory.glob("*.sql")):
            version = path.stem
            if version in applied:
                continue
            sql = path.read_text(encoding="utf-8")
            # executescript() commits any open transaction before it runs, so
            # the BEGIN/COMMIT have to live inside the script itself for the
            # migration and its bookkeeping row to land atomically.
            literal_version = version.replace("'", "''")
            script = (
                "BEGIN;\n"
                f"{sql}\n"
                "INSERT INTO schema_migrations (version, applied_at) "
                f"VALUES ('{literal_version}', datetime('now'));\n"
                "COMMIT;\n"
            )
            try:
                connection.executescript(script)
            except sqlite3.Error as exc:
                try:
                    connection.execute("ROLLBACK")
                except sqlite3.Error:  # pragma: no cover - rollback of a closed txn
                    pass
                raise MigrationError(f"migration {version} failed: {exc}") from exc
            newly_applied.append(version)

        return newly_applied

    def applied_migrations(self) -> List[Tuple[str, str]]:
        if not self.table_exists("schema_migrations"):
            return []
        rows = self.query_all(
            "SELECT version, applied_at FROM schema_migrations ORDER BY version"
        )
        return [(row["version"], row["applied_at"]) for row in rows]

    def table_exists(self, name: str) -> bool:
        row = self.query_one(
            "SELECT 1 FROM sqlite_master WHERE type IN ('table', 'view') AND name = ?",
            (name,),
        )
        return row is not None

    # ------------------------------------------------------------------
    # maintenance
    # ------------------------------------------------------------------
    def integrity_check(self) -> bool:
        return self.query_value("PRAGMA integrity_check") == "ok"

    def vacuum(self) -> None:
        self.execute("VACUUM")


def _norm_for_sql(value: Optional[str]) -> str:
    return normalize_search_text(value)


def open_database(config: Optional[NexaConfig] = None, *, migrate: bool = True) -> Database:
    """Open (creating if needed) a ready-to-use database.

    This is the single entry point other subsystems use; it satisfies
    "schema can be created from an empty folder" in the definition of done.
    """
    database = Database(config)
    database.connect()
    if migrate:
        database.migrate()
    return database
