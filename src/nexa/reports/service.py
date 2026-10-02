"""`ReportService` — the public entry point for the whole report layer.

This is the interface Section 24.3 freezes, and the only thing other members
call:

    ReportService.build_meeting_report(meeting, actions, recipients, language)
    ReportService.build_reminder(employee, action, meeting, language)

Both return a `RenderedEmail` from `nexa.contracts.email`, which is also what
`EmailSender.send` accepts — so rendering and sending compose without an
adapter in between.

A meeting report goes to many recipients, and each one is addressed by name, so
`build_meeting_report` returns one `RenderedEmail` per recipient. The HTML is
rendered once per distinct greeting rather than once per recipient; on a 200-
person report that is the difference between 200 template renders and 1.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence

from ..contracts.email import RenderedEmail
from ..contracts.meetings import ActionItem, EmailLanguage, Meeting
from ..contracts.people import Employee
from ..core.clock import Clock, SystemClock
from ..core.timezone import DEFAULT_TIMEZONE
from ..core.validation import is_valid_email
from .formatter import ReportFormatter
from .models import resolve_language
from .renderer import ReportRenderer
from .subject_builder import meeting_report_subject, reminder_subject


class ReportService:
    """Builds `RenderedEmail` objects from approved meeting data.

    Deliberately has no database and no network: it takes domain objects and
    returns rendered text, which is what makes Section 24.6's "rendering can be
    fully tested without network access" true by construction.
    """

    def __init__(
        self,
        renderer: Optional[ReportRenderer] = None,
        clock: Optional[Clock] = None,
        tz_name: str = DEFAULT_TIMEZONE,
    ):
        self.renderer = renderer or ReportRenderer()
        self.clock = clock or SystemClock(tz_name)
        self.tz = tz_name
        self._formatters: Dict[str, ReportFormatter] = {}

    def formatter(self, language: str) -> ReportFormatter:
        language = resolve_language(language)
        if language not in self._formatters:
            self._formatters[language] = ReportFormatter(language, self.clock, self.tz)
        return self._formatters[language]

    # -------------------------------------------------------------- reports
    def build_meeting_report(
        self,
        meeting: Meeting,
        actions: Sequence[ActionItem],
        recipients: Sequence[Employee],
        language: Optional[str] = None,
        *,
        include_evidence: bool = True,
        employees: Optional[Sequence[Employee]] = None,
    ) -> List[RenderedEmail]:
        """One `RenderedEmail` per recipient.

        `language` defaults to the meeting's own `email_language`, which is what
        the meeting template or the review screen set. `employees` is the pool
        used to resolve owner names; it defaults to `recipients`, which is
        enough when owners are among the recipients and is a cheap way for the
        UI to pass the full directory when they are not.
        """
        language = resolve_language(language or meeting.email_language)
        fmt = self.formatter(language)
        by_id = _index_by_id(employees if employees is not None else recipients)
        subject = meeting_report_subject(meeting, language, fmt)

        rendered: List[RenderedEmail] = []
        cache: Dict[str, tuple] = {}
        for recipient in recipients:
            email = (getattr(recipient, "email", "") or "").strip()
            if not is_valid_email(email):
                # Member 1's resolver already drops unsendable employees and
                # reports them as skipped; this is the backstop for a recipient
                # list assembled by hand in the UI.
                continue
            name = getattr(recipient, "full_name", "") or ""
            if name not in cache:
                context = fmt.report_context(
                    meeting, actions, recipient, by_id, include_evidence
                )
                cache[name] = self.renderer.render_report(context, language)
            html, text = cache[name]
            rendered.append(
                RenderedEmail(
                    to_email=email,
                    to_name=name,
                    subject=subject,
                    html_body=html,
                    text_body=text,
                    language=language,
                )
            )
        return rendered

    def build_report_preview(
        self,
        meeting: Meeting,
        actions: Sequence[ActionItem],
        recipients: Sequence[Employee],
        language: Optional[str] = None,
        *,
        include_evidence: bool = True,
        employees: Optional[Sequence[Employee]] = None,
    ) -> RenderedEmail:
        """One representative render for the preview screen (Section 9).

        Addressed to the first recipient so the greeting is real rather than a
        placeholder, and produced without touching the network.
        """
        language = resolve_language(language or meeting.email_language)
        fmt = self.formatter(language)
        first = recipients[0] if recipients else None
        by_id = _index_by_id(employees if employees is not None else recipients)
        context = fmt.report_context(meeting, actions, first, by_id, include_evidence)
        html, text = self.renderer.render_report(context, language)
        return RenderedEmail(
            to_email=(getattr(first, "email", "") or "") if first else "",
            to_name=(getattr(first, "full_name", "") or "") if first else "",
            subject=meeting_report_subject(meeting, language, fmt),
            html_body=html,
            text_body=text,
            language=language,
        )

    # ------------------------------------------------------------ reminders
    def build_reminder(
        self,
        employee: Employee,
        action: ActionItem,
        meeting: Optional[Meeting] = None,
        language: Optional[str] = None,
        *,
        include_evidence: bool = False,
    ) -> RenderedEmail:
        """A reminder personalized to one employee and one task (Section 11).

        Evidence is off by default here: a reminder is a short operational
        nudge, and the colloquial original sentence belongs in the report and
        the review screen rather than in every reminder.
        """
        language = resolve_language(
            language
            or (meeting.email_language if meeting is not None else None)
            or EmailLanguage.AR.value
        )
        fmt = self.formatter(language)
        context = fmt.reminder_context(employee, action, meeting, include_evidence)
        html, text = self.renderer.render_reminder(context, language)
        return RenderedEmail(
            to_email=(getattr(employee, "email", "") or "").strip(),
            to_name=getattr(employee, "full_name", "") or "",
            subject=reminder_subject(action, language, fmt),
            html_body=html,
            text_body=text,
            language=language,
        )

    def available_languages(self) -> tuple:
        return self.renderer.available_languages()


def _index_by_id(employees: Optional[Sequence[Employee]]) -> Dict[int, Employee]:
    return {
        employee.id: employee
        for employee in (employees or ())
        if getattr(employee, "id", None) is not None
    }
