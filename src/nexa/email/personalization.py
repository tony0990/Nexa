"""Per-recipient reminder content (Sections 11 and 36).

The rule that drives this module: *"A recipient should receive only the tasks
relevant to them unless the admin explicitly targets them for broader
reminders."*

That is a privacy boundary, not a formatting preference. A meeting report is a
shared document and goes out identically to everyone selected; a reminder is
operational mail about one person's own commitments, and leaking a colleague's
overdue task into it is a real disclosure. So the default is strict ownership
matching, and the broader behaviour is opt-in through `include_unassigned` /
`explicit_targets`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

from ..contracts.meetings import ActionItem, ActionStatus
from ..contracts.people import Employee

# A completed or cancelled task is not reminded about. Member 5 also checks this
# at claim time (Section 25.5, "completed task"); doing it here too means a
# reminder built from a stale action list cannot nag about finished work.
REMINDABLE_STATUSES = frozenset({ActionStatus.PENDING.value, ActionStatus.OVERDUE.value})


@dataclass(frozen=True)
class RecipientBundle:
    """One employee and the actions a reminder to them may mention."""

    employee: Employee
    actions: Sequence[ActionItem] = field(default_factory=tuple)

    def __bool__(self) -> bool:
        return bool(self.actions)


def is_remindable(action: ActionItem) -> bool:
    status = str(getattr(action.status, "value", action.status) or "")
    return status in REMINDABLE_STATUSES


def owns(action: ActionItem, employee: Employee) -> bool:
    """True when `employee` is the assigned owner of `action`.

    Matching is by employee id only. `owner_raw_text` is deliberately *not*
    matched on: it holds a spoken name such as `أحمد`, and three employees may
    share it (Section 2.1). Guessing there would mail one person's task to
    another, which is exactly the ambiguity the review screen exists to resolve.
    """
    owner_id = getattr(action, "owner_employee_id", None)
    employee_id = getattr(employee, "id", None)
    return owner_id is not None and employee_id is not None and owner_id == employee_id


def actions_for(
    employee: Employee,
    actions: Sequence[ActionItem],
    *,
    include_unassigned: bool = False,
    only_remindable: bool = True,
) -> List[ActionItem]:
    """The subset of `actions` a reminder to `employee` may mention.

    `include_unassigned` covers the case where the admin deliberately sends an
    unowned task to someone to pick up; it is off by default because an
    unassigned action belongs to nobody and silently attaching it to everyone's
    reminder would be noise at best.
    """
    out: List[ActionItem] = []
    for action in actions:
        if only_remindable and not is_remindable(action):
            continue
        if owns(action, employee):
            out.append(action)
        elif include_unassigned and getattr(action, "owner_employee_id", None) is None:
            out.append(action)
    return out


def bundle_by_recipient(
    employees: Sequence[Employee],
    actions: Sequence[ActionItem],
    *,
    include_unassigned: bool = False,
    only_remindable: bool = True,
    skip_empty: bool = True,
) -> List[RecipientBundle]:
    """Group actions per recipient, dropping recipients with nothing due.

    `skip_empty` is what prevents Nexa's worst possible email: a reminder that
    says "you have no tasks". A recipient with no due items gets no mail.
    """
    bundles: List[RecipientBundle] = []
    for employee in employees:
        owned = actions_for(
            employee,
            actions,
            include_unassigned=include_unassigned,
            only_remindable=only_remindable,
        )
        if owned or not skip_empty:
            bundles.append(RecipientBundle(employee=employee, actions=tuple(owned)))
    return bundles


def owners_of(
    actions: Sequence[ActionItem], employees: Sequence[Employee]
) -> List[RecipientBundle]:
    """Bundles for the ASSIGNEE target type (Section 6.3).

    Only employees who actually own one of `actions` appear, so "send reminders
    to assignees" cannot widen into "send to everyone".
    """
    by_id: Dict[int, Employee] = {
        employee.id: employee
        for employee in employees
        if getattr(employee, "id", None) is not None
    }
    grouped: Dict[int, List[ActionItem]] = {}
    for action in actions:
        owner_id = getattr(action, "owner_employee_id", None)
        if owner_id is None or owner_id not in by_id:
            continue
        if not is_remindable(action):
            continue
        grouped.setdefault(owner_id, []).append(action)
    return [
        RecipientBundle(employee=by_id[owner_id], actions=tuple(owned))
        for owner_id, owned in grouped.items()
    ]


def most_urgent(actions: Sequence[ActionItem]) -> Optional[ActionItem]:
    """The action a batched reminder should lead with.

    Earliest real deadline first; items with no deadline sort last, because an
    undated task is not urgent and should not displace a dated one at the top of
    the mail.
    """
    dated = [action for action in actions if _deadline_key(action) is not None]
    if dated:
        return min(dated, key=lambda action: _deadline_key(action))
    return actions[0] if actions else None


def _deadline_key(action: ActionItem):
    if action.due_at is not None:
        return (0, action.due_at.timestamp())
    if action.due_date is not None:
        return (0, float(action.due_date.toordinal()) * 86400)
    return None
