"""Fake meetings, actions and employees for Member 4's tests (Section 24.4).

Member 4 owns no audio, no AI and no scheduler, so everything here is built by
hand from the contract dataclasses. The data deliberately covers the cases the
report layer has to get right rather than only the happy path:

* Arabic, English and code-switched task text and evidence
* a deadline with a time, a deadline without one, and no deadline at all
* an owner resolved to an employee, an owner heard but unmatched, and none
* an item still flagged `NEEDS_REVIEW`
* a completed item, which must never produce a reminder
* an employee with a malformed address, which must be skipped not crashed on

All timestamps are relative to `REFERENCE_MOMENT`, which the shared conftest
pins, so "due tomorrow" means the same thing on every run.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from typing import List

from nexa.contracts.meetings import (
    ActionItem,
    ActionStatus,
    EmailLanguage,
    Meeting,
    MeetingStatus,
    ReviewState,
)
from nexa.contracts.people import Employee

# Sunday 20 September 2026, 10:00 Cairo — the same instant the shared conftest
# pins, repeated here so this module can be used standalone.
REFERENCE_MOMENT = datetime(2026, 9, 20, 8, 0, tzinfo=timezone.utc)
TODAY = date(2026, 9, 20)
TOMORROW = TODAY + timedelta(days=1)
NEXT_WEEK = TODAY + timedelta(days=5)
YESTERDAY = TODAY - timedelta(days=1)

AHMED = Employee(id=7, full_name="أحمد حسن", email="ahmed@example.com", job_title="Backend")
SARAH = Employee(id=8, full_name="Sarah Ali", email="sarah@example.com", job_title="QA")
NADA = Employee(id=9, full_name="ندى مصطفى", email="nada@example.com")
# Deliberately malformed: the report layer must skip this address, and the
# preview must explain why, rather than raising.
BROKEN = Employee(id=10, full_name="Broken Address", email="not-an-email")
# Valid address but deactivated: the preview marks it undeliverable.
RETIRED = Employee(id=11, full_name="Omar Retired", email="omar@example.com", active=False)

EMPLOYEES: List[Employee] = [AHMED, SARAH, NADA, BROKEN, RETIRED]


def meeting(language: str = EmailLanguage.AR.value, **overrides) -> Meeting:
    values = dict(
        id=1,
        title="Digital Transformation Weekly Meeting",
        started_at=REFERENCE_MOMENT,
        ended_at=REFERENCE_MOMENT + timedelta(hours=1),
        status=MeetingStatus.APPROVED.value,
        email_language=language,
        participant_ids=(AHMED.id, SARAH.id, NADA.id),
    )
    values.update(overrides)
    return Meeting(**values)


# ---------------------------------------------------------------- action items
# Arabic task, owner resolved, deadline with a time, code-switched evidence.
ACTION_WITH_TIME = ActionItem(
    id=101,
    meeting_id=1,
    task="تجهيز العرض التقديمي للإدارة",
    owner_employee_id=AHMED.id,
    owner_raw_text="أحمد",
    raw_date_phrase="بكرة الساعة three",
    due_date=TOMORROW,
    due_time=time(15, 0),
    due_at=datetime(2026, 9, 21, 13, 0, tzinfo=timezone.utc),  # 15:00 Cairo
    source_text="الـpresentation Thursday الساعة three",
    confidence=0.91,
    review_state=ReviewState.APPROVED.value,
    status=ActionStatus.PENDING.value,
)

# English task, owner resolved, deadline without a time (Section 2.1's
# "Time not specified").
ACTION_NO_TIME = ActionItem(
    id=102,
    meeting_id=1,
    task="Database Integration",
    owner_employee_id=SARAH.id,
    owner_raw_text="Sarah",
    raw_date_phrase="next Friday",
    due_date=NEXT_WEEK,
    source_text="Sarah, please finish the database integration by next Friday.",
    confidence=0.88,
    review_state=ReviewState.APPROVED.value,
    status=ActionStatus.PENDING.value,
)

# Owner heard but never matched to an employee: the raw spoken name must still
# appear in the report rather than being dropped (Section 2.2).
ACTION_UNMATCHED_OWNER = ActionItem(
    id=103,
    meeting_id=1,
    task="مراجعة عقد المورد",
    owner_employee_id=None,
    owner_raw_text="محمد",
    raw_date_phrase="الأسبوع الجاي",
    due_date=NEXT_WEEK,
    source_text="محمد يراجع عقد المورد الأسبوع الجاي",
    confidence=0.64,
    review_state=ReviewState.NEEDS_REVIEW.value,
    status=ActionStatus.PENDING.value,
)

# No owner and no deadline at all: both "Unassigned" and "Deadline not
# specified" must render.
ACTION_NO_OWNER_NO_DATE = ActionItem(
    id=104,
    meeting_id=1,
    task="Prepare the onboarding checklist",
    owner_employee_id=None,
    owner_raw_text=None,
    due_date=None,
    due_time=None,
    source_text="We also need an onboarding checklist at some point.",
    confidence=0.45,
    review_state=ReviewState.NEEDS_REVIEW.value,
    status=ActionStatus.PENDING.value,
)

# Overdue, owned by Nada.
ACTION_OVERDUE = ActionItem(
    id=105,
    meeting_id=1,
    task="إرسال تقرير الحضور",
    owner_employee_id=NADA.id,
    owner_raw_text="ندى",
    due_date=YESTERDAY,
    source_text="ندى تبعت تقرير الحضور امبارح",
    review_state=ReviewState.APPROVED.value,
    status=ActionStatus.OVERDUE.value,
)

# Completed: must never generate a reminder (Section 25.5, "completed task").
ACTION_COMPLETED = ActionItem(
    id=106,
    meeting_id=1,
    task="Send the signed contract",
    owner_employee_id=AHMED.id,
    due_date=TOMORROW,
    source_text="Ahmed sends the signed contract tomorrow.",
    review_state=ReviewState.APPROVED.value,
    status=ActionStatus.COMPLETED.value,
    completed_at=REFERENCE_MOMENT,
)

APPROVED_ACTIONS: List[ActionItem] = [
    ACTION_WITH_TIME,
    ACTION_NO_TIME,
    ACTION_UNMATCHED_OWNER,
    ACTION_NO_OWNER_NO_DATE,
]

ALL_ACTIONS: List[ActionItem] = APPROVED_ACTIONS + [ACTION_OVERDUE, ACTION_COMPLETED]

SENDABLE_EMPLOYEES: List[Employee] = [AHMED, SARAH, NADA]
