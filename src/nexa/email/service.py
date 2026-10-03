"""`EmailService` and `GmailConnectionService` — Member 4's public surface.

`EmailService` composes the report layer and a sender: render, send, and hand
back per-recipient results. It deliberately does **not** write to the database.
Section 24.1 puts the boundary there — "Member 4 returns send result data,
Member 1's data layer persists it" — so this module takes an optional
`delivery_sink` callback and Member 1's `DeliveryRepository` is wired to it by
the caller. That keeps one owner for every SQL statement and lets every test
here run with no database at all.

`GmailConnectionService` is the Settings-screen surface from Section 24.3:
`connect()`, `test()`, `disconnect()`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, List, Optional, Sequence

from ..contracts.email import DeliveryKind, RenderedEmail, SendResult
from ..contracts.meetings import ActionItem, EmailLanguage, Meeting
from ..contracts.people import Employee
from ..core.clock import Clock, SystemClock
from ..core.timezone import DEFAULT_TIMEZONE
from ..reports.service import ReportService
from ..reports.subject_builder import digest_subject
from .errors import EmailError, GmailAuthError, GmailNotConfiguredError
from .gmail_client import FakeEmailSender, GmailSender
from .oauth import GmailOAuthFlow, OAuthClient, SCOPES, default_client_secrets_path
from .personalization import RecipientBundle, bundle_by_recipient, most_urgent
from .preview import EmailPreview, EmailPreviewService
from .token_store import StoredCredentials, default_token_store


@dataclass(frozen=True)
class DeliveryAttempt:
    """What happened for one recipient. Member 1 persists these."""

    rendered: RenderedEmail
    result: SendResult
    employee_id: Optional[int] = None
    meeting_id: Optional[int] = None
    action_item_id: Optional[int] = None
    reminder_id: Optional[int] = None

    @property
    def ok(self) -> bool:
        return bool(self.result.ok)

    @property
    def recipient_email(self) -> str:
        return self.rendered.to_email


@dataclass
class SendSummary:
    """The outcome of one report or reminder batch."""

    attempts: List[DeliveryAttempt] = field(default_factory=list)
    skipped: List[str] = field(default_factory=list)

    @property
    def sent(self) -> List[DeliveryAttempt]:
        return [item for item in self.attempts if item.ok]

    @property
    def failed(self) -> List[DeliveryAttempt]:
        return [item for item in self.attempts if not item.ok]

    @property
    def all_ok(self) -> bool:
        return bool(self.attempts) and not self.failed

    @property
    def gmail_message_ids(self) -> List[str]:
        return [
            item.result.gmail_message_id
            for item in self.sent
            if item.result.gmail_message_id
        ]


class EmailService:
    """Renders and sends meeting reports and personalized reminders."""

    def __init__(
        self,
        sender=None,
        reports: Optional[ReportService] = None,
        clock: Optional[Clock] = None,
        tz_name: str = DEFAULT_TIMEZONE,
        *,
        from_email: str = "",
        from_name: str = "Nexa",
        delivery_sink: Optional[Callable[[DeliveryAttempt], None]] = None,
        connection: Optional["GmailConnectionService"] = None,
    ):
        self.sender = sender if sender is not None else FakeEmailSender()
        self.clock = clock or SystemClock(tz_name)
        self.reports = reports or ReportService(clock=self.clock, tz_name=tz_name)
        self.from_email = from_email or getattr(self.sender, "from_email", "") or ""
        self.from_name = from_name
        self.delivery_sink = delivery_sink
        self.connection = connection

    # ---------------------------------------------------------------- preview
    def preview_service(self, connected: Optional[bool] = None) -> EmailPreviewService:
        return EmailPreviewService(
            from_email=self.from_email,
            from_name=self.from_name,
            connected=self.is_connected() if connected is None else connected,
        )

    def preview_meeting_report(
        self,
        meeting: Meeting,
        actions: Sequence[ActionItem],
        recipients: Sequence[Employee],
        language: Optional[str] = None,
        *,
        include_evidence: bool = True,
        employees: Optional[Sequence[Employee]] = None,
    ) -> EmailPreview:
        """Render a report preview without sending anything (Section 9)."""
        language = language or meeting.email_language
        rendered = self.reports.build_report_preview(
            meeting,
            actions,
            recipients,
            language,
            include_evidence=include_evidence,
            employees=employees,
        )
        rows = self.reports.formatter(language).build_rows(
            actions,
            {e.id: e for e in (employees or recipients) if getattr(e, "id", None)},
            include_evidence,
        )
        return self.preview_service().preview(rendered, recipients, rows)

    def preview_reminder(
        self,
        employee: Employee,
        action: ActionItem,
        meeting: Optional[Meeting] = None,
        language: Optional[str] = None,
    ) -> EmailPreview:
        """Backs `[ Preview Reminder Template ]` in Settings (Section 9)."""
        rendered = self.reports.build_reminder(employee, action, meeting, language)
        return self.preview_service().preview(rendered, [employee])

    # ------------------------------------------------------------------- send
    def send(self, rendered: RenderedEmail, **ids) -> DeliveryAttempt:
        """Send one rendered email and record the attempt.

        Never raises for a delivery failure: an `EmailError` is turned into a
        failed `SendResult` so the caller always gets an attempt to persist. A
        send that threw would leave Member 5's worker holding a claimed reminder
        with no delivery row explaining why.
        """
        try:
            result = self.sender.send(rendered)
        except EmailError as exc:
            result = SendResult(ok=False, error_message=str(exc))
        except Exception as exc:  # a transport that raises something unexpected
            result = SendResult(ok=False, error_message=f"{type(exc).__name__}: {exc}")
        attempt = DeliveryAttempt(rendered=rendered, result=result, **ids)
        if self.delivery_sink is not None:
            self.delivery_sink(attempt)
        return attempt

    def send_meeting_report(
        self,
        meeting: Meeting,
        actions: Sequence[ActionItem],
        recipients: Sequence[Employee],
        language: Optional[str] = None,
        *,
        include_evidence: bool = True,
        employees: Optional[Sequence[Employee]] = None,
    ) -> SendSummary:
        """Send the approved report to every recipient.

        One recipient failing does not stop the others: a 40-person report where
        address 3 is stale still reaches the other 39, and the summary carries
        both outcomes for the audit trail.
        """
        language = language or meeting.email_language
        rendered_list = self.reports.build_meeting_report(
            meeting,
            actions,
            recipients,
            language,
            include_evidence=include_evidence,
            employees=employees,
        )
        by_email = {
            (getattr(person, "email", "") or "").strip().casefold(): person
            for person in recipients
        }
        summary = SendSummary()
        addressed = set()
        for rendered in rendered_list:
            key = rendered.to_email.strip().casefold()
            addressed.add(key)
            person = by_email.get(key)
            summary.attempts.append(
                self.send(
                    rendered,
                    employee_id=getattr(person, "id", None),
                    meeting_id=meeting.id,
                )
            )
        # Recipients the report layer declined to render for (invalid address).
        summary.skipped = [
            (getattr(person, "email", "") or "")
            for key, person in by_email.items()
            if key not in addressed
        ]
        return summary

    def send_reminder(
        self,
        employee: Employee,
        action: ActionItem,
        meeting: Optional[Meeting] = None,
        language: Optional[str] = None,
        *,
        reminder_id: Optional[int] = None,
        include_evidence: bool = False,
    ) -> DeliveryAttempt:
        """Send one personalized reminder (Section 11)."""
        rendered = self.reports.build_reminder(
            employee, action, meeting, language, include_evidence=include_evidence
        )
        return self.send(
            rendered,
            employee_id=getattr(employee, "id", None),
            action_item_id=action.id,
            meeting_id=getattr(meeting, "id", None),
            reminder_id=reminder_id,
        )

    def send_personalized_reminders(
        self,
        employees: Sequence[Employee],
        actions: Sequence[ActionItem],
        meeting: Optional[Meeting] = None,
        language: Optional[str] = None,
        *,
        include_unassigned: bool = False,
    ) -> SendSummary:
        """Fan out reminders, each covering only that recipient's own tasks.

        A recipient with nothing due receives no mail at all, rather than an
        email saying they have no tasks (see `personalization.bundle_by_recipient`).
        """
        summary = SendSummary()
        for bundle in bundle_by_recipient(
            employees, actions, include_unassigned=include_unassigned
        ):
            summary.attempts.extend(
                self.send_bundle(bundle, meeting, language).attempts
            )
        return summary

    def send_bundle(
        self,
        bundle: RecipientBundle,
        meeting: Optional[Meeting] = None,
        language: Optional[str] = None,
    ) -> SendSummary:
        """Send one recipient's due tasks.

        A single task gets the normal reminder. Several get one mail led by the
        most urgent, with a subject that names the count — a separate mail per
        task would mean four notifications at 20:00 for the same person.
        """
        summary = SendSummary()
        if not bundle.actions:
            return summary
        lead = most_urgent(bundle.actions)
        attempt_language = language or (
            meeting.email_language if meeting is not None else EmailLanguage.AR.value
        )
        rendered = self.reports.build_reminder(
            bundle.employee, lead, meeting, attempt_language
        )
        if len(bundle.actions) > 1:
            # Keep the body (which is about the lead task) but make the subject
            # honest about how many items are due.
            rendered = RenderedEmail(
                to_email=rendered.to_email,
                to_name=rendered.to_name,
                subject=digest_subject(
                    bundle.actions,
                    attempt_language,
                    self.reports.formatter(attempt_language),
                    meeting,
                ),
                html_body=rendered.html_body,
                text_body=rendered.text_body,
                language=rendered.language,
            )
        summary.attempts.append(
            self.send(
                rendered,
                employee_id=getattr(bundle.employee, "id", None),
                action_item_id=lead.id,
                meeting_id=getattr(meeting, "id", None),
            )
        )
        return summary

    # ------------------------------------------------------------ connection
    def is_connected(self) -> bool:
        """Whether a send would have a usable account behind it.

        Asks, in order: an explicitly wired `GmailConnectionService`, then the
        sender itself (`GmailSender` checks its stored credential;
        `FakeEmailSender` is always connected, which is what lets Members 5 and
        6 walk the full preview → `[ Send Now ]` path offline). A transport that
        answers neither is treated as not connected, so an unknown sender fails
        closed rather than enabling a Send button that cannot work.
        """
        if self.connection is not None:
            return self.connection.status().connected
        sender_check = getattr(self.sender, "is_connected", None)
        if callable(sender_check):
            try:
                return bool(sender_check())
            except EmailError:
                return False
        return False

    @property
    def delivery_kinds(self) -> tuple:
        return tuple(kind.value for kind in DeliveryKind)


@dataclass(frozen=True)
class ConnectionStatus:
    """What the Settings screen shows about the Gmail connection."""

    connected: bool = False
    account_email: Optional[str] = None
    scopes: tuple = ()
    error: Optional[str] = None
    store_available: bool = True

    @property
    def summary(self) -> str:
        if self.connected:
            return f"Connected as {self.account_email or 'unknown account'}"
        return self.error or "Not connected"


class GmailConnectionService:
    """`connect()` / `test()` / `disconnect()` for the Settings screen.

    The token never passes through this class's return values or its messages
    (Section 38): it goes from the OAuth flow straight into the token store, and
    callers only ever see a `ConnectionStatus`.
    """

    def __init__(
        self,
        token_store=None,
        client: Optional[OAuthClient] = None,
        client_secrets_path: Optional[Path] = None,
        *,
        from_name: str = "Nexa",
    ):
        self.token_store = token_store if token_store is not None else default_token_store()
        self._client = client
        self.client_secrets_path = client_secrets_path
        self.from_name = from_name

    def client(self) -> OAuthClient:
        if self._client is None:
            self._client = OAuthClient.from_file(
                self.client_secrets_path or default_client_secrets_path()
            )
        return self._client

    def connect(self, port: int = 0) -> ConnectionStatus:
        """Run the desktop consent flow and store the refresh token."""
        if not self.token_store.is_available():
            return ConnectionStatus(
                connected=False,
                store_available=False,
                error=(
                    "No credential store is available on this machine, so Gmail "
                    "credentials cannot be saved securely."
                ),
            )
        try:
            flow = GmailOAuthFlow(self.client())
            stored = flow.authorize(port=port)
            refreshed = flow.refresh(stored)
            account = self._probe_account(flow, refreshed)
            saved = StoredCredentials(
                refresh_token=refreshed.refresh_token,
                client_id=refreshed.client_id,
                client_secret=refreshed.client_secret,
                token_uri=refreshed.token_uri,
                scopes=refreshed.scopes,
                token=refreshed.token,
                account_email=account,
            )
            self.token_store.save(saved)
        except (GmailAuthError, GmailNotConfiguredError, EmailError) as exc:
            return ConnectionStatus(connected=False, error=str(exc))
        return ConnectionStatus(
            connected=True, account_email=account, scopes=tuple(saved.scopes or SCOPES)
        )

    def test(self) -> ConnectionStatus:
        """Verify the stored credential still works, without sending mail.

        A refresh is the cheapest real check: it proves the grant has not been
        revoked. Sending a probe email to verify a connection would put a stray
        message in the admin's Sent folder every time Settings is opened.
        """
        stored = self.token_store.load()
        if stored is None or not stored.is_complete():
            return ConnectionStatus(connected=False, error="Gmail is not connected.")
        try:
            flow = GmailOAuthFlow(self.client())
            refreshed = flow.refresh(stored)
        except (GmailAuthError, GmailNotConfiguredError, EmailError) as exc:
            return ConnectionStatus(
                connected=False, account_email=stored.account_email, error=str(exc)
            )
        account = stored.account_email or self._probe_account(flow, refreshed)
        if refreshed.token != stored.token or account != stored.account_email:
            # Cache the fresh access token so the next send skips a refresh.
            self.token_store.save(
                StoredCredentials(
                    refresh_token=stored.refresh_token,
                    client_id=stored.client_id,
                    client_secret=stored.client_secret,
                    token_uri=stored.token_uri,
                    scopes=stored.scopes,
                    token=refreshed.token,
                    account_email=account,
                )
            )
        return ConnectionStatus(
            connected=True, account_email=account, scopes=tuple(stored.scopes or SCOPES)
        )

    def disconnect(self) -> ConnectionStatus:
        """Forget the stored credential.

        Local only, on purpose: it does not revoke the grant at Google. An admin
        who wants the grant itself withdrawn does that in their Google account,
        and silently revoking from here would break a second Nexa installation
        using the same account.
        """
        self.token_store.delete()
        return ConnectionStatus(connected=False, error="Not connected")

    def status(self) -> ConnectionStatus:
        """Cheap, offline status for painting the Settings screen."""
        if not self.token_store.is_available():
            return ConnectionStatus(
                connected=False,
                store_available=False,
                error="No credential store is available on this machine.",
            )
        stored = self.token_store.load()
        if stored is None or not stored.is_complete():
            return ConnectionStatus(connected=False, error="Not connected")
        return ConnectionStatus(
            connected=True,
            account_email=stored.account_email,
            scopes=tuple(stored.scopes or SCOPES),
        )

    def sender(self, from_email: Optional[str] = None) -> GmailSender:
        """A `GmailSender` bound to the stored credential."""
        stored = self.token_store.load()
        if stored is None or not stored.is_complete():
            raise GmailAuthError("Gmail is not connected. Connect an account in Settings.")
        return GmailSender(
            GmailOAuthFlow(self.client()),
            stored,
            from_email or stored.account_email or "",
            self.from_name,
        )

    def _probe_account(self, flow: GmailOAuthFlow, stored: StoredCredentials):
        """Best-effort lookup of the connected address for display.

        Failure is not an error: the connection is valid whether or not the
        address could be read, so a probe failure must not fail `connect()`.
        """
        try:
            return GmailSender(flow, stored).profile_email()
        except Exception:
            return stored.account_email
