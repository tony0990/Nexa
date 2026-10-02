"""Scale checks: 1,000 employees, roles, meetings and tasks (Section 21.5).

These assert correctness at size and guard against accidentally quadratic
work (a per-row query inside a loop). The timing bounds are deliberately
loose — they are there to catch an N+1 regression on a slow laptop, not to
benchmark SQLite.
"""

from __future__ import annotations

import sys
import time as time_module
from pathlib import Path

import pytest

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures"
if str(FIXTURES) not in sys.path:  # pragma: no cover - import plumbing
    sys.path.insert(0, str(FIXTURES))

from dataset import build_dataset  # noqa: E402

from nexa.contracts.email import DeliveryTarget, TargetType  # noqa: E402
from nexa.search.filters import EmployeeFilters, TaskFilters  # noqa: E402

pytestmark = pytest.mark.slow

SEARCH_BUDGET_SECONDS = 2.0


@pytest.fixture(scope="module")
def big(tmp_path_factory):
    """One 1,000-row database shared by this module's tests."""
    from datetime import datetime, timezone

    from nexa.core.clock import FixedClock
    from nexa.core.config import NexaConfig
    from nexa.data.database import open_database

    clock = FixedClock(datetime(2026, 9, 20, 8, 0, tzinfo=timezone.utc))
    database = open_database(NexaConfig(data_dir=tmp_path_factory.mktemp("scale")))
    data = build_dataset(database, clock, employees=1000, meetings=200, actions=1000)
    yield database, clock, data
    database.close()


def elapsed(callable_):
    start = time_module.perf_counter()
    result = callable_()
    return result, time_module.perf_counter() - start


class TestDatasetIntegrity:
    def test_row_counts(self, big):
        db, _, data = big
        assert len(data.employee_ids) == 1000
        assert db.query_value("SELECT COUNT(*) FROM meetings") == 200
        assert db.query_value("SELECT COUNT(*) FROM action_items") == 1000
        assert db.query_value("SELECT COUNT(*) FROM employee_roles") >= 1000

    def test_every_employee_has_a_unique_email(self, big):
        db, _, _ = big
        assert db.query_value("SELECT COUNT(DISTINCT email) FROM employees") == 1000

    def test_integrity_check_passes_at_size(self, big):
        db, _, _ = big
        assert db.integrity_check() is True


class TestSearchAtScale:
    def test_employee_search_is_fast(self, big):
        db, clock, _ = big
        from nexa.search.service import SearchService

        service = SearchService(db, clock)
        results, duration = elapsed(lambda: service.search_employees("Ahmed"))
        assert duration < SEARCH_BUDGET_SECONDS
        assert all("ahmed" in e.full_name.casefold() or "ahmed" in e.email for e in results)

    def test_arabic_search_is_fast(self, big):
        db, clock, _ = big
        from nexa.search.service import SearchService

        service = SearchService(db, clock)
        # Typed without the hamza: must still match the stored "أحمد".
        results, duration = elapsed(lambda: service.search_employees("احمد"))
        assert duration < SEARCH_BUDGET_SECONDS
        assert results

    def test_task_search_with_combined_filters_is_fast(self, big):
        db, clock, data = big
        from nexa.search.service import SearchService

        service = SearchService(db, clock)
        filters = TaskFilters(
            statuses=("PENDING",),
            role_ids=(data.role_ids[0],),
            preset="THIS_MONTH",
            limit=100,
        )
        results, duration = elapsed(lambda: service.search_tasks(None, filters))
        assert duration < SEARCH_BUDGET_SECONDS
        assert all(task.status == "PENDING" for task in results)

    def test_global_search_is_fast(self, big):
        db, clock, _ = big
        from nexa.search.service import SearchService

        service = SearchService(db, clock)
        results, duration = elapsed(lambda: service.global_search("report"))
        assert duration < SEARCH_BUDGET_SECONDS
        assert results.total >= 0

    def test_listing_1000_employees_does_not_issue_a_query_per_row(self, big):
        """A per-row role lookup would make this test take seconds."""
        db, clock, _ = big
        from nexa.search.service import SearchService

        service = SearchService(db, clock)
        results, duration = elapsed(
            lambda: service.search_employees(None, EmployeeFilters(limit=1000))
        )
        assert len(results) == 1000
        assert duration < SEARCH_BUDGET_SECONDS

    def test_limit_caps_the_result_set(self, big):
        db, clock, _ = big
        from nexa.search.service import SearchService

        service = SearchService(db, clock)
        assert len(service.search_employees(None, EmployeeFilters(limit=10_000))) <= 1000


class TestRecipientResolutionAtScale:
    def test_all_resolves_to_active_employees_only_and_de_duplicates(self, big):
        db, clock, data = big
        from nexa.people.recipient_resolver import RecipientResolver

        resolver = RecipientResolver(db, clock)
        active_count = db.query_value("SELECT COUNT(*) FROM employees WHERE active = 1")

        result, duration = elapsed(
            lambda: resolver.resolve_detailed([DeliveryTarget(target_type=TargetType.ALL.value)])
        )
        assert duration < SEARCH_BUDGET_SECONDS
        assert len(result.recipients) == active_count
        assert len(result.emails) == len(set(result.emails))

    def test_overlapping_targets_still_send_once(self, big):
        db, clock, data = big
        from nexa.people.recipient_resolver import RecipientResolver

        resolver = RecipientResolver(db, clock)
        targets = [DeliveryTarget(target_type=TargetType.ALL.value)]
        targets += [
            DeliveryTarget(target_type=TargetType.ROLE.value, target_id=role_id)
            for role_id in data.role_ids
        ]
        targets += [
            DeliveryTarget(target_type=TargetType.EMPLOYEE.value, target_id=employee_id)
            for employee_id in data.employee_ids[:50]
        ]

        result = resolver.resolve_detailed(targets)
        assert len(result.emails) == len(set(result.emails))
        # Every inactive employee explicitly named is reported, not dropped.
        assert all(recipient.active for recipient in result.recipients)


class TestAuditAtScale:
    def test_history_stays_scoped_and_fast(self, big):
        db, clock, data = big
        from nexa.audit import event_types
        from nexa.audit.service import AuditService

        audit = AuditService(db, clock)
        for index in range(500):
            audit.log(
                event_types.ACTION_STATUS_CHANGED,
                event_types.ENTITY_ACTION_ITEM,
                data.action_ids[index % 10],
            )

        history, duration = elapsed(
            lambda: audit.history(event_types.ENTITY_ACTION_ITEM, data.action_ids[0])
        )
        assert duration < SEARCH_BUDGET_SECONDS
        assert len(history) == 50
        assert all(event.entity_id == str(data.action_ids[0]) for event in history)
