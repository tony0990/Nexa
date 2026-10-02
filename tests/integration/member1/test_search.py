"""Search and filtering against a populated database (Section 39.5)."""

from __future__ import annotations

from datetime import date, time

import pytest

from nexa.contracts.meetings import ActionItem, ActionStatus, Meeting, MeetingStatus, ReviewState
from nexa.contracts.scheduling import Reminder, ReminderStatus
from nexa.data.repositories.actions import ActionRepository
from nexa.data.repositories.meetings import MeetingRepository
from nexa.data.repositories.reminders import ReminderRepository
from nexa.search.filters import (
    DatePreset,
    EmployeeFilters,
    MeetingFilters,
    TaskFilters,
    overdue_tasks,
    unassigned_tasks,
)


@pytest.fixture
def world(people, db, clock):
    """The dataset from the Section 31 search example, plus edge cases."""
    developers = people.create_role("Developers")
    managers = people.create_role("Managers")

    ahmed = people.create_employee(
        "أحمد حسن", "ahmed@example.com", department="Development",
        job_title="Backend Engineer", role_ids=[developers.id],
    )
    mona = people.create_employee(
        "Mona Ali", "mona@example.com", department="Finance",
        job_title="Accountant", role_ids=[managers.id],
    )
    sara = people.create_employee(
        "Sara Nabil", "sara@example.com", department="Development", job_title="QA Engineer"
    )
    retired = people.create_employee("Old Employee", "old@example.com", department="Finance")
    people.deactivate_employee(retired.id)

    meetings = MeetingRepository(db, clock)
    weekly = meetings.create(
        Meeting(
            title="Weekly Development Meeting",
            status=MeetingStatus.APPROVED.value,
            started_at=clock.now_utc(),
            participant_ids=(ahmed.id, sara.id),
        )
    )
    budget = meetings.create(
        Meeting(
            title="اجتماع الميزانية",
            status=MeetingStatus.PENDING_REVIEW.value,
            started_at=clock.now_utc(),
            participant_ids=(mona.id,),
        )
    )

    actions = ActionRepository(db, clock)
    database_task = actions.create(
        ActionItem(
            meeting_id=weekly.id,
            task="Database Integration",
            owner_employee_id=ahmed.id,
            owner_raw_text="أحمد",
            raw_date_phrase="before Monday",
            due_date=date(2026, 9, 21),
            source_text="أحمد يخلص الـdatabase before Monday",
            confidence=0.94,
            review_state=ReviewState.APPROVED.value,
        )
    )
    presentation = actions.create(
        ActionItem(
            meeting_id=weekly.id,
            task="Presentation ready",
            due_date=date(2026, 9, 24),
            due_time=time(15, 0),
            raw_date_phrase="يوم الخميس الساعة three",
            source_text="الـpresentation تكون ready يوم الخميس الساعة three",
            confidence=0.81,
        )
    )
    late_report = actions.create(
        ActionItem(
            meeting_id=budget.id,
            task="Budget report",
            owner_employee_id=mona.id,
            due_date=date(2026, 9, 15),
        )
    )
    done = actions.create(
        ActionItem(
            meeting_id=weekly.id,
            task="API Review",
            owner_employee_id=ahmed.id,
            due_date=date(2026, 9, 19),
            status=ActionStatus.COMPLETED.value,
        )
    )
    undated = actions.create(ActionItem(meeting_id=weekly.id, task="Discuss budget later"))

    return {
        "developers": developers,
        "managers": managers,
        "ahmed": ahmed,
        "mona": mona,
        "sara": sara,
        "retired": retired,
        "weekly": weekly,
        "budget": budget,
        "database_task": database_task,
        "presentation": presentation,
        "late_report": late_report,
        "done": done,
        "undated": undated,
    }


class TestEmployeeSearch:
    def test_by_english_name(self, search, world):
        assert [e.id for e in search.search_employees("Mona")] == [world["mona"].id]

    def test_by_arabic_name(self, search, world):
        assert [e.id for e in search.search_employees("أحمد")] == [world["ahmed"].id]

    def test_arabic_spelling_variant_still_matches(self, search, world):
        # Typed without the hamza: احمد instead of أحمد.
        assert [e.id for e in search.search_employees("احمد")] == [world["ahmed"].id]

    def test_by_email(self, search, world):
        assert [e.id for e in search.search_employees("mona@example")] == [world["mona"].id]

    def test_by_department(self, search, world):
        found = {e.id for e in search.search_employees("Development")}
        assert found == {world["ahmed"].id, world["sara"].id}

    def test_by_job_title(self, search, world):
        assert [e.id for e in search.search_employees("Accountant")] == [world["mona"].id]

    def test_by_role_name(self, search, world):
        assert [e.id for e in search.search_employees("Developers")] == [world["ahmed"].id]

    def test_empty_result(self, search, world):
        assert search.search_employees("nobody-by-this-name") == []

    def test_blank_query_returns_everyone(self, search, world):
        assert len(search.search_employees("")) == 4

    def test_active_filter(self, search, world):
        ids = {e.id for e in search.search_employees(None, EmployeeFilters(active=True))}
        assert world["retired"].id not in ids

    def test_inactive_filter(self, search, world):
        ids = [e.id for e in search.search_employees(None, EmployeeFilters(active=False))]
        assert ids == [world["retired"].id]

    def test_department_and_role_filters_combine(self, search, world):
        results = search.search_employees(
            None,
            EmployeeFilters(
                active=True, departments=("Development",), role_ids=(world["developers"].id,)
            ),
        )
        assert [e.id for e in results] == [world["ahmed"].id]

    def test_query_and_filter_combine(self, search, world):
        assert search.search_employees("Development", EmployeeFilters(active=False)) == []

    def test_results_are_sorted_by_name(self, search, world):
        names = [e.full_name for e in search.search_employees(None, EmployeeFilters(active=True))]
        assert names == sorted(names, key=lambda n: n.casefold())

    def test_suggest_matches_a_prefix_only(self, search, world):
        assert [e.id for e in search.employees.suggest("Mon")] == [world["mona"].id]
        assert search.employees.suggest("ona") == []

    def test_limit_is_respected(self, search, world):
        assert len(search.search_employees(None, EmployeeFilters(limit=2))) == 2


