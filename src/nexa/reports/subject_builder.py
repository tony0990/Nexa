"""Subject lines for reports and reminders.

Kept separate from the body templates because a subject has constraints a body
does not: it is a single line, it cannot contain HTML, and mail clients
truncate it. Gmail shows roughly 70 characters on desktop and far fewer on a
phone, so the distinguishing part (the task, the meeting) comes before the
deadline, and the whole thing is trimmed on a word boundary.
"""

from __future__ import annotations

from typing import Optional, Sequence

from ..contracts.meetings import ActionItem, EmailLanguage, Meeting
from .formatter import ReportFormatter, lexicon
from .models import resolve_language

# Long enough not to lose the task, short enough that Gmail's own ellipsis is
# rarely the one a recipient sees.
MAX_SUBJECT_LENGTH = 120

# Collapsed in subjects: a newline in a header is a header-injection vector,
# and a tab renders as a blank in most clients.
_FORBIDDEN = {"\r": " ", "\n": " ", "\t": " "}


def sanitize_subject(value: str) -> str:
    """Strip CR/LF and collapse whitespace.

    This is a trust boundary, not cosmetics: meeting titles and task text
    originate from transcribed speech and admin typing, and a subject built
    from them is written straight into a MIME header. A bare `\\n` there would
    let crafted text append its own headers.
    """
    text = value or ""
    for bad, good in _FORBIDDEN.items():
        text = text.replace(bad, good)
    return " ".join(text.split())


def truncate(value: str, limit: int = MAX_SUBJECT_LENGTH) -> str:
    """Trim to `limit` characters on a word boundary, with an ellipsis."""
    text = sanitize_subject(value)
    if len(text) <= limit:
        return text
    cut = text[: limit - 1]
    if " " in cut:
        cut = cut[: cut.rindex(" ")]
    return f"{cut.rstrip()}…"


def meeting_report_subject(
    meeting: Meeting, language: str = EmailLanguage.AR.value, formatter=None
) -> str:
    """`[Nexa] Meeting Action Report — <title> — <date>`."""
    language = resolve_language(language)
    lex = lexicon(language)
    formatter = formatter or ReportFormatter(language)
    title = sanitize_subject(meeting.title or "")
    return truncate(lex.subject_report(title, formatter.meeting_date_text(meeting)))


def reminder_subject(
    action: ActionItem, language: str = EmailLanguage.AR.value, formatter=None
) -> str:
    """`[Nexa Reminder] <task> — Due Tomorrow` (Section 11)."""
    language = resolve_language(language)
    lex = lexicon(language)
    formatter = formatter or ReportFormatter(language)
    task = sanitize_subject(action.task or "")
    return truncate(lex.subject_reminder(task, formatter.days_until(action)))


def digest_subject(
    actions: Sequence[ActionItem],
    language: str = EmailLanguage.AR.value,
    formatter=None,
    meeting: Optional[Meeting] = None,
) -> str:
    """Subject for a reminder covering several tasks at once.

    Member 5's rule engine can batch a recipient's due items into one send; a
    single-task subject would then name one task and silently hide the rest.
    """
    if len(actions) == 1:
        return reminder_subject(actions[0], language, formatter)
    language = resolve_language(language)
    lex = lexicon(language)
    count = len(actions)
    if language == EmailLanguage.AR.value:
        return truncate(f"[Nexa] تذكير — {count} مهام مستحقة")
    noun = "task" if count == 1 else "tasks"
    return truncate(f"[Nexa Reminder] {count} {noun} due")
