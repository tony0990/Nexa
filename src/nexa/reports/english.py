"""Professional business English lexicon for reports and reminders (10.2).

Mirrors `arabic.py` module-for-module so `formatter.py` can select one of the
two by language and never branch on it again. Same rule applies: this module
supplies the formal frame, never the task content.
"""

from __future__ import annotations

DIRECTION = "ltr"
LANG_ATTR = "en"

MONTHS = (
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)

# Indexed by `date.weekday()` (Monday = 0).
WEEKDAYS = (
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
)

MERIDIEM = {"am": "AM", "pm": "PM"}

LABELS = {
    "report_title": "Meeting Action Report",
    "reminder_title": "Task Reminder",
    "meeting": "Meeting",
    "date": "Date",
    "action_items": "Action Items",
    "number": "#",
    "task": "Task",
    "owner": "Owner",
    "deadline": "Deadline",
    "status": "Status",
    "evidence": "Original phrase",
    "needs_review": "Needs review",
    "no_actions": "No action items were recorded for this meeting.",
    "generated_at": "Generated",
    "unassigned": "Unassigned",
    "time_not_specified": "Time not specified",
    "date_not_specified": "Deadline not specified",
}

STATUSES = {
    "PENDING": "Pending",
    "COMPLETED": "Completed",
    "OVERDUE": "Overdue",
    "CANCELLED": "Cancelled",
}

REVIEW_NOTE = "This item was flagged for review before final approval."

SIGNATURE = "Regards,\nNexa"


def greeting(name: str) -> str:
    name = (name or "").strip()
    return f"Dear {name}," if name else "Dear colleague,"


def report_intro(meeting_title: str, count: int) -> str:
    if count == 0:
        return (
            f"Please find below the action report for “{meeting_title}”. "
            "No action items or deadlines were recorded for this meeting."
        )
    if count == 1:
        return (
            f"Please find below the action report for “{meeting_title}”, "
            "covering one approved action item and its deadline."
        )
    return (
        f"Please find below the action report for “{meeting_title}”, "
        f"covering {count} approved action items and their deadlines."
    )


def report_closing() -> str:
    return (
        "Kindly observe the deadlines listed above. "
        "Please let us know if any item requires correction."
    )


def reminder_intro(task: str, due_phrase_text: str) -> str:
    return (
        f"This is a reminder that your assigned action item "
        f"“{task}” {due_phrase_text}."
    )


def reminder_closing() -> str:
    return "If the task is already complete, please update its status in Nexa."


def due_phrase(days_until: "int | None") -> str:
    if days_until is None:
        return "has no deadline set yet"
    if days_until < 0:
        overdue = abs(days_until)
        return "is 1 day overdue" if overdue == 1 else f"is {overdue} days overdue"
    if days_until == 0:
        return "is due today"
    if days_until == 1:
        return "is due tomorrow"
    return f"is due in {days_until} days"


def subject_report(meeting_title: str, meeting_date: str) -> str:
    return f"[Nexa] Meeting Action Report — {meeting_title} — {meeting_date}"


def subject_reminder(task: str, days_until: "int | None") -> str:
    """e.g. "[Nexa Reminder] Database Integration — Due Tomorrow" (Section 11)."""
    return f"[Nexa Reminder] {task} — {_subject_due(days_until)}"


def _subject_due(days_until: "int | None") -> str:
    if days_until is None:
        return "No Deadline Set"
    if days_until < 0:
        overdue = abs(days_until)
        return "1 Day Overdue" if overdue == 1 else f"{overdue} Days Overdue"
    if days_until == 0:
        return "Due Today"
    if days_until == 1:
        return "Due Tomorrow"
    return f"Due in {days_until} Days"
