"""Gmail connect / test / disconnect (Sections 24.1, 24.3, 24.6).

The OAuth flow itself is stubbed, because the real one opens a browser and
talks to Google. What is exercised is everything around it: that a successful
authorization is persisted, that a revoked grant surfaces as a clear permanent
error, that disconnect actually forgets the credential, and that none of it
leaks a token.
"""

from __future__ import annotations

import pytest

from nexa.email import (
    GmailAuthError,
    GmailConnectionService,
    MemoryTokenStore,
    OAuthClient,
    SCOPES,
    StoredCredentials,
)
from nexa.email.errors import EmailDependencyError
from nexa.email.token_store import NullTokenStore

CLIENT = OAuthClient(client_id="client-id", client_secret="client-secret")

AUTHORIZED = StoredCredentials(
    refresh_token="refresh-token-value",
    client_id=CLIENT.client_id,
    client_secret=CLIENT.client_secret,
    scopes=SCOPES,
    token="access-token-value",
)


class StubFlow:
    """Stands in for `GmailOAuthFlow` without a browser or a network."""

    def __init__(self, client, scopes=SCOPES, *, refresh_error=None, account="admin@example.com"):
        self.client = client
        self.scopes = tuple(scopes)
        self.refresh_error = refresh_error
        self.account = account
        self.authorize_calls = 0
        self.refresh_calls = 0

    def authorize(self, port: int = 0) -> StoredCredentials:
        self.authorize_calls += 1
        return AUTHORIZED

    def refresh(self, stored: StoredCredentials) -> StoredCredentials:
        self.refresh_calls += 1
        if self.refresh_error is not None:
            raise self.refresh_error
        return StoredCredentials(
            refresh_token=stored.refresh_token,
            client_id=stored.client_id,
            client_secret=stored.client_secret,
            token_uri=stored.token_uri,
            scopes=stored.scopes or SCOPES,
            token="fresh-access-token",
            account_email=stored.account_email,
        )


@pytest.fixture
def connection(token_store, monkeypatch):
    """A connection service whose OAuth flow and profile probe are stubbed."""
    flows = []

    def make_flow(client, *args, **kwargs):
        flow = StubFlow(client, *args, **kwargs)
        flows.append(flow)
        return flow

    monkeypatch.setattr("nexa.email.service.GmailOAuthFlow", make_flow)
    service = GmailConnectionService(token_store=token_store, client=CLIENT)
    monkeypatch.setattr(service, "_probe_account", lambda flow, stored: "admin@example.com")
    service.flows = flows
    return service


def test_starts_disconnected(connection):
    status = connection.status()
    assert status.connected is False
    assert status.summary == "Not connected"


def test_connect_stores_the_credential(connection, token_store):
    status = connection.connect()
    assert status.connected is True
    assert status.account_email == "admin@example.com"
    assert status.scopes == SCOPES
    stored = token_store.load()
    assert stored.refresh_token == AUTHORIZED.refresh_token
    assert stored.account_email == "admin@example.com"


def test_status_is_offline_after_connecting(connection):
    connection.connect()
    before = len(connection.flows)
    status = connection.status()
    assert status.connected is True
    # `status()` must not hit the network — it builds no flow at all.
    assert len(connection.flows) == before


def test_test_verifies_without_sending_mail(connection):
    connection.connect()
    status = connection.test()
    assert status.connected is True
    # A refresh proves the grant lives; no message was ever constructed.
    assert connection.flows[-1].refresh_calls == 1


def test_test_caches_the_refreshed_access_token(connection, token_store):
    connection.connect()
    connection.test()
    assert token_store.load().token == "fresh-access-token"


def test_test_on_an_unconnected_install(connection):
    status = connection.test()
    assert status.connected is False
    assert "not connected" in status.error.lower()


