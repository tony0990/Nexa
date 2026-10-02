"""MIME construction and subject lines.

The MIME layer is where an Arabic report either arrives readable or arrives as
mojibake, so the header encoding and the part ordering are asserted explicitly
rather than assumed.
"""

from __future__ import annotations

import base64
from email import message_from_bytes
from email.header import decode_header, make_header

import pytest

from nexa.contracts.email import RenderedEmail
from nexa.email import (
    InvalidRecipientError,
    build_gmail_payload,
    build_mime_message,
    to_gmail_raw,
)
from nexa.email.mime_builder import encode_header, format_address
from nexa.reports.subject_builder import (
    MAX_SUBJECT_LENGTH,
    digest_subject,
    meeting_report_subject,
    reminder_subject,
    sanitize_subject,
    truncate,
)

from tests.fixtures import member4 as data

FROM = "nexa.sender@example.com"


def rendered(**overrides) -> RenderedEmail:
    values = dict(
        to_email=data.AHMED.email,
        to_name=data.AHMED.full_name,
        subject="تقرير مهام الاجتماع",
        html_body="<p>مرحباً</p>",
        text_body="مرحباً",
        language="AR",
    )
    values.update(overrides)
    return RenderedEmail(**values)


# ------------------------------------------------------------------- headers
def test_ascii_header_is_left_alone():
    assert encode_header("Meeting Action Report") == "Meeting Action Report"


def test_arabic_header_is_rfc2047_encoded_and_round_trips():
    encoded = encode_header("تقرير مهام الاجتماع")
    assert encoded.startswith("=?utf-8?")
    assert str(make_header(decode_header(encoded))) == "تقرير مهام الاجتماع"


def test_arabic_display_name_round_trips():
    address = format_address(data.AHMED.email, data.AHMED.full_name)
    assert data.AHMED.email in address
    assert str(make_header(decode_header(address))).startswith("أحمد حسن")


def test_blank_name_gives_a_bare_address():
    assert format_address("a@b.com", "") == "a@b.com"


# ------------------------------------------------------------------ structure
def test_message_is_multipart_alternative_text_first():
    """Order is load-bearing: a client picks the *last* part it can render."""
    message = build_mime_message(rendered(), FROM, "Nexa")
    assert message.get_content_type() == "multipart/alternative"
    assert [part.get_content_type() for part in message.get_payload()] == [
        "text/plain",
        "text/html",
    ]


def test_bodies_are_utf8_and_survive_a_round_trip():
    message = build_mime_message(rendered(), FROM, "Nexa")
    parsed = message_from_bytes(message.as_bytes())
    text, html = parsed.get_payload()
    assert text.get_payload(decode=True).decode("utf-8") == "مرحباً"
    assert html.get_payload(decode=True).decode("utf-8") == "<p>مرحباً</p>"


def test_headers_are_set():
    message = build_mime_message(rendered(), FROM, "Nexa", reply_to="boss@example.com")
    assert FROM in message["From"]
    assert data.AHMED.email in message["To"]
    assert message["Date"]
    assert message["Message-ID"]
    assert "boss@example.com" in message["Reply-To"]
    assert message["Content-Language"] == "ar"


def test_content_language_follows_the_report_language():
    assert build_mime_message(rendered(language="EN"), FROM)["Content-Language"] == "en"


def test_invalid_recipient_is_rejected_before_any_send():
    with pytest.raises(InvalidRecipientError):
        build_mime_message(rendered(to_email="not-an-email"), FROM)
    with pytest.raises(InvalidRecipientError):
        build_mime_message(rendered(to_email=""), FROM)


# ------------------------------------------------------------- gmail encoding
def test_raw_is_base64url_not_plain_base64():
    """Gmail rejects `+` and `/`, so the encoding must be url-safe."""
    payload = build_gmail_payload(rendered(), FROM, "Nexa")
    raw = payload["raw"]
    assert "+" not in raw and "/" not in raw
    decoded = base64.urlsafe_b64decode(raw.encode("ascii"))
    assert b"multipart/alternative" in decoded


