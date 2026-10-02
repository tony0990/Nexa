"""Migration 004, which widens two CHECK constraints to allow BILINGUAL.

This exists because the obvious implementation of this migration *destroys
data*. 001_initial.sql constrains `meetings.email_language` and
`email_deliveries.language` to ('AR','EN'), SQLite cannot ALTER a CHECK, and the
standard table-rebuild fix is unsafe here: the runner enables
`PRAGMA foreign_keys = ON`, under which `DROP TABLE` performs an implicit
`DELETE FROM` that fires `ON DELETE CASCADE` on every child — so dropping
`meetings` deletes meeting_participants, transcript_segments and action_items.

`test_rebuilding_meetings_would_cascade_delete_children` pins that fact down, so
nobody "simplifies" 004 back into a rebuild later. The other tests assert that
004 itself keeps every row, index and constraint intact.
"""

from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path

import pytest

from nexa.core.config import NexaConfig
from nexa.core.errors import MigrationError
from nexa.data.database import open_database

REPO_ROOT = Path(__file__).resolve().parents[3]
MIGRATIONS = REPO_ROOT / "migrations"
BILINGUAL_MIGRATION = "004_bilingual_email_language.sql"
EARLIER = ("001_initial.sql", "002_search_indexes.sql", "003_audit_indexes.sql")

CHILD_TABLES = ("meeting_participants", "transcript_segments", "action_items")
ALL_TABLES = ("meetings", *CHILD_TABLES, "email_deliveries")


def _seed(db) -> None:
    """One meeting with a child row in every table that cascades from it."""
    db.execute(
        "INSERT INTO employees (full_name, full_name_norm, email, active, "
        "created_at, updated_at) VALUES ('A','a','a@b.com',1,'now','now')"
    )
    db.execute(
        "INSERT INTO meetings (title, title_norm, status, email_language, "
        "created_at, updated_at) VALUES ('M','m','APPROVED','AR','now','now')"
    )
    db.execute(
        "INSERT INTO meeting_participants (meeting_id, employee_id, created_at) "
        "VALUES (1,1,'now')"
    )
    db.execute(
        "INSERT INTO transcript_segments (meeting_id, segment_index, raw_text, "
        "created_at) VALUES (1,0,'hi','now')"
    )
    db.execute(
        "INSERT INTO action_items (meeting_id, task, created_at, updated_at) "
        "VALUES (1,'T','now','now')"
    )
    db.execute(
        "INSERT INTO email_deliveries (meeting_id, recipient_email, subject, "
        "language, status, attempted_at) VALUES (1,'a@b.com','S','AR','SENT','now')"
    )
    db.connect().commit()


def _counts(db) -> dict:
    return {table: db.query_value(f"SELECT COUNT(*) FROM {table}") for table in ALL_TABLES}


@pytest.fixture
def staged(tmp_path):
    """A database migrated to 003 and seeded, with 004 not yet applied."""
    directory = tmp_path / "migrations"
    directory.mkdir()
    for name in EARLIER:
        shutil.copy(MIGRATIONS / name, directory / name)
    config = NexaConfig(data_dir=tmp_path / "data", migrations_dir=directory)
    db = open_database(config)
    _seed(db)
    yield db, config, directory
    db.close()


def _apply_bilingual(directory: Path) -> None:
    shutil.copy(MIGRATIONS / BILINGUAL_MIGRATION, directory / BILINGUAL_MIGRATION)


# --------------------------------------------------- the trap being avoided
def test_rebuilding_meetings_would_cascade_delete_children(staged):
    """Pins down *why* 004 does not rebuild the table.

    If a future SQLite release stopped cascading on DROP TABLE, this test would
    fail and 004 could be simplified. Until then it documents the hazard with a
    measurement instead of a comment.
    """
    db, _, _ = staged
    before = _counts(db)
    assert all(before[table] == 1 for table in CHILD_TABLES)

    db.connect().executescript(
        """
        BEGIN;
        CREATE TABLE meetings_rebuilt (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            title_norm TEXT NOT NULL DEFAULT '',
            template_id INTEGER REFERENCES meeting_templates (id) ON DELETE SET NULL,
            started_at TEXT, ended_at TEXT,
            audio_source TEXT NOT NULL DEFAULT 'MICROPHONE',
            status TEXT NOT NULL DEFAULT 'DRAFT',
            email_language TEXT NOT NULL DEFAULT 'AR'
                CHECK (email_language IN ('AR', 'EN', 'BILINGUAL')),
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        INSERT INTO meetings_rebuilt SELECT * FROM meetings;
        DROP TABLE meetings;
        ALTER TABLE meetings_rebuilt RENAME TO meetings;
        COMMIT;
        """
    )
    after = _counts(db)
    assert after["meetings"] == 1, "the parent survives, which is what hides the bug"
    for table in CHILD_TABLES:
        assert after[table] == 0, (
            f"{table} unexpectedly survived — if DROP TABLE no longer cascades, "
            "migration 004 can be simplified to a plain table rebuild"
        )


# -------------------------------------------------------- 004 is lossless
def test_migration_preserves_every_row(staged):
    db, _, directory = staged
    before = _counts(db)
    _apply_bilingual(directory)
    assert db.migrate(directory) == ["004_bilingual_email_language"]
    assert _counts(db) == before


