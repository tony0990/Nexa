"""Reminder state machine, reminder types, idempotency keys, audit names."""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from nexa.audit import event_types
from typing import Optional


class ReminderStatus(str, Enum):
    PENDING = "PENDING"
    CLAIMED = "CLAIMED"
    SENDING = "SENDING"
    SENT = "SENT"
    RETRY_WAIT = "RETRY_WAIT"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    SNOOZED = "SNOOZED"
    SKIPPED_COMPLETED = "SKIPPED_COMPLETED"


class ReminderType(str, Enum):
    PREVIOUS_DAY = "PREVIOUS_DAY"      # default: previous day 20:00
    EVENT_DAY = "EVENT_DAY"            # default: event day 08:00
    EARLY_EVENT = "EARLY_EVENT"        # smart rule for early events
    OFFSET_BEFORE = "OFFSET_BEFORE"    # N minutes before the deadline
    SNOOZE = "SNOOZE"                  # occurrence created by snooze


class ActionStatus:
    PENDING = "PENDING"
    COMPLETED = "COMPLETED"
    OVERDUE = "OVERDUE"
    CANCELLED = "CANCELLED"


S = ReminderStatus
ALLOWED_TRANSITIONS: dict[ReminderStatus, frozenset[ReminderStatus]] = {
    S.PENDING: frozenset({S.CLAIMED, S.CANCELLED, S.SNOOZED, S.SKIPPED_COMPLETED}),
    S.RETRY_WAIT: frozenset({S.CLAIMED, S.CANCELLED, S.SNOOZED, S.SKIPPED_COMPLETED}),
    S.CLAIMED: frozenset({S.SENDING, S.PENDING, S.CANCELLED, S.SKIPPED_COMPLETED, S.FAILED}),
    S.SENDING: frozenset({S.SENT, S.RETRY_WAIT, S.FAILED}),
    S.SNOOZED: frozenset(),            # replaced by a new PENDING occurrence
    S.SENT: frozenset(),
    S.FAILED: frozenset(),
    S.CANCELLED: frozenset(),
    S.SKIPPED_COMPLETED: frozenset(),
}

UNSENT_STATES = (S.PENDING, S.RETRY_WAIT)
# Unsent + currently claimed (a worker's later conditional UPDATE will then fail safely).
CANCELLABLE_STATES = (S.PENDING, S.RETRY_WAIT, S.CLAIMED)
TERMINAL_STATES = frozenset({S.SENT, S.FAILED, S.CANCELLED, S.SKIPPED_COMPLETED, S.SNOOZED})


class InvalidTransition(Exception):
    pass


def can_transition(src: ReminderStatus, dst: ReminderStatus) -> bool:
    return ReminderStatus(dst) in ALLOWED_TRANSITIONS[ReminderStatus(src)]


def assert_transition(src: ReminderStatus, dst: ReminderStatus) -> None:
    if not can_transition(src, dst):
        raise InvalidTransition(f"{src} -> {dst} is not allowed")


def make_idempotency_key(
    action_id: int,
    reminder_type: ReminderType,
    scheduled_at: datetime,
    extra: Optional[str] = None,
) -> str:
    ts = scheduled_at.astimezone(timezone.utc).strftime("%Y%m%dT%H%MZ")
    key = f"action:{action_id}:{ReminderType(reminder_type).value}:{ts}"
    return f"{key}:{extra}" if extra else key


def reminder_type_from_key(key: str) -> Optional[ReminderType]:
    parts = (key or "").split(":")
    if len(parts) >= 3:
        try:
            return ReminderType(parts[2])
        except ValueError:
            return None
    return None


class AuditNames:
    """Audit event names, re-exported from Member 1's canonical vocabulary.

    These strings are written into `audit_events.event_type` forever and the
    audit-trail screen filters on them, so there can only be one spelling.
    This class originally defined its own — "reminder.create" against Member 1's
    "reminder.created", and so on — which would have split the history for every
    reminder event in two and left half of it invisible to the UI.

    Aliases, not copies: adding a name in `nexa.audit.event_types` is enough,
    and a renamed constant fails here at import rather than silently writing an
    unknown event.
    """

    REMINDER_CREATE = event_types.REMINDER_CREATED
    REMINDER_CANCEL = event_types.REMINDER_CANCELLED
    REMINDER_SEND = event_types.REMINDER_SENT
    REMINDER_FAIL = event_types.REMINDER_FAILED
    REMINDER_RETRY = event_types.REMINDER_RETRY_SCHEDULED
    REMINDER_SKIP_COMPLETED = event_types.REMINDER_SKIPPED_COMPLETED
    REMINDER_SNOOZE = event_types.REMINDER_SNOOZED
    REMINDER_LATE_RECOVERY = event_types.REMINDER_LATE_RECOVERED
    ACTION_COMPLETE = event_types.ACTION_COMPLETED
    ACTION_RESCHEDULE = event_types.ACTION_RESCHEDULED
    WORKER_START = event_types.WORKER_STARTED
    WORKER_STOP = event_types.WORKER_STOPPED
