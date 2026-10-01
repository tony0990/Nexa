"""M0 fixture corpus integrity checks."""

from __future__ import annotations

import pytest

from tests.conftest import FIXTURE_CATEGORIES, FIXTURES_ROOT, iter_category_fixtures

MIN_FIXTURES_PER_CATEGORY = 4


@pytest.mark.m0
@pytest.mark.parametrize("category", FIXTURE_CATEGORIES)
def test_fixture_category_exists_with_minimum_count(category: str) -> None:
    category_dir = FIXTURES_ROOT / category
    assert category_dir.is_dir(), f"Missing fixture directory: {category_dir}"
    fixtures = list(iter_category_fixtures(category))
    assert len(fixtures) >= MIN_FIXTURES_PER_CATEGORY, (
        f"{category}: expected >={MIN_FIXTURES_PER_CATEGORY} fixtures, got {len(fixtures)}"
    )


@pytest.mark.m0
@pytest.mark.parametrize("category", FIXTURE_CATEGORIES)
def test_fixture_required_fields(category: str) -> None:
    for fixture in iter_category_fixtures(category):
        assert "fixture_id" in fixture
        assert "reference_datetime" in fixture
        if category == "near_duplicate_pairs":
            assert "segment_a" in fixture
            assert "segment_b" in fixture
            assert "candidate_a" in fixture
            assert "candidate_b" in fixture
            assert "expected_decision" in fixture
        else:
            assert "segment_text" in fixture
            assert "expected" in fixture
            assert "items" in fixture["expected"]


@pytest.mark.m0
def test_zero_action_fixtures_expect_empty_items() -> None:
    for fixture in iter_category_fixtures("zero_action"):
        assert fixture["expected"]["items"] == [], (
            f"{fixture['fixture_id']} must expect empty items (precision guardrail)"
        )
