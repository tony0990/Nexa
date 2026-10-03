"""Report rendering — Member 4.

Approved meeting data in, professional Arabic or English email bodies out. No
database, no network, no LLM: Section 24.1 makes approved action data the single
source of truth for report content, so this layer only formats and renders it.

    from nexa.reports import ReportService

    service = ReportService()
    emails = service.build_meeting_report(meeting, actions, recipients, "EN")

Report language is Arabic **or** English per send (Section 1's final language
decision), which is why `nexa.contracts.meetings.EmailLanguage` has exactly two
members and there is no bilingual renderer.
"""

from .formatter import ReportFormatter, lexicon
from .models import (
    MeetingReportContext,
    ReminderContext,
    ReportRequest,
    ReportRow,
    is_rtl,
    resolve_language,
)
from .renderer import ReportRenderer, TemplateNotFoundError, default_templates_dir
from .service import ReportService
from .subject_builder import (
    digest_subject,
    meeting_report_subject,
    reminder_subject,
    sanitize_subject,
)

__all__ = [
    "MeetingReportContext",
    "ReminderContext",
    "ReportFormatter",
    "ReportRenderer",
    "ReportRequest",
    "ReportRow",
    "ReportService",
    "TemplateNotFoundError",
    "default_templates_dir",
    "digest_subject",
    "is_rtl",
    "lexicon",
    "meeting_report_subject",
    "reminder_subject",
    "resolve_language",
    "sanitize_subject",
]
