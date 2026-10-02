"""Shared fixtures for every member's tests.

Both halves of this file were lost when Member 3's branch was merged into
`main` (the conflict was resolved by emptying the file, which left every
Member 1 test unable to import `nexa`). They are restored here as the union
they should have been: Member 1's database/service fixtures and Member 3's
transcript-corpus fixtures do not overlap.

Every test gets its own database file in a temporary folder, which also
exercises the "schema can be created from an empty folder" requirement on
every single run.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

import pytest

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:  # pragma: no cover - import plumbing
    sys.path.insert(0, str(SRC))

from nexa.audit.service import Actor, AuditService  # noqa: E402
from nexa.core.clock import FixedClock  # noqa: E402
from nexa.core.config import NexaConfig  # noqa: E402
from nexa.data.database import open_database  # noqa: E402
from nexa.people.recipient_resolver import RecipientResolver  # noqa: E402
from nexa.people.service import PeopleService  # noqa: E402
from nexa.search.service import SearchService  # noqa: E402

# Sunday 20 September 2026, 10:00 Cairo (08:00 UTC). Sunday is chosen so the
# week-boundary tests are unambiguous under an Egyptian working week.
REFERENCE_MOMENT = datetime(2026, 9, 20, 8, 0, tzinfo=timezone.utc)


# --------------------------------------------------------------- Member 1
@pytest.fixture
def clock() -> FixedClock:
    return FixedClock(REFERENCE_MOMENT)


@pytest.fixture
def config(tmp_path: Path) -> NexaConfig:
    return NexaConfig(data_dir=tmp_path / "data")


@pytest.fixture
def db(config: NexaConfig):
    database = open_database(config)
    yield database
    database.close()


@pytest.fixture
def audit(db, clock) -> AuditService:
    return AuditService(db, clock, default_actor=Actor.user("admin"))


@pytest.fixture
def people(db, clock, audit) -> PeopleService:
    return PeopleService(db, clock, audit, actor=Actor.user("admin"))


@pytest.fixture
def resolver(db, clock) -> RecipientResolver:
    return RecipientResolver(db, clock)


@pytest.fixture
def search(db, clock) -> SearchService:
    return SearchService(db, clock)


# --------------------------------------------------------------- Member 3
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
