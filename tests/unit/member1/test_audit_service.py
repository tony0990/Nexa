"""Audit recording, querying and the export view model."""

from __future__ import annotations

from datetime import date

import pytest

from nexa.audit import event_types
from nexa.audit.service import Actor, AuditService
from nexa.contracts.audit import ActorType, AuditEvent
from nexa.core.errors import DatabaseError


class TestRecording:
    def test_record_stores_every_field(self, audit):
        event = audit.record(
            AuditEvent(
                actor_type=ActorType.WORKER.value,
                actor_id="NexaWorker",
                event_type=event_types.REMINDER_SENT,
                entity_type=event_types.ENTITY_REMINDER,
                entity_id=42,
                metadata={"recipients": 8},
            )
        )
        assert event.id is not None
        assert event.entity_id == "42"
        assert event.metadata == {"recipients": 8}
        assert event.created_at is not None

    def test_log_uses_the_default_actor(self, audit):
        event = audit.log(event_types.MEETING_CREATED, event_types.ENTITY_MEETING, 1)
        assert (event.actor_type, event.actor_id) == (ActorType.USER.value, "admin")

    def test_actor_can_be_overridden_per_call(self, audit):
        event = audit.log(
            event_types.REMINDER_SENT,
            event_types.ENTITY_REMINDER,
            1,
            actor=Actor.worker(),
        )
        assert event.actor_type == ActorType.WORKER.value

    def test_arabic_values_round_trip(self, audit):
        event = audit.log(
            event_types.ACTION_CREATED,
            event_types.ENTITY_ACTION_ITEM,
            1,
            new_value={"task": "تجهيز العرض التقديمي"},
        )
        assert audit.history(event_types.ENTITY_ACTION_ITEM, 1)[0].new_value == event.new_value

    def test_log_change_records_only_differences(self, audit):
        event = audit.log_change(
            event_types.ACTION_UPDATED,
            event_types.ENTITY_ACTION_ITEM,
            17,
            {"due_date": "2026-09-08", "task": "Report"},
            {"due_date": "2026-09-09", "task": "Report"},
        )
        assert event.old_value == {"due_date": "2026-09-08"}
        assert event.new_value == {"due_date": "2026-09-09"}

    def test_log_change_returns_none_when_nothing_changed(self, audit):
        assert (
            audit.log_change(
                event_types.ACTION_UPDATED,
                event_types.ENTITY_ACTION_ITEM,
                17,
                {"task": "Report"},
                {"task": "Report"},
            )
            is None
        )


class TestAppendOnly:
    def test_updates_are_rejected_by_the_database(self, audit, db):
        event = audit.log(event_types.MEETING_CREATED, event_types.ENTITY_MEETING, 1)
        with pytest.raises(DatabaseError, match="append-only"):
            db.execute("UPDATE audit_events SET event_type = 'x' WHERE id = ?", (event.id,))

    def test_deletes_are_rejected_by_the_database(self, audit, db):
        event = audit.log(event_types.MEETING_CREATED, event_types.ENTITY_MEETING, 1)
        with pytest.raises(DatabaseError, match="append-only"):
            db.execute("DELETE FROM audit_events WHERE id = ?", (event.id,))

    def test_the_service_exposes_no_mutation_methods(self, audit):
        assert not hasattr(audit.repo, "update")
        assert not hasattr(audit.repo, "delete")


class TestQueries:
    def test_history_is_chronological(self, audit):
        for event_type in (
            event_types.ACTION_CREATED,
            event_types.ACTION_OWNER_ASSIGNED,
            event_types.ACTION_COMPLETED,
        ):
            audit.log(event_type, event_types.ENTITY_ACTION_ITEM, 5)
        assert [event.event_type for event in audit.history(event_types.ENTITY_ACTION_ITEM, 5)] == [
            event_types.ACTION_CREATED,
            event_types.ACTION_OWNER_ASSIGNED,
            event_types.ACTION_COMPLETED,
        ]

    def test_history_is_scoped_to_one_entity(self, audit):
        audit.log(event_types.ACTION_CREATED, event_types.ENTITY_ACTION_ITEM, 1)
        audit.log(event_types.ACTION_CREATED, event_types.ENTITY_ACTION_ITEM, 2)
        assert len(audit.history(event_types.ENTITY_ACTION_ITEM, 1)) == 1

    def test_by_actor(self, audit):
        audit.log(event_types.REMINDER_SENT, event_types.ENTITY_REMINDER, 1, actor=Actor.worker())
        audit.log(event_types.MEETING_CREATED, event_types.ENTITY_MEETING, 1)
        worker_events = audit.by_actor(ActorType.WORKER.value)
        assert [event.event_type for event in worker_events] == [event_types.REMINDER_SENT]

    def test_by_date(self, audit, clock):
        audit.log(event_types.MEETING_CREATED, event_types.ENTITY_MEETING, 1)
        assert len(audit.by_date(clock.today())) == 1
        assert audit.by_date(date(2026, 1, 1)) == []

    def test_by_date_spans_a_range(self, audit, clock):
        audit.log(event_types.MEETING_CREATED, event_types.ENTITY_MEETING, 1)
        clock.advance(days=2)
        audit.log(event_types.MEETING_APPROVED, event_types.ENTITY_MEETING, 1)
        assert len(audit.by_date(date(2026, 9, 20), date(2026, 9, 22))) == 2
        assert len(audit.by_date(date(2026, 9, 21), date(2026, 9, 22))) == 1

    def test_by_event_type(self, audit):
        audit.log(event_types.EMAIL_SENT, event_types.ENTITY_EMAIL_DELIVERY, 1)
        audit.log(event_types.EMAIL_FAILED, event_types.ENTITY_EMAIL_DELIVERY, 2)
        assert len(audit.by_event_type(event_types.EMAIL_FAILED)) == 1

    def test_recent_is_newest_first(self, audit, clock):
        audit.log(event_types.MEETING_CREATED, event_types.ENTITY_MEETING, 1)
        clock.advance(minutes=5)
        audit.log(event_types.MEETING_APPROVED, event_types.ENTITY_MEETING, 1)
        assert audit.recent()[0].event_type == event_types.MEETING_APPROVED


class TestViewModel:
    def test_entry_fields(self, audit):
        audit.log_change(
            event_types.ACTION_UPDATED,
            event_types.ENTITY_ACTION_ITEM,
            17,
            {"due_date": "2026-09-08"},
            {"due_date": "2026-09-09"},
        )
        entry = audit.export_view_model(event_types.ENTITY_ACTION_ITEM, 17)[0]
        assert entry.changed_fields == ["due_date"]
        assert entry.actor == "USER:admin"
        assert entry.summary == "action_item #17 action.updated (due_date)"
        assert entry.local_time.startswith("2026-09-20")

    def test_entry_without_changes_has_a_simple_summary(self, audit):
        audit.log(event_types.RECORDING_STARTED, event_types.ENTITY_MEETING, 3)
        entry = audit.export_view_model(event_types.ENTITY_MEETING, 3)[0]
        assert entry.summary == "meeting #3 recording.started"

    def test_export_without_entity_returns_recent_events(self, audit):
        audit.log(event_types.MEETING_CREATED, event_types.ENTITY_MEETING, 1)
        audit.log(event_types.MEETING_APPROVED, event_types.ENTITY_MEETING, 1)
        assert len(audit.export_view_model()) == 2

    def test_system_actor_has_no_id_suffix(self, db, clock):
        service = AuditService(db, clock, default_actor=Actor.system())
        service.log(event_types.DATABASE_BACKED_UP, "system")
        assert service.export_view_model()[0].actor == "SYSTEM"
