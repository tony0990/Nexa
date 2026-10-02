"""OAuth token storage, backed by Windows Credential Manager.

Section 38 is unambiguous: OAuth tokens are never stored as plain text in a
config file, and no Gmail password is stored at all. So the refresh token goes
through `keyring`, which on Windows is the Credential Manager.

Three stores share one interface:

* `KeyringTokenStore` — the real one, used by the application.
* `MemoryTokenStore` — tests and the `FakeEmailSender`. Nothing touches disk.
* `NullTokenStore` — "no credential backend here", so the UI can report
  "Gmail cannot be connected on this machine" instead of crashing.

`__repr__` is overridden on every store and the token value is never put in a
message or an exception, because Section 38 also requires that logs and crash
reports never contain a token.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Optional

from .errors import EmailDependencyError

SERVICE_NAME = "Nexa.Gmail"
DEFAULT_ACCOUNT = "default"


@dataclass
class StoredCredentials:
    """The refresh-token material needed to rebuild a Gmail session.

    `token` (the short-lived access token) is optional: it expires in an hour,
    so it is a cache, not the credential. `refresh_token` is the secret worth
    protecting.
    """

    refresh_token: str = ""
    client_id: str = ""
    client_secret: str = ""
    token_uri: str = "https://oauth2.googleapis.com/token"
    scopes: tuple = ()
    token: Optional[str] = None
    account_email: Optional[str] = None

    def is_complete(self) -> bool:
        return bool(self.refresh_token and self.client_id and self.client_secret)

    def to_json(self) -> str:
        return json.dumps(
            {
                "refresh_token": self.refresh_token,
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "token_uri": self.token_uri,
                "scopes": list(self.scopes),
                "token": self.token,
                "account_email": self.account_email,
            },
            ensure_ascii=False,
        )

    @classmethod
    def from_json(cls, raw: str) -> "StoredCredentials":
        data = json.loads(raw)
        return cls(
            refresh_token=data.get("refresh_token") or "",
            client_id=data.get("client_id") or "",
            client_secret=data.get("client_secret") or "",
            token_uri=data.get("token_uri") or "https://oauth2.googleapis.com/token",
            scopes=tuple(data.get("scopes") or ()),
            token=data.get("token"),
            account_email=data.get("account_email"),
        )

    def __repr__(self) -> str:
        """Never prints secret material (Section 38)."""
        return (
            f"StoredCredentials(account_email={self.account_email!r}, "
            f"scopes={list(self.scopes)!r}, refresh_token=<redacted>, "
            f"client_secret=<redacted>)"
        )

    __str__ = __repr__


class KeyringTokenStore:
    """Stores credentials in the OS credential vault via `keyring`."""

    def __init__(self, service_name: str = SERVICE_NAME, account: str = DEFAULT_ACCOUNT):
        self.service_name = service_name
        self.account = account

    def _keyring(self):
        try:
            import keyring
        except ImportError as exc:  # pragma: no cover - depends on install
            raise EmailDependencyError(
                "keyring is not installed, so Gmail credentials cannot be stored "
                "securely. Install requirements/base.txt."
            ) from exc
        return keyring

    def load(self) -> Optional[StoredCredentials]:
        raw = self._keyring().get_password(self.service_name, self.account)
        if not raw:
            return None
        try:
            return StoredCredentials.from_json(raw)
        except (ValueError, TypeError):
            # A corrupt entry is treated as "not connected" rather than raising:
            # the admin can reconnect, and the alternative is an app that will
            # not start.
            return None

    def save(self, credentials: StoredCredentials) -> None:
        self._keyring().set_password(
            self.service_name, self.account, credentials.to_json()
        )

    def delete(self) -> None:
        keyring = self._keyring()
        try:
            keyring.delete_password(self.service_name, self.account)
        except Exception:
            # keyring raises PasswordDeleteError when there is nothing stored.
            # Disconnecting an account that is already disconnected is a no-op,
            # not an error.
            pass

    def is_available(self) -> bool:
        """True when a usable credential backend exists on this machine."""
        try:
            keyring = self._keyring()
        except EmailDependencyError:
            return False
        try:
            from keyring.backends.fail import Keyring as FailKeyring

            return not isinstance(keyring.get_keyring(), FailKeyring)
        except Exception:  # pragma: no cover - backend probing is best-effort
            return True

    def __repr__(self) -> str:
        return f"KeyringTokenStore(service_name={self.service_name!r})"


@dataclass
class MemoryTokenStore:
    """In-process store for tests and the fake sender. Never touches disk."""

    credentials: Optional[StoredCredentials] = field(default=None)

    def load(self) -> Optional[StoredCredentials]:
        return self.credentials

    def save(self, credentials: StoredCredentials) -> None:
        self.credentials = credentials

    def delete(self) -> None:
        self.credentials = None

    def is_available(self) -> bool:
        return True

    def __repr__(self) -> str:
        state = "connected" if self.credentials else "empty"
        return f"MemoryTokenStore({state})"


class NullTokenStore:
    """No credential backend. Every load is empty and every save is refused."""

    def load(self) -> Optional[StoredCredentials]:
        return None

    def save(self, credentials: StoredCredentials) -> None:
        raise EmailDependencyError(
            "No credential store is available on this machine, so Gmail "
            "credentials cannot be saved."
        )

    def delete(self) -> None:
        return None

    def is_available(self) -> bool:
        return False

    def __repr__(self) -> str:
        return "NullTokenStore()"


def default_token_store(account: str = DEFAULT_ACCOUNT):
    """The keyring store when one works here, otherwise the null store."""
    store = KeyringTokenStore(account=account)
    return store if store.is_available() else NullTokenStore()
