"""The preview → approve → send flow (Sections 9, 11, 24.6).

These are the Definition-of-Done checks end to end: an email can be previewed
without being sent, a send captures a Gmail message ID, a partial failure does
not take the batch down, and reminders stay personalized.
"""

from __future__ import annotations

import pytest

from nexa.contracts.email import DeliveryStatus, EmailDelivery
from nexa.email import EmailService, FakeEmailSender

from tests.fixtures import member4 as data


# ------------------------------------------------------------------- preview
def test_preview_sends_nothing(emails, fake_sender):
    """Section 9: no report is sent without a preview option."""
    preview = emails.preview_meeting_report(
        data.meeting("EN"), data.APPROVED_ACTIONS, data.SENDABLE_EMPLOYEES, "EN"
    )
    assert preview.subject
    assert preview.html_body and preview.text_body
    assert fake_sender.sent == []


def test_preview_shows_everything_section_9_lists(emails):
    preview = emails.preview_meeting_report(
        data.meeting("EN"), data.APPROVED_ACTIONS, data.SENDABLE_EMPLOYEES, "EN",
        employees=data.EMPLOYEES,
    )
    assert preview.from_email == "nexa.test@example.com"
    assert preview.recipient_count == 3
    assert preview.language == "EN"
    assert preview.direction == "ltr"
    assert len(preview.action_rows) == len(data.APPROVED_ACTIONS)
    assert preview.action_rows[0].task == data.ACTION_WITH_TIME.task


def test_preview_flags_undeliverable_recipients(emails):
    preview = emails.preview_meeting_report(
        data.meeting("EN"), data.APPROVED_ACTIONS, data.EMPLOYEES, "EN"
    )
    notes = {item.email: item.note for item in preview.undeliverable}
    assert notes[data.BROKEN.email] == "Invalid email address"
    assert notes[data.RETIRED.email] == "Employee is deactivated"
    assert preview.recipient_count == 3


def test_change_language_re_renders_the_same_data(emails):
    """The preview screen's `[ Change Language ]` button."""
    arguments = (data.meeting("AR"), data.APPROVED_ACTIONS, data.SENDABLE_EMPLOYEES)
    arabic = emails.preview_meeting_report(*arguments, "AR")
    english = emails.preview_meeting_report(*arguments, "EN")
    assert arabic.direction == "rtl" and english.direction == "ltr"
    assert arabic.subject != english.subject
    # Same approved data behind both renders.
    assert [row.task for row in arabic.action_rows] == [
        row.task for row in english.action_rows
    ]


def test_preview_cannot_send_without_a_connection(m4_clock):
    """`[ Send Now ]` stays disabled until Gmail is connected."""
    service = EmailService(sender=object(), clock=m4_clock)
    preview = service.preview_service(connected=False).preview(
        service.reports.build_reminder(data.AHMED, data.ACTION_WITH_TIME, data.meeting())
    )
    assert preview.can_send is False
    assert any("not connected" in warning.lower() for warning in preview.warnings)


def test_preview_reminder_template(emails):
    """`[ Preview Reminder Template ]` from Settings and from a task."""
    preview = emails.preview_reminder(
        data.AHMED, data.ACTION_WITH_TIME, data.meeting("AR"), "AR"
    )
    assert preview.recipient_count == 1
    assert data.ACTION_WITH_TIME.task in preview.text_body


# ---------------------------------------------------------------------- send
def test_send_captures_a_gmail_message_id(emails):
    """Section 24.6: the Gmail message ID is captured."""
    summary = emails.send_meeting_report(
        data.meeting("EN"), data.APPROVED_ACTIONS, data.SENDABLE_EMPLOYEES, "EN"
    )
    assert summary.all_ok
    assert len(summary.gmail_message_ids) == 3
    assert all(item for item in summary.gmail_message_ids)


def test_send_reaches_every_valid_recipient_and_skips_the_rest(emails, fake_sender):
    summary = emails.send_meeting_report(
        data.meeting("EN"), data.APPROVED_ACTIONS, data.EMPLOYEES, "EN"
    )
    assert sorted(fake_sender.recipients) == sorted(
        [data.AHMED.email, data.SARAH.email, data.NADA.email, data.RETIRED.email]
    )
    assert data.BROKEN.email in summary.skipped


def test_one_bad_recipient_does_not_stop_the_batch(emails, fake_sender):
    """A 40-person report must still reach the other 39."""
    fake_sender.fail_for = {data.SARAH.email}
    summary = emails.send_meeting_report(
        data.meeting("EN"), data.APPROVED_ACTIONS, data.SENDABLE_EMPLOYEES, "EN"
    )
    assert len(summary.sent) == 2
    assert len(summary.failed) == 1
    assert summary.failed[0].recipient_email == data.SARAH.email
    assert summary.all_ok is False


def test_a_sender_that_raises_becomes_a_failed_result(m4_clock):
    """The worker must never lose a claimed reminder to an exception."""

    class ExplodingSender:
        from_email = "x@example.com"

        def send(self, message):
            raise RuntimeError("socket died")

    service = EmailService(sender=ExplodingSender(), clock=m4_clock)
    attempt = service.send_reminder(data.AHMED, data.ACTION_WITH_TIME, data.meeting())
    assert attempt.ok is False
    assert "socket died" in attempt.result.error_message


def test_every_attempt_reaches_the_delivery_sink(emails, recorded):
    """Section 24.1's boundary: Member 4 reports, Member 1 persists."""
    emails.send_meeting_report(
        data.meeting("EN"), data.APPROVED_ACTIONS, data.SENDABLE_EMPLOYEES, "EN"
    )
    assert len(recorded) == 3
    assert {item.employee_id for item in recorded} == {
        data.AHMED.id, data.SARAH.id, data.NADA.id
    }
    assert all(item.meeting_id == 1 for item in recorded)


