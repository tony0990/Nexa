"""Language-aware formatting: the only module that touches dates and labels.

`formatter.py` picks `arabic` or `english` once and exposes a single
`Lexicon`-shaped façade, so neither `renderer.py` nor any template ever
branches on language again.

Dates are formatted from the **local** Cairo calendar day, not from UTC: a
deadline stored as `2026-09-10T21:00:00+00:00` is Thursday 11 September in
Cairo, and a report that said Thursday 10 September would be wrong. All
conversion goes through Member 1's `core.timezone` rather than being redone
here.

Digits stay ASCII in both languages. Arabic-Indic digits render inconsistently
across mail clients and break the plain-text fallback's alignment, and Egyptian
formal correspondence accepts ASCII numerals.
"""

from __future__ import annotations

from datetime import date, datetime, time
from typing import Optional, Sequence

from ..contracts.meetings import ActionItem, EmailLanguage, Meeting, ReviewState
from ..contracts.people import Employee
from ..core.clock import Clock, SystemClock
from ..core.timezone import DEFAULT_TIMEZONE, to_local
from . import arabic, english
from .models import MeetingReportContext, ReminderContext, ReportRow, resolve_language

_LEXICONS = {
    EmailLanguage.AR.value: arabic,
    EmailLanguage.EN.value: english,
}


def lexicon(language: str):
    """Return the `arabic` or `english` module for `language`."""
    return _LEXICONS[resolve_language(language)]


