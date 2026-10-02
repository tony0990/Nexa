"""Employee and role administration through PeopleService."""

from __future__ import annotations

import pytest

from nexa.audit import event_types
from nexa.core.errors import ConflictError, NotFoundError, ValidationError


class TestCreateEmployee:
    def test_creates_and_returns_the_stored_employee(self, people):
        employee = people.create_employee(
            "Ahmed Hassan", "ahmed@example.com", department="Development", job_title="Engineer"
        )
        assert employee.id is not None
        assert employee.full_name == "Ahmed Hassan"
        assert employee.department == "Development"
        assert employee.active is True
        assert employee.created_at is not None

    def test_email_is_stored_lowercase(self, people):
        employee = people.create_employee("Ahmed Hassan", "  Ahmed@EXAMPLE.com ")
        assert employee.email == "ahmed@example.com"

    def test_arabic_name_is_preserved_exactly(self, people):
        employee = people.create_employee("أحمد حسن", "ahmed@example.com")
        assert employee.full_name == "أحمد حسن"

    def test_duplicate_email_is_rejected(self, people):
        people.create_employee("Ahmed Hassan", "ahmed@example.com")
        with pytest.raises(ConflictError) as excinfo:
            people.create_employee("Ahmed Other", "AHMED@example.com")
        assert excinfo.value.code == "duplicate_email"

    def test_invalid_email_is_rejected(self, people):
        with pytest.raises(ValidationError):
            people.create_employee("Ahmed Hassan", "ahmed-at-example")

    def test_blank_name_is_rejected(self, people):
        with pytest.raises(ValidationError):
            people.create_employee("   ", "ahmed@example.com")

    def test_roles_can_be_assigned_at_creation(self, people):
        role = people.create_role("Managers")
        employee = people.create_employee("Ahmed", "a@example.com", role_ids=[role.id])
        assert employee.role_ids == (role.id,)

    def test_creation_is_audited(self, people, audit):
        employee = people.create_employee("Ahmed Hassan", "ahmed@example.com")
        history = audit.history(event_types.ENTITY_EMPLOYEE, employee.id)
        assert [event.event_type for event in history] == [event_types.EMPLOYEE_CREATED]
        assert history[0].new_value["email"] == "ahmed@example.com"
        assert history[0].actor_id == "admin"

    def test_failed_creation_leaves_no_audit_row(self, people, audit):
        people.create_employee("Ahmed Hassan", "ahmed@example.com")
        before = audit.count()
        with pytest.raises(ConflictError):
            people.create_employee("Someone Else", "ahmed@example.com")
        assert audit.count() == before


class TestUpdateEmployee:
    def test_updates_only_the_given_fields(self, people):
        employee = people.create_employee(
            "Ahmed Hassan", "ahmed@example.com", department="Development"
        )
        updated = people.update_employee(employee.id, job_title="Team Lead")
        assert updated.job_title == "Team Lead"
        assert updated.department == "Development"
        assert updated.full_name == "Ahmed Hassan"

    def test_clearing_an_optional_field(self, people):
        employee = people.create_employee("Ahmed", "a@example.com", department="Development")
        assert people.update_employee(employee.id, department="  ").department is None

    def test_unknown_field_is_rejected(self, people):
        employee = people.create_employee("Ahmed", "a@example.com")
        with pytest.raises(ValidationError) as excinfo:
            people.update_employee(employee.id, salary=100)
        assert excinfo.value.code == "unknown_field"

    def test_email_collision_is_rejected(self, people):
        people.create_employee("Ahmed", "ahmed@example.com")
        other = people.create_employee("Mona", "mona@example.com")
        with pytest.raises(ConflictError):
            people.update_employee(other.id, email="ahmed@example.com")

    def test_keeping_your_own_email_is_allowed(self, people):
        employee = people.create_employee("Ahmed", "ahmed@example.com")
        updated = people.update_employee(employee.id, email="ahmed@example.com", job_title="Lead")
        assert updated.job_title == "Lead"

    def test_missing_employee_raises(self, people):
        with pytest.raises(NotFoundError):
            people.update_employee(999, job_title="Lead")

    def test_audit_records_only_changed_fields(self, people, audit):
        employee = people.create_employee("Ahmed", "a@example.com", department="Development")
        people.update_employee(employee.id, job_title="Lead")
        update = audit.history(event_types.ENTITY_EMPLOYEE, employee.id)[-1]
        assert update.event_type == event_types.EMPLOYEE_UPDATED
        assert set(update.new_value) == {"job_title"}
        assert update.old_value == {"job_title": None}

    def test_no_op_update_writes_no_audit_row(self, people, audit):
        employee = people.create_employee("Ahmed", "a@example.com", job_title="Lead")
        before = audit.count()
        people.update_employee(employee.id, job_title="Lead")
        assert audit.count() == before