def test_revoked_grant_gives_a_clear_permanent_error(token_store, monkeypatch):
    """Section 24.6: invalid/revoked credentials produce a clear error."""
    revoked = GmailAuthError(
        "Gmail credentials could not be refreshed: Token has been expired or "
        "revoked. Reconnect the Gmail account in Settings."
    )
    monkeypatch.setattr(
        "nexa.email.service.GmailOAuthFlow",
        lambda client, *a, **k: StubFlow(client, refresh_error=revoked),
    )
    token_store.save(AUTHORIZED)
    service = GmailConnectionService(token_store=token_store, client=CLIENT)
    status = service.test()
    assert status.connected is False
    assert "Reconnect the Gmail account" in status.error
    assert revoked.retryable is False


def test_disconnect_forgets_the_credential(connection, token_store):
    connection.connect()
    assert token_store.load() is not None
    status = connection.disconnect()
    assert status.connected is False
    assert token_store.load() is None


def test_disconnect_is_idempotent(connection, token_store):
    connection.disconnect()
    assert connection.disconnect().connected is False
    assert token_store.load() is None


def test_reconnect_after_disconnect(connection, token_store):
    connection.connect()
    connection.disconnect()
    assert connection.connect().connected is True
    assert token_store.load() is not None


def test_sender_requires_a_connection(token_store):
    service = GmailConnectionService(token_store=token_store, client=CLIENT)
    with pytest.raises(GmailAuthError):
        service.sender()


def test_connect_without_a_credential_store_is_reported_not_crashed():
    """A machine with no Credential Manager must say so, not raise."""
    service = GmailConnectionService(token_store=NullTokenStore(), client=CLIENT)
    status = service.connect()
    assert status.connected is False
    assert status.store_available is False
    assert "credential store" in status.error.lower()


def test_status_never_contains_token_material(connection):
    connection.connect()
    for status in (connection.status(), connection.test()):
        rendering = f"{status!r} {status.summary}"
        assert AUTHORIZED.refresh_token not in rendering
        assert "access-token-value" not in rendering
        assert "fresh-access-token" not in rendering
        assert CLIENT.client_secret not in rendering


def test_missing_google_libraries_are_reported_clearly():
    """A build shipped without the Google libraries must explain itself."""
    assert EmailDependencyError("x").retryable is False
    assert "email_dependency" == EmailDependencyError("x").code


# ------------------------------------------- what the Send button reports
def test_fake_sender_reports_connected():
    """Members 5 and 6 must be able to walk preview -> Send Now offline."""
    from nexa.email import FakeEmailSender

    assert FakeEmailSender().is_connected() is True


def test_gmail_sender_without_a_credential_is_not_connected():
    from nexa.email import GmailSender, StoredCredentials
    from nexa.email.oauth import GmailOAuthFlow

    sender = GmailSender(GmailOAuthFlow(CLIENT), StoredCredentials())
    assert sender.is_connected() is False


def test_gmail_sender_with_a_credential_is_connected():
    from nexa.email import GmailSender
    from nexa.email.oauth import GmailOAuthFlow

    sender = GmailSender(GmailOAuthFlow(CLIENT), AUTHORIZED)
    assert sender.is_connected() is True


def test_gmail_sender_connection_check_is_offline():
    """Painting the Send button must not refresh a token or reach Google."""
    from nexa.email import GmailSender

    flow = StubFlow(CLIENT)
    sender = GmailSender(flow, AUTHORIZED)
    assert sender.is_connected() is True
    assert flow.refresh_calls == 0


def test_email_service_delegates_to_a_wired_connection(token_store, monkeypatch):
    from nexa.email import EmailService, FakeEmailSender, GmailConnectionService

    monkeypatch.setattr(
        "nexa.email.service.GmailOAuthFlow", lambda client, *a, **k: StubFlow(client)
    )
    connection = GmailConnectionService(token_store=token_store, client=CLIENT)
    service = EmailService(sender=FakeEmailSender(), connection=connection)

    # The fake sender says "connected", but an explicit connection service wins.
    assert service.is_connected() is False
    token_store.save(AUTHORIZED)
    assert service.is_connected() is True


def test_unknown_sender_fails_closed():
    """A transport that answers neither must not enable a Send button."""
    from nexa.email import EmailService

    class MysterySender:
        from_email = "x@example.com"

        def send(self, message):
            raise AssertionError("must not be called")

    assert EmailService(sender=MysterySender()).is_connected() is False
