"""Frozen cross-team contracts.

Section 17: this package is a kickoff artifact. Changing it requires team
agreement; individual members implement these interfaces inside their own
packages and never import each other's private modules.
"""

from .audio import AudioRecordingService, RecordedAudio
from .audit import ActorType, AuditEvent, AuditService
from .email import (
    DeliveryKind,
    DeliveryStatus,
    DeliveryTarget,
    EmailDelivery,
    EmailSender,
    RecipientResolver,
    RenderedEmail,
    SendResult,
    TargetType,
)
from .extraction import ActionCandidate, ExtractionService
from .meetings import (
    ActionItem,
    ActionStatus,
    AudioSource,
    EmailLanguage,
    Meeting,
    MeetingRepository,
    MeetingStatus,
    MeetingTemplate,
    ReviewState,
    TranscriptSegment,
)
from .people import Employee, EmployeeRepository, PeopleService, Role
from .scheduling import (
    Reminder,
    ReminderQueue,
    ReminderRule,
    ReminderRuleType,
    ReminderStatus,
)
from .transcription import Transcript, TranscriptionService

__all__ = [
    "ActionCandidate",
    "ActionItem",
    "ActionStatus",
    "ActorType",
    "AudioRecordingService",
    "AudioSource",
    "AuditEvent",
    "AuditService",
    "DeliveryKind",
    "DeliveryStatus",
    "DeliveryTarget",
    "EmailDelivery",
    "EmailLanguage",
    "EmailSender",
    "Employee",
    "EmployeeRepository",
    "ExtractionService",
    "Meeting",
    "MeetingRepository",
    "MeetingStatus",
    "MeetingTemplate",
    "PeopleService",
    "RecipientResolver",
    "RecordedAudio",
    "Reminder",
    "ReminderQueue",
    "ReminderRule",
    "ReminderRuleType",
    "ReminderStatus",
    "RenderedEmail",
    "ReviewState",
    "Role",
    "SendResult",
    "TargetType",
    "Transcript",
    "TranscriptSegment",
    "TranscriptionService",
]
