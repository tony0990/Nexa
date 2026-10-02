"""MIME construction for Gmail (Section 24.1).

Every message is `multipart/alternative` with the plain-text part first and the
HTML part second, which is what the RFC requires and what makes the plain-text
fallback in Section 24.5 real rather than decorative: a client that cannot
render HTML shows the last part it understands, and ordering it wrong means the
fallback is never used.

Two details that matter for Arabic:

* **Headers.** A subject like `تقرير مهام الاجتماع` is not ASCII, so it is
  RFC 2047 encoded. Python's `email.header.Header` does this; writing the raw
  string into the header would produce mojibake in most clients.
* **Bodies.** UTF-8 throughout, declared on each part.

Note the stdlib `email` package is what `from email.mime...` resolves to here,
not this package: Python 3 absolute imports mean `email` is the top-level
stdlib module, and `nexa.email` is only reachable by its full dotted name.
"""

from __future__ import annotations

import base64
from email.header import Header
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr, formatdate, make_msgid
from typing import Optional

from ..contracts.email import RenderedEmail
from ..core.validation import is_valid_email
from .errors import InvalidRecipientError

CHARSET = "utf-8"


def encode_header(value: str) -> str:
    """RFC 2047 encode a header value when it is not pure ASCII.

    ASCII values are returned untouched so an English subject stays readable in
    raw message sources and in logs.
    """
    text = value or ""
    try:
        text.encode("ascii")
        return text
    except UnicodeEncodeError:
        return Header(text, CHARSET).encode()


def format_address(email: str, name: Optional[str] = None) -> str:
    """`Name <addr>`, with the display name RFC 2047 encoded if needed.

    `formataddr` handles the quoting rules; passing it an already-encoded name
    keeps an Arabic display name intact.
    """
    address = (email or "").strip()
    display = (name or "").strip()
    if not display:
        return address
    return formataddr((encode_header(display), address))


def build_mime_message(
    message: RenderedEmail,
    from_email: str,
    from_name: Optional[str] = None,
    *,
    reply_to: Optional[str] = None,
) -> MIMEMultipart:
    """Build the `multipart/alternative` message for one recipient.

    Raises `InvalidRecipientError` before anything is sent when the address is
    not structurally valid — Nexa's own check, reusing Member 1's validator, so
    a typo costs a validation error rather than a Gmail API round trip and a
    FAILED delivery row.
    """
    to_email = (message.to_email or "").strip()
    if not is_valid_email(to_email):
        raise InvalidRecipientError(f"{message.to_email!r} is not a valid email address")

    root = MIMEMultipart("alternative")
    root["To"] = format_address(to_email, message.to_name)
    root["From"] = format_address(from_email, from_name)
    root["Subject"] = encode_header(message.subject)
    root["Date"] = formatdate(localtime=True)
    # A Message-ID makes a reminder and its report distinct conversations in the
    # recipient's client, instead of Gmail threading unrelated mails together.
    root["Message-ID"] = make_msgid(domain=_domain_of(from_email))
    if reply_to:
        root["Reply-To"] = format_address(reply_to)
    # Arabic reports are RTL; this is advisory but some clients honour it.
    root["Content-Language"] = "ar" if str(message.language).upper() == "AR" else "en"

    # Order is load-bearing: least-capable alternative first.
    root.attach(MIMEText(message.text_body or "", "plain", CHARSET))
    root.attach(MIMEText(message.html_body or "", "html", CHARSET))
    return root


def to_gmail_raw(mime_message) -> str:
    """Base64**url** encode for the Gmail API's `raw` field.

    Standard base64 is not interchangeable here: Gmail rejects `+` and `/`,
    which is why this is `urlsafe_b64encode` and not `b64encode`.
    """
    return base64.urlsafe_b64encode(mime_message.as_bytes()).decode("ascii")


def build_gmail_payload(
    message: RenderedEmail,
    from_email: str,
    from_name: Optional[str] = None,
    *,
    reply_to: Optional[str] = None,
) -> dict:
    """The request body for `users.messages.send`."""
    mime = build_mime_message(message, from_email, from_name, reply_to=reply_to)
    return {"raw": to_gmail_raw(mime)}


def _domain_of(email: str) -> Optional[str]:
    _, _, domain = (email or "").partition("@")
    return domain or None