class TestMeetingSearch:
    def test_by_title(self, search, world):
        assert [m.id for m in search.search_meetings("Weekly")] == [world["weekly"].id]

    def test_by_arabic_title(self, search, world):
        assert [m.id for m in search.search_meetings("الميزانية")] == [world["budget"].id]

    def test_by_participant_name(self, search, world):
        # "Ahmed" finds the meeting Ahmed attended (Section 31).
        assert world["weekly"].id in {m.id for m in search.search_meetings("أحمد")}

    def test_by_extracted_task_text(self, search, world):
        assert world["weekly"].id in {m.id for m in search.search_meetings("Database Integration")}

    def test_by_evidence_phrase(self, search, world):
        assert world["weekly"].id in {m.id for m in search.search_meetings("الساعة three")}

    def test_status_filter(self, search, world):
        results = search.search_meetings(None, MeetingFilters(statuses=("PENDING_REVIEW",)))
        assert [m.id for m in results] == [world["budget"].id]

    def test_today_filter(self, search, world):
        assert len(search.search_meetings(None, MeetingFilters(preset=DatePreset.TODAY.value))) == 2

    def test_past_month_filter_excludes_today(self, search, world):
        results = search.search_meetings(
            None, MeetingFilters(date_from=date(2026, 8, 1), date_to=date(2026, 8, 31))
        )
        assert results == []

    def test_participant_filter(self, search, world):
        results = search.search_meetings(
            None, MeetingFilters(participant_ids=(world["mona"].id,))
        )
        assert [m.id for m in results] == [world["budget"].id]

    def test_failed_email_filter(self, search, world, db, clock):
        from nexa.contracts.email import EmailDelivery
        from nexa.data.repositories.deliveries import DeliveryRepository

        deliveries = DeliveryRepository(db, clock)
        delivery = deliveries.record_attempt(
            EmailDelivery(meeting_id=world["budget"].id, recipient_email="mona@example.com")
        )
        deliveries.mark_failed(delivery.id, "no internet")

        results = search.search_meetings(None, MeetingFilters(has_failed_email=True))
        assert [m.id for m in results] == [world["budget"].id]
        healthy = search.search_meetings(None, MeetingFilters(has_failed_email=False))
        assert [m.id for m in healthy] == [world["weekly"].id]

    def test_empty_result(self, search, world):
        assert search.search_meetings("nonexistent meeting") == []


