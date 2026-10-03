from __future__ import annotations
from dataclasses import dataclass
from typing import Optional, Protocol


@dataclass
class Employee:
    id: int
    full_name: str = ""
    email: Optional[str] = None
    department: Optional[str] = None
    job_title: Optional[str] = None
    active: bool = True


@dataclass
class DeliveryTarget:
    delivery_kind: str            # REPORT | REMINDER
    target_type: str              # ALL | MEETING_PARTICIPANTS | ROLE | EMPLOYEE | ASSIGNEE
    target_id: Optional[int] = None
    meeting_id: Optional[int] = None
    action_item_id: Optional[int] = None


class RecipientResolver(Protocol):
    def resolve(self, targets: list[DeliveryTarget]) -> list[Employee]: ...
