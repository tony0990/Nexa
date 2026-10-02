"""Filter definitions and SQL construction (Section 6.5).

Filters are plain dataclasses the UI fills in; each one knows how to turn
itself into a `WHERE` fragment plus bound parameters. They combine with AND,
so "overdue + owned by Ahmed + from last week's meeting" is one query rather
than three passes in Python.

All values are bound, never interpolated.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from enum import Enum
from typing import List, Optional, Sequence, Tuple

from ..contracts.meetings import ActionStatus, MeetingStatus, ReviewState
from ..core.clock import Clock
from ..core.errors import ValidationError
from ..core.timezone import month_bounds, week_bounds

MAX_LIMIT = 1000
DEFAULT_LIMIT = 200


class DatePreset(str, Enum):
    """Named date windows offered in the UI."""

    ANY = "ANY"
    TODAY = "TODAY"
    TOMORROW = "TOMORROW"
    THIS_WEEK = "THIS_WEEK"
    NEXT_WEEK = "NEXT_WEEK"
    THIS_MONTH = "THIS_MONTH"
    UPCOMING = "UPCOMING"
    PAST = "PAST"


class SortOrder(str, Enum):
    DUE_DATE_ASC = "DUE_DATE_ASC"
    DUE_DATE_DESC = "DUE_DATE_DESC"
    CREATED_DESC = "CREATED_DESC"
    NAME_ASC = "NAME_ASC"


def resolve_preset(
    preset: Optional[str], clock: Clock, *, week_starts_on: int = 6
) -> Tuple[Optional[date], Optional[date]]:
    """Turn a preset into an inclusive `(first_day, last_day)` local range.

    `None` on either side means unbounded. The working week starts on Sunday
    by default, which is the Egyptian working week.
    """
    value = getattr(preset, "value", preset)
    if value is None or value == DatePreset.ANY.value:
        return None, None

    today = clock.today()

    if value == DatePreset.TODAY.value:
        return today, today
    if value == DatePreset.TOMORROW.value:
        tomorrow = today + timedelta(days=1)
        return tomorrow, tomorrow
    if value == DatePreset.THIS_WEEK.value:
        return week_bounds(today, week_starts_on)
    if value == DatePreset.NEXT_WEEK.value:
        first, last = week_bounds(today + timedelta(days=7), week_starts_on)
        return first, last
    if value == DatePreset.THIS_MONTH.value:
        return month_bounds(today)
    if value == DatePreset.UPCOMING.value:
        return today, None
    if value == DatePreset.PAST.value:
        return None, today - timedelta(days=1)

    raise ValidationError(f"unknown date preset {value!r}", field="preset", code="choice")


class Conditions:
    """Accumulates `WHERE` fragments and their bound parameters."""

    def __init__(self) -> None:
        self.clauses: List[str] = []
        self.params: List[object] = []

    def add(self, clause: str, *params: object) -> "Conditions":
        self.clauses.append(clause)
        self.params.extend(params)
        return self

    def add_in(self, column: str, values: Sequence) -> "Conditions":
        cleaned = [getattr(value, "value", value) for value in values if value is not None]
        if not cleaned:
            return self
        placeholders = ",".join("?" * len(cleaned))
        return self.add(f"{column} IN ({placeholders})", *cleaned)

    def where(self) -> str:
        if not self.clauses:
            return ""
        return " WHERE " + " AND ".join(self.clauses)

    def __bool__(self) -> bool:
        return bool(self.clauses)


def clamp_limit(limit: Optional[int]) -> int:
    if limit is None:
        return DEFAULT_LIMIT
    return max(1, min(int(limit), MAX_LIMIT))


# ======================================================================
# employees
# ======================================================================
@dataclass
class EmployeeFilters:
    """Active / inactive, department, role (Section 6.5)."""

    active: Optional[bool] = None
    departments: Sequence[str] = field(default_factory=tuple)
    job_titles: Sequence[str] = field(default_factory=tuple)
    role_ids: Sequence[int] = field(default_factory=tuple)
    limit: Optional[int] = None
    sort: str = SortOrder.NAME_ASC.value

    def build(self, conditions: Optional[Conditions] = None) -> Conditions:
        # `is None`, not `or`: an empty Conditions is falsy, and `or` would
        # silently drop the caller's object along with its query clause.
        cond = Conditions() if conditions is None else conditions
        if self.active is not None:
            cond.add("e.active = ?", 1 if self.active else 0)
        cond.add_in("e.department", self.departments)
        cond.add_in("e.job_title", self.job_titles)
        if self.role_ids:
            placeholders = ",".join("?" * len(self.role_ids))
            cond.add(
                "EXISTS (SELECT 1 FROM employee_roles er WHERE er.employee_id = e.id "
                f"AND er.role_id IN ({placeholders}))",
                *[int(role_id) for role_id in self.role_ids],
            )
        return cond

    def order_by(self) -> str:
        if self.sort == SortOrder.CREATED_DESC.value:
            return " ORDER BY e.created_at DESC, e.id DESC"
        return " ORDER BY e.full_name_norm, e.id"


# ======================================================================
# meetings
# ======================================================================
@dataclass
class MeetingFilters:
    """Today / this week / this month, status, template, failed email."""

    statuses: Sequence[str] = field(default_factory=tuple)
    preset: Optional[str] = None
    date_from: Optional[date] = None
    date_to: Optional[date] = None
    template_ids: Sequence[int] = field(default_factory=tuple)
    participant_ids: Sequence[int] = field(default_factory=tuple)
    has_failed_email: Optional[bool] = None
    pending_review: Optional[bool] = None
    limit: Optional[int] = None
    sort: str = SortOrder.CREATED_DESC.value

    def build(self, clock: Clock, conditions: Optional[Conditions] = None) -> Conditions:
        # `is None`, not `or`: an empty Conditions is falsy, and `or` would
        # silently drop the caller's object along with its query clause.
        cond = Conditions() if conditions is None else conditions
        cond.add_in("m.status", self.statuses)

        first, last = _effective_range(self.preset, self.date_from, self.date_to, clock)
        # Meetings are filtered on their local start day; a meeting that has
        # not started yet falls back to its creation day.
        if first is not None:
            cond.add("date(COALESCE(m.started_at, m.created_at)) >= ?", first.isoformat())
        if last is not None:
            cond.add("date(COALESCE(m.started_at, m.created_at)) <= ?", last.isoformat())

        cond.add_in("m.template_id", self.template_ids)

        if self.participant_ids:
            placeholders = ",".join("?" * len(self.participant_ids))
            cond.add(
                "EXISTS (SELECT 1 FROM meeting_participants mp "
                "WHERE mp.meeting_id = m.id "
                f"AND mp.employee_id IN ({placeholders}))",
                *[int(employee_id) for employee_id in self.participant_ids],
            )

        if self.pending_review:
            cond.add("m.status = ?", MeetingStatus.PENDING_REVIEW.value)

        if self.has_failed_email is not None:
            exists = (
                "EXISTS (SELECT 1 FROM email_deliveries ed WHERE ed.meeting_id = m.id "
                "AND ed.status = 'FAILED')"
            )
            cond.add(exists if self.has_failed_email else f"NOT {exists}")

        return cond

    def order_by(self) -> str:
        if self.sort == SortOrder.NAME_ASC.value:
            return " ORDER BY m.title_norm, m.id"
        return " ORDER BY COALESCE(m.started_at, m.created_at) DESC, m.id DESC"


# ======================================================================
# tasks
# ======================================================================
@dataclass
class TaskFilters:
    """The full task filter set from Section 6.5.

    `overdue`, `completed` and `snoozed` are convenience switches on top of
    `statuses`; they can be combined with everything else.
    """

    statuses: Sequence[str] = field(default_factory=tuple)
    review_states: Sequence[str] = field(default_factory=tuple)
    owner_ids: Sequence[int] = field(default_factory=tuple)
    role_ids: Sequence[int] = field(default_factory=tuple)
    meeting_ids: Sequence[int] = field(default_factory=tuple)
    preset: Optional[str] = None
    date_from: Optional[date] = None
    date_to: Optional[date] = None
    overdue: Optional[bool] = None
    completed: Optional[bool] = None
    snoozed: Optional[bool] = None
    unassigned: Optional[bool] = None
    without_due_date: Optional[bool] = None
    min_confidence: Optional[float] = None
    limit: Optional[int] = None
    sort: str = SortOrder.DUE_DATE_ASC.value

    def build(self, clock: Clock, conditions: Optional[Conditions] = None) -> Conditions:
        # `is None`, not `or`: an empty Conditions is falsy, and `or` would
        # silently drop the caller's object along with its query clause.
        cond = Conditions() if conditions is None else conditions
        cond.add_in("a.status", self.statuses)
        cond.add_in("a.review_state", self.review_states)
        cond.add_in("a.meeting_id", self.meeting_ids)

        if self.owner_ids:
            cond.add_in("a.owner_employee_id", self.owner_ids)

        if self.role_ids:
            placeholders = ",".join("?" * len(self.role_ids))
            cond.add(
                "EXISTS (SELECT 1 FROM employee_roles er "
                "WHERE er.employee_id = a.owner_employee_id "
                f"AND er.role_id IN ({placeholders}))",
                *[int(role_id) for role_id in self.role_ids],
            )

        first, last = _effective_range(self.preset, self.date_from, self.date_to, clock)
        if first is not None:
            cond.add("a.due_date IS NOT NULL AND a.due_date >= ?", first.isoformat())
        if last is not None:
            cond.add("a.due_date IS NOT NULL AND a.due_date <= ?", last.isoformat())

        if self.overdue is not None:
            today = clock.today().isoformat()
            # "Overdue" is computed from the deadline, not only from the
            # status flag, so an item is correct even before the periodic
            # sweep has flipped it to OVERDUE.
            expression = (
                "(a.status IN ('PENDING', 'OVERDUE') AND a.due_date IS NOT NULL "
                "AND a.due_date < ?)"
            )
            cond.add(expression if self.overdue else f"NOT {expression}", today)

        if self.completed is not None:
            cond.add(
                "a.status = ?" if self.completed else "a.status <> ?",
                ActionStatus.COMPLETED.value,
            )

        if self.snoozed is not None:
            expression = (
                "EXISTS (SELECT 1 FROM reminders r WHERE r.action_item_id = a.id "
                "AND r.status = 'SNOOZED')"
            )
            cond.add(expression if self.snoozed else f"NOT {expression}")

        if self.unassigned is not None:
            cond.add(
                "a.owner_employee_id IS NULL"
                if self.unassigned
                else "a.owner_employee_id IS NOT NULL"
            )

        if self.without_due_date is not None:
            cond.add(
                "a.due_date IS NULL" if self.without_due_date else "a.due_date IS NOT NULL"
            )

        if self.min_confidence is not None:
            cond.add("a.confidence IS NOT NULL AND a.confidence >= ?", float(self.min_confidence))

        return cond

    def order_by(self) -> str:
        if self.sort == SortOrder.DUE_DATE_DESC.value:
            return " ORDER BY COALESCE(a.due_date, '0000-01-01') DESC, a.id DESC"
        if self.sort == SortOrder.CREATED_DESC.value:
            return " ORDER BY a.created_at DESC, a.id DESC"
        # Items with no deadline sort last: they are not urgent by definition.
        return " ORDER BY COALESCE(a.due_date, '9999-12-31'), COALESCE(a.due_time, '23:59'), a.id"


# ======================================================================
# presets shared by meetings and tasks
# ======================================================================
def _effective_range(
    preset: Optional[str],
    date_from: Optional[date],
    date_to: Optional[date],
    clock: Clock,
) -> Tuple[Optional[date], Optional[date]]:
    """Explicit dates win over a preset; otherwise the preset is expanded."""
    if date_from is not None or date_to is not None:
        if date_from is not None and date_to is not None and date_from > date_to:
            raise ValidationError(
                "date_from must not be after date_to", field="date_from", code="range"
            )
        return date_from, date_to
    return resolve_preset(preset, clock)


# Convenience factories matching the filter chips in the UI.
def today_tasks() -> TaskFilters:
    return TaskFilters(preset=DatePreset.TODAY.value, statuses=(ActionStatus.PENDING.value,))


def overdue_tasks() -> TaskFilters:
    return TaskFilters(overdue=True)


def completed_tasks() -> TaskFilters:
    return TaskFilters(completed=True, sort=SortOrder.DUE_DATE_DESC.value)


def pending_review_tasks() -> TaskFilters:
    return TaskFilters(review_states=(ReviewState.NEEDS_REVIEW.value,))


def unassigned_tasks() -> TaskFilters:
    return TaskFilters(unassigned=True, statuses=(ActionStatus.PENDING.value,))


def active_employees() -> EmployeeFilters:
    return EmployeeFilters(active=True)


def meetings_pending_review() -> MeetingFilters:
    return MeetingFilters(statuses=(MeetingStatus.PENDING_REVIEW.value,))
