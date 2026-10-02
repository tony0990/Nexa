"""Repository behaviour against a real SQLite file."""

from __future__ import annotations

from datetime import date, time

import pytest

from nexa.contracts.email import DeliveryKind, DeliveryStatus, DeliveryTarget, EmailDelivery, TargetType
from nexa.contracts.meetings import (
    ActionItem,
    ActionStatus,
    Meeting,
    MeetingStatus,
    MeetingTemplate,
    ReviewState,
    TranscriptSegment,
)
from nexa.contracts.people import Employee
from nexa.contracts.scheduling import Reminder, ReminderRuleType, ReminderStatus
from nexa.core.errors import ConflictError, NotFoundError
from nexa.core.timezone import to_local
from nexa.data.repositories.actions import ActionRepository
from nexa.data.repositories.deliveries import DeliveryRepository
from nexa.data.repositories.employees import EmployeeRepository
from nexa.data.repositories.meetings import MeetingRepository
from nexa.data.repositories.reminders import ReminderRepository
from nexa.data.repositories.settings import SettingsRepository
from nexa.data.repositories.templates import TemplateRepository
from nexa.contracts.scheduling import ReminderRule


@pytest.fixture
def employees(db, clock):
    return EmployeeRepository(db, clock)


@pytest.fixture
def meetings(db, clock):
    return MeetingRepository(db, clock)


@pytest.fixture
def actions(db, clock):
    return ActionRepository(db, clock)


@pytest.fixture
def reminders(db, clock):
    return ReminderRepository(db, clock)


@pytest.fixture
def deliveries(db, clock):
    return DeliveryRepository(db, clock)


class TestEmployeeRepository:
    def test_create_and_read_back(self, employees):
        created = employees.create(Employee(full_name="Ahmed Hassan", email="ahmed@example.com"))
        assert employees.get(created.id) == created

    def test_get_by_email_is_case_insensitive(self, employees):
        employees.create(Employee(full_name="Ahmed", email="Ahmed@Example.com"))
        assert employees.get_by_email("AHMED@EXAMPLE.COM") is not None

    def test_get_many_preserves_requested_order(self, employees):
        first = employees.create(Employee(full_name="Ahmed", email="a@example.com"))
        second = employees.create(Employee(full_name="Mona", email="m@example.com"))
        assert [e.id for e in employees.get_many([second.id, first.id])] == [second.id, first.id]

    def test_get_many_ignores_unknown_ids(self, employees):
        created = employees.create(Employee(full_name="Ahmed", email="a@example.com"))
        assert [e.id for e in employees.get_many([created.id, 999])] == [created.id]

    def test_get_many_with_no_ids(self, employees):
        assert employees.get_many([]) == []

    def test_update_changes_the_stored_row(self, employees):
        created = employees.create(Employee(full_name="Ahmed", email="a@example.com"))
        updated = employees.update(
            Employee(id=created.id, full_name="Ahmed Hassan", email="a@example.com", job_title="Lead")
        )
        assert (updated.full_name, updated.job_title) == ("Ahmed Hassan", "Lead")

    def test_update_missing_employee_raises(self, employees):
        with pytest.raises(NotFoundError):
            employees.update(Employee(id=999, full_name="Ghost", email="g@example.com"))

    def test_duplicate_email_raises_conflict(self, employees):
        employees.create(Employee(full_name="Ahmed", email="a@example.com"))
        with pytest.raises(ConflictError):
            employees.create(Employee(full_name="Other", email="a@example.com"))

    def test_bulk_create(self, employees):
        count = employees.bulk_create(
            [Employee(full_name=f"Employee {i}", email=f"e{i}@example.com") for i in range(50)]
        )
        assert count == 50
        assert employees.count() == 50

    def test_departments_are_distinct_and_sorted(self, employees):
        employees.create(Employee(full_name="A", email="a@example.com", department="Finance"))
        employees.create(Employee(full_name="B", email="b@example.com", department="Development"))
        employees.create(Employee(full_name="C", email="c@example.com", department="Finance"))
        assert employees.departments() == ["Development", "Finance"]

    def test_delete(self, employees):
        created = employees.create(Employee(full_name="Ahmed", email="a@example.com"))
        employees.delete(created.id)
        assert employees.get(created.id) is None

    def test_rebuild_search_text(self, employees, db):
        created = employees.create(Employee(full_name="أحمد حسن", email="a@example.com"))
        db.execute("UPDATE employees SET search_text = '' WHERE id = ?", (created.id,))
        assert employees.rebuild_search_text() == 1
        assert db.query_value("SELECT search_text FROM employees WHERE id = ?", (created.id,))


