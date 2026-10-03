"""Email preview — "no report is sent without a preview option" (Section 9).

`EmailPreview` is a plain snapshot of exactly what would be transmitted. It is
built from the same `RenderedEmail` that `EmailSender.send` receives, never
re-rendered with different inputs, so what the admin approves on the preview
screen is what leaves the machine.

Nothing here touches the network: `preview()` on an unconnected installation
still returns a full preview and simply reports `connected = False`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Sequence

from ..contracts.email import RenderedEmail
from ..contracts.meetings import EmailLanguage
from ..core.validation import is_valid_email
from ..reports.models import ReportRow, is_rtl


@dataclass(frozen=True)
class PreviewRecipient:
    """One row of the preview's recipient list."""

    email: str
    name: str = ""
    deliverable: bool = True
    note: Optional[str] = None


@dataclass(frozen=True)
class EmailPreview:
    """Everything the preview screen in Section 9 displays.

    `action_rows` is carried separately from `html_body` so Member 6 can render
    the action-item table with native widgets instead of parsing the HTML back
    apart.
    """

    from_email: str = ""
    from_name: str = ""
    subject: str = ""
    language: str = EmailLanguage.AR.value
    direction: str = "rtl"
    html_body: str = ""
    text_body: str = ""
    recipients: Sequence[PreviewRecipient] = field(default_factory=tuple)
    action_rows: Sequence[ReportRow] = field(default_factory=tuple)
    connected: bool = False
    warnings: Sequence[str] = field(default_factory=tuple)

    @property
    def recipient_count(self) -> int:
        """Addresses that would actually be attempted."""
        return sum(1 for item in self.recipients if item.deliverable)

    @property
    def undeliverable(self) -> Sequence[PreviewRecipient]:
        return tuple(item for item in self.recipients if not item.deliverable)

    @property
    def can_send(self) -> bool:
        """The `[ Send Now ]` button's enabled state."""
        return self.connected and self.recipient_count > 0


class EmailPreviewService:
    """Builds an `EmailPreview` from a rendered email.

    Section 24.3 freezes this as `EmailPreviewService.preview(rendered_email)`.
    """

    def __init__(
        self,
        from_email: str = "",
        from_name: str = "",
        connected: bool = False,
    ):
        self.from_email = from_email
        self.from_name = from_name
        self.connected = connected

    def preview(
        self,
        rendered_email: RenderedEmail,
        recipients: Optional[Sequence] = None,
        action_rows: Optional[Sequence[ReportRow]] = None,
    ) -> EmailPreview:
        """Snapshot one rendered email.

        `recipients` are the employees the send would actually go to; when it is
        omitted the preview shows the single address on the rendered email,
        which is the one-recipient reminder case.
        """
        people = (
            tuple(_as_recipient(item) for item in recipients)
            if recipients is not None
            else (
                (PreviewRecipient(rendered_email.to_email, rendered_email.to_name,
                                  is_valid_email(rendered_email.to_email)),)
                if rendered_email.to_email
                else ()
            )
        )
        return EmailPreview(
            from_email=self.from_email,
            from_name=self.from_name,
            subject=rendered_email.subject,
            language=rendered_email.language,
            direction="rtl" if is_rtl(rendered_email.language) else "ltr",
            html_body=rendered_email.html_body,
            text_body=rendered_email.text_body,
            recipients=people,
            action_rows=tuple(action_rows or ()),
            connected=self.connected,
            warnings=tuple(_warnings(rendered_email, people, self.connected)),
        )


def _as_recipient(item) -> PreviewRecipient:
    """Accept an `Employee`, a `PreviewRecipient`, or a bare address string."""
    if isinstance(item, PreviewRecipient):
        return item
    if isinstance(item, str):
        return PreviewRecipient(item.strip(), "", is_valid_email(item))
    email = (getattr(item, "email", "") or "").strip()
    name = getattr(item, "full_name", "") or ""
    active = getattr(item, "active", True)
    if not is_valid_email(email):
        return PreviewRecipient(email, name, False, "Invalid email address")
    if not active:
        return PreviewRecipient(email, name, False, "Employee is deactivated")
    return PreviewRecipient(email, name, True)


def _warnings(
    rendered: RenderedEmail, recipients: Sequence[PreviewRecipient], connected: bool
) -> List[str]:
    """Reasons the admin should look twice before pressing Send.

    Warnings, not errors: the admin can still choose to send. Blocking a send
    because one of forty addresses is stale would be worse than reporting it.
    """
    out: List[str] = []
    if not connected:
        out.append("Gmail is not connected. Connect an account in Settings before sending.")
    if not recipients:
        out.append("No recipients selected.")
    bad = [item for item in recipients if not item.deliverable]
    if bad:
        out.append(
            f"{len(bad)} recipient(s) will be skipped: "
            + ", ".join(f"{item.email or '(blank)'} ({item.note})" for item in bad)
        )
    if not (rendered.text_body or "").strip():
        out.append("The plain-text fallback is empty.")
    if not (rendered.html_body or "").strip():
        out.append("The HTML body is empty.")
    if not (rendered.subject or "").strip():
        out.append("The subject is empty.")
    return out