class TestActivation:
    def test_deactivate_and_reactivate(self, people):
        employee = people.create_employee("Ahmed", "a@example.com")
        assert people.deactivate_employee(employee.id).active is False
        assert people.reactivate_employee(employee.id).active is True

    def test_deactivating_twice_is_idempotent(self, people, audit):
        employee = people.create_employee("Ahmed", "a@example.com")
        people.deactivate_employee(employee.id)
        before = audit.count()
        people.deactivate_employee(employee.id)
        assert audit.count() == before

    def test_deactivation_is_audited(self, people, audit):
        employee = people.create_employee("Ahmed", "a@example.com")
        people.deactivate_employee(employee.id)
        assert audit.history(event_types.ENTITY_EMPLOYEE, employee.id)[-1].event_type == (
            event_types.EMPLOYEE_DEACTIVATED
        )

    def test_listing_can_exclude_inactive(self, people):
        active = people.create_employee("Ahmed", "a@example.com")
        inactive = people.create_employee("Mona", "m@example.com")
        people.deactivate_employee(inactive.id)
        listed = [employee.id for employee in people.list_employees(active_only=True)]
        assert listed == [active.id]


class TestRoles:
    def test_create_and_list(self, people):
        people.create_role("Managers", "Department heads")
        people.create_role("Developers")
        assert [role.name for role in people.list_roles()] == ["Developers", "Managers"]

    def test_duplicate_role_name_is_rejected(self, people):
        people.create_role("Managers")
        with pytest.raises(ConflictError):
            people.create_role("  managers ")

    def test_update_role(self, people):
        role = people.create_role("Managers")
        assert people.update_role(role.id, description="Heads").description == "Heads"

    def test_delete_role(self, people):
        role = people.create_role("Managers")
        people.delete_role(role.id)
        with pytest.raises(NotFoundError):
            people.get_role(role.id)

    def test_assign_and_remove(self, people):
        employee = people.create_employee("Ahmed", "a@example.com")
        role = people.create_role("Managers")
        assert people.assign_role(employee.id, role.id) is True
        assert people.assign_role(employee.id, role.id) is False  # already assigned
        assert [r.name for r in people.roles_for_employee(employee.id)] == ["Managers"]
        assert people.remove_role(employee.id, role.id) is True
        assert people.remove_role(employee.id, role.id) is False

    def test_assign_to_missing_employee_raises(self, people):
        role = people.create_role("Managers")
        with pytest.raises(NotFoundError):
            people.assign_role(999, role.id)

    def test_assign_missing_role_raises(self, people):
        employee = people.create_employee("Ahmed", "a@example.com")
        with pytest.raises(NotFoundError):
            people.assign_role(employee.id, 999)

    def test_set_roles_replaces_the_whole_set(self, people):
        employee = people.create_employee("Ahmed", "a@example.com")
        managers = people.create_role("Managers")
        developers = people.create_role("Developers")
        qa = people.create_role("QA")
        people.set_roles(employee.id, [managers.id, developers.id])
        result = people.set_roles(employee.id, [developers.id, qa.id])
        assert sorted(role.name for role in result) == ["Developers", "QA"]

    def test_role_members_excludes_inactive_by_default(self, people):
        role = people.create_role("Managers")
        active = people.create_employee("Ahmed", "a@example.com", role_ids=[role.id])
        inactive = people.create_employee("Mona", "m@example.com", role_ids=[role.id])
        people.deactivate_employee(inactive.id)
        assert [e.id for e in people.role_members(role.id)] == [active.id]
        assert len(people.role_members(role.id, active_only=False)) == 2

    def test_deleting_a_role_removes_its_assignments(self, people):
        role = people.create_role("Managers")
        employee = people.create_employee("Ahmed", "a@example.com", role_ids=[role.id])
        people.delete_role(role.id)
        assert people.roles_for_employee(employee.id) == []

    def test_role_assignment_is_audited(self, people, audit):
        employee = people.create_employee("Ahmed", "a@example.com")
        role = people.create_role("Managers")
        people.assign_role(employee.id, role.id)
        events = [e.event_type for e in audit.history(event_types.ENTITY_EMPLOYEE, employee.id)]
        assert event_types.ROLE_ASSIGNED in events
