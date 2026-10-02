"""Shared meeting/action domain models and repository contracts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time
from enum import Enum
from typing import Optional, Protocol, Sequence


class MeetingStatus(str, Enum):
    DRAFT = "DRAFT"
    RECORDING = "RECORDING"
    PROCESSING = "PROCESSING"
    PENDING_REVIEW = "PENDING_REVIEW"
    APPROVED = "APPROVED"
    ARCHIVED = "ARCHIVED"


class ActionStatus(str, Enum):
    PENDING = "PENDING"
    COMPLETED = "COMPLETED"
    OVERDUE = "OVERDUE"
    CANCELLED = "CANCELLED"


class ReviewState(str, Enum):
    NEEDS_REVIEW = "NEEDS_REVIEW"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class EmailLanguage(str, Enum):
    AR = "AR"
    EN = "EN"


class AudioSource(str, Enum):
    MICROPHONE = "MICROPHONE"
    COMPUTER = "COMPUTER"
    BOTH = "BOTH"


@dataclass(frozen=True)
class Meeting:
    id: Optional[int] = None
    title: str = ""
    template_id: Optional[int] = None
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    audio_source: str = AudioSource.MICROPHONE.value
    status: str = MeetingStatus.DRAFT.value
    email_language: str = EmailLanguage.AR.value
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    participant_ids: tuple[int, ...] = ()


@dataclass(frozen=True)
class TranscriptSegment:
    id: Optional[int] = None
    meeting_id: Optional[int] = None
    segment_index: int = 0
    start_ms: int = 0
    end_ms: int = 0
    raw_text: str = ""
    confirmed_text: Optional[str] = None
    language_hint: Optional[str] = None
    created_at: Optional[datetime] = None


@dataclass(frozen=True)
class ActionItem:
    """An approved, trackable commitment extracted from a meeting.

    ``source_text`` and ``raw_date_phrase`` are the original spoken evidence and
    must never be overwritten by the normalized interpretation (Section 2.2).
    """

    id: Optional[int] = None
    meeting_id: Optional[int] = None
    task: str = ""
    owner_employee_id: Optional[int] = None
    owner_raw_text: Optional[str] = None
    raw_date_phrase: Optional[str] = None
    due_date: Optional[date] = None
    due_time: Optional[time] = None
    due_at: Optional[datetime] = None
    source_text: Optional[str] = None
    confidence: Optional[float] = None
    review_state: str = ReviewState.NEEDS_REVIEW.value
    status: str = ActionStatus.PENDING.value
    completed_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


@dataclass(frozen=True)
class MeetingTemplate:
    id: Optional[int] = None
    name: str = ""
    default_title: Optional[str] = None
    default_audio_source: Optional[str] = None
    default_email_language: Optional[str] = None
    default_report_target_config: Optional[dict] = None
    default_reminder_target_config: Optional[dict] = None
    default_reminder_rule_config: Optional[dict] = None
    active: bool = True
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class MeetingRepository(Protocol):
    def create(self, meeting: Meeting) -> Meeting: ...

    def get(self, meeting_id: int) -> Optional[Meeting]: ...

    def save_action(self, action: ActionItem) -> ActionItem: ...

    def actions_for_meeting(self, meeting_id: int) -> Sequence[ActionItem]: ...
