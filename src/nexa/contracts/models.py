from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class Employee:
    id: int
    full_name: str
    email: str
    department: str
    job_title: str
    roles: list[str] = field(default_factory=list)
    active: bool = True


@dataclass
class Role:
    id: int
    name: str
    description: str = ""
    active: bool = True


@dataclass
class Meeting:
    id: int
    title: str
    template_name: str
    audio_source: str
    participants: list[str]
    status: str
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    email_language: str = "ENGLISH"


@dataclass
class Transcript:
    raw_text: str
    confirmed_text: str
    segments: list[dict] = field(default_factory=list)


@dataclass
class ActionCandidate:
    id: int
    task: str
    owner_raw_text: str
    owner_employee_id: Optional[int]
    raw_date_phrase: str
    due_display: str
    source_text: str
    confidence: float
    review_state: str = "PENDING"
    possible_duplicate_of: Optional[int] = None
    status: str = "PENDING"


@dataclass
class ActionItem:
    id: int
    meeting_id: int
    task: str
    owner_name: str
    due_display: str
    reminder_display: str
    status: str
    source_text: str = ""
    meeting_title: str = ""
    due_iso: str = ""


@dataclass
class Reminder:
    id: int
    action_item_id: int
    scheduled_display: str
    status: str


@dataclass
class RenderedEmail:
    language: str
    subject: str
    html: str
    text: str
    sender: str
    recipients: list[str]


@dataclass
class EmailPreview:
    rendered: RenderedEmail


@dataclass
class SendResult:
    success: bool
    message_id: str = ""
    error: str = ""


@dataclass
class AuditEvent:
    created_at: str
    event_type: str
    entity_type: str
    entity_id: str
    actor: str
    detail: str


@dataclass
class RecordedAudio:
    path: str
    duration_seconds: int
    source: str
