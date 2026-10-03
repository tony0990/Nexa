"""Audit event and entity type constants (Section 12).

Event names are stable strings: they are written into the database forever, so
they are never renamed, only added to. The UI translates them for display.
"""

from __future__ import annotations

# ---------------------------------------------------------------- entities
ENTITY_MEETING = "meeting"
ENTITY_ACTION_ITEM = "action_item"
ENTITY_EMPLOYEE = "employee"
ENTITY_ROLE = "role"
ENTITY_REMINDER = "reminder"
ENTITY_EMAIL_DELIVERY = "email_delivery"
ENTITY_TEMPLATE = "meeting_template"
ENTITY_SETTING = "setting"
ENTITY_TRANSCRIPT = "transcript"
ENTITY_WORKER = "worker"

# ------------------------------------------------------------------ meeting
MEETING_CREATED = "meeting.created"
MEETING_UPDATED = "meeting.updated"
MEETING_DELETED = "meeting.deleted"
MEETING_STATUS_CHANGED = "meeting.status_changed"
MEETING_APPROVED = "meeting.approved"
MEETING_PARTICIPANTS_CHANGED = "meeting.participants_changed"

RECORDING_STARTED = "recording.started"
RECORDING_STOPPED = "recording.stopped"
EXTRACTION_COMPLETED = "extraction.completed"
TRANSCRIPT_SEGMENT_CONFIRMED = "transcript.segment_confirmed"
TRANSCRIPT_DELETED = "transcript.deleted"

# -------------------------------------------------------------- action item
ACTION_CREATED = "action.created"
ACTION_UPDATED = "action.updated"
ACTION_DELETED = "action.deleted"
ACTION_OWNER_ASSIGNED = "action.owner_assigned"
ACTION_STATUS_CHANGED = "action.status_changed"
ACTION_COMPLETED = "action.completed"
ACTION_CANCELLED = "action.cancelled"
ACTION_RESCHEDULED = "action.rescheduled"
ACTION_DUPLICATE_MERGED = "action.duplicate_merged"
ACTION_REVIEW_STATE_CHANGED = "action.review_state_changed"

# ----------------------------------------------------------------- reminder
REMINDER_CREATED = "reminder.created"
REMINDER_CANCELLED = "reminder.cancelled"
REMINDER_SNOOZED = "reminder.snoozed"
REMINDER_SENT = "reminder.sent"
REMINDER_FAILED = "reminder.failed"
REMINDER_SKIPPED_COMPLETED = "reminder.skipped_completed"
# Added for Member 5's worker. A retry is not a failure and a late recovery is
# not an ordinary send: collapsing either into the names above would make the
# audit trail unable to distinguish "we are trying again" from "we gave up".
REMINDER_RETRY_SCHEDULED = "reminder.retry_scheduled"
REMINDER_LATE_RECOVERED = "reminder.late_recovered"

# -------------------------------------------------------------------- email
EMAIL_QUEUED = "email.queued"
EMAIL_SENT = "email.sent"
EMAIL_FAILED = "email.failed"
REPORT_SENT = "report.sent"

# ----------------------------------------------------------------- employee
EMPLOYEE_CREATED = "employee.created"
EMPLOYEE_UPDATED = "employee.updated"
EMPLOYEE_DEACTIVATED = "employee.deactivated"
EMPLOYEE_REACTIVATED = "employee.reactivated"
EMPLOYEE_DELETED = "employee.deleted"

# --------------------------------------------------------------------- role
ROLE_CREATED = "role.created"
ROLE_UPDATED = "role.updated"
ROLE_DELETED = "role.deleted"
ROLE_ASSIGNED = "role.assigned"
ROLE_UNASSIGNED = "role.unassigned"

# ----------------------------------------------------------------- template
TEMPLATE_CREATED = "template.created"
TEMPLATE_UPDATED = "template.updated"
TEMPLATE_DELETED = "template.deleted"

# ----------------------------------------------------------------- settings
SETTING_CHANGED = "setting.changed"

# ------------------------------------------------------------------- worker
WORKER_STARTED = "worker.started"
WORKER_STOPPED = "worker.stopped"

# ------------------------------------------------------------------- system
DATABASE_BACKED_UP = "system.database_backed_up"
DATABASE_RESTORED = "system.database_restored"

ALL_EVENT_TYPES = tuple(
    value
    for name, value in sorted(globals().items())
    if name.isupper() and not name.startswith("ENTITY_") and isinstance(value, str)
)