class TestMeetingRepository:
    def test_create_with_participants(self, meetings, employees):
        ahmed = employees.create(Employee(full_name="Ahmed", email="a@example.com"))
        mona = employees.create(Employee(full_name="Mona", email="m@example.com"))
        meeting = meetings.create(
            Meeting(title="Weekly Development Meeting", participant_ids=(ahmed.id, mona.id))
        )
        assert set(meeting.participant_ids) == {ahmed.id, mona.id}

    def test_duplicate_participants_are_collapsed(self, meetings, employees):
        ahmed = employees.create(Employee(full_name="Ahmed", email="a@example.com"))
        meeting = meetings.create(Meeting(title="Weekly", participant_ids=(ahmed.id, ahmed.id)))
        assert meeting.participant_ids == (ahmed.id,)

    def test_set_participants_replaces_the_list(self, meetings, employees):
        ahmed = employees.create(Employee(full_name="Ahmed", email="a@example.com"))
        mona = employees.create(Employee(full_name="Mona", email="m@example.com"))
        meeting = meetings.create(Meeting(title="Weekly", participant_ids=(ahmed.id,)))
        assert meetings.set_participants(meeting.id, [mona.id]) == [mona.id]

    def test_add_and_remove_participant(self, meetings, employees):
        ahmed = employees.create(Employee(full_name="Ahmed", email="a@example.com"))
        meeting = meetings.create(Meeting(title="Weekly"))
        assert meetings.add_participant(meeting.id, ahmed.id) is True
        assert meetings.add_participant(meeting.id, ahmed.id) is False
        assert meetings.remove_participant(meeting.id, ahmed.id) is True

    def test_status_transitions(self, meetings):
        meeting = meetings.create(Meeting(title="Weekly"))
        assert meetings.set_status(meeting.id, MeetingStatus.APPROVED).status == "APPROVED"

    def test_timestamps_round_trip_through_utc(self, meetings, clock):
        meeting = meetings.create(Meeting(title="Weekly", started_at=clock.now_utc()))
        assert meetings.get(meeting.id).started_at == clock.now_utc()

    def test_transcript_segments(self, meetings):
        meeting = meetings.create(Meeting(title="Weekly"))
        meetings.add_segments(
            meeting.id,
            [
                TranscriptSegment(segment_index=0, raw_text="أحمد يخلص الـdatabase before Monday"),
                TranscriptSegment(segment_index=1, raw_text="The final report يتبعت يوم الاتنين"),
            ],
        )
        segments = meetings.segments(meeting.id)
        assert [s.segment_index for s in segments] == [0, 1]
        assert segments[0].raw_text == "أحمد يخلص الـdatabase before Monday"

    def test_confirming_a_segment_keeps_the_raw_text(self, meetings):
        meeting = meetings.create(Meeting(title="Weekly"))
        meetings.add_segments(meeting.id, [TranscriptSegment(segment_index=0, raw_text="raw asr")])
        segment = meetings.segments(meeting.id)[0]
        confirmed = meetings.confirm_segment(segment.id, "corrected by the admin")
        assert confirmed.confirmed_text == "corrected by the admin"
        assert confirmed.raw_text == "raw asr"

    def test_delete_segments_applies_retention(self, meetings):
        meeting = meetings.create(Meeting(title="Weekly"))
        meetings.add_segments(meeting.id, [TranscriptSegment(segment_index=0, raw_text="x")])
        assert meetings.delete_segments(meeting.id) == 1
        assert meetings.segments(meeting.id) == []


