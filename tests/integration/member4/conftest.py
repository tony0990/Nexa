"""Fixtures for Member 4's integration tests.

"Integration" here means the whole Member 4 stack composed together — report
rendering, MIME, personalization, preview and sending — plus the seam where
Member 1's `DeliveryRepository` persists the results. Still no network: the
Gmail transport is faked at the `EmailSender` protocol, which is the only thing
that would reach out.
"""

from __future__ import annotations

import pytest

from nexa.core.clock import FixedClock
from nexa.email import EmailService, FakeEmailSender, MemoryTokenStore
from nexa.reports import ReportService

from tests.fixtures import member4 as data


@pytest.fixture
def m4_clock() -> FixedClock:
    return FixedClock(data.REFERENCE_MOMENT)


@pytest.fixture
def fake_sender() -> FakeEmailSender:
    return FakeEmailSender(from_email="nexa.test@example.com", from_name="Nexa")


@pytest.fixture
def recorded() -> list:
    """Collects every `DeliveryAttempt` the service hands back."""
    return []


@pytest.fixture
def emails(fake_sender, m4_clock, recorded) -> EmailService:
    return EmailService(
        sender=fake_sender,
        reports=ReportService(clock=m4_clock),
        clock=m4_clock,
        from_email="nexa.test@example.com",
        delivery_sink=recorded.append,
    )


@pytest.fixture
def token_store() -> MemoryTokenStore:
    return MemoryTokenStore()
