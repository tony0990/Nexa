"""Recipient resolution: expansion, de-duplication and exclusions."""

from __future__ import annotations

import pytest

from nexa.contracts.email import DeliveryKind, DeliveryTarget, TargetType
from nexa.contracts.meetings import ActionItem, Meeting
from nexa.core.errors import ValidationError
from nexa.data.repositories.actions import ActionRepository
from nexa.data.repositories.meetings import MeetingRepository
from nexa.people.recipient_resolver import (  # noqa: I001
    SKIP_DUPLICATE_EMAIL,
    SKIP_INACTIVE,
    SKIP_INVALID_EMAIL,
)


@pytest.fixture
def org(people, db, clock):
    """A small organization: 3 employees, 2 roles, 1 meeting, 1 action."""
    managers = people.create_role("Managers")
    developers = people.create_role("Developers")

    ahmed = people.create_employee(
        "أحمد حسن", "ahmed@example.com", department="Development", role_ids=[developers.id]
    )
    mona = people.create_employee(
        "Mona Ali", "mona@example.com", department="Finance", role_ids=[managers.id]
    )
    sara = people.create_employee("Sara Nabil", "sara@example.com", department="Development")

    meetings = MeetingRepository(db, clock)
    meeting = meetings.create(
        Meeting(title="Weekly Development Meeting", participant_ids=(ahmed.id, sara.id))
    )
    actions = ActionRepository(db, clock)
    action = actions.create(
        ActionItem(meeting_id=meeting.id, task="Finish database", owner_employee_id=ahmed.id)
    )
    return {
        "managers": managers,
        "developers": developers,
        "ahmed": ahmed,
        "mona": mona,
        "sara": sara,
        "meeting": meeting,
        "action": action,
    }


NOW = "2026-09-20T08:00:00+00:00"


def target(target_type, **kwargs) -> DeliveryTarget:
    return DeliveryTarget(target_type=target_type, **kwargs)


class TestExpansion:
    def test_all_returns_every_active_employee(self, resolver, org):
        recipients = resolver.resolve([target(TargetType.ALL.value)])
        assert {e.email for e in recipients} == {
            "ahmed@example.com",
            "mona@example.com",
            "sara@example.com",
        }

    def test_meeting_participants(self, resolver, org):
        recipients = resolver.resolve(
            [target(TargetType.MEETING_PARTICIPANTS.value, meeting_id=org["meeting"].id)]
        )
        assert {e.email for e in recipients} == {"ahmed@example.com", "sara@example.com"}

    def test_role(self, resolver, org):
        recipients = resolver.resolve(
            [target(TargetType.ROLE.value, target_id=org["developers"].id)]
        )
        assert [e.email for e in recipients] == ["ahmed@example.com"]

    def test_employee(self, resolver, org):
        recipients = resolver.resolve(
            [target(TargetType.EMPLOYEE.value, target_id=org["mona"].id)]
        )
        assert [e.email for e in recipients] == ["mona@example.com"]

    def test_assignee(self, resolver, org):
        recipients = resolver.resolve(
            [target(TargetType.ASSIGNEE.value, action_item_id=org["action"].id)]
        )
        assert [e.email for e in recipients] == ["ahmed@example.com"]

    def test_unassigned_action_resolves_to_nobody(self, resolver, org, db, clock):
        actions = ActionRepository(db, clock)
        orphan = actions.create(ActionItem(task="Presentation ready"))
        assert resolver.resolve(
            [target(TargetType.ASSIGNEE.value, action_item_id=orphan.id)]
        ) == []

    def test_empty_target_list(self, resolver, org):
        assert resolver.resolve([]) == []


