"""Filter construction: presets, combination and SQL safety."""

from __future__ import annotations

from datetime import date

import pytest

from nexa.core.errors import ValidationError
from nexa.search.filters import (
    Conditions,
    DatePreset,
    EmployeeFilters,
    MeetingFilters,
    TaskFilters,
    clamp_limit,
    resolve_preset,
)


class TestResolvePreset:
    def test_any_is_unbounded(self, clock):
        assert resolve_preset(DatePreset.ANY.value, clock) == (None, None)
        assert resolve_preset(None, clock) == (None, None)

    def test_today(self, clock):
        assert resolve_preset("TODAY", clock) == (date(2026, 9, 20), date(2026, 9, 20))

    def test_tomorrow(self, clock):
        assert resolve_preset("TOMORROW", clock) == (date(2026, 9, 21), date(2026, 9, 21))

    def test_this_week_starts_on_sunday(self, clock):
        assert resolve_preset("THIS_WEEK", clock) == (date(2026, 9, 20), date(2026, 9, 26))

    def test_next_week(self, clock):
        assert resolve_preset("NEXT_WEEK", clock) == (date(2026, 9, 27), date(2026, 10, 3))

    def test_this_month(self, clock):
        assert resolve_preset("THIS_MONTH", clock) == (date(2026, 9, 1), date(2026, 9, 30))

    def test_upcoming_has_no_upper_bound(self, clock):
        assert resolve_preset("UPCOMING", clock) == (date(2026, 9, 20), None)

    def test_past_has_no_lower_bound(self, clock):
        assert resolve_preset("PAST", clock) == (None, date(2026, 9, 19))

    def test_unknown_preset_is_rejected(self, clock):
        with pytest.raises(ValidationError):
            resolve_preset("LAST_CENTURY", clock)


class TestConditions:
    def test_empty_conditions_produce_no_where(self):
        assert Conditions().where() == ""

    def test_clauses_are_anded(self):
        cond = Conditions().add("a = ?", 1).add("b = ?", 2)
        assert cond.where() == " WHERE a = ? AND b = ?"
        assert cond.params == [1, 2]

    def test_add_in_builds_placeholders(self):
        cond = Conditions().add_in("status", ["PENDING", "OVERDUE"])
        assert cond.where() == " WHERE status IN (?,?)"
        assert cond.params == ["PENDING", "OVERDUE"]

    def test_add_in_ignores_empty_sequences(self):
        assert not Conditions().add_in("status", [])

    def test_add_in_unwraps_enums(self):
        from nexa.contracts.meetings import ActionStatus

        cond = Conditions().add_in("status", [ActionStatus.PENDING])
        assert cond.params == ["PENDING"]


class TestTaskFilters:
    def test_no_filters_means_no_conditions(self, clock):
        assert TaskFilters().build(clock).where() == ""

    def test_filters_combine(self, clock):
        filters = TaskFilters(
            statuses=("PENDING",),
            owner_ids=(3,),
            meeting_ids=(7,),
            preset="TODAY",
            unassigned=False,
        )
        where = filters.build(clock).where()
        assert where.count("AND") >= 4
        assert "a.status IN (?)" in where
        assert "a.owner_employee_id IN (?)" in where
        assert "a.due_date >= ?" in where

    def test_overdue_uses_the_deadline_not_only_the_status(self, clock):
        cond = TaskFilters(overdue=True).build(clock)
        assert "due_date < ?" in cond.where()
        assert cond.params == ["2026-09-20"]

    def test_not_overdue_is_negated(self, clock):
        where = TaskFilters(overdue=False).build(clock).where()
        assert where.replace(" WHERE ", "", 1).startswith("NOT")

    def test_snoozed_checks_reminders(self, clock):
        assert "reminders" in TaskFilters(snoozed=True).build(clock).where()

    def test_role_filter_joins_through_the_owner(self, clock):
        cond = TaskFilters(role_ids=(2, 5)).build(clock)
        assert "employee_roles" in cond.where()
        assert cond.params == [2, 5]

    def test_explicit_dates_override_the_preset(self, clock):
        cond = TaskFilters(
            preset="TODAY", date_from=date(2026, 1, 1), date_to=date(2026, 1, 31)
        ).build(clock)
        assert cond.params == ["2026-01-01", "2026-01-31"]

    def test_reversed_date_range_is_rejected(self, clock):
        with pytest.raises(ValidationError):
            TaskFilters(date_from=date(2026, 2, 1), date_to=date(2026, 1, 1)).build(clock)

    def test_order_by_puts_undated_items_last(self, clock):
        assert "9999-12-31" in TaskFilters().order_by()


class TestMeetingFilters:
    def test_status_filter(self, clock):
        cond = MeetingFilters(statuses=("APPROVED",)).build(clock)
        assert cond.params == ["APPROVED"]

    def test_failed_email_filter_uses_exists(self, clock):
        where = MeetingFilters(has_failed_email=True).build(clock).where()
        assert "email_deliveries" in where and "FAILED" in where

    def test_no_failed_email_is_negated(self, clock):
        assert "NOT EXISTS" in MeetingFilters(has_failed_email=False).build(clock).where()

    def test_participant_filter(self, clock):
        cond = MeetingFilters(participant_ids=(4,)).build(clock)
        assert "meeting_participants" in cond.where()
        assert cond.params == [4]


class TestEmployeeFilters:
    def test_active_filter_binds_an_integer(self):
        cond = EmployeeFilters(active=True).build()
        assert cond.params == [1]

    def test_inactive_filter(self):
        assert EmployeeFilters(active=False).build().params == [0]

    def test_role_filter(self):
        cond = EmployeeFilters(role_ids=(1, 2)).build()
        assert "employee_roles" in cond.where()
        assert cond.params == [1, 2]

    def test_department_filter(self):
        assert EmployeeFilters(departments=("Development",)).build().params == ["Development"]


class TestClampLimit:
    def test_default(self):
        assert clamp_limit(None) == 200

    def test_minimum_is_one(self):
        assert clamp_limit(0) == 1
        assert clamp_limit(-5) == 1

    def test_maximum_is_capped(self):
        assert clamp_limit(10_000) == 1000
