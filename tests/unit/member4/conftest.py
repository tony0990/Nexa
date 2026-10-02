"""Member 4 fixtures: a clock-pinned report/email stack with no network."""

from __future__ import annotations

import pytest

from nexa.core.clock import FixedClock
from nexa.email import EmailService, FakeEmailSender, MemoryTokenStore
from nexa.reports import ReportService

from tests.fixtures import member4 as data


@pytest.fixture
def m4_clock() -> FixedClock:
    """Pinned so "due tomorrow" is deterministic (Sunday 20 Sep 2026, Cairo)."""
    return FixedClock(data.REFERENCE_MOMENT)


@pytest.fixture
def reports(m4_clock) -> ReportService:
    return ReportService(clock=m4_clock)


@pytest.fixture
def fake_sender() -> FakeEmailSender:
    return FakeEmailSender(from_email="nexa.test@example.com", from_name="Nexa")


@pytest.fixture
def emails(fake_sender, reports, m4_clock) -> EmailService:
    return EmailService(sender=fake_sender, reports=reports, clock=m4_clock)


@pytest.fixture
def token_store() -> MemoryTokenStore:
    return MemoryTokenStore()
