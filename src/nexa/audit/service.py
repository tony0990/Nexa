"""Audit trail service.

Every subsystem records through this one service so the trail has a single
shape.

Recording deliberately happens *inside* the caller's transaction: if the
audit row cannot be written, the change it describes is rolled back too. An
audited system that silently loses entries is worse than one that refuses
the operation.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Dict, List, Optional, Sequence

from ..contracts.audit import ActorType, AuditEvent
from ..core.clock import Clock, SystemClock
from ..core.timezone import to_local
from ..data.database import Database
from ..data.repositories.audit import AuditRepository
from . import event_types


@dataclass(frozen=True)
class Actor:
    """Who performed an action. `USER` with no id means the local admin."""

    actor_type: str = ActorType.USER.value
    actor_id: Optional[str] = None

    @staticmethod
    def system() -> "Actor":
        return Actor(ActorType.SYSTEM.value, None)

    @staticmethod
    def worker() -> "Actor":
        return Actor(ActorType.WORKER.value, "NexaWorker")

    @staticmethod
    def user(actor_id: Optional[str] = None) -> "Actor":
        return Actor(ActorType.USER.value, actor_id)


@dataclass(frozen=True)
class AuditEntry:
    """Audit row flattened for display (the export view model)."""

    id: Optional[int]
    local_time: str
    event_type: str
    entity_type: str
    entity_id: Optional[str]
    actor: str
    summary: str
    old_value: Optional[Dict[str, Any]]
    new_value: Optional[Dict[str, Any]]
    changed_fields: Sequence[str]


class AuditService:
    def __init__(
        self,
        database: Database,
        clock: Optional[Clock] = None,
        *,
        default_actor: Optional[Actor] = None,
    ):
        self.db = database
        self.clock = clock or SystemClock(database.config.timezone)
        self.repo = AuditRepository(database, self.clock)
        self.default_actor = default_actor or Actor.user()

    # ------------------------------------------------------------------
    # recording
    # ------------------------------------------------------------------
    def record(self, event: AuditEvent) -> AuditEvent:
        """Append an event exactly as given."""
        return self.repo.append(event)

    def log(
        self,
        event_type: str,
        entity_type: str,
        entity_id: object = None,
        *,
        old_value: Optional[Dict[str, Any]] = None,
        new_value: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        actor: Optional[Actor] = None,
    ) -> AuditEvent:
        """Convenience wrapper used by the other services."""
        who = actor or self.default_actor
        return self.repo.append(
            AuditEvent(
                actor_type=who.actor_type,
                actor_id=who.actor_id,
                event_type=event_type,
                entity_type=entity_type,
                entity_id=None if entity_id is None else str(entity_id),
                old_value=old_value,
                new_value=new_value,
                metadata=metadata,
                created_at=self.clock.now_utc(),
            )
        )

    def log_change(
        self,
        event_type: str,
        entity_type: str,
        entity_id: object,
        before: Dict[str, Any],
        after: Dict[str, Any],
        *,
        actor: Optional[Actor] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[AuditEvent]:
        """Record only the fields that actually changed.

        Returns `None` when nothing changed, so an idempotent save does not
        fill the trail with empty rows.
        """
        changed = _changed_fields(before, after)
        if not changed:
            return None
        return self.log(
            event_type,
            entity_type,
            entity_id,
            old_value={key: before.get(key) for key in changed},
            new_value={key: after.get(key) for key in changed},
            metadata=metadata,
            actor=actor,
        )

    # ------------------------------------------------------------------
    # queries
    # ------------------------------------------------------------------
    def history(self, entity_type: str, entity_id: object, *, limit: int = 500) -> List[AuditEvent]:
        return self.repo.by_entity(entity_type, entity_id, limit=limit)

    def by_date(self, first_day: date, last_day: Optional[date] = None, *, limit: int = 1000) -> List[AuditEvent]:
        return self.repo.by_date_range(first_day, last_day or first_day, limit=limit)

    def by_actor(
        self,
        actor_type: Optional[str] = None,
        actor_id: Optional[str] = None,
        *,
        limit: int = 500,
    ) -> List[AuditEvent]:
        return self.repo.by_actor(actor_type, actor_id, limit=limit)

    def by_event_type(self, event_type: str, *, limit: int = 500) -> List[AuditEvent]:
        return self.repo.by_event_type(event_type, limit=limit)

    def recent(self, limit: int = 100) -> List[AuditEvent]:
        return self.repo.recent(limit)

    def count(self) -> int:
        return self.repo.count()

    # ------------------------------------------------------------------
    # export view model
    # ------------------------------------------------------------------
    def to_view_model(self, events: Sequence[AuditEvent]) -> List[AuditEntry]:
        """Flatten events for the audit screen or a CSV export."""
        return [self._entry(event) for event in events]

    def export_view_model(
        self, entity_type: Optional[str] = None, entity_id: object = None, *, limit: int = 500
    ) -> List[AuditEntry]:
        if entity_type is not None and entity_id is not None:
            events = self.history(entity_type, entity_id, limit=limit)
        else:
            events = list(reversed(self.recent(limit)))
        return self.to_view_model(events)

    def _entry(self, event: AuditEvent) -> AuditEntry:
        changed = _changed_fields(event.old_value or {}, event.new_value or {})
        moment = event.created_at or self.clock.now_utc()
        return AuditEntry(
            id=event.id,
            local_time=to_local(moment, self.db.config.timezone).strftime("%Y-%m-%d %H:%M"),
            event_type=event.event_type,
            entity_type=event.entity_type,
            entity_id=event.entity_id,
            actor=_actor_label(event),
            summary=_summarize(event, changed),
            old_value=event.old_value,
            new_value=event.new_value,
            changed_fields=changed,
        )


def _changed_fields(before: Dict[str, Any], after: Dict[str, Any]) -> List[str]:
    keys = set(before) | set(after)
    return sorted(key for key in keys if before.get(key) != after.get(key))


def _actor_label(event: AuditEvent) -> str:
    if event.actor_id:
        return f"{event.actor_type}:{event.actor_id}"
    return event.actor_type


def _summarize(event: AuditEvent, changed_fields: Sequence[str]) -> str:
    """One readable line, e.g. `action_item #17 action.updated (due_date)`."""
    target = event.entity_type
    if event.entity_id:
        target = f"{target} #{event.entity_id}"
    if changed_fields:
        return f"{target} {event.event_type} ({', '.join(changed_fields)})"
    return f"{target} {event.event_type}"


__all__ = ["Actor", "AuditEntry", "AuditService", "event_types"]