class TestTaskSearch:
    def test_by_task_name(self, search, world):
        assert [a.id for a in search.search_tasks("Database Integration")] == [
            world["database_task"].id
        ]

    def test_by_owner_name(self, search, world):
        found = {a.id for a in search.search_tasks("أحمد")}
        assert {world["database_task"].id, world["done"].id} <= found

    def test_by_meeting_title(self, search, world):
        found = {a.id for a in search.search_tasks("Weekly Development")}
        assert world["presentation"].id in found

    def test_by_evidence_text(self, search, world):
        # The admin remembers the sentence, not the task name.
        assert [a.id for a in search.search_tasks("تكون ready")] == [world["presentation"].id]

    def test_by_raw_date_phrase(self, search, world):
        assert [a.id for a in search.search_tasks("before Monday")] == [
            world["database_task"].id
        ]

    def test_status_filter(self, search, world):
        results = search.search_tasks(None, TaskFilters(statuses=(ActionStatus.COMPLETED.value,)))
        assert [a.id for a in results] == [world["done"].id]

    def test_completed_filter(self, search, world):
        assert [a.id for a in search.search_tasks(None, TaskFilters(completed=True))] == [
            world["done"].id
        ]

    def test_overdue_filter(self, search, world):
        assert [a.id for a in search.search_tasks(None, overdue_tasks())] == [
            world["late_report"].id
        ]

    def test_overdue_excludes_completed_items(self, search, world):
        overdue_ids = {a.id for a in search.search_tasks(None, overdue_tasks())}
        assert world["done"].id not in overdue_ids

    def test_unassigned_filter(self, search, world):
        ids = {a.id for a in search.search_tasks(None, unassigned_tasks())}
        assert ids == {world["presentation"].id, world["undated"].id}

    def test_today_filter(self, search, world):
        assert search.search_tasks(None, TaskFilters(preset=DatePreset.TODAY.value)) == []

    def test_tomorrow_filter(self, search, world):
        results = search.search_tasks(None, TaskFilters(preset=DatePreset.TOMORROW.value))
        assert [a.id for a in results] == [world["database_task"].id]

    def test_this_week_filter(self, search, world):
        ids = {a.id for a in search.search_tasks(None, TaskFilters(preset="THIS_WEEK"))}
        assert ids == {world["database_task"].id, world["presentation"].id}

    def test_owner_filter(self, search, world):
        results = search.search_tasks(None, TaskFilters(owner_ids=(world["mona"].id,)))
        assert [a.id for a in results] == [world["late_report"].id]

    def test_role_filter_follows_the_owner(self, search, world):
        results = search.search_tasks(None, TaskFilters(role_ids=(world["developers"].id,)))
        assert {a.id for a in results} == {world["database_task"].id, world["done"].id}

    def test_meeting_filter(self, search, world):
        results = search.search_tasks(None, TaskFilters(meeting_ids=(world["budget"].id,)))
        assert [a.id for a in results] == [world["late_report"].id]

    def test_review_state_filter(self, search, world):
        results = search.search_tasks(
            None, TaskFilters(review_states=(ReviewState.NEEDS_REVIEW.value,))
        )
        assert world["database_task"].id not in {a.id for a in results}

    def test_snoozed_filter(self, search, world, db, clock):
        reminders = ReminderRepository(db, clock)
        reminder = reminders.create(
            Reminder(action_item_id=world["presentation"].id, scheduled_at=clock.now_utc())
        )
        reminders.update_status(reminder.id, ReminderStatus.SNOOZED)
        results = search.search_tasks(None, TaskFilters(snoozed=True))
        assert [a.id for a in results] == [world["presentation"].id]

    def test_without_due_date_filter(self, search, world):
        results = search.search_tasks(None, TaskFilters(without_due_date=True))
        assert [a.id for a in results] == [world["undated"].id]

    def test_confidence_filter(self, search, world):
        results = search.search_tasks(None, TaskFilters(min_confidence=0.9))
        assert [a.id for a in results] == [world["database_task"].id]

    def test_filters_combine(self, search, world):
        results = search.search_tasks(
            "database",
            TaskFilters(
                statuses=(ActionStatus.PENDING.value,),
                owner_ids=(world["ahmed"].id,),
                meeting_ids=(world["weekly"].id,),
                preset="THIS_WEEK",
            ),
        )
        assert [a.id for a in results] == [world["database_task"].id]

    def test_contradictory_filters_return_nothing(self, search, world):
        assert search.search_tasks(None, TaskFilters(completed=True, overdue=True)) == []

    def test_ordering_puts_undated_last(self, search, world):
        ordered = [a.task for a in search.search_tasks()]
        assert ordered[-1] == "Discuss budget later"

    def test_rows_include_owner_and_meeting_for_display(self, search, world):
        rows = {row.action.id: row for row in search.search_task_rows()}
        row = rows[world["database_task"].id]
        assert row.owner_name == "أحمد حسن"
        assert row.meeting_title == "Weekly Development Meeting"

    def test_status_counts(self, search, world):
        assert search.task_status_counts() == {"PENDING": 4, "COMPLETED": 1}


class TestGlobalSearch:
    def test_groups_results_by_category(self, search, world):
        results = search.global_search("أحمد")
        assert [e.id for e in results.employees] == [world["ahmed"].id]
        assert world["weekly"].id in {m.id for m in results.meetings}
        assert world["database_task"].id in {a.id for a in results.tasks}

    def test_group_counts(self, search, world):
        counts = search.global_search("Ahmed").group_counts()
        assert set(counts) == {"employees", "meetings", "tasks"}
        # His name is stored in Arabic, but his email address is Latin, so a
        # Latin query still finds him.
        assert counts["employees"] == 1

    def test_owner_name_reaches_every_group(self, search, world):
        # Searching a person finds the person, the meetings they attended and
        # the tasks they own (Section 31).
        results = search.global_search("Mona")
        assert [e.id for e in results.employees] == [world["mona"].id]
        assert [m.id for m in results.meetings] == [world["budget"].id]
        assert [a.id for a in results.tasks] == [world["late_report"].id]

    def test_empty_query_returns_nothing(self, search, world):
        assert search.global_search("").is_empty
        assert search.global_search("   ").is_empty

    def test_no_matches(self, search, world):
        results = search.global_search("zzzz-not-found")
        assert results.is_empty and results.total == 0

    def test_total_sums_every_group(self, search, world):
        results = search.global_search("database")
        assert results.total == (
            results.employee_total + results.meeting_total + results.task_total
        )

    def test_wildcards_in_the_query_are_literal(self, search, world):
        # "%" must not behave as "match everything".
        assert search.global_search("%").is_empty
