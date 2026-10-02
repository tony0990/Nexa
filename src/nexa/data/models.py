"""Row <-> domain mapping.

Domain models live in `nexa.contracts` because the whole team shares them.
This module is the only place that knows how those models are laid out in
SQLite, so a schema change stays inside the data layer.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime, time
from typing import Any, Dict, Optional, Sequence

from ..contracts.audit import AuditEvent
from ..contracts.email import DeliveryTarget, EmailDelivery
from ..contracts.meetings import ActionItem, Meeting, MeetingTemplate, TranscriptSegment
from ..contracts.people import Employee, Role
from ..contracts.scheduling import Reminder, ReminderRule
from ..core.timezone import parse_utc

DATE_FORMAT = "%Y-%m-%d"
TIME_FORMAT = "%H:%M"


# ----------------------------------------------------------------------
# scalar conversions
# ----------------------------------------------------------------------
def to_bool(value: Any) -> bool:
    return bool(value)


def date_to_db(value: Optional[date]) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, datetime):
        value = value.date()
    return value.strftime(DATE_FORMAT)


def date_from_db(value: Optional[str]) -> Optional[date]:
    if not value:
        return None
    return datetime.strptime(value, DATE_FORMAT).date()


def time_to_db(value: Optional[time]) -> Optional[str]:
    if value is None:
        return None
    return value.strftime(TIME_FORMAT)


def time_from_db(value: Optional[str]) -> Optional[time]:
    if not value:
        return None
    return datetime.strptime(value, TIME_FORMAT).time()


def json_to_db(value: Optional[Any]) -> Optional[str]:
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def json_from_db(value: Optional[str]) -> Optional[Any]:
    if value is None or value == "":
        return None
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        # Never let one malformed historical row break a whole audit screen.
        return {"_unparsed": value}


# ----------------------------------------------------------------------
# row -> domain
# ----------------------------------------------------------------------
def row_to_employee(row: sqlite3.Row, role_ids: Sequence[int] = ()) -> Employee:
    return Employee(
        id=row["id"],
        full_name=row["full_name"],
        email=row["email"],
        department=row["department"],
        job_title=row["job_title"],
        active=to_bool(row["active"]),
        created_at=parse_utc(row["created_at"]),
        updated_at=parse_utc(row["updated_at"]),
        role_ids=tuple(role_ids),
    )


def row_to_role(row: sqlite3.Row) -> Role:
    return Role(
        id=row["id"],
        name=row["name"],
        description=row["description"],
        active=to_bool(row["active"]),
        created_at=parse_utc(row["created_at"]),
        updated_at=parse_utc(row["updated_at"]),
    )


def row_to_meeting(row: sqlite3.Row, participant_ids: Sequence[int] = ()) -> Meeting:
    return Meeting(
        id=row["id"],
        title=row["title"],
        template_id=row["template_id"],
        started_at=parse_utc(row["started_at"]),
        ended_at=parse_utc(row["ended_at"]),
        audio_source=row["audio_source"],
        status=row["status"],
        email_language=row["email_language"],
        created_at=parse_utc(row["created_at"]),
        updated_at=parse_utc(row["updated_at"]),
        participant_ids=tuple(participant_ids),
    )


def row_to_segment(row: sqlite3.Row) -> TranscriptSegment:
    return TranscriptSegment(
        id=row["id"],
        meeting_id=row["meeting_id"],
        segment_index=row["segment_index"],
        start_ms=row["start_ms"],
        end_ms=row["end_ms"],
        raw_text=row["raw_text"],
        confirmed_text=row["confirmed_text"],
        language_hint=row["language_hint"],
        created_at=parse_utc(row["created_at"]),
    )


def row_to_action(row: sqlite3.Row) -> ActionItem:
    return ActionItem(
        id=row["id"],
        meeting_id=row["meeting_id"],
        task=row["task"],
        owner_employee_id=row["owner_employee_id"],
        owner_raw_text=row["owner_raw_text"],
        raw_date_phrase=row["raw_date_phrase"],
        due_date=date_from_db(row["due_date"]),
        due_time=time_from_db(row["due_time"]),
        due_at=parse_utc(row["due_at"]),
        source_text=row["source_text"],
        confidence=row["confidence"],
        review_state=row["review_state"],
        status=row["status"],
        completed_at=parse_utc(row["completed_at"]),
        created_at=parse_utc(row["created_at"]),
        updated_at=parse_utc(row["updated_at"]),
    )


def row_to_reminder(row: sqlite3.Row) -> Reminder:
    return Reminder(
        id=row["id"],
        action_item_id=row["action_item_id"],
        scheduled_at=parse_utc(row["scheduled_at"]),
        status=row["status"],
        attempt_count=row["attempt_count"],
        next_attempt_at=parse_utc(row["next_attempt_at"]),
        claimed_at=parse_utc(row["claimed_at"]),
        sent_at=parse_utc(row["sent_at"]),
        last_error=row["last_error"],
        idempotency_key=row["idempotency_key"],
        created_at=parse_utc(row["created_at"]),
        updated_at=parse_utc(row["updated_at"]),
    )


def row_to_reminder_rule(row: sqlite3.Row) -> ReminderRule:
    return ReminderRule(
        id=row["id"],
        action_item_id=row["action_item_id"],
        rule_type=row["rule_type"],
        offset_minutes=row["offset_minutes"],
        fixed_local_time=time_from_db(row["fixed_local_time"]),
        enabled=to_bool(row["enabled"]),
        created_at=parse_utc(row["created_at"]),
    )


def row_to_delivery_target(row: sqlite3.Row) -> DeliveryTarget:
    return DeliveryTarget(
        id=row["id"],
        meeting_id=row["meeting_id"],
        action_item_id=row["action_item_id"],
        delivery_kind=row["delivery_kind"],
        target_type=row["target_type"],
        target_id=row["target_id"],
        created_at=parse_utc(row["created_at"]),
    )


def row_to_email_delivery(row: sqlite3.Row) -> EmailDelivery:
    return EmailDelivery(
        id=row["id"],
        meeting_id=row["meeting_id"],
        action_item_id=row["action_item_id"],
        reminder_id=row["reminder_id"],
        recipient_employee_id=row["recipient_employee_id"],
        recipient_email=row["recipient_email"],
        subject=row["subject"],
        language=row["language"],
        status=row["status"],
        gmail_message_id=row["gmail_message_id"],
        attempted_at=parse_utc(row["attempted_at"]),
        sent_at=parse_utc(row["sent_at"]),
        error_message=row["error_message"],
    )


def row_to_template(row: sqlite3.Row) -> MeetingTemplate:
    return MeetingTemplate(
        id=row["id"],
        name=row["name"],
        default_title=row["default_title"],
        default_audio_source=row["default_audio_source"],
        default_email_language=row["default_email_language"],
        default_report_target_config=json_from_db(row["default_report_target_config"]),
        default_reminder_target_config=json_from_db(row["default_reminder_target_config"]),
        default_reminder_rule_config=json_from_db(row["default_reminder_rule_config"]),
        active=to_bool(row["active"]),
        created_at=parse_utc(row["created_at"]),
        updated_at=parse_utc(row["updated_at"]),
    )


def row_to_audit_event(row: sqlite3.Row) -> AuditEvent:
    return AuditEvent(
        id=row["id"],
        actor_type=row["actor_type"],
        actor_id=row["actor_id"],
        event_type=row["event_type"],
        entity_type=row["entity_type"],
        entity_id=row["entity_id"],
        old_value=json_from_db(row["old_value_json"]),
        new_value=json_from_db(row["new_value_json"]),
        metadata=json_from_db(row["metadata_json"]),
        created_at=parse_utc(row["created_at"]),
    )


def employee_snapshot(employee: Employee) -> Dict[str, Any]:
    """Compact dict used as audit old/new values."""
    return {
        "id": employee.id,
        "full_name": employee.full_name,
        "email": employee.email,
        "department": employee.department,
        "job_title": employee.job_title,
        "active": employee.active,
    }


def role_snapshot(role: Role) -> Dict[str, Any]:
    return {
        "id": role.id,
        "name": role.name,
        "description": role.description,
        "active": role.active,
    }
