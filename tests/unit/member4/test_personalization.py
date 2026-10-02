"""Per-recipient reminder content (Section 11).

The headline property under test is a privacy one: a reminder must contain only
the recipient's own tasks. `test_recipients_never_see_each_others_tasks` is the
one that would catch a real disclosure.
"""

from __future__ import annotations

from nexa.contracts.meetings import ActionItem
from nexa.email.personalization import (
    actions_for,
    bundle_by_recipient,
    is_remindable,
    most_urgent,
    owners_of,
    owns,
)

from tests.fixtures import member4 as data


def test_ownership_is_by_id():
    assert owns(data.ACTION_WITH_TIME, data.AHMED) is True
    assert owns(data.ACTION_WITH_TIME, data.SARAH) is False


def test_spoken_name_alone_does_not_establish_ownership():
    """Several employees can be called أحمد (Section 2.1), so a raw name is
    never enough to mail someone a task."""
    assert data.ACTION_UNMATCHED_OWNER.owner_raw_text == "محمد"
    for employee in data.EMPLOYEES:
        assert owns(data.ACTION_UNMATCHED_OWNER, employee) is False


def test_completed_and_cancelled_are_not_remindable():
    assert is_remindable(data.ACTION_COMPLETED) is False
    assert is_remindable(ActionItem(task="x", status="CANCELLED")) is False
    assert is_remindable(data.ACTION_WITH_TIME) is True
    assert is_remindable(data.ACTION_OVERDUE) is True


def test_actions_for_returns_only_owned_items():
    assert actions_for(data.AHMED, data.ALL_ACTIONS) == [data.ACTION_WITH_TIME]
    assert actions_for(data.SARAH, data.ALL_ACTIONS) == [data.ACTION_NO_TIME]
    assert actions_for(data.NADA, data.ALL_ACTIONS) == [data.ACTION_OVERDUE]


def test_completed_task_produces_no_reminder():
    """Section 25.5's "completed task" row, enforced on the email side too."""
    owned = actions_for(data.AHMED, data.ALL_ACTIONS)
    assert data.ACTION_COMPLETED not in owned


def test_unassigned_is_excluded_by_default_and_opt_in():
    assert data.ACTION_NO_OWNER_NO_DATE not in actions_for(data.AHMED, data.ALL_ACTIONS)
    opted_in = actions_for(data.AHMED, data.ALL_ACTIONS, include_unassigned=True)
    assert data.ACTION_NO_OWNER_NO_DATE in opted_in


def test_recipients_never_see_each_others_tasks():
    bundles = bundle_by_recipient(data.SENDABLE_EMPLOYEES, data.ALL_ACTIONS)
    seen = {}
    for bundle in bundles:
        for action in bundle.actions:
            assert action.owner_employee_id == bundle.employee.id
            # No action may appear in two different recipients' bundles.
            assert action.id not in seen
            seen[action.id] = bundle.employee.id


def test_recipient_with_nothing_due_gets_no_bundle():
    """Nexa must never send "you have no tasks"."""
    idle = data.Employee(id=999, full_name="Idle", email="idle@example.com")
    bundles = bundle_by_recipient([idle], data.ALL_ACTIONS)
    assert bundles == []


def test_skip_empty_can_be_disabled():
    idle = data.Employee(id=999, full_name="Idle", email="idle@example.com")
    bundles = bundle_by_recipient([idle], data.ALL_ACTIONS, skip_empty=False)
    assert len(bundles) == 1
    assert not bundles[0]


def test_owners_of_covers_only_real_assignees():
    bundles = owners_of(data.ALL_ACTIONS, data.EMPLOYEES)
    assert {bundle.employee.id for bundle in bundles} == {
        data.AHMED.id, data.SARAH.id, data.NADA.id
    }


def test_owners_of_excludes_completed_only_owners():
    only_completed = owners_of([data.ACTION_COMPLETED], data.EMPLOYEES)
    assert only_completed == []


def test_most_urgent_prefers_the_earliest_deadline():
    assert most_urgent([data.ACTION_NO_TIME, data.ACTION_WITH_TIME]) is data.ACTION_WITH_TIME


def test_most_urgent_sorts_undated_last():
    assert most_urgent(
        [data.ACTION_NO_OWNER_NO_DATE, data.ACTION_NO_TIME]
    ) is data.ACTION_NO_TIME


def test_most_urgent_of_nothing_is_none():
    assert most_urgent([]) is None


def test_most_urgent_of_only_undated_still_returns_one():
    assert most_urgent([data.ACTION_NO_OWNER_NO_DATE]) is data.ACTION_NO_OWNER_NO_DATE