class ReportFormatter:
    """Turns approved domain objects into language-specific presentation rows.

    One instance per language keeps the lexicon lookup out of every call and
    makes the preview screen's `[ Change Language ]` button a cheap re-render
    with a second formatter.
    """

    def __init__(
        self,
        language: str = EmailLanguage.AR.value,
        clock: Optional[Clock] = None,
        tz_name: str = DEFAULT_TIMEZONE,
    ):
        self.language = resolve_language(language)
        self.lex = lexicon(self.language)
        self.clock = clock or SystemClock(tz_name)
        self.tz = tz_name

    # ------------------------------------------------------------------ dates
    def format_date(self, value: Optional[date]) -> str:
        if value is None:
            return self.lex.LABELS["date_not_specified"]
        weekday = self.lex.WEEKDAYS[value.weekday()]
        month = self.lex.MONTHS[value.month - 1]
        if self.language == EmailLanguage.AR.value:
            return f"{weekday} {value.day} {month} {value.year}"
        return f"{weekday}, {value.day} {month} {value.year}"

    def format_time(self, value: Optional[time]) -> str:
        """12-hour clock. A missing time is "time not specified" (Section 2.1)."""
        if value is None:
            return self.lex.LABELS["time_not_specified"]
        hour = value.hour % 12 or 12
        meridiem = self.lex.MERIDIEM["am" if value.hour < 12 else "pm"]
        return f"{hour}:{value.minute:02d} {meridiem}"

    def format_datetime(self, value: Optional[datetime]) -> str:
        if value is None:
            return self.lex.LABELS["date_not_specified"]
        local = to_local(value, self.tz)
        return f"{self.format_date(local.date())} — {self.format_time(local.time())}"

    def local_due_date(self, action: ActionItem) -> Optional[date]:
        """The calendar day a deadline falls on in the application timezone.

        `due_at` wins when present because Member 5 schedules from it; `due_date`
        is the admin-visible day and is used when no instant was computed.
        """
        if action.due_at is not None:
            return to_local(action.due_at, self.tz).date()
        return action.due_date

    def format_deadline(self, action: ActionItem) -> str:
        """Full deadline text: day, plus time only when one was specified."""
        day = self.local_due_date(action)
        if day is None:
            return self.lex.LABELS["date_not_specified"]
        if action.due_time is None and action.due_at is None:
            return self.format_date(day)
        at = action.due_time
        if at is None and action.due_at is not None:
            at = to_local(action.due_at, self.tz).time()
        return f"{self.format_date(day)} — {self.format_time(at)}"

    def days_until(self, action: ActionItem) -> Optional[int]:
        """Whole local days from today to the deadline; negative when overdue."""
        day = self.local_due_date(action)
        if day is None:
            return None
        return (day - self.clock.today()).days

    # ------------------------------------------------------------------- rows
    def owner_name(
        self, action: ActionItem, employees_by_id: Optional[dict] = None
    ) -> str:
        """Resolved owner name, the raw spoken name, or "Unassigned".

        When extraction heard a name it could not match to an employee, the raw
        text is shown rather than dropped — the admin approved the item with
        that evidence, and hiding it would lose information (Section 2.2).
        """
        employee = (employees_by_id or {}).get(action.owner_employee_id)
        if employee is not None and getattr(employee, "full_name", ""):
            return employee.full_name
        raw = (action.owner_raw_text or "").strip()
        return raw or self.lex.LABELS["unassigned"]

    def status_text(self, action: ActionItem) -> str:
        key = str(getattr(action.status, "value", action.status) or "")
        return self.lex.STATUSES.get(key, key)

    def build_row(
        self,
        number: int,
        action: ActionItem,
        employees_by_id: Optional[dict] = None,
        include_evidence: bool = True,
    ) -> ReportRow:
        needs_review = (
            str(getattr(action.review_state, "value", action.review_state))
            == ReviewState.NEEDS_REVIEW.value
        )
        evidence = None
        if include_evidence:
            # raw_date_phrase is the narrower evidence (the words that produced
            # the deadline); source_text is the whole confirmed sentence. Prefer
            # the sentence, which is what the review screen showed the admin.
            evidence = (action.source_text or action.raw_date_phrase or "").strip() or None
        return ReportRow(
            number=number,
            task=(action.task or "").strip(),
            owner=self.owner_name(action, employees_by_id),
            deadline=self.format_deadline(action),
            status=self.status_text(action),
            evidence=evidence,
            needs_review=needs_review,
            review_note=self.lex.REVIEW_NOTE if needs_review else None,
        )

    def build_rows(
        self,
        actions: Sequence[ActionItem],
        employees_by_id: Optional[dict] = None,
        include_evidence: bool = True,
    ) -> tuple:
        return tuple(
            self.build_row(index, action, employees_by_id, include_evidence)
            for index, action in enumerate(actions, start=1)
        )

    # --------------------------------------------------------------- contexts
    def meeting_date_text(self, meeting: Meeting) -> str:
        moment = meeting.started_at or meeting.created_at
        if moment is None:
            return self.lex.LABELS["date_not_specified"]
        return self.format_date(to_local(moment, self.tz).date())

    def report_context(
        self,
        meeting: Meeting,
        actions: Sequence[ActionItem],
        recipient: Optional[Employee] = None,
        employees_by_id: Optional[dict] = None,
        include_evidence: bool = True,
    ) -> MeetingReportContext:
        rows = self.build_rows(actions, employees_by_id, include_evidence)
        recipient_name = getattr(recipient, "full_name", "") or ""
        meeting_title = (meeting.title or "").strip()
        return MeetingReportContext(
            language=self.language,
            direction=self.lex.DIRECTION,
            title=self.lex.LABELS["report_title"],
            meeting_title=meeting_title,
            meeting_date=self.meeting_date_text(meeting),
            recipient_name=recipient_name,
            greeting=self.lex.greeting(recipient_name),
            intro=self.lex.report_intro(meeting_title, len(rows)),
            closing=self.lex.report_closing(),
            signature=self.lex.SIGNATURE,
            rows=rows,
            labels=dict(self.lex.LABELS),
            show_evidence=include_evidence,
            generated_at=self.format_datetime(self.clock.now_utc()),
        )

    def reminder_context(
        self,
        employee: Employee,
        action: ActionItem,
        meeting: Optional[Meeting] = None,
        include_evidence: bool = False,
    ) -> ReminderContext:
        recipient_name = getattr(employee, "full_name", "") or ""
        days = self.days_until(action)
        due_text = self.lex.due_phrase(days)
        task = (action.task or "").strip()
        evidence = (action.source_text or "").strip() if include_evidence else ""
        return ReminderContext(
            language=self.language,
            direction=self.lex.DIRECTION,
            title=self.lex.LABELS["reminder_title"],
            recipient_name=recipient_name,
            greeting=self.lex.greeting(recipient_name),
            intro=self.lex.reminder_intro(task, due_text),
            closing=self.lex.reminder_closing(),
            signature=self.lex.SIGNATURE,
            task=task,
            deadline=self.format_deadline(action),
            due_phrase=due_text,
            meeting_title=(getattr(meeting, "title", "") or "").strip(),
            labels=dict(self.lex.LABELS),
            evidence=evidence or None,
            generated_at=self.format_datetime(self.clock.now_utc()),
        )
