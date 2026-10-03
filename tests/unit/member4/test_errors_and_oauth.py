"""Error classification, token storage and the OAuth surface.

The retryable/permanent split is Member 5's retry contract, so it is asserted
case by case. The security requirements in Section 38 — no plain-text tokens, no
tokens in logs — are asserted too, because "we were careful" is not a test.
"""

from __future__ import annotations

import json

import pytest

from nexa.email import (
    EmailDependencyError,
    GmailAuthError,
    GmailNotConfiguredError,
    MemoryTokenStore,
    NullTokenStore,
    OAuthClient,
    SCOPES,
    StoredCredentials,
    classify_status,
    from_http_error,
)
from nexa.email.errors import PermanentEmailError, TransientEmailError
from nexa.email.oauth import GMAIL_SEND_SCOPE


class FakeResponse:
    def __init__(self, status: int):
        self.status = status


class FakeHttpError(Exception):
    """Shaped like `googleapiclient.errors.HttpError`."""

    def __init__(self, status: int, reason: str = "", message: str = "boom"):
        super().__init__(message)
        self.resp = FakeResponse(status)
        self.content = json.dumps(
            {"error": {"code": status, "message": message,
                       "errors": [{"reason": reason, "message": message}]}}
        ).encode()


# -------------------------------------------------------------------- scopes
def test_scope_is_send_only():
    """Least privilege (Section 38): Nexa can send and cannot read mail."""
    assert SCOPES == (GMAIL_SEND_SCOPE,)
    assert GMAIL_SEND_SCOPE.endswith("/auth/gmail.send")
    assert "readonly" not in GMAIL_SEND_SCOPE
    assert "mail.google.com" not in GMAIL_SEND_SCOPE


# ------------------------------------------------------------ classification
@pytest.mark.parametrize("status", [408, 429, 500, 502, 503, 504])
def test_transient_statuses_retry(status):
    assert classify_status(status) is True


@pytest.mark.parametrize("status", [400, 401, 404, 413, 422])
def test_permanent_statuses_do_not_retry(status):
    assert classify_status(status) is False


def test_403_is_split_by_reason():
    """Gmail uses 403 for both "slow down" and "not permitted"."""
    assert classify_status(403, "rateLimitExceeded") is True
    assert classify_status(403, "userRateLimitExceeded") is True
    assert classify_status(403, "insufficientPermissions") is False


def test_unknown_failure_defaults_to_retryable():
    """A dropped reminder is unrecoverable; a retried one is not."""
    assert classify_status(None) is True
    assert classify_status(599) is True


@pytest.mark.parametrize(
    "status,reason,expected",
    [
        (429, "rateLimitExceeded", TransientEmailError),
        (503, "backendError", TransientEmailError),
        (401, "authError", GmailAuthError),
        (403, "insufficientPermissions", GmailAuthError),
        (403, "rateLimitExceeded", TransientEmailError),
        (400, "invalidArgument", PermanentEmailError),
    ],
)
def test_http_errors_map_to_the_taxonomy(status, reason, expected):
    assert isinstance(from_http_error(FakeHttpError(status, reason)), expected)


def test_revoked_grant_is_permanent_and_says_so():
    """Section 24.6: revoked credentials give a clear error, not a retry loop."""
    error = from_http_error(
        FakeHttpError(400, "invalid_grant", "Token has been expired or revoked.")
    )
    assert isinstance(error, GmailAuthError)
    assert error.retryable is False
    assert "revoked" in str(error).lower()


def test_no_internet_is_retryable():
    """A socket error has no HTTP status at all (Section 39.3, "no internet")."""
    error = from_http_error(OSError("[Errno 11001] getaddrinfo failed"))
    assert error.retryable is True


def test_retryable_flag_is_on_the_class():
    assert TransientEmailError("x").retryable is True
    assert PermanentEmailError("x").retryable is False
    assert GmailAuthError("x").retryable is False
    assert EmailDependencyError("x").retryable is False


# --------------------------------------------------------------- token store
def test_memory_store_round_trip(token_store):
    credentials = StoredCredentials(
        refresh_token="r", client_id="c", client_secret="s",
        scopes=SCOPES, account_email="admin@example.com",
    )
    token_store.save(credentials)
    assert token_store.load().account_email == "admin@example.com"
    token_store.delete()
    assert token_store.load() is None


def test_credentials_json_round_trip():
    original = StoredCredentials(
        refresh_token="r", client_id="c", client_secret="s", scopes=SCOPES
    )
    assert StoredCredentials.from_json(original.to_json()) == original


def test_incomplete_credentials_are_not_usable():
    assert StoredCredentials().is_complete() is False
    assert StoredCredentials(refresh_token="r").is_complete() is False
    assert StoredCredentials(
        refresh_token="r", client_id="c", client_secret="s"
    ).is_complete() is True


def test_repr_never_leaks_secret_material():
    """Section 38: logs and crash reports must not contain tokens."""
    credentials = StoredCredentials(
        refresh_token="SECRET-REFRESH", client_id="c",
        client_secret="SECRET-CLIENT", token="SECRET-ACCESS",
    )
    for rendering in (repr(credentials), str(credentials), f"{credentials}"):
        assert "SECRET-REFRESH" not in rendering
        assert "SECRET-CLIENT" not in rendering
        assert "<redacted>" in rendering


def test_oauth_client_repr_never_leaks_the_secret():
    client = OAuthClient(client_id="id", client_secret="SECRET")
    assert "SECRET" not in repr(client)
    assert "<redacted>" in repr(client)


def test_null_store_refuses_to_save():
    store = NullTokenStore()
    assert store.is_available() is False
    assert store.load() is None
    with pytest.raises(EmailDependencyError):
        store.save(StoredCredentials(refresh_token="r", client_id="c", client_secret="s"))


def test_memory_store_repr_is_a_state_not_a_token():
    store = MemoryTokenStore()
    assert repr(store) == "MemoryTokenStore(empty)"
    store.save(StoredCredentials(refresh_token="SECRET", client_id="c", client_secret="s"))
    assert "SECRET" not in repr(store)


# --------------------------------------------------------- client secrets file
def test_client_secrets_are_read_from_an_installed_app_file(tmp_path):
    path = tmp_path / "client.json"
    path.write_text(
        json.dumps(
            {"installed": {"client_id": "abc.apps.googleusercontent.com",
                           "client_secret": "shh",
                           "token_uri": "https://oauth2.googleapis.com/token"}}
        ),
        encoding="utf-8",
    )
    client = OAuthClient.from_file(path)
    assert client.client_id == "abc.apps.googleusercontent.com"
    assert client.to_flow_config()["installed"]["client_id"] == client.client_id


def test_missing_client_secrets_file_is_a_clear_error(tmp_path):
    with pytest.raises(GmailNotConfiguredError) as caught:
        OAuthClient.from_file(tmp_path / "nope.json")
    assert "OAuth client file" in str(caught.value)


def test_malformed_client_secrets_file_is_a_clear_error(tmp_path):
    path = tmp_path / "client.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(GmailNotConfiguredError):
        OAuthClient.from_file(path)


def test_client_secrets_without_an_id_is_rejected(tmp_path):
    path = tmp_path / "client.json"
    path.write_text(json.dumps({"installed": {"client_secret": "shh"}}), encoding="utf-8")
    with pytest.raises(GmailNotConfiguredError):
        OAuthClient.from_file(path)
