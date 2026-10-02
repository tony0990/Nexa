"""Paired English/Arabic lexicon — the BILINGUAL mode (Sections 10.3, 24.1).

Section 10.3 fixes the layout: labels are paired `English | Arabic`, and a date
is shown in both forms.

    NEXA
    Meeting Action Report | تقرير مهام الاجتماع

    Meeting | الاجتماع
    Digital Transformation Weekly Meeting

    Date | التاريخ
    4 September 2026 | 4 سبتمبر 2026

    Action Items | المهام

Note what is *not* paired. Employee names are never mechanically translated,
and task text is never translated either — it is approved data, and
re-expressing it in a second language would be inventing report content, which
Section 24.1 forbids. So a bilingual report pairs the **frame** (labels, dates,
salutation, intro, closing) and shows the **data** once, exactly as approved.
That is also why there is no third date engine here: `ReportFormatter` composes
the Arabic and English formatters and joins their output.

The base direction is LTR because Section 10.3's layout leads with English. The
Arabic half of each pair carries `dir="auto"` in the templates so it still
shapes and aligns correctly inside an LTR document.

This is one email, not two sends: `EmailLanguage.BILINGUAL` is a rendering mode.
"""

from __future__ import annotations

from . import arabic, english

DIRECTION = "ltr"
LANG_ATTR = "en"

#: Joins the two halves of every paired string.
SEPARATOR = " | "

#: Separates the English and Arabic halves of a multi-sentence paragraph.
PARAGRAPH_SEPARATOR = "\n\n"

# Kept so anything reaching for a month or weekday name on this module gets the
# English set rather than an AttributeError. Paired dates are built by the
# formatter, which has both single-language formatters to hand.
MONTHS = english.MONTHS
WEEKDAYS = english.WEEKDAYS
MERIDIEM = english.MERIDIEM


def pair(english_text: str, arabic_text: str) -> str:
    """`English | Arabic`, dropping an empty half rather than leaving a bare bar."""
    left = (english_text or "").strip()
    right = (arabic_text or "").strip()
    if not left:
        return right
    if not right:
        return left
    if left == right:
        # Identical halves happen for values that are not language-specific,
        # such as an unresolved spoken owner name. Showing it twice would look
        # like a rendering bug.
        return left
    return f"{left}{SEPARATOR}{right}"


LABELS = {
    key: pair(value, arabic.LABELS[key]) for key, value in english.LABELS.items()
}

STATUSES = {
    key: pair(value, arabic.STATUSES[key]) for key, value in english.STATUSES.items()
}

REVIEW_NOTE = pair(english.REVIEW_NOTE, arabic.REVIEW_NOTE)

# The signature is already two lines; pairing it inline would be unreadable, so
# the halves are stacked.
SIGNATURE = f"{english.SIGNATURE}{PARAGRAPH_SEPARATOR}{arabic.SIGNATURE}"


def greeting(name: str) -> str:
    """Both salutations, stacked. The name itself is written once per half."""
    return f"{english.greeting(name)}{PARAGRAPH_SEPARATOR}{arabic.greeting(name)}"


def report_intro(meeting_title: str, count: int) -> str:
    return (
        f"{english.report_intro(meeting_title, count)}"
        f"{PARAGRAPH_SEPARATOR}"
        f"{arabic.report_intro(meeting_title, count)}"
    )


def report_closing() -> str:
    return (
        f"{english.report_closing()}"
        f"{PARAGRAPH_SEPARATOR}"
        f"{arabic.report_closing()}"
    )


def reminder_intro(task: str, due_phrase_text: str) -> str:
    """Both sentences, each with its own urgency phrase.

    `due_phrase_text` arrives already paired, so it is not reused here: each
    half gets the phrase in its own language instead, or the English sentence
    would carry an Arabic clause.
    """
    return (
        f"{english.reminder_intro(task, due_phrase_text)}"
        f"{PARAGRAPH_SEPARATOR}"
        f"{arabic.reminder_intro(task, due_phrase_text)}"
    )


def reminder_closing() -> str:
    return (
        f"{english.reminder_closing()}"
        f"{PARAGRAPH_SEPARATOR}"
        f"{arabic.reminder_closing()}"
    )


def due_phrase(days_until: "int | None") -> str:
    return pair(english.due_phrase(days_until), arabic.due_phrase(days_until))


def subject_report(meeting_title: str, meeting_date: str) -> str:
    """One subject line, English-led.

    A fully paired subject would be roughly twice as long as what Gmail shows
    on a phone, so the Arabic half is the short title only and the date — which
    `meeting_date` already carries in both forms — is left to the body.
    """
    return f"[Nexa] Meeting Action Report | تقرير مهام الاجتماع — {meeting_title}"


def subject_reminder(task: str, days_until: "int | None") -> str:
    return f"[Nexa Reminder | تذكير] {task} — {english._subject_due(days_until)}"
