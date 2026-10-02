"""Schema creation and migration safety."""

from __future__ import annotations

from pathlib import Path

import pytest

from nexa.core.config import NexaConfig
from nexa.core.errors import MigrationError
from nexa.data.database import Database, open_database

EXPECTED_TABLES = {
    "employees",
    "roles",
    "employee_roles",
    "meetings",
    "meeting_participants",
    "meeting_templates",
    "transcript_segments",
    "action_items",
    "reminder_rules",
    "reminders",
    "delivery_targets",
    "email_deliveries",
    "audit_events",
    "settings",
    "schema_migrations",
}


class TestFreshDatabase:
    def test_schema_is_created_from_an_empty_folder(self, tmp_path: Path):
        data_dir = tmp_path / "brand-new"
        assert not data_dir.exists()

        database = open_database(NexaConfig(data_dir=data_dir))
        try:
            assert database.config.database_path.is_file()
            tables = {
                row["name"]
                for row in database.query_all(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                )
            }
            assert EXPECTED_TABLES <= tables
        finally:
            database.close()

    def test_every_migration_is_recorded(self, db):
        assert [version for version, _ in db.applied_migrations()] == [
            "001_initial",
            "002_search_indexes",
            "003_audit_indexes",
        ]

    def test_indexes_exist(self, db):
        indexes = {
            row["name"]
            for row in db.query_all("SELECT name FROM sqlite_master WHERE type = 'index'")
        }
        assert "ux_employees_email" in indexes
        assert "ix_action_items_status_due" in indexes
        assert "ix_audit_events_entity" in indexes

    def test_foreign_keys_are_enforced(self, db):
        assert db.query_value("PRAGMA foreign_keys") == 1

    def test_integrity_check_passes(self, db):
        assert db.integrity_check() is True


class TestRerunningMigrations:
    def test_second_run_applies_nothing(self, db):
        assert db.migrate() == []

    def test_reopening_an_existing_database_is_safe(self, config):
        first = open_database(config)
        first.close()
        second = open_database(config)
        try:
            assert second.migrate() == []
            assert len(second.applied_migrations()) == 3
        finally:
            second.close()

    def test_new_migration_is_applied_to_an_existing_database(self, db, tmp_path: Path):
        directory = tmp_path / "extra-migrations"
        directory.mkdir()
        (directory / "004_demo.sql").write_text(
            "CREATE TABLE demo_only (id INTEGER PRIMARY KEY);", encoding="utf-8"
        )
        assert db.migrate(directory) == ["004_demo"]
        assert db.table_exists("demo_only")


class TestFailedMigration:
    def test_a_broken_migration_leaves_the_database_untouched(self, db, tmp_path: Path):
        directory = tmp_path / "broken"
        directory.mkdir()
        (directory / "004_broken.sql").write_text(
            "CREATE TABLE ok_table (id INTEGER PRIMARY KEY);\n"
            "CREATE TABLE ok_table (id INTEGER PRIMARY KEY);\n",  # duplicate: fails
            encoding="utf-8",
        )
        with pytest.raises(MigrationError):
            db.migrate(directory)

        assert not db.table_exists("ok_table")
        assert "004_broken" not in [version for version, _ in db.applied_migrations()]

    def test_missing_directory_is_reported(self, db, tmp_path: Path):
        with pytest.raises(MigrationError, match="not found"):
            db.migrate(tmp_path / "does-not-exist")


class TestConstraints:
    def test_status_values_are_constrained(self, db):
        from nexa.core.errors import DatabaseError

        db.execute(
            "INSERT INTO meetings (title, title_norm, audio_source, status, "
            "email_language, created_at, updated_at) VALUES ('x', 'x', 'MICROPHONE', "
            "'DRAFT', 'AR', '2026-09-20T08:00:00+00:00', '2026-09-20T08:00:00+00:00')"
        )
        with pytest.raises(DatabaseError):
            db.execute("UPDATE meetings SET status = 'NOT_A_STATUS' WHERE id = 1")

    def test_confidence_is_constrained_to_0_1(self, db):
        from nexa.core.errors import DatabaseError

        with pytest.raises(DatabaseError):
            db.execute(
                "INSERT INTO action_items (task, confidence, created_at, updated_at) "
                "VALUES ('x', 1.5, '2026-09-20T08:00:00+00:00', '2026-09-20T08:00:00+00:00')"
            )

    def test_deleting_a_meeting_cascades_to_its_actions(self, db, clock):
        from nexa.contracts.meetings import ActionItem, Meeting
        from nexa.data.repositories.actions import ActionRepository
        from nexa.data.repositories.meetings import MeetingRepository

        meetings = MeetingRepository(db, clock)
        actions = ActionRepository(db, clock)
        meeting = meetings.create(Meeting(title="Weekly"))
        actions.create(ActionItem(meeting_id=meeting.id, task="Finish database"))

        meetings.delete(meeting.id)
        assert db.query_value("SELECT COUNT(*) FROM action_items") == 0

    def test_reminder_idempotency_key_is_unique(self, db, clock):
        from nexa.contracts.meetings import ActionItem
        from nexa.contracts.scheduling import Reminder
        from nexa.core.errors import DatabaseError
        from nexa.data.repositories.actions import ActionRepository
        from nexa.data.repositories.reminders import ReminderRepository

        action = ActionRepository(db, clock).create(ActionItem(task="Finish database"))
        reminders = ReminderRepository(db, clock)
        reminders.create(
            Reminder(
                action_item_id=action.id,
                scheduled_at=clock.now_utc(),
                idempotency_key="action-1-evening",
            )
        )
        with pytest.raises(DatabaseError):
            reminders.create(
                Reminder(
                    action_item_id=action.id,
                    scheduled_at=clock.now_utc(),
                    idempotency_key="action-1-evening",
                )
            )

    def test_null_idempotency_keys_do_not_collide(self, db, clock):
        from nexa.contracts.meetings import ActionItem
        from nexa.contracts.scheduling import Reminder
        from nexa.data.repositories.actions import ActionRepository
        from nexa.data.repositories.reminders import ReminderRepository

        action = ActionRepository(db, clock).create(ActionItem(task="Finish database"))
        reminders = ReminderRepository(db, clock)
        reminders.create(Reminder(action_item_id=action.id, scheduled_at=clock.now_utc()))
        reminders.create(Reminder(action_item_id=action.id, scheduled_at=clock.now_utc()))
        assert reminders.count() == 2


class TestMemoryDatabase:
    def test_in_memory_database_works_for_fast_tests(self):
        database = Database(NexaConfig.in_memory())
        try:
            database.migrate()
            assert database.table_exists("employees")
        finally:
            database.close()
