"""Gmail delivery, previews and personalization — Member 4.

    from nexa.email import EmailService, FakeEmailSender
    from nexa.reports import ReportService

    service = EmailService(sender=FakeEmailSender())
    preview = service.preview_meeting_report(meeting, actions, recipients, "EN")
    summary = service.send_meeting_report(meeting, actions, recipients, "EN")

Other members depend on `EmailSender` from `nexa.contracts.email`, never on
`GmailSender`: `FakeEmailSender` satisfies the same protocol, so the worker, the
scheduler and the UI all run offline.

Note this package is named `email` because Section 24.2 specifies it. It does
not shadow the standard library: Python 3 resolves `import email` inside these
modules to the stdlib top-level package, since this one is only reachable as
`nexa.email`.
"""

from .errors import (
    EmailDependencyError,
    EmailError,
    GmailAuthError,
    GmailNotConfiguredError,
    InvalidRecipientError,
    PermanentEmailError,
    TransientEmailError,
    classify_status,
    from_http_error,
)
from .gmail_client import FakeEmailSender, GmailSender, SentMessage, build_sender
from .mime_builder import build_gmail_payload, build_mime_message, to_gmail_raw
from .oauth import GMAIL_SEND_SCOPE, SCOPES, GmailOAuthFlow, OAuthClient
from .personalization import RecipientBundle, actions_for, bundle_by_recipient, owners_of
from .preview import EmailPreview, EmailPreviewService, PreviewRecipient
from .service import (
    ConnectionStatus,
    DeliveryAttempt,
    EmailService,
    GmailConnectionService,
    SendSummary,
)
from .token_store import (
    KeyringTokenStore,
    MemoryTokenStore,
    NullTokenStore,
    StoredCredentials,
    default_token_store,
)

__all__ = [
    "ConnectionStatus",
    "DeliveryAttempt",
    "EmailDependencyError",
    "EmailError",
    "EmailPreview",
    "EmailPreviewService",
    "EmailService",
    "FakeEmailSender",
    "GMAIL_SEND_SCOPE",
    "GmailAuthError",
    "GmailConnectionService",
    "GmailNotConfiguredError",
    "GmailOAuthFlow",
    "GmailSender",
    "InvalidRecipientError",
    "KeyringTokenStore",
    "MemoryTokenStore",
    "NullTokenStore",
    "OAuthClient",
    "PermanentEmailError",
    "PreviewRecipient",
    "RecipientBundle",
    "SCOPES",
    "SendSummary",
    "SentMessage",
    "StoredCredentials",
    "TransientEmailError",
    "actions_for",
    "build_gmail_payload",
    "build_mime_message",
    "build_sender",
    "bundle_by_recipient",
    "classify_status",
    "default_token_store",
    "from_http_error",
    "owners_of",
    "to_gmail_raw",
]