def test_raw_decodes_back_to_the_same_message():
    message = build_mime_message(rendered(), FROM, "Nexa")
    decoded = base64.urlsafe_b64decode(to_gmail_raw(message).encode("ascii"))
    assert message_from_bytes(decoded)["To"] == message["To"]


# -------------------------------------------------------------------- subjects
def test_header_injection_is_stripped():
    """Subjects are built from transcribed speech, so this is a trust boundary."""
    attack = "Report\r\nBcc: attacker@example.com"
    assert "\r" not in sanitize_subject(attack)
    assert "\n" not in sanitize_subject(attack)
    assert sanitize_subject(attack) == "Report Bcc: attacker@example.com"


def test_injection_cannot_survive_into_a_mime_header():
    message = build_mime_message(
        rendered(subject=sanitize_subject("Report\r\nBcc: x@example.com")), FROM
    )
    assert message["Bcc"] is None


def test_long_subject_is_truncated_on_a_word_boundary():
    subject = truncate("word " * 60)
    assert len(subject) <= MAX_SUBJECT_LENGTH
    assert subject.endswith("…")
    assert "  " not in subject


def test_short_subject_is_untouched():
    assert truncate("Short subject") == "Short subject"


def test_english_report_subject(m4_clock):
    from nexa.reports import ReportFormatter

    subject = meeting_report_subject(
        data.meeting("EN"), "EN", ReportFormatter("EN", m4_clock)
    )
    assert subject.startswith("[Nexa] Meeting Action Report")
    assert "Digital Transformation Weekly Meeting" in subject
    assert "Sunday, 20 September 2026" in subject


def test_arabic_report_subject(m4_clock):
    from nexa.reports import ReportFormatter

    subject = meeting_report_subject(
        data.meeting("AR"), "AR", ReportFormatter("AR", m4_clock)
    )
    assert "تقرير مهام الاجتماع" in subject
    assert "الأحد 20 سبتمبر 2026" in subject


def test_reminder_subject_matches_the_spec_example(m4_clock):
    """Section 11 shows exactly: `[Nexa Reminder] <task> — Due Tomorrow`."""
    from nexa.contracts.meetings import ActionItem
    from nexa.reports import ReportFormatter

    action = ActionItem(task="Database Integration", due_date=data.TOMORROW)
    subject = reminder_subject(action, "EN", ReportFormatter("EN", m4_clock))
    assert subject == "[Nexa Reminder] Database Integration — Due Tomorrow"


@pytest.mark.parametrize(
    "due,expected",
    [
        (data.TODAY, "Due Today"),
        (data.TOMORROW, "Due Tomorrow"),
        (data.NEXT_WEEK, "Due in 5 Days"),
        (data.YESTERDAY, "1 Day Overdue"),
        (None, "No Deadline Set"),
    ],
)
def test_reminder_subject_urgency(m4_clock, due, expected):
    from nexa.contracts.meetings import ActionItem
    from nexa.reports import ReportFormatter

    action = ActionItem(task="T", due_date=due)
    assert reminder_subject(action, "EN", ReportFormatter("EN", m4_clock)).endswith(expected)


def test_digest_subject_names_the_count(m4_clock):
    from nexa.reports import ReportFormatter

    subject = digest_subject(
        [data.ACTION_WITH_TIME, data.ACTION_NO_TIME], "EN", ReportFormatter("EN", m4_clock)
    )
    assert subject == "[Nexa Reminder] 2 tasks due"


def test_digest_of_one_is_a_normal_reminder(m4_clock):
    from nexa.reports import ReportFormatter

    fmt = ReportFormatter("EN", m4_clock)
    assert digest_subject([data.ACTION_NO_TIME], "EN", fmt) == reminder_subject(
        data.ACTION_NO_TIME, "EN", fmt
    )
