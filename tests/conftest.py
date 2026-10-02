"""Shared fixtures for Member 1's tests.

Every test gets its own database file in a temporary folder, which also
exercises the "schema can be created from an empty folder" requirement on
every single run.
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

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
