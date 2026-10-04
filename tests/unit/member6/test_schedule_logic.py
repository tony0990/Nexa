from datetime import datetime

import pytest

from nexa.services.fakes import FakeReminderService
from nexa.ui.schedule.viewmodel import ScheduleViewModel, parse_when, snooze_target

NOW = datetime(2026, 9, 7, 8, 0)


def test_relative_snooze_options():
    assert snooze_target("30m", NOW) == "2026-09-07 08:30"
    assert snooze_target("1h", NOW) == "2026-09-07 09:00"
    assert snooze_target("3h", NOW) == "2026-09-07 11:00"


def test_tomorrow_morning_uses_configured_time():
    assert snooze_target("tomorrow", NOW, morning="08:00") == "2026-09-08 08:00"
    assert snooze_target("tomorrow", NOW, morning="09:30") == "2026-09-08 09:30"
    assert snooze_target("tomorrow", NOW, morning="bad") == "2026-09-08 08:00"


def test_custom_snooze_validates_input_and_rejects_past():
    assert snooze_target("custom", NOW, "2026-09-07 10:00") == "2026-09-07 10:00"
    with pytest.raises(ValueError):
        snooze_target("custom", NOW, "not a date")
    with pytest.raises(ValueError):
        snooze_target("custom", NOW, "2026-09-06 10:00")


def test_parse_when_accepts_common_formats():
    assert parse_when("2026-09-10T16:00") == datetime(2026, 9, 10, 16, 0)
    assert parse_when("10/09/2026 16:00") == datetime(2026, 9, 10, 16, 0)


def test_snooze_changes_reminder_not_deadline():
    reminders = FakeReminderService()
    vm = ScheduleViewModel(reminders)
    before = next(a for a in reminders.list_actions() if a.id == 1).due_display
    vm.snooze(1, "custom", "2026-09-07 10:00", now=NOW)
    action = next(a for a in reminders.list_actions() if a.id == 1)
    assert action.reminder_display == "2026-09-07 10:00"
    assert action.due_display == before


def test_reschedule_updates_deadline_and_marked_dates():
    reminders = FakeReminderService()
    vm = ScheduleViewModel(reminders)
    vm.reschedule(1, "2026-09-12 16:00", now=NOW)
    assert "2026-09-12" in vm.marked_dates()
    with pytest.raises(ValueError):
        vm.reschedule(1, "2026-01-01 10:00", now=NOW)


def test_mark_complete_skips_future_reminders_and_updates_counts():
    reminders = FakeReminderService()
    reminders.mark_complete(1)
    assert reminders.dashboard_counts()["completed"] == 1
    assert all(r.status == "SKIPPED_COMPLETED" for r in reminders._reminders if r.action_item_id == 1)
