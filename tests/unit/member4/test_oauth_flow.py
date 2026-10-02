"""The real `GmailOAuthFlow` code, with only Google's library faked.

The connection tests stub `GmailOAuthFlow` wholesale, which verifies the
Settings-screen behaviour but leaves `oauth.py`'s own body untested — and that
body holds the details that are easy to get wrong and expensive to discover in
production:

* `access_type="offline"` and `prompt="consent"` are what make Google return a
  refresh token at all. Drop either and the first authorization looks fine,
  then Nexa stops sending an hour later with a credential it cannot refresh.
* `port=0` lets the OS choose, so the flow does not fail when something already
  holds a fixed port.
* A response with no refresh token must be rejected loudly rather than stored.

Faking `InstalledAppFlow` at the library boundary exercises all of that. What is
left unverified is only Google's own server, which no local test can cover.
"""

from __future__ import annotations

import sys
import types

import pytest

from nexa.email import GmailAuthError, OAuthClient, SCOPES, StoredCredentials
from nexa.email.errors import EmailDependencyError
from nexa.email.oauth import GmailOAuthFlow

CLIENT = OAuthClient(client_id="client-id.apps.googleusercontent.com", client_secret="shh")


class FakeGoogleCredentials:
    def __init__(self, refresh_token="refresh-value", token="access-value"):
        self.refresh_token = refresh_token
        self.token = token
        self.refresh_calls = 0
        self.refresh_error = None

    def refresh(self, request):
        self.refresh_calls += 1
        if self.refresh_error is not None:
            raise self.refresh_error
        self.token = "refreshed-access-value"


class FakeInstalledAppFlow:
    """Stands in for `google_auth_oauthlib.flow.InstalledAppFlow`."""

    last = None

    def __init__(self, client_config, scopes, credentials=None):
        self.client_config = client_config
        self.scopes = scopes
        self.run_kwargs = None
        self._credentials = credentials or FakeGoogleCredentials()
        FakeInstalledAppFlow.last = self

    @classmethod
    def from_client_config(cls, client_config, scopes):
        return cls(client_config, scopes)

    def run_local_server(self, **kwargs):
        self.run_kwargs = kwargs
        return self._credentials


@pytest.fixture
def fake_google(monkeypatch):
    """Install fake `google_auth_oauthlib` / `google.auth` / `google.oauth2`.

    The real libraries may or may not be installed on a given machine, so the
    modules are injected into `sys.modules` either way: the test must assert on
    Nexa's code, not on which packages happen to be present.
    """
    flow_module = types.ModuleType("google_auth_oauthlib.flow")
    flow_module.InstalledAppFlow = FakeInstalledAppFlow
    package = types.ModuleType("google_auth_oauthlib")
    package.flow = flow_module
    monkeypatch.setitem(sys.modules, "google_auth_oauthlib", package)
    monkeypatch.setitem(sys.modules, "google_auth_oauthlib.flow", flow_module)

    credentials_module = types.ModuleType("google.oauth2.credentials")
    credentials_module.Credentials = lambda **kwargs: FakeGoogleCredentials(
        refresh_token=kwargs.get("refresh_token"), token=kwargs.get("token")
    )
    monkeypatch.setitem(sys.modules, "google.oauth2.credentials", credentials_module)

    requests_module = types.ModuleType("google.auth.transport.requests")
    requests_module.Request = lambda: object()
    monkeypatch.setitem(sys.modules, "google.auth.transport.requests", requests_module)
    return FakeInstalledAppFlow


# -------------------------------------------------------------- authorize
def test_authorize_requests_offline_access_and_consent(fake_google):
    """Without both, Google returns no refresh token and sending dies in an hour."""
    GmailOAuthFlow(CLIENT).authorize()
    assert fake_google.last.run_kwargs["access_type"] == "offline"
    assert fake_google.last.run_kwargs["prompt"] == "consent"


def test_authorize_lets_the_os_pick_the_port(fake_google):
    GmailOAuthFlow(CLIENT).authorize()
    assert fake_google.last.run_kwargs["port"] == 0


def test_authorize_honours_an_explicit_port(fake_google):
    GmailOAuthFlow(CLIENT).authorize(port=8731)
    assert fake_google.last.run_kwargs["port"] == 8731


def test_authorize_requests_only_the_send_scope(fake_google):
    GmailOAuthFlow(CLIENT).authorize()
    assert fake_google.last.scopes == list(SCOPES)