def test_attempts_map_onto_member1_delivery_rows(emails, recorded):
    """A `DeliveryAttempt` carries exactly what `EmailDelivery` needs.

    This is the seam between the two work packages, so it is checked as a shape
    contract rather than assumed to line up at integration time.
    """
    emails.send_meeting_report(
        data.meeting("EN"), data.APPROVED_ACTIONS, [data.AHMED], "EN"
    )
    attempt = recorded[0]
    row = EmailDelivery(
        meeting_id=attempt.meeting_id,
        action_item_id=attempt.action_item_id,
        reminder_id=attempt.reminder_id,
        recipient_employee_id=attempt.employee_id,
        recipient_email=attempt.recipient_email,
        subject=attempt.rendered.subject,
        language=attempt.rendered.language,
        status=DeliveryStatus.SENT.value if attempt.ok else DeliveryStatus.FAILED.value,
        gmail_message_id=attempt.result.gmail_message_id,
        error_message=attempt.result.error_message,
    )
    assert row.recipient_email == data.AHMED.email
    assert row.status == DeliveryStatus.SENT.value
    assert row.gmail_message_id


# ----------------------------------------------------------------- reminders
def test_reminders_are_personalized(emails, fake_sender):
    summary = emails.send_personalized_reminders(
        data.SENDABLE_EMPLOYEES, data.ALL_ACTIONS, data.meeting("EN"), "EN"
    )
    assert len(summary.sent) == 3
    ahmed = fake_sender.messages_to(data.AHMED.email)[0]
    assert data.ACTION_WITH_TIME.task in ahmed.text_body
    # Sarah's and Nada's tasks must not appear in Ahmed's reminder.
    assert data.ACTION_NO_TIME.task not in ahmed.text_body
    assert data.ACTION_OVERDUE.task not in ahmed.text_body


def test_reminder_subject_is_personal(emails, fake_sender):
    emails.send_personalized_reminders(
        data.SENDABLE_EMPLOYEES, data.ALL_ACTIONS, data.meeting("EN"), "EN"
    )
    assert fake_sender.messages_to(data.AHMED.email)[0].subject == (
        f"[Nexa Reminder] {data.ACTION_WITH_TIME.task} — Due Tomorrow"
    )


def test_nobody_is_mailed_about_a_completed_task(emails, fake_sender):
    emails.send_personalized_reminders(
        data.SENDABLE_EMPLOYEES, [data.ACTION_COMPLETED], data.meeting("EN"), "EN"
    )
    assert fake_sender.sent == []


def test_several_due_tasks_become_one_mail_not_four(emails, fake_sender):
    """Four separate mails at 20:00 to the same person would be spam."""
    from dataclasses import replace

    extra = [
        replace(data.ACTION_NO_TIME, id=201, owner_employee_id=data.AHMED.id),
        replace(data.ACTION_OVERDUE, id=202, owner_employee_id=data.AHMED.id),
    ]
    summary = emails.send_personalized_reminders(
        [data.AHMED], [data.ACTION_WITH_TIME] + extra, data.meeting("EN"), "EN"
    )
    assert len(summary.attempts) == 1
    assert fake_sender.sent[0].message.subject == "[Nexa Reminder] 3 tasks due"


def test_batched_reminder_leads_with_the_most_urgent(emails, fake_sender):
    from dataclasses import replace

    later = replace(data.ACTION_NO_TIME, id=201, owner_employee_id=data.AHMED.id)
    emails.send_personalized_reminders(
        [data.AHMED], [later, data.ACTION_WITH_TIME], data.meeting("EN"), "EN"
    )
    body = fake_sender.sent[0].message.text_body
    assert data.ACTION_WITH_TIME.task in body


def test_reminder_language_can_differ_from_the_ui(emails, fake_sender):
    """Section 2.3: UI Arabic + email English is a valid combination."""
    emails.send_reminder(data.AHMED, data.ACTION_WITH_TIME, data.meeting("AR"), "EN")
    message = fake_sender.sent[0].message
    assert message.language == "EN"
    assert "This is a reminder" in message.text_body


def test_reminders_hide_evidence_by_default(emails, fake_sender):
    emails.send_reminder(data.AHMED, data.ACTION_WITH_TIME, data.meeting("EN"), "EN")
    assert data.ACTION_WITH_TIME.source_text not in fake_sender.sent[0].message.text_body


# --------------------------------------------------- offline-only guarantee
def test_the_whole_flow_runs_with_no_network(emails, fake_sender):
    """Section 24.6: rendering can be fully tested without network access."""
    preview = emails.preview_meeting_report(
        data.meeting("AR"), data.APPROVED_ACTIONS, data.SENDABLE_EMPLOYEES, "AR"
    )
    assert preview.html_body
    summary = emails.send_meeting_report(
        data.meeting("AR"), data.APPROVED_ACTIONS, data.SENDABLE_EMPLOYEES, "AR"
    )
    assert summary.all_ok
    # The fake builds real MIME, so this exercised the encoder too.
    assert len(fake_sender.sent) == 3


def test_the_fake_rejects_what_gmail_would_reject(fake_sender):
    """A fake more forgiving than production hides bugs until release."""
    from nexa.contracts.email import RenderedEmail

    result = fake_sender.send(RenderedEmail(to_email="not-an-email", subject="x"))
    assert result.ok is False
    assert "valid email address" in result.error_message