class TestActionRepository:
    def test_create_preserves_the_original_evidence(self, actions, meetings):
        meeting = meetings.create(Meeting(title="Weekly"))
        action = actions.create(
            ActionItem(
                meeting_id=meeting.id,
                task="Finish database integration",
                owner_raw_text="أحمد",
                raw_date_phrase="قبل يوم الاتنين",
                due_date=date(2026, 9, 21),
                source_text="أحمد يخلص الـdatabase قبل يوم الاتنين",
                confidence=0.94,
            )
        )
        stored = actions.get(action.id)
        assert stored.source_text == "أحمد يخلص الـdatabase قبل يوم الاتنين"
        assert stored.raw_date_phrase == "قبل يوم الاتنين"
        assert stored.owner_raw_text == "أحمد"
        assert stored.confidence == 0.94

    def test_due_at_is_resolved_when_a_time_is_known(self, actions):
        action = actions.create(
            ActionItem(task="Presentation ready", due_date=date(2026, 9, 24), due_time=time(15, 0))
        )
        stored = actions.get(action.id)
        assert stored.due_at is not None
        assert to_local(stored.due_at).hour == 15

    def test_due_at_stays_null_when_the_time_is_unspecified(self, actions):
        action = actions.create(ActionItem(task="Report", due_date=date(2026, 9, 24)))
        assert actions.get(action.id).due_at is None

    def test_assign_owner(self, actions, employees):
        ahmed = employees.create(Employee(full_name="Ahmed", email="a@example.com"))
        action = actions.create(ActionItem(task="Finish database"))
        assert actions.assign_owner(action.id, ahmed.id).owner_employee_id == ahmed.id
        assert actions.assign_owner(action.id, None).owner_employee_id is None

    def test_completing_records_the_timestamp(self, actions, clock):
        action = actions.create(ActionItem(task="Finish database"))
        completed = actions.set_status(action.id, ActionStatus.COMPLETED)
        assert completed.status == "COMPLETED"
        assert completed.completed_at == clock.now_utc()

    def test_completed_timestamp_is_cleared_when_reopened(self, actions):
        action = actions.create(ActionItem(task="Finish database"))
        actions.set_status(action.id, ActionStatus.COMPLETED)
        assert actions.set_status(action.id, ActionStatus.PENDING).completed_at is None

    def test_cancelled_items_cannot_be_completed(self, actions):
        action = actions.create(ActionItem(task="Finish database"))
        actions.set_status(action.id, ActionStatus.CANCELLED)
        with pytest.raises(ConflictError):
            actions.set_status(action.id, ActionStatus.COMPLETED)

    def test_review_state(self, actions):
        action = actions.create(ActionItem(task="Finish database"))
        assert actions.set_review_state(action.id, ReviewState.APPROVED).review_state == "APPROVED"

    def test_reschedule_keeps_the_evidence(self, actions):
        action = actions.create(
            ActionItem(
                task="Report",
                due_date=date(2026, 9, 21),
                raw_date_phrase="يوم الاتنين",
                source_text="التقرير يتسلم يوم الاتنين",
            )
        )
        moved = actions.reschedule(action.id, date(2026, 9, 24), time(16, 0))
        assert moved.due_date == date(2026, 9, 24)
        assert moved.raw_date_phrase == "يوم الاتنين"
        assert moved.source_text == "التقرير يتسلم يوم الاتنين"

    def test_bulk_create_is_atomic(self, actions, meetings):
        meeting = meetings.create(Meeting(title="Weekly"))
        saved = actions.bulk_create(
            [
                ActionItem(meeting_id=meeting.id, task="Finish database"),
                ActionItem(meeting_id=meeting.id, task="Presentation ready"),
            ]
        )
        assert len(saved) == 2
        assert actions.count() == 2

    def test_mark_overdue_sweeps_past_deadlines(self, actions, clock):
        past = actions.create(ActionItem(task="Late report", due_date=date(2026, 9, 18)))
        future = actions.create(ActionItem(task="Future report", due_date=date(2026, 9, 30)))
        undated = actions.create(ActionItem(task="No deadline"))

        assert actions.mark_overdue() == 1
        assert actions.get(past.id).status == "OVERDUE"
        assert actions.get(future.id).status == "PENDING"
        assert actions.get(undated.id).status == "PENDING"

    def test_for_meeting_orders_by_deadline(self, actions, meetings):
        meeting = meetings.create(Meeting(title="Weekly"))
        actions.create(ActionItem(meeting_id=meeting.id, task="Later", due_date=date(2026, 9, 30)))
        actions.create(ActionItem(meeting_id=meeting.id, task="Sooner", due_date=date(2026, 9, 21)))
        actions.create(ActionItem(meeting_id=meeting.id, task="Undated"))
        assert [a.task for a in actions.for_meeting(meeting.id)] == ["Sooner", "Later", "Undated"]