def test_migration_keeps_the_indexes(staged):
    """DROP TABLE would have taken 002's indexes with it."""
    db, _, directory = staged
    _apply_bilingual(directory)
    db.migrate(directory)
    for name in (
        "ix_meetings_status",
        "ix_meetings_started_at",
        "ix_meetings_template",
        "ix_meetings_title_norm",
        "ix_email_deliveries_meeting",
        "ix_email_deliveries_status",
        "ix_email_deliveries_recipient",
    ):
        assert db.query_value(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='index' AND name=?", (name,)
        ) == 1, f"{name} was lost"


def test_database_is_still_sound_after_the_schema_edit(staged):
    """writable_schema is only acceptable if it leaves the file intact."""
    db, config, directory = staged
    _apply_bilingual(directory)
    db.migrate(directory)
    db.close()
    reopened = open_database(config)
    try:
        assert reopened.query_value("PRAGMA integrity_check") == "ok"
        assert reopened.query_all("PRAGMA foreign_key_check") == []
    finally:
        reopened.close()


def test_bilingual_can_be_stored_after_the_migration(staged):
    """No reopen here on purpose: migrate() must leave the live connection usable.

    The schema edit is invisible to a connection that cached the old schema, so
    `migrate()` reconnects. Without that, this insert fails on a first run.
    """
    db, _, directory = staged
    _apply_bilingual(directory)
    db.migrate(directory)
    reopened = db
    try:
        reopened.execute(
            "INSERT INTO meetings (title, title_norm, status, email_language, "
            "created_at, updated_at) VALUES ('B','b','DRAFT','BILINGUAL','now','now')"
        )
        reopened.execute(
            "INSERT INTO email_deliveries (meeting_id, recipient_email, subject, "
            "language, status, attempted_at) "
            "VALUES (2,'a@b.com','S','BILINGUAL','SENT','now')"
        )
        reopened.connect().commit()
        assert reopened.query_value(
            "SELECT COUNT(*) FROM meetings WHERE email_language='BILINGUAL'"
        ) == 1
    finally:
        pass


def test_the_check_constraint_still_rejects_junk(staged):
    """Widening must not become removing."""
    db, config, directory = staged
    _apply_bilingual(directory)
    db.migrate(directory)
    db.close()
    reopened = open_database(config)
    try:
        with pytest.raises(Exception):
            reopened.execute(
                "INSERT INTO meetings (title, title_norm, status, email_language, "
                "created_at, updated_at) VALUES ('C','c','DRAFT','KLINGON','now','now')"
            )
    finally:
        reopened.close()


def test_migration_is_idempotent(staged):
    db, _, directory = staged
    _apply_bilingual(directory)
    assert db.migrate(directory) == ["004_bilingual_email_language"]
    assert db.migrate(directory) == []


def test_fresh_database_gets_every_migration(tmp_path):
    """The normal path: an empty folder, all four migrations, bilingual usable."""
    config = NexaConfig(data_dir=tmp_path / "data")
    db = open_database(config)
    try:
        applied = [version for version, _ in db.applied_migrations()]
        assert "004_bilingual_email_language" in applied
        db.execute(
            "INSERT INTO meetings (title, title_norm, status, email_language, "
            "created_at, updated_at) VALUES ('B','b','DRAFT','BILINGUAL','now','now')"
        )
        db.connect().commit()
    finally:
        db.close()


# ------------------------------------------------------------- self-guarding
def test_migration_aborts_if_the_check_text_no_longer_matches(tmp_path):
    """`replace()` is silent on a miss, so 004 verifies its own work.

    A reformatted 001_initial.sql would otherwise leave 004 recorded as applied
    while having changed nothing — and the failure would surface much later, as
    a CHECK violation when an admin picks bilingual.
    """
    directory = tmp_path / "migrations"
    directory.mkdir()
    reformatted = (MIGRATIONS / "001_initial.sql").read_text(encoding="utf-8").replace(
        "CHECK (email_language IN ('AR', 'EN'))",
        "CHECK (email_language IN ('AR','EN'))",
    )
    (directory / "001_initial.sql").write_text(reformatted, encoding="utf-8")
    for name in ("002_search_indexes.sql", "003_audit_indexes.sql", BILINGUAL_MIGRATION):
        shutil.copy(MIGRATIONS / name, directory / name)

    with pytest.raises(MigrationError) as caught:
        open_database(NexaConfig(data_dir=tmp_path / "data", migrations_dir=directory))
    assert "004_bilingual_email_language" in str(caught.value)


def test_a_failed_guard_rolls_the_whole_migration_back(tmp_path):
    """The bookkeeping row must not survive a failed migration."""
    directory = tmp_path / "migrations"
    directory.mkdir()
    reformatted = (MIGRATIONS / "001_initial.sql").read_text(encoding="utf-8").replace(
        "CHECK (email_language IN ('AR', 'EN'))",
        "CHECK (email_language IN ('AR','EN'))",
    )
    (directory / "001_initial.sql").write_text(reformatted, encoding="utf-8")
    for name in ("002_search_indexes.sql", "003_audit_indexes.sql", BILINGUAL_MIGRATION):
        shutil.copy(MIGRATIONS / name, directory / name)
    data_dir = tmp_path / "data"
    with pytest.raises(MigrationError):
        open_database(NexaConfig(data_dir=data_dir, migrations_dir=directory))

    connection = sqlite3.connect(data_dir / "nexa.db")
    try:
        applied = {
            row[0]
            for row in connection.execute("SELECT version FROM schema_migrations")
        }
        assert "004_bilingual_email_language" not in applied
        leftover = connection.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE name='_m004_guard'"
        ).fetchone()[0]
        assert leftover == 0, "the guard table leaked into the schema"
    finally:
        connection.close()
