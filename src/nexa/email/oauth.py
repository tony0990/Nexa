"""Desktop OAuth flow for Gmail (Section 24.1).

Scope is `gmail.send` and nothing else. That is the least-privilege scope that
can do Nexa's job (Section 38): it permits sending and grants no ability to
read, search or delete the admin's mail. Widening it would make the consent
screen scarier and the breach surface larger for no feature.

The flow is the installed-application flow: `InstalledAppFlow.run_local_server`
opens the system browser, Google redirects to a one-shot localhost listener, and
the authorization code never leaves the machine. There is no client-side secret
worth protecting in a desktop app, which is why this flow exists and why a
refresh token, not a password, is what gets stored (Section 38 again).

Every google import is lazy, so `nexa.email` imports and renders on a machine
with no Google libraries installed.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Sequence

from .errors import EmailDependencyError, GmailAuthError, GmailNotConfiguredError
from .token_store import StoredCredentials

# Least privilege: send only.
GMAIL_SEND_SCOPE = "https://www.googleapis.com/auth/gmail.send"
SCOPES: tuple = (GMAIL_SEND_SCOPE,)

CLIENT_SECRETS_FILENAME = "gmail_client_secret.json"


@dataclass(frozen=True)
class OAuthClient:
    """The Google OAuth client this installation was issued.

    Shipped with the application or dropped into the data directory by the
    admin. Not a secret in the usual sense for an installed app, but still kept
    out of source control.
    """

    client_id: str
    client_secret: str
    token_uri: str = "https://oauth2.googleapis.com/token"
    auth_uri: str = "https://accounts.google.com/o/oauth2/auth"

    @classmethod
    def from_file(cls, path: Path) -> "OAuthClient":
        """Read a Google Cloud "Desktop app" client secrets JSON file."""
        path = Path(path)
        if not path.is_file():
            raise GmailNotConfiguredError(
                f"No Gmail OAuth client file at {path}. Add the Google Cloud "
                "desktop client secrets before connecting Gmail."
            )
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except ValueError as exc:
            raise GmailNotConfiguredError(
                f"The Gmail OAuth client file at {path} is not valid JSON."
            ) from exc
        block = data.get("installed") or data.get("web") or data
        client_id = block.get("client_id")
        client_secret = block.get("client_secret")
        if not client_id or not client_secret:
            raise GmailNotConfiguredError(
                f"The Gmail OAuth client file at {path} has no client_id/"
                "client_secret."
            )
        return cls(
            client_id=client_id,
            client_secret=client_secret,
            token_uri=block.get("token_uri") or cls.token_uri,
            auth_uri=block.get("auth_uri") or cls.auth_uri,
        )

    def to_flow_config(self) -> dict:
        return {
            "installed": {
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "auth_uri": self.auth_uri,
                "token_uri": self.token_uri,
                "redirect_uris": ["http://localhost"],
            }
        }

    def __repr__(self) -> str:
        """Never prints the client secret (Section 38)."""
        return f"OAuthClient(client_id={self.client_id!r}, client_secret=<redacted>)"


def default_client_secrets_path(data_dir: Optional[Path] = None) -> Path:
    """Where the client secrets file is looked for."""
    if data_dir is not None:
        return Path(data_dir) / CLIENT_SECRETS_FILENAME
    from ..core.config import default_data_dir

    return default_data_dir() / CLIENT_SECRETS_FILENAME


class GmailOAuthFlow:
    """Runs the desktop consent flow and refreshes access tokens."""

    def __init__(self, client: OAuthClient, scopes: Sequence[str] = SCOPES):
        self.client = client
        self.scopes = tuple(scopes)

    def authorize(self, port: int = 0) -> StoredCredentials:
        """Open the browser, get consent, and return storable credentials.

        `access_type=offline` plus `prompt=consent` is what makes Google return
        a refresh token. Without them a re-authorization returns only an access
        token, the stored credential has nothing to refresh with, and Nexa
        silently stops sending an hour later.

        `port=0` lets the OS pick a free localhost port, so the flow does not
        fail when something already holds a hard-coded one.
        """
        try:
            from google_auth_oauthlib.flow import InstalledAppFlow
        except ImportError as exc:
            raise EmailDependencyError(
                "google-auth-oauthlib is not installed, so Gmail cannot be "
                "connected. Install requirements/base.txt."
            ) from exc

        flow = InstalledAppFlow.from_client_config(
            self.client.to_flow_config(), scopes=list(self.scopes)
        )
        credentials = flow.run_local_server(
            port=port,
            access_type="offline",
            prompt="consent",
            open_browser=True,
        )
        if not getattr(credentials, "refresh_token", None):
            raise GmailAuthError(
                "Google did not return a refresh token. Remove Nexa's access in "
                "your Google account and connect again."
            )
        return StoredCredentials(
            refresh_token=credentials.refresh_token,
            client_id=self.client.client_id,
            client_secret=self.client.client_secret,
            token_uri=self.client.token_uri,
            scopes=self.scopes,
            token=getattr(credentials, "token", None),
        )

    def build_credentials(self, stored: StoredCredentials):
        """Rebuild a live `Credentials` object from stored material.

        Refreshing is left to the Google library, which does it transparently on
        the first API call when the access token is stale.
        """
        try:
            from google.oauth2.credentials import Credentials
        except ImportError as exc:
            raise EmailDependencyError(
                "google-auth is not installed, so Gmail cannot be used. "
                "Install requirements/base.txt."
            ) from exc
        if not stored.is_complete():
            raise GmailAuthError(
                "Gmail is not connected. Connect an account in Settings."
            )
        return Credentials(
            token=stored.token,
            refresh_token=stored.refresh_token,
            token_uri=stored.token_uri,
            client_id=stored.client_id,
            client_secret=stored.client_secret,
            scopes=list(stored.scopes or SCOPES),
        )

    def refresh(self, stored: StoredCredentials) -> StoredCredentials:
        """Force a refresh now, returning credentials with a fresh access token.

        A revoked or expired grant surfaces here as `GmailAuthError`, which is
        permanent — Section 24.6's "invalid/revoked credentials produce a clear
        error". The underlying `RefreshError` message is included because it
        distinguishes "revoked" from "clock skew", and it contains no token.
        """
        credentials = self.build_credentials(stored)
        try:
            from google.auth.transport.requests import Request
        except ImportError as exc:
            raise EmailDependencyError(
                "google-auth's requests transport is not installed."
            ) from exc
        try:
            credentials.refresh(Request())
        except Exception as exc:
            raise GmailAuthError(
                f"Gmail credentials could not be refreshed: {exc}. "
                "Reconnect the Gmail account in Settings."
            ) from exc
        return StoredCredentials(
            refresh_token=stored.refresh_token,
            client_id=stored.client_id,
            client_secret=stored.client_secret,
            token_uri=stored.token_uri,
            scopes=stored.scopes or SCOPES,
            token=credentials.token,
            account_email=stored.account_email,
        )