class TestReminderRepository:
    @pytest.fixture
    def action(self, actions):
        return actions.create(ActionItem(task="Finish database", due_date=date(2026, 9, 24)))

    def test_create_and_read(self, reminders, action, clock):
        reminder = reminders.create(
            Reminder(action_item_id=action.id, scheduled_at=clock.now_utc())
        )
        assert reminders.get(reminder.id).status == "PENDING"

    def test_due_returns_only_reached_occurrences(self, reminders, action, clock):
        from datetime import timedelta

        due_now = reminders.create(
            Reminder(action_item_id=action.id, scheduled_at=clock.now_utc() - timedelta(minutes=5))
        )
        reminders.create(
            Reminder(action_item_id=action.id, scheduled_at=clock.now_utc() + timedelta(hours=2))
        )
        assert [r.id for r in reminders.due(clock.now_utc())] == [due_now.id]

    def test_update_status_tracks_attempts(self, reminders, action, clock):
        reminder = reminders.create(
            Reminder(action_item_id=action.id, scheduled_at=clock.now_utc())
        )
        failed = reminders.update_status(
            reminder.id, ReminderStatus.RETRY_WAIT, last_error="no internet", increment_attempt=True
        )
        assert (failed.status, failed.attempt_count, failed.last_error) == (
            "RETRY_WAIT",
            1,
            "no internet",
        )

    def test_marking_sent_stores_the_timestamp(self, reminders, action, clock):
        reminder = reminders.create(
            Reminder(action_item_id=action.id, scheduled_at=clock.now_utc())
        )
        sent = reminders.update_status(reminder.id, ReminderStatus.SENT, sent_at=clock.now_utc())
        assert sent.sent_at == clock.now_utc()

    def test_snoozing_moves_the_occurrence_only(self, reminders, actions, action, clock):
        from datetime import timedelta

        reminder = reminders.create(
            Reminder(action_item_id=action.id, scheduled_at=clock.now_utc())
        )
        snoozed = reminders.reschedule(reminder.id, clock.now_utc() + timedelta(hours=1))
        assert snoozed.status == "SNOOZED"
        # The task deadline is untouched (Section 6.7).
        assert actions.get(action.id).due_date == date(2026, 9, 24)

    def test_completing_a_task_closes_open_reminders(self, reminders, action, clock):
        from datetime import timedelta

        open_one = reminders.create(
            Reminder(action_item_id=action.id, scheduled_at=clock.now_utc() + timedelta(days=1))
        )
        already_sent = reminders.create(
            Reminder(action_item_id=action.id, scheduled_at=clock.now_utc())
        )
        reminders.update_status(already_sent.id, ReminderStatus.SENT)

        closed = reminders.cancel_open_for_action(
            action.id, status=ReminderStatus.SKIPPED_COMPLETED
        )
        assert closed == 1
        assert reminders.get(open_one.id).status == "SKIPPED_COMPLETED"
        assert reminders.get(already_sent.id).status == "SENT"

    def test_reminder_rules(self, reminders, action):
        rule = reminders.add_rule(
            ReminderRule(
                action_item_id=action.id,
                rule_type=ReminderRuleType.PREVIOUS_DAY_FIXED.value,
                fixed_local_time=time(20, 0),
            )
        )
        assert rule.fixed_local_time == time(20, 0)
        assert len(reminders.rules_for_action(action.id)) == 1
        reminders.set_rule_enabled(rule.id, False)
        assert reminders.rules_for_action(action.id)[0].enabled is False


