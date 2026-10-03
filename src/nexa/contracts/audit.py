"""Shared audit contracts. The append-only audit log is owned by Member 1."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional, Protocol, Sequence, runtime_checkable


class ActorType(str, Enum):
    USER = "USER"
    SYSTEM = "SYSTEM"
    WORKER = "WORKER"


@dataclass(frozen=True)
class AuditEvent:
    id: Optional[int] = None
    actor_type: str = ActorType.USER.value
    actor_id: Optional[str] = None
    event_type: str = ""
    entity_type: str = ""
    entity_id: Optional[str] = None
    old_value: Optional[dict] = None
    new_value: Optional[dict] = None
    metadata: Optional[dict] = None
    created_at: Optional[datetime] = None


@runtime_checkable
class AuditService(Protocol):
    def record(self, event: AuditEvent) -> AuditEvent: ...

    def history(self, entity_type: str, entity_id: object) -> Sequence[AuditEvent]: ...
