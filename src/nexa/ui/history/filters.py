"""Pure filtering helpers for the Audit Trail and Email History screens."""

from __future__ import annotations

AUDIT_ENTITIES = ["all", "meeting", "action", "email"]
DELIVERY_STATUSES = ["all", "SENT", "FAILED", "PENDING"]
DELIVERY_KINDS = ["all", "REPORT", "REMINDER"]


def filter_audit(events, text: str = "", entity_type: str = "all"):
    """Filter by entity type and free text (matches event, 'type:id', actor, detail).

    Typing e.g. 'action:17' shows the entity history of that action.
    """
    q = (text or "").strip().lower()
    rows = list(events)
    if entity_type and entity_type != "all":
        rows = [e for e in rows if e.entity_type == entity_type]
    if q:
        rows = [
            e
            for e in rows
            if q in f"{e.event_type} {e.entity_type}:{e.entity_id} {e.actor} {e.detail}".lower()
        ]
    return rows


def filter_deliveries(rows, text: str = "", status: str = "all", kind: str = "all"):
    q = (text or "").strip().lower()
    out = list(rows)
    if status and status != "all":
        out = [r for r in out if r["status"] == status]
    if kind and kind != "all":
        out = [r for r in out if r["kind"] == kind]
    if q:
        out = [r for r in out if q in f"{r['subject']} {r['to']}".lower()]
    return out