class TestDeduplication:
    def test_overlapping_targets_send_once(self, resolver, org):
        recipients = resolver.resolve(
            [
                target(TargetType.ALL.value),
                target(TargetType.MEETING_PARTICIPANTS.value, meeting_id=org["meeting"].id),
                target(TargetType.ROLE.value, target_id=org["developers"].id),
                target(TargetType.EMPLOYEE.value, target_id=org["ahmed"].id),
                target(TargetType.ASSIGNEE.value, action_item_id=org["action"].id),
            ]
        )
        emails = [e.email for e in recipients]
        assert len(emails) == len(set(emails)) == 3

    def test_two_employees_sharing_a_mailbox_are_collapsed(self, resolver, people, org, db):
        # The unique index normally prevents this; dropping it simulates data
        # imported from an older system. Resolution must still send one email
        # per mailbox rather than trusting the constraint.
        db.execute("DROP INDEX ux_employees_email")
        db.execute(
            "INSERT INTO employees (full_name, full_name_norm, email, search_text, "
            "active, created_at, updated_at) VALUES (?, ?, ?, ?, 1, ?, ?)",
            ("Shared Desk", "shared desk", "ahmed@example.com", "shared desk", NOW, NOW),
        )
        result = resolver.resolve_detailed([target(TargetType.ALL.value)])
        assert [e.email for e in result.recipients].count("ahmed@example.com") == 1
        assert SKIP_DUPLICATE_EMAIL in {skip.reason for skip in result.skipped}

    def test_reasons_explain_why_each_recipient_is_included(self, resolver, org):
        result = resolver.resolve_detailed(
            [
                target(TargetType.MEETING_PARTICIPANTS.value, meeting_id=org["meeting"].id),
                target(TargetType.ROLE.value, target_id=org["developers"].id),
            ]
        )
        assert result.reasons[org["ahmed"].id] == (
            f"MEETING_PARTICIPANTS:{org['meeting'].id}",
            f"ROLE:{org['developers'].id}",
        )
        assert result.reasons[org["sara"].id] == (
            f"MEETING_PARTICIPANTS:{org['meeting'].id}",
        )


class TestExclusions:
    def test_inactive_employees_are_never_recipients(self, resolver, people, org):
        people.deactivate_employee(org["sara"].id)
        result = resolver.resolve_detailed([target(TargetType.ALL.value)])
        assert org["sara"].id not in {e.id for e in result.recipients}

    def test_inactive_participant_is_reported_as_skipped(self, resolver, people, org):
        people.deactivate_employee(org["sara"].id)
        result = resolver.resolve_detailed(
            [target(TargetType.MEETING_PARTICIPANTS.value, meeting_id=org["meeting"].id)]
        )
        assert [(skip.employee.id, skip.reason) for skip in result.skipped] == [
            (org["sara"].id, SKIP_INACTIVE)
        ]

    def test_unusable_address_is_reported_not_silently_dropped(self, resolver, db, org):
        # A legacy row can hold an address the validator would reject today.
        db.execute(
            "INSERT INTO employees (full_name, full_name_norm, email, search_text, "
            "active, created_at, updated_at) VALUES (?, ?, ?, ?, 1, ?, ?)",
            ("Broken Record", "broken record", "not-an-email", "broken record", NOW, NOW),
        )
        result = resolver.resolve_detailed([target(TargetType.ALL.value)])
        assert SKIP_INVALID_EMAIL in {skip.reason for skip in result.skipped}
        assert "not-an-email" not in result.emails


class TestValidation:
    def test_meeting_participants_without_meeting_id(self, resolver):
        with pytest.raises(ValidationError):
            resolver.resolve([target(TargetType.MEETING_PARTICIPANTS.value)])

    def test_role_without_target_id(self, resolver):
        with pytest.raises(ValidationError):
            resolver.resolve([target(TargetType.ROLE.value)])

    def test_assignee_without_action_id(self, resolver):
        with pytest.raises(ValidationError):
            resolver.resolve([target(TargetType.ASSIGNEE.value)])

    def test_unknown_target_type(self, resolver):
        with pytest.raises(ValidationError):
            resolver.resolve([target("EVERYONE_EVERYWHERE")])


class TestStoredTargets:
    def test_resolve_for_meeting_reads_saved_targets(self, resolver, db, clock, org):
        from nexa.data.repositories.deliveries import DeliveryRepository

        deliveries = DeliveryRepository(db, clock)
        deliveries.set_targets_for_meeting(
            org["meeting"].id,
            DeliveryKind.REPORT.value,
            [
                DeliveryTarget(target_type=TargetType.MEETING_PARTICIPANTS.value),
                DeliveryTarget(
                    target_type=TargetType.ROLE.value, target_id=org["managers"].id
                ),
            ],
        )
        result = resolver.resolve_for_meeting(org["meeting"].id)
        assert {e.email for e in result.recipients} == {
            "ahmed@example.com",
            "sara@example.com",
            "mona@example.com",
        }

    def test_resolve_for_action_defaults_to_the_assignee(self, resolver, org):
        result = resolver.resolve_for_action(org["action"].id)
        assert result.emails == ["ahmed@example.com"]
