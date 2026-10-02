"""Gmail API transport, plus the fake that stands in for it everywhere else.

`GmailSender` and `FakeEmailSender` both satisfy `EmailSender` from
`nexa.contracts.email`, so Member 5's worker and Member 6's UI are wired to the
protocol and never to Gmail. That is what lets the scheduler's stress tests
(Section 25.5 — 100 reminders in the same second, restart mid-processing) run
without a network or a Google account.

Neither sender raises on a send failure: both return `SendResult(ok=False, ...)`
with the error message, because a failed send is an expected outcome that must
land in a delivery row, not an exception that aborts a worker tick holding a
claimed reminder.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, List, Optional

from ..contracts.email import RenderedEmail, SendResult
from .errors import EmailError, from_http_error
from .mime_builder import build_gmail_payload
from .oauth import GmailOAuthFlow, OAuthClient
from .token_store import StoredCredentials

# The Gmail API's "me" refers to the authenticated account, so Nexa never needs
# to know or store the sending address to send.
AUTHENTICATED_USER = "me"


class GmailSender:
    """Sends through the Gmail API with an OAuth credential."""

    def __init__(
        self,
        flow: GmailOAuthFlow,
        stored: StoredCredentials,
        from_email: Optional[str] = None,
        from_name: Optional[str] = None,
        *,
        service=None,
    ):
        self.flow = flow
        self.stored = stored
        self.from_email = from_email or stored.account_email or ""
        self.from_name = from_name
        self._service = service

    def service(self):
        """Build (once) the Gmail API client.

        `cache_discovery=False` suppresses the `oauth2client` file-cache warning
        and avoids writing a discovery cache into a packaged install directory
        that may not be writable.
        """
        if self._service is None:
            try:
                from googleapiclient.discovery import build
            except ImportError as exc:
                from .errors import EmailDependencyError

                raise EmailDependencyError(
                    "google-api-python-client is not installed, so Gmail cannot "
                    "send. Install requirements/base.txt."
                ) from exc
            credentials = self.flow.build_credentials(self.stored)
            self._service = build(
                "gmail", "v1", credentials=credentials, cache_discovery=False
            )
        return self._service

    def send(self, message: RenderedEmail) -> SendResult:
        """Send one message and capture the Gmail message ID (Section 24.6)."""
        try:
            payload = build_gmail_payload(
                message, self.from_email, self.from_name
            )
            sent = (
                self.service()
                .users()
                .messages()
                .send(userId=AUTHENTICATED_USER, body=payload)
                .execute()
            )
        except EmailError as exc:
            # Already classified (invalid recipient, missing dependency, auth).
            return SendResult(ok=False, error_message=str(exc))
        except Exception as exc:
            return SendResult(ok=False, error_message=str(from_http_error(exc)))
        return SendResult(ok=True, gmail_message_id=(sent or {}).get("id"))

    def profile_email(self) -> Optional[str]:
        """The connected account's address, for the preview's "From" line."""
        try:
            profile = (
                self.service()
                .users()
                .getProfile(userId=AUTHENTICATED_USER)
                .execute()
            )
        except Exception:
            return self.from_email or None
        return (profile or {}).get("emailAddress") or self.from_email or None


@dataclass
class SentMessage:
    """A message `FakeEmailSender` accepted, kept for assertions."""

    message: RenderedEmail
    gmail_message_id: str


@dataclass
class FakeEmailSender:
    """In-memory `EmailSender` for every member who does not own Gmail.

    `fail_for` lets a test make one address fail without affecting the rest,
    which is how a partially-failed multi-recipient report is exercised.
    `fail_next` makes the next send fail once, which is how Member 5's
    retry-then-succeed path is exercised.
    """

    from_email: str = "nexa.test@example.com"
    from_name: Optional[str] = "Nexa"
    sent: List[SentMessage] = field(default_factory=list)
    fail_for: set = field(default_factory=set)
    fail_next: int = 0
    error_message: str = "Fake sender was told to fail"
    validate: bool = True
    on_send: Optional[Callable[[RenderedEmail], None]] = None

    def send(self, message: RenderedEmail) -> SendResult:
        if self.on_send is not None:
            self.on_send(message)
        if self.fail_next > 0:
            self.fail_next -= 1
            return SendResult(ok=False, error_message=self.error_message)
        if (message.to_email or "").strip().casefold() in {
            address.casefold() for address in self.fail_for
        }:
            return SendResult(ok=False, error_message=self.error_message)
        if self.validate:
            # Build the real MIME message even though nothing is transmitted, so
            # the fake rejects what Gmail would reject (a malformed address, a
            # subject that cannot be encoded) instead of being more forgiving
            # than production and hiding bugs until release.
            try:
                build_gmail_payload(message, self.from_email, self.from_name)
            except EmailError as exc:
                return SendResult(ok=False, error_message=str(exc))
        gmail_message_id = f"fake-{len(self.sent) + 1:06d}"
        self.sent.append(SentMessage(message=message, gmail_message_id=gmail_message_id))
        return SendResult(ok=True, gmail_message_id=gmail_message_id)

    # ------------------------------------------------------------ assertions
    def profile_email(self) -> Optional[str]:
        return self.from_email

    @property
    def recipients(self) -> List[str]:
        return [item.message.to_email for item in self.sent]

    def messages_to(self, email: str) -> List[RenderedEmail]:
        target = (email or "").strip().casefold()
        return [
            item.message
            for item in self.sent
            if (item.message.to_email or "").strip().casefold() == target
        ]

    def clear(self) -> None:
        self.sent.clear()


def build_sender(
    client: OAuthClient,
    stored: StoredCredentials,
    from_email: Optional[str] = None,
    from_name: Optional[str] = None,
) -> GmailSender:
    return GmailSender(GmailOAuthFlow(client), stored, from_email, from_name)
