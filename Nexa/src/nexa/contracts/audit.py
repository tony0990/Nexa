from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Optional, Protocol


@dataclass
class AuditEvent:
    actor_type: str
    actor_id: Optional[str]
    event_type: str
    entity_type: str
    entity_id: Optional[int]
    old_value: Optional[dict] = None
    new_value: Optional[dict] = None
    metadata: dict[str, Any] = field(default_factory=dict)


class AuditService(Protocol):
    def record(self, event: AuditEvent) -> Any: ...
