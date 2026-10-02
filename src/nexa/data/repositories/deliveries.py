"""Delivery targets and email delivery history.

Member 4 sends the mail and hands back the result; this repository is where
that result is persisted, and where the abstract recipient selections chosen
in the UI are stored before resolution.
"""

from __future__ import annotations

from datetime import datetime
from typing import Iterable, List, Optional

from ...contracts.email import DeliveryStatus, DeliveryTarget, EmailDelivery
from ...core.errors import NotFoundError
from ...core.timezone import isoformat_utc
from ...core.validation import normalize_email
from ..models import row_to_delivery_target, row_to_email_delivery
from ..transactions import unit_of_work
from .base import BaseRepository

_TARGET_COLUMNS = (
    "id, meeting_id, action_item_id, delivery_kind, target_type, target_id, created_at"
)
_DELIVERY_COLUMNS = (
    "id, meeting_id, action_item_id, reminder_id, recipient_employee_id, "
    "recipient_email, subject, language, status, gmail_message_id, attempted_at, "
    "sent_at, error_message"
)


class DeliveryRepository(BaseRepository):
    # ------------------------------------------------------------------
    # delivery targets
    # ------------------------------------------------------------------
    def add_target(self, target: DeliveryTarget) -> DeliveryTarget:
        with unit_of_work(self.db):
            self.db.execute(
                """
                INSERT INTO delivery_targets (
                    meeting_id, action_item_id, delivery_kind, target_type,
                    target_id, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    target.meeting_id,
                    target.action_item_id,
                    getattr(target.delivery_kind, "value", target.delivery_kind),
                    getattr(target.target_type, "value", target.target_type),
                    target.target_id,
                    self.now_str(),
                ),
            )
            target_id = self._last_insert_id()
        row = self.db.query_one(
            f"SELECT {_TARGET_COLUMNS} FROM delivery_targets WHERE id = ?", (target_id,)
        )
        return row_to_delivery_target(row)

    def set_targets_for_meeting(
        self, meeting_id: int, delivery_kind: str, targets: Iterable[DeliveryTarget]
    ) -> List[DeliveryTarget]:
        """Replace a meeting's recipient selection for one delivery kind."""
        kind = getattr(delivery_kind, "value", delivery_kind)
        with unit_of_work(self.db):
            self.db.execute(
                "DELETE FROM delivery_targets WHERE meeting_id = ? AND delivery_kind = ?",
                (meeting_id, kind),
            )
            saved = []
            for target in targets:
                saved.append(
                    self.add_target(
                        DeliveryTarget(
                            meeting_id=meeting_id,
                            action_item_id=target.action_item_id,
                            delivery_kind=kind,
                            target_type=target.target_type,
                            target_id=target.target_id,
                        )
                    )
                )
        return saved

    def targets_for_meeting(
        self, meeting_id: int, delivery_kind: Optional[str] = None
    ) -> List[DeliveryTarget]:
        sql = f"SELECT {_TARGET_COLUMNS} FROM delivery_targets WHERE meeting_id = ?"
        params: list = [meeting_id]
        if delivery_kind is not None:
            sql += " AND delivery_kind = ?"
            params.append(getattr(delivery_kind, "value", delivery_kind))
        sql += " ORDER BY id"
        return [row_to_delivery_target(row) for row in self.db.query_all(sql, params)]

    def targets_for_action(
        self, action_item_id: int, delivery_kind: Optional[str] = None
    ) -> List[DeliveryTarget]:
        sql = f"SELECT {_TARGET_COLUMNS} FROM delivery_targets WHERE action_item_id = ?"
        params: list = [action_item_id]
        if delivery_kind is not None:
            sql += " AND delivery_kind = ?"
            params.append(getattr(delivery_kind, "value", delivery_kind))
        sql += " ORDER BY id"
        return [row_to_delivery_target(row) for row in self.db.query_all(sql, params)]

    def delete_target(self, target_id: int) -> None:
        with unit_of_work(self.db):
            cursor = self.db.execute("DELETE FROM delivery_targets WHERE id = ?", (target_id,))
            if cursor.rowcount == 0:
                raise NotFoundError("delivery_target", target_id)

    # ------------------------------------------------------------------
    # email deliveries
    # ------------------------------------------------------------------
    def record_attempt(self, delivery: EmailDelivery) -> EmailDelivery:
        """Create the delivery row before the send is attempted."""
        with unit_of_work(self.db):
            self.db.execute(
                """
                INSERT INTO email_deliveries (
                    meeting_id, action_item_id, reminder_id, recipient_employee_id,
                    recipient_email, subject, language, status, gmail_message_id,
                    attempted_at, sent_at, error_message
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    delivery.meeting_id,
                    delivery.action_item_id,
                    delivery.reminder_id,
                    delivery.recipient_employee_id,
                    normalize_email(delivery.recipient_email),
                    delivery.subject,
                    getattr(delivery.language, "value", delivery.language),
                    getattr(delivery.status, "value", delivery.status),
                    delivery.gmail_message_id,
                    isoformat_utc(delivery.attempted_at, self.tz) or self.now_str(),
                    isoformat_utc(delivery.sent_at, self.tz),
                    delivery.error_message,
                ),
            )
            delivery_id = self._last_insert_id()
        return self.get_or_raise(delivery_id)

    def mark_sent(
        self, delivery_id: int, gmail_message_id: str, sent_at: Optional[datetime] = None
    ) -> EmailDelivery:
        with unit_of_work(self.db):
            cursor = self.db.execute(
                "UPDATE email_deliveries SET status = 'SENT', gmail_message_id = ?, "
                "sent_at = ?, error_message = NULL WHERE id = ?",
                (
                    gmail_message_id,
                    isoformat_utc(sent_at, self.tz) or self.now_str(),
                    delivery_id,
                ),
            )
            if cursor.rowcount == 0:
                raise NotFoundError("email_delivery", delivery_id)
        return self.get_or_raise(delivery_id)

    def mark_failed(self, delivery_id: int, error_message: str) -> EmailDelivery:
        with unit_of_work(self.db):
            cursor = self.db.execute(
                "UPDATE email_deliveries SET status = 'FAILED', error_message = ? WHERE id = ?",
                (error_message, delivery_id),
            )
            if cursor.rowcount == 0:
                raise NotFoundError("email_delivery", delivery_id)
        return self.get_or_raise(delivery_id)

    def get(self, delivery_id: int) -> Optional[EmailDelivery]:
        row = self.db.query_one(
            f"SELECT {_DELIVERY_COLUMNS} FROM email_deliveries WHERE id = ?", (delivery_id,)
        )
        return None if row is None else row_to_email_delivery(row)

    def get_or_raise(self, delivery_id: int) -> EmailDelivery:
        delivery = self.get(delivery_id)
        if delivery is None:
            raise NotFoundError("email_delivery", delivery_id)
        return delivery

    def for_meeting(self, meeting_id: int) -> List[EmailDelivery]:
        rows = self.db.query_all(
            f"SELECT {_DELIVERY_COLUMNS} FROM email_deliveries WHERE meeting_id = ? "
            "ORDER BY id",
            (meeting_id,),
        )
        return [row_to_email_delivery(row) for row in rows]

    def for_employee(self, employee_id: int, limit: int = 100) -> List[EmailDelivery]:
        rows = self.db.query_all(
            f"SELECT {_DELIVERY_COLUMNS} FROM email_deliveries "
            "WHERE recipient_employee_id = ? ORDER BY id DESC LIMIT ?",
            (employee_id, limit),
        )
        return [row_to_email_delivery(row) for row in rows]

    def failed(self, limit: int = 100) -> List[EmailDelivery]:
        rows = self.db.query_all(
            f"SELECT {_DELIVERY_COLUMNS} FROM email_deliveries WHERE status = 'FAILED' "
            "ORDER BY id DESC LIMIT ?",
            (limit,),
        )
        return [row_to_email_delivery(row) for row in rows]

    def meeting_ids_with_failed_email(self) -> List[int]:
        """Backs the "Has failed email" meeting filter (Section 6.5)."""
        rows = self.db.query_all(
            "SELECT DISTINCT meeting_id FROM email_deliveries "
            "WHERE status = 'FAILED' AND meeting_id IS NOT NULL"
        )
        return [row["meeting_id"] for row in rows]

    def count(self, *, status: Optional[str] = None) -> int:
        if status is None:
            return int(self.db.query_value("SELECT COUNT(*) FROM email_deliveries", default=0))
        return int(
            self.db.query_value(
                "SELECT COUNT(*) FROM email_deliveries WHERE status = ?",
                (getattr(status, "value", status),),
                default=0,
            )
        )

    def statuses(self) -> List[str]:
        return [status.value for status in DeliveryStatus]
