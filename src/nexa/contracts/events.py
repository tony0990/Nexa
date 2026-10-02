"""Application-level event names shared across subsystems.

These are in-process notification names, not audit event types. Audit event
types live in `nexa.audit.event_types`.
"""

from __future__ import annotations

MEETING_CREATED = "meeting.created"
MEETING_APPROVED = "meeting.approved"
RECORDING_STARTED = "recording.started"
RECORDING_STOPPED = "recording.stopped"
EXTRACTION_COMPLETED = "extraction.completed"
ACTION_SAVED = "action.saved"
ACTION_COMPLETED = "action.completed"
REMINDER_SCHEDULED = "reminder.scheduled"
REMINDER_SENT = "reminder.sent"
EMAIL_SENT = "email.sent"
EMPLOYEE_CHANGED = "employee.changed"
SETTINGS_CHANGED = "settings.changed"
