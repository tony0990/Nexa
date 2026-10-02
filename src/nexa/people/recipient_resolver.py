"""Resolve abstract delivery targets to a unique list of employees.

Nexa never sends the same email twice to the same person: a combination such
as "all meeting participants + the Managers role + Ahmed specifically"
collapses to one row per employee, and to one row per email address even if
two employee records share an address (Section 36).

Inactive employees and employees without a usable address are never
recipients; they are returned separately so the email preview can tell the
admin *why* somebody is missing instead of silently dropping them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from ..contracts.email import DeliveryKind, DeliveryTarget, TargetType
from ..contracts.people import Employee
from ..core.clock import Clock, SystemClock
from ..core.errors import ValidationError
from ..core.validation import is_valid_email, normalize_email
from ..data.database import Database
from ..data.repositories.actions import ActionRepository
from ..data.repositories.employees import EmployeeRepository
from ..data.repositories.meetings import MeetingRepository
from ..data.repositories.roles import RoleRepository

SKIP_INACTIVE = "inactive"
SKIP_NO_EMAIL = "no_email"
SKIP_INVALID_EMAIL = "invalid_email"
SKIP_DUPLICATE_EMAIL = "duplicate_email"


@dataclass(frozen=True)
class SkippedRecipient:
    employee: Employee
    reason: str


@dataclass(frozen=True)
class ResolutionResult:
    recipients: Tuple[Employee, ...] = ()
    skipped: Tuple[SkippedRecipient, ...] = ()
    reasons: Dict[int, Tuple[str, ...]] = field(default_factory=dict)
    """Why each recipient is included, keyed by employee id.

    e.g. `{7: ("MEETING_PARTICIPANTS", "ROLE:3")}` — shown in the preview so
    the admin understands the list.
    """

    def __iter__(self):
        return iter(self.recipients)

    def __len__(self) -> int:
        return len(self.recipients)

    @property
    def emails(self) -> List[str]:
        return [employee.email for employee in self.recipients]


class RecipientResolver:
    def __init__(self, database: Database, clock: Optional[Clock] = None):
        self.db = database
        self.clock = clock or SystemClock(database.config.timezone)
        self.employees = EmployeeRepository(database, self.clock)
        self.roles = RoleRepository(database, self.clock)
        self.meetings = MeetingRepository(database, self.clock)
        self.actions = ActionRepository(database, self.clock)

    # ------------------------------------------------------------------
    # public API
    # ------------------------------------------------------------------
    def resolve(self, targets: Sequence[DeliveryTarget]) -> List[Employee]:
        """Contract entry point: unique, sendable employees."""
        return list(self.resolve_detailed(targets).recipients)

    def resolve_detailed(self, targets: Sequence[DeliveryTarget]) -> ResolutionResult:
        """Resolution plus the reasons and the skip list."""
        ordered_ids: List[int] = []
        reasons: Dict[int, List[str]] = {}

        for target in targets:
            label, employee_ids = self._expand(target)
            for employee_id in employee_ids:
                if employee_id not in reasons:
                    reasons[employee_id] = []
                    ordered_ids.append(employee_id)
                if label not in reasons[employee_id]:
                    reasons[employee_id].append(label)

        return self._filter_sendable(ordered_ids, reasons)

    def resolve_for_meeting(
        self, meeting_id: int, delivery_kind: str = DeliveryKind.REPORT.value
    ) -> ResolutionResult:
        """Resolve the targets stored for a meeting."""
        from ..data.repositories.deliveries import DeliveryRepository

        targets = DeliveryRepository(self.db, self.clock).targets_for_meeting(
            meeting_id, delivery_kind
        )
        return self.resolve_detailed(targets)

    def resolve_for_action(self, action_item_id: int) -> ResolutionResult:
        """Default reminder recipient: the assignee (Section 36)."""
        return self.resolve_detailed(
            [
                DeliveryTarget(
                    action_item_id=action_item_id,
                    delivery_kind=DeliveryKind.REMINDER.value,
                    target_type=TargetType.ASSIGNEE.value,
                )
            ]
        )

    # ------------------------------------------------------------------
    # internals
    # ------------------------------------------------------------------
    def _expand(self, target: DeliveryTarget) -> Tuple[str, List[int]]:
        target_type = getattr(target.target_type, "value", target.target_type)

        if target_type == TargetType.ALL.value:
            return "ALL", [employee.id for employee in self.employees.list_active()]

        if target_type == TargetType.MEETING_PARTICIPANTS.value:
            meeting_id = target.meeting_id
            if meeting_id is None:
                raise ValidationError(
                    "MEETING_PARTICIPANTS target requires meeting_id",
                    field="meeting_id",
                    code="required",
                )
            return (
                f"MEETING_PARTICIPANTS:{meeting_id}",
                list(self.meetings.participant_ids(meeting_id)),
            )

        if target_type == TargetType.ROLE.value:
            role_id = target.target_id
            if role_id is None:
                raise ValidationError(
                    "ROLE target requires target_id", field="target_id", code="required"
                )
            return f"ROLE:{role_id}", self.roles.member_ids(role_id, active_only=True)

        if target_type == TargetType.EMPLOYEE.value:
            employee_id = target.target_id
            if employee_id is None:
                raise ValidationError(
                    "EMPLOYEE target requires target_id", field="target_id", code="required"
                )
            return f"EMPLOYEE:{employee_id}", [int(employee_id)]

        if target_type == TargetType.ASSIGNEE.value:
            action_id = target.action_item_id
            if action_id is None:
                raise ValidationError(
                    "ASSIGNEE target requires action_item_id",
                    field="action_item_id",
                    code="required",
                )
            return f"ASSIGNEE:{action_id}", self.actions.owner_ids_for_actions([action_id])

        raise ValidationError(
            f"unknown target_type {target_type!r}", field="target_type", code="choice"
        )

    def _filter_sendable(
        self, employee_ids: Iterable[int], reasons: Dict[int, List[str]]
    ) -> ResolutionResult:
        recipients: List[Employee] = []
        skipped: List[SkippedRecipient] = []
        seen_emails: set = set()

        for employee in self.employees.get_many(list(employee_ids)):
            if not employee.active:
                skipped.append(SkippedRecipient(employee, SKIP_INACTIVE))
                continue
            email = normalize_email(employee.email)
            if not email:
                skipped.append(SkippedRecipient(employee, SKIP_NO_EMAIL))
                continue
            if not is_valid_email(email):
                skipped.append(SkippedRecipient(employee, SKIP_INVALID_EMAIL))
                continue
            if email in seen_emails:
                # Two employee records sharing one mailbox: send once.
                skipped.append(SkippedRecipient(employee, SKIP_DUPLICATE_EMAIL))
                continue
            seen_emails.add(email)
            recipients.append(employee)

        return ResolutionResult(
            recipients=tuple(recipients),
            skipped=tuple(skipped),
            reasons={
                employee.id: tuple(reasons.get(employee.id, ())) for employee in recipients
            },
        )