def test_authorize_passes_the_installed_app_config(fake_google):
    GmailOAuthFlow(CLIENT).authorize()
    installed = fake_google.last.client_config["installed"]
    assert installed["client_id"] == CLIENT.client_id
    assert installed["client_secret"] == CLIENT.client_secret


def test_authorize_returns_storable_credentials(fake_google):
    stored = GmailOAuthFlow(CLIENT).authorize()
    assert stored.refresh_token == "refresh-value"
    assert stored.token == "access-value"
    assert stored.client_id == CLIENT.client_id
    assert stored.scopes == SCOPES
    assert stored.is_complete() is True


def test_authorize_rejects_a_response_with_no_refresh_token(fake_google, monkeypatch):
    """Storing this would leave a credential that cannot be refreshed."""
    monkeypatch.setattr(
        FakeInstalledAppFlow,
        "from_client_config",
        classmethod(
            lambda cls, config, scopes: cls(
                config, scopes, credentials=FakeGoogleCredentials(refresh_token=None)
            )
        ),
    )
    with pytest.raises(GmailAuthError) as caught:
        GmailOAuthFlow(CLIENT).authorize()
    assert "refresh token" in str(caught.value)
    assert "connect again" in str(caught.value)


# ---------------------------------------------------------------- refresh
def test_refresh_returns_a_new_access_token_and_keeps_the_refresh_token(fake_google):
    stored = StoredCredentials(
        refresh_token="keep-me", client_id="c", client_secret="s", scopes=SCOPES,
        account_email="admin@example.com",
    )
    refreshed = GmailOAuthFlow(CLIENT).refresh(stored)
    assert refreshed.token == "refreshed-access-value"
    assert refreshed.refresh_token == "keep-me"
    assert refreshed.account_email == "admin@example.com"


def test_refresh_on_an_incomplete_credential_is_an_auth_error(fake_google):
    with pytest.raises(GmailAuthError) as caught:
        GmailOAuthFlow(CLIENT).refresh(StoredCredentials())
    assert "not connected" in str(caught.value).lower()


def test_refresh_failure_becomes_a_clear_permanent_error(fake_google, monkeypatch):
    """Section 24.6: revoked credentials produce a clear error."""
    credentials_module = sys.modules["google.oauth2.credentials"]

    def revoked(**kwargs):
        fake = FakeGoogleCredentials(refresh_token=kwargs.get("refresh_token"))
        fake.refresh_error = RuntimeError("Token has been expired or revoked.")
        return fake

    monkeypatch.setattr(credentials_module, "Credentials", revoked)
    stored = StoredCredentials(refresh_token="r", client_id="c", client_secret="s")
    with pytest.raises(GmailAuthError) as caught:
        GmailOAuthFlow(CLIENT).refresh(stored)
    message = str(caught.value)
    assert "revoked" in message
    assert "Reconnect the Gmail account in Settings" in message
    assert caught.value.retryable is False


def test_refresh_error_message_carries_no_token_material(fake_google, monkeypatch):
    """Section 38: an error that reaches a log must not contain a token."""
    credentials_module = sys.modules["google.oauth2.credentials"]

    def revoked(**kwargs):
        fake = FakeGoogleCredentials(refresh_token=kwargs.get("refresh_token"))
        fake.refresh_error = RuntimeError("invalid_grant")
        return fake

    monkeypatch.setattr(credentials_module, "Credentials", revoked)
    stored = StoredCredentials(
        refresh_token="SECRET-REFRESH", client_id="c", client_secret="SECRET-CLIENT"
    )
    with pytest.raises(GmailAuthError) as caught:
        GmailOAuthFlow(CLIENT).refresh(stored)
    assert "SECRET-REFRESH" not in str(caught.value)
    assert "SECRET-CLIENT" not in str(caught.value)


# ------------------------------------------------------------- dependencies
def test_missing_oauthlib_is_a_clear_dependency_error(monkeypatch):
    """A build shipped without the Google libraries must explain itself."""
    monkeypatch.setitem(sys.modules, "google_auth_oauthlib.flow", None)
    monkeypatch.setitem(sys.modules, "google_auth_oauthlib", None)
    with pytest.raises(EmailDependencyError) as caught:
        GmailOAuthFlow(CLIENT).authorize()
    assert "google-auth-oauthlib" in str(caught.value)
    assert "requirements/base.txt" in str(caught.value)
