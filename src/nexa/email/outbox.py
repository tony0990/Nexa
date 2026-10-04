"""A sender that writes real emails to a folder instead of sending them.

Section 24.4 lists a Gmail account and an OAuth client as team/admin setup, so
until they exist nothing could be tried end to end: every send failed with "not
connected". `OutboxSender` closes that gap for real-life testing. It builds the
exact MIME message `GmailSender` would transmit — headers, RFC 2047 Arabic
subject, `multipart/alternative` — and saves it as a `.eml` file that opens in
Outlook, Thunderbird or Windows Mail, plus the HTML body as a browser-viewable
sibling.

It is deliberately *not* disguised as Gmail:

* `gmail_message_id` is `outbox:<filename>`, so a delivery row can never be
  mistaken for a real send;
* `is_outbox` is True, which the Settings screen reads to say "saved to the
  outbox folder" instead of "connected";
* it satisfies the same `EmailSender` protocol, so swapping in `GmailSender`
  later changes nothing else.
"""

from __future__ import annotations

import re
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional

from ..contracts.email import RenderedEmail, SendResult
from .errors import EmailError
from .mime_builder import build_mime_message

_UNSAFE = re.compile(r"[^\w.@-]+", re.UNICODE)


class OutboxSender:
    """Satisfies `EmailSender`; the "network" is a folder on disk."""

    is_outbox = True

    def __init__(
        self,
        folder: Path,
        from_email: str = "nexa@localhost",
        from_name: Optional[str] = "Nexa",
    ):
        self.folder = Path(folder)
        self.from_email = from_email
        self.from_name = from_name
        self._lock = threading.Lock()
        self._counter = 0

    def is_connected(self) -> bool:
        """Always usable: writing a file needs no account."""
        return True

    def profile_email(self) -> str:
        return self.from_email

    def send(self, message: RenderedEmail) -> SendResult:
        try:
            mime = build_mime_message(message, self.from_email, self.from_name)
        except EmailError as exc:
            # Same classification Gmail would give, so retry behaviour matches.
            return SendResult(ok=False, error_message=str(exc), retryable=exc.retryable)
        try:
            self.folder.mkdir(parents=True, exist_ok=True)
            with self._lock:
                self._counter += 1
                stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
                recipient = _UNSAFE.sub("_", message.to_email)[:60]
                stem = f"{stamp}-{self._counter:03d}-{recipient}"
                (self.folder / f"{stem}.eml").write_bytes(mime.as_bytes())
                (self.folder / f"{stem}.html").write_text(message.html_body or "", encoding="utf-8")
        except OSError as exc:
            # A full or read-only disk may clear up; try again later.
            return SendResult(ok=False, error_message=f"Could not write to the outbox: {exc}", retryable=True)
        return SendResult(ok=True, gmail_message_id=f"outbox:{stem}.eml")