class TestDeliveryRepository:
    def test_targets_for_a_meeting(self, deliveries, meetings):
        meeting = meetings.create(Meeting(title="Weekly"))
        deliveries.set_targets_for_meeting(
            meeting.id,
            DeliveryKind.REPORT.value,
            [
                DeliveryTarget(target_type=TargetType.ALL.value),
                DeliveryTarget(target_type=TargetType.ROLE.value, target_id=1),
            ],
        )
        stored = deliveries.targets_for_meeting(meeting.id, DeliveryKind.REPORT.value)
        assert [t.target_type for t in stored] == ["ALL", "ROLE"]

    def test_setting_targets_replaces_the_previous_selection(self, deliveries, meetings):
        meeting = meetings.create(Meeting(title="Weekly"))
        deliveries.set_targets_for_meeting(
            meeting.id, DeliveryKind.REPORT.value, [DeliveryTarget(target_type="ALL")]
        )
        deliveries.set_targets_for_meeting(
            meeting.id,
            DeliveryKind.REPORT.value,
            [DeliveryTarget(target_type="MEETING_PARTICIPANTS")],
        )
        stored = deliveries.targets_for_meeting(meeting.id, DeliveryKind.REPORT.value)
        assert [t.target_type for t in stored] == ["MEETING_PARTICIPANTS"]

    def test_report_and_reminder_targets_are_independent(self, deliveries, meetings):
        meeting = meetings.create(Meeting(title="Weekly"))
        deliveries.set_targets_for_meeting(
            meeting.id, DeliveryKind.REPORT.value, [DeliveryTarget(target_type="ALL")]
        )
        deliveries.set_targets_for_meeting(
            meeting.id, DeliveryKind.REMINDER.value, [DeliveryTarget(target_type="ASSIGNEE")]
        )
        assert len(deliveries.targets_for_meeting(meeting.id)) == 2

    def test_delivery_lifecycle(self, deliveries, meetings, employees):
        meeting = meetings.create(Meeting(title="Weekly"))
        ahmed = employees.create(Employee(full_name="Ahmed", email="a@example.com"))
        delivery = deliveries.record_attempt(
            EmailDelivery(
                meeting_id=meeting.id,
                recipient_employee_id=ahmed.id,
                recipient_email="A@example.com",
                subject="Meeting report",
                language="AR",
                status=DeliveryStatus.SENDING.value,
            )
        )
        assert delivery.recipient_email == "a@example.com"
        assert delivery.attempted_at is not None

        sent = deliveries.mark_sent(delivery.id, "gmail-message-1")
        assert (sent.status, sent.gmail_message_id) == ("SENT", "gmail-message-1")
        assert sent.sent_at is not None

    def test_failed_deliveries_are_queryable(self, deliveries, meetings):
        meeting = meetings.create(Meeting(title="Weekly"))
        delivery = deliveries.record_attempt(
            EmailDelivery(meeting_id=meeting.id, recipient_email="a@example.com")
        )
        deliveries.mark_failed(delivery.id, "revoked OAuth token")
        assert [d.id for d in deliveries.failed()] == [delivery.id]
        assert deliveries.meeting_ids_with_failed_email() == [meeting.id]


class TestTemplateRepository:
    def test_create_with_json_config(self, db, clock):
        templates = TemplateRepository(db, clock)
        template = templates.create(
            MeetingTemplate(
                name="Weekly Development Meeting",
                default_title="Weekly Development Meeting",
                default_audio_source="BOTH",
                default_email_language="AR",
                default_report_target_config={"targets": [{"type": "MEETING_PARTICIPANTS"}]},
            )
        )
        stored = templates.get(template.id)
        assert stored.default_report_target_config == {
            "targets": [{"type": "MEETING_PARTICIPANTS"}]
        }

    def test_duplicate_name_is_rejected(self, db, clock):
        templates = TemplateRepository(db, clock)
        templates.create(MeetingTemplate(name="Weekly"))
        with pytest.raises(ConflictError):
            templates.create(MeetingTemplate(name=" weekly "))

    def test_lookup_by_name_is_normalized(self, db, clock):
        templates = TemplateRepository(db, clock)
        templates.create(MeetingTemplate(name="اجتماع أسبوعي"))
        assert templates.get_by_name("اجتماع اسبوعي") is not None


class TestSettingsRepository:
    def test_defaults_are_inserted_once(self, db, clock):
        settings = SettingsRepository(db, clock)
        first = settings.ensure_defaults()
        settings.set("ui_language", "EN")
        second = settings.ensure_defaults()
        assert second["ui_language"] == "EN"
        assert set(first) == set(second)

    def test_values_keep_their_type(self, db, clock):
        settings = SettingsRepository(db, clock)
        settings.ensure_defaults()
        assert settings.get("missed_reminder_recovery_hours") == 12
        settings.set("missed_reminder_recovery_hours", 6)
        assert settings.get("missed_reminder_recovery_hours") == 6

    def test_unknown_key_returns_the_default(self, db, clock):
        assert SettingsRepository(db, clock).get("nope", "fallback") == "fallback"

    def test_delete(self, db, clock):
        settings = SettingsRepository(db, clock)
        settings.set("temporary", True)
        assert settings.delete("temporary") is True
        assert settings.delete("temporary") is False
