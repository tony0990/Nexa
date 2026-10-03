"""Fakes for dependencies Member 5 does not own (spec 25.4)."""
from __future__ import annotations

from nexa.contracts.email import RenderedEmail, SendResult
from nexa.contracts.people import Employee


class FakeEmailSender:
    def __init__(self):
        self.sent: list[RenderedEmail] = []

    def send(self, rendered_email):
        self.sent.append(rendered_email)
        return SendResult(ok=True, gmail_message_id=f"fake-{len(self.sent)}")


class ScriptedEmailSender(FakeEmailSender):
    """Fails the first `fail_times` calls (retryable unless permanent=True)."""
    def __init__(self, fail_times=0, permanent=False):
        super().__init__()
        self.fail_times, self.permanent, self.calls = fail_times, permanent, 0

    def send(self, rendered_email):
        self.calls += 1
        if self.calls <= self.fail_times:
            return SendResult(ok=False, error_message="boom", retryable=not self.permanent)
        return super().send(rendered_email)


class FakeResolver:
    def __init__(self, employees):
        self.employees = {e.id: e for e in employees}

    def resolve(self, targets):
        out = []
        for t in targets:
            if t.target_type in ("ASSIGNEE", "EMPLOYEE") and t.target_id in self.employees:
                out.append(self.employees[t.target_id])
            elif t.target_type == "ALL":
                out.extend(self.employees.values())
        return out


class FakeBuilder:
    """Stands in for Member 4's ReportService.build_reminder.

    Returns the canonical RenderedEmail, which addresses one recipient through
    `to_email` — `email_deliveries.recipient_email` is a single address, so a
    list was never storable.
    """

    def build_reminder(self, employee, action, meeting, language):
        return RenderedEmail(
            to_email=employee.email or "",
            to_name=employee.full_name,
            subject=f"[Nexa Reminder] {action.task}",
            text_body=f"Dear {employee.full_name}",
            language=language,
        )


class RecordingAudit:
    def __init__(self):
        self.events = []

    def record(self, event):
        self.events.append(event)

    def types(self):
        return [e.event_type for e in self.events]
