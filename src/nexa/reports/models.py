"""Value objects the report layer renders from.

These are deliberately *presentation* objects: every field is already a string
formatted for one language, so a template never has to make a formatting or a
language decision. The domain objects they are built from (`Meeting`,
`ActionItem`, `Employee`) stay untouched in `nexa.contracts`.

Section 24.1 is explicit that approved action data is the source of truth and
the LLM never writes report prose, so nothing here invents content: every
string is either a fixed label from `arabic.py`/`english.py` or a formatted
copy of approved data.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Sequence

from ..contracts.email import DeliveryKind
from ..contracts.meetings import EmailLanguage


@dataclass(frozen=True)
class ReportRow:
    """One action item, formatted for one language.

    `evidence` is the original spoken phrase (Section 2.2). It is carried into
    the report so a recipient can see why Nexa read a commitment the way it
    did, and it is the only place casual meeting speech is allowed to appear
    verbatim in an otherwise formal email (Section 10.1).
    """

    number: int
    task: str
    owner: str
    deadline: str
    status: str
    evidence: Optional[str] = None
    needs_review: bool = False
    review_note: Optional[str] = None


@dataclass(frozen=True)
class MeetingReportContext:
    """Everything the meeting-report templates are allowed to see."""

    language: str
    direction: str
    title: str
    meeting_title: str
    meeting_date: str
    recipient_name: str
    greeting: str
    intro: str
    closing: str
    signature: str
    rows: Sequence[ReportRow] = field(default_factory=tuple)
    labels: dict = field(default_factory=dict)
    show_evidence: bool = True
    generated_at: str = ""


@dataclass(frozen=True)
class ReminderContext:
    """Everything the reminder templates are allowed to see (Section 11)."""

    language: str
    direction: str
    title: str
    recipient_name: str
    greeting: str
    intro: str
    closing: str
    signature: str
    task: str
    deadline: str
    due_phrase: str
    meeting_title: str
    labels: dict = field(default_factory=dict)
    evidence: Optional[str] = None
    generated_at: str = ""


@dataclass(frozen=True)
class ReportRequest:
    """A render request, kept separate so the UI can round-trip a preview.

    The preview screen's `[ Change Language ]` and `[ Edit Recipients ]`
    buttons (Section 9) re-render from a modified copy of this instead of
    rebuilding state from scratch.
    """

    language: str = EmailLanguage.AR.value
    delivery_kind: str = DeliveryKind.REPORT.value
    include_evidence: bool = True
    only_recipient_actions: bool = False


def resolve_language(value: Optional[str]) -> str:
    """Coerce any language input to one of the three modes in Section 24.1.

    Anything unrecognized falls back to Arabic, the default in
    `DEFAULT_SETTINGS`, rather than raising: a report must still render if a
    stale settings row holds a language this build does not know.
    """
    text = str(getattr(value, "value", value) or "").strip().upper()
    if text in {"EN", "ENGLISH"}:
        return EmailLanguage.EN.value
    if text in {"BILINGUAL", "BOTH", "AR+EN", "AR_EN"}:
        return EmailLanguage.BILINGUAL.value
    return EmailLanguage.AR.value


def is_rtl(language: str) -> bool:
    """True when the email's base direction is right-to-left.

    Bilingual is LTR: Section 10.3's layout leads with English, and the Arabic
    half of each pair is marked `dir="auto"` so it still shapes correctly inside
    an LTR document.
    """
    return resolve_language(language) == EmailLanguage.AR.value


def is_bilingual(language: Optional[str]) -> bool:
    return resolve_language(language) == EmailLanguage.BILINGUAL.value
