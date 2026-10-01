"""Shared pytest fixtures for transcript corpus loading."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterator

import pytest

FIXTURES_ROOT = Path(__file__).parent / "fixtures" / "transcripts"

FIXTURE_CATEGORIES = (
    "arabic_only",
    "english_only",
    "mixed_codeswitch",
    "multi_action_single_segment",
    "zero_action",
    "ambiguous_date",
    "ambiguous_owner_duplicate_names",
    "missing_owner",
    "missing_time",
    "near_duplicate_pairs",
)


def _load_json_fixtures(category: str) -> list[dict[str, Any]]:
    category_dir = FIXTURES_ROOT / category
    if not category_dir.is_dir():
        return []
    fixtures: list[dict[str, Any]] = []
    for path in sorted(category_dir.glob("*.json")):
        with path.open(encoding="utf-8") as handle:
            data = json.load(handle)
        data["_path"] = str(path)
        fixtures.append(data)
    return fixtures


@pytest.fixture(params=FIXTURE_CATEGORIES)
def fixture_category(request: pytest.FixtureRequest) -> str:
    return request.param


def iter_category_fixtures(category: str) -> Iterator[dict[str, Any]]:
    yield from _load_json_fixtures(category)


@pytest.fixture
def all_transcript_fixtures() -> dict[str, list[dict[str, Any]]]:
    return {category: _load_json_fixtures(category) for category in FIXTURE_CATEGORIES}
