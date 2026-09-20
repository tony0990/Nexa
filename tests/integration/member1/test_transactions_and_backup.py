"""Transaction guarantees and the backup helper."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from nexa.contracts.meetings import ActionItem, Meeting
from nexa.contracts.people import Employee
from nexa.core.errors import ConflictError, DatabaseError, NexaError
from nexa.data.backup import BackupService
from nexa.data.database import open_database
from nexa.data.repositories.actions import ActionRepository
from nexa.data.repositories.employees import EmployeeRepository
from nexa.data.repositories.meetings import MeetingRepository
from nexa.data.transactions import in_transaction, unit_of_work


class TestTransactions:
    def test_commit_persists(self, db, clock):
        employees = EmployeeRepository(db, clock)
        with unit_of_work(db):
            employees.create(Employee(full_name="Ahmed", email="a@example.com"))
        assert employees.count() == 1

    def test_exception_rolls_everything_back(self, db, clock):
        employees = EmployeeRepository(db, clock)
        with pytest.raises(RuntimeError):
            with unit_of_work(db):
                employees.create(Employee(full_name="Ahmed", email="a@example.com"))
                employees.create(Employee(full_name="Mona", email="m@example.com"))
                raise RuntimeError("something went wrong halfway")
        assert employees.count() == 0

    def test_nested_blocks_commit_as_one_unit(self, db, clock):
        employees = EmployeeRepository(db, clock)
        with pytest.raises(RuntimeError):
            with unit_of_work(db):
                employees.create(Employee(full_name="Ahmed", email="a@example.com"))
                with unit_of_work(db):  # savepoint
                    employees.create(Employee(full_name="Mona", email="m@example.com"))
                raise RuntimeError("outer failure")
        assert employees.count() == 0

    def test_inner_failure_can_be_caught_without_losing_the_outer_work(self, db, clock):
        employees = EmployeeRepository(db, clock)
        with unit_of_work(db):
            employees.create(Employee(full_name="Ahmed", email="a@example.com"))
            with pytest.raises(ConflictError):
                with unit_of_work(db):
                    employees.create(Employee(full_name="Clash", email="a@example.com"))
        assert employees.count() == 1

    def test_depth_is_restored_after_an_error(self, db, clock):
        assert not in_transaction()
        with pytest.raises(RuntimeError):
            with unit_of_work(db):
                assert in_transaction()
                raise RuntimeError("boom")
        assert not in_transaction()

    def test_service_level_rollback_keeps_audit_and_data_consistent(self, people, audit, db):
        """A failed multi-step operation must leave no partial trace."""
        role = people.create_role("Managers")
        audit_before = audit.count()

        with pytest.raises(ConflictError):
            with unit_of_work(db):
                people.create_employee("Ahmed", "ahmed@example.com", role_ids=[role.id])
                people.create_employee("Clash", "ahmed@example.com")

        assert people.list_employees() == []
        assert audit.count() == audit_before

    def test_sqlite_errors_are_wrapped(self, db):
        with pytest.raises(DatabaseError):
            with unit_of_work(db):
                db.execute("INSERT INTO employees (nope) VALUES (1)")

    def test_meeting_and_actions_commit_together(self, db, clock):
        meetings = MeetingRepository(db, clock)
        actions = ActionRepository(db, clock)
        with pytest.raises(RuntimeError):
            with unit_of_work(db):
                meeting = meetings.create(Meeting(title="Weekly"))
                actions.create(ActionItem(meeting_id=meeting.id, task="Finish database"))
                raise RuntimeError("approval aborted")
        assert meetings.count() == 0
        assert actions.count() == 0


class TestBackup:
    def test_backup_creates_a_readable_copy(self, db, clock, config):
        EmployeeRepository(db, clock).create(
            Employee(full_name="Ahmed Hassan", email="ahmed@example.com")
        )
        info = BackupService(db).create()

        assert info.path.is_file()
        assert info.size_bytes > 0

        copy = sqlite3.connect(str(info.path))
        try:
            assert copy.execute("SELECT COUNT(*) FROM employees").fetchone()[0] == 1
        finally:
            copy.close()

    def test_backups_are_listed_newest_first(self, db):
        service = BackupService(db)
        first = service.create(label="first")
        second = service.create(label="second")
        listed = [info.path for info in service.list_backups()]
        assert set(listed) == {first.path, second.path}
        assert listed[0].stat().st_mtime >= listed[1].stat().st_mtime

    def test_label_appears_in_the_filename(self, db):
        info = BackupService(db).create(label="before demo")
        assert "before-demo" in info.path.name

    def test_prune_keeps_the_newest(self, db):
        service = BackupService(db)
        for index in range(4):
            service.create(label=f"run{index}")
        removed = service.prune(keep=2)
        assert len(removed) == 2
        assert len(service.list_backups()) == 2

    def test_restore_brings_back_the_old_state(self, db, clock):
        employees = EmployeeRepository(db, clock)
        employees.create(Employee(full_name="Ahmed", email="ahmed@example.com"))

        service = BackupService(db)
        snapshot = service.create(label="good")

        employees.create(Employee(full_name="Mona", email="mona@example.com"))
        assert employees.count() == 2

        service.restore(snapshot.path)
        assert employees.count() == 1
        assert employees.get_by_email("mona@example.com") is None

    def test_restore_takes_a_safety_copy_first(self, db):
        service = BackupService(db)
        snapshot = service.create(label="good")
        service.restore(snapshot.path)
        assert any("pre-restore" in info.path.name for info in service.list_backups())

    def test_restoring_a_missing_file_is_rejected(self, db, tmp_path: Path):
        with pytest.raises(NexaError):
            BackupService(db).restore(tmp_path / "nope.db")

    def test_in_memory_databases_cannot_be_backed_up(self):
        from nexa.core.config import NexaConfig
        from nexa.data.database import Database

        database = Database(NexaConfig.in_memory())
        database.migrate()
        try:
            with pytest.raises(NexaError):
                BackupService(database).create()
        finally:
            database.close()

    def test_backup_survives_a_reopen(self, config, clock):
        database = open_database(config)
        try:
            EmployeeRepository(database, clock).create(
                Employee(full_name="Ahmed", email="a@example.com")
            )
            info = BackupService(database).create()
        finally:
            database.close()

        reopened = open_database(config)
        try:
            assert BackupService(reopened).list_backups()[0].path == info.path
        finally:
            reopened.close()
