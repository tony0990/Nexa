"""The BILINGUAL rendering mode (Sections 10.3, 24.1, 24.5, 24.6).

The properties that matter, and that a careless implementation gets wrong:

* the **frame** is paired (labels, dates, salutation, intro, closing)
* the **data** is not (names and task text appear once, untranslated)
* both date forms are present, from one calendar day
* it is one email, not two sends
"""

from __future__ import annotations

import pytest

from nexa.contracts.meetings import ActionItem, EmailLanguage
from nexa.reports import ReportFormatter, lexicon
from nexa.reports import bilingual
from nexa.reports.models import is_bilingual, is_rtl, resolve_language

from tests.fixtures import member4 as data

BILINGUAL = EmailLanguage.BILINGUAL.value


# ------------------------------------------------------------------- pairing
def test_pair_joins_with_a_bar():
    assert bilingual.pair("Meeting", "الاجتماع") == "Meeting | الاجتماع"


def test_pair_drops_an_empty_half():
    assert bilingual.pair("Meeting", "") == "Meeting"
    assert bilingual.pair("", "الاجتماع") == "الاجتماع"


def test_pair_collapses_identical_halves():
    """An unresolved spoken owner name is the same in both; twice looks broken."""
    assert bilingual.pair("محمد", "محمد") == "محمد"


def test_every_label_is_paired():
    english = lexicon("EN").LABELS
    arabic = lexicon("AR").LABELS
    for key, value in bilingual.LABELS.items():
        assert value == bilingual.pair(english[key], arabic[key])


def test_labels_match_the_spec_layout():
    """Section 10.3 names these three explicitly."""
    assert bilingual.LABELS["meeting"] == "Meeting | الاجتماع"
    assert bilingual.LABELS["date"] == "Date | التاريخ"
    assert bilingual.LABELS["action_items"] == "Action Items | المهام"


def test_statuses_are_paired():
    assert bilingual.STATUSES["PENDING"] == "Pending | قيد التنفيذ"


def test_resolution_and_direction():
    assert resolve_language("BILINGUAL") == BILINGUAL
    assert is_bilingual("BILINGUAL") is True
    assert is_bilingual("AR") is False
    # Section 10.3 leads with English.
    assert is_rtl(BILINGUAL) is False
    assert bilingual.DIRECTION == "ltr"


# ---------------------------------------------------------------- formatting
def test_dates_carry_both_forms(m4_clock):
    """Section 10.3: `4 September 2026 | 4 سبتمبر 2026`."""
    from datetime import date

    text = ReportFormatter(BILINGUAL, m4_clock).format_date(date(2026, 9, 4))
    assert text == "Friday, 4 September 2026 | الجمعة 4 سبتمبر 2026"


def test_times_carry_both_forms(m4_clock):
    from datetime import time

    assert ReportFormatter(BILINGUAL, m4_clock).format_time(time(15, 0)) == (
        "3:00 PM | 3:00 مساءً"
    )


def test_missing_time_is_paired(m4_clock):
    assert ReportFormatter(BILINGUAL, m4_clock).format_time(None) == (
        "Time not specified | الوقت غير محدد"
    )


def test_deadline_is_paired(m4_clock):
    text = ReportFormatter(BILINGUAL, m4_clock).format_deadline(data.ACTION_WITH_TIME)
    assert " | " in text
    assert "21 September 2026" in text
    assert "21 سبتمبر 2026" in text


def test_both_halves_agree_on_the_calendar_day(m4_clock):
    """Both halves come from one local date, so they cannot disagree."""
    from datetime import datetime, timezone

    late = ActionItem(task="x", due_at=datetime(2026, 9, 10, 22, 30, tzinfo=timezone.utc))
    text = ReportFormatter(BILINGUAL, m4_clock).format_deadline(late)
    assert "11 September 2026" in text
    assert "11 سبتمبر 2026" in text


def test_days_until_is_not_paired(m4_clock):
    """It is a number used for urgency, not a displayed string."""
    assert ReportFormatter(BILINGUAL, m4_clock).days_until(data.ACTION_WITH_TIME) == 1


def test_unassigned_owner_is_paired(m4_clock):
    owner = ReportFormatter(BILINGUAL, m4_clock).owner_name(
        data.ACTION_NO_OWNER_NO_DATE, {}
    )
    assert owner == "Unassigned | غير مُسنَدة"


def test_resolved_owner_name_is_not_translated(m4_clock):
    """Section 10.3: do not mechanically translate employee names."""
    fmt = ReportFormatter(BILINGUAL, m4_clock)
    owner = fmt.owner_name(data.ACTION_WITH_TIME, {data.AHMED.id: data.AHMED})
    assert owner == data.AHMED.full_name
    assert " | " not in owner


# -------------------------------------------------------------------- bodies
@pytest.fixture
def rendered(reports):
    return reports.build_meeting_report(
        data.meeting(BILINGUAL), data.APPROVED_ACTIONS, data.SENDABLE_EMPLOYEES,
        BILINGUAL, employees=data.EMPLOYEES,
    )


def test_one_email_not_two_sends(rendered):
    """BILINGUAL is a rendering mode: one message per recipient, not two."""
    assert len(rendered) == len(data.SENDABLE_EMPLOYEES)
    assert all(item.language == BILINGUAL for item in rendered)


def test_body_follows_the_spec_layout(rendered):
    body = rendered[0].text_body
    assert "Meeting Action Report | تقرير مهام الاجتماع" in body
    assert "Meeting | الاجتماع:" in body
    assert "Date | التاريخ:" in body
    assert "Action Items | المهام" in body


def test_both_salutations_appear(rendered):
    body = rendered[0].text_body
    assert f"Dear {data.AHMED.full_name}," in body
    assert f"السيد/السيدة {data.AHMED.full_name}،" in body


def test_both_intros_and_closings_appear(rendered):
    body = rendered[0].text_body
    assert "Please find below the action report" in body
    assert "نرفق إليكم تقرير اجتماع" in body
    assert "Kindly observe the deadlines" in body
    assert "نرجو الالتزام بالمواعيد" in body


def test_both_signatures_appear(rendered):
    body = rendered[0].text_body
    assert "Regards,\nNexa" in body
    assert "مع التحية،\nنظام Nexa" in body


def test_task_text_appears_once_and_untranslated(rendered):
    """Translating approved task text would be inventing content (24.1)."""
    body = rendered[0].text_body
    assert body.count(data.ACTION_NO_TIME.task) == 1
    assert body.count(data.ACTION_WITH_TIME.task) == 1


def test_evidence_is_preserved_exactly_and_once(rendered):
    body = rendered[0].text_body
    assert body.count(data.ACTION_WITH_TIME.source_text) == 1


def test_html_is_ltr_with_an_arabic_capable_font(rendered):
    html = rendered[0].html_body
    assert 'dir="ltr"' in html
    # Both scripts in one document, so the stack must cover Arabic.
    assert "Tahoma" in html


def test_html_marks_mixed_content_auto_direction(rendered):
    """Paired text inside an LTR document needs dir="auto" to align."""
    assert 'dir="auto"' in rendered[0].html_body


def test_paired_paragraphs_do_not_collapse_in_html(rendered):
    """HTML eats a blank line unless the paragraph preserves it."""
    assert "white-space:pre-line" in rendered[0].html_body


def test_no_unrendered_template_syntax(rendered):
    for item in rendered:
        for body in (item.html_body, item.text_body):
            assert "{{" not in body and "{%" not in body


def test_zero_actions_still_renders(reports):
    rendered = reports.build_meeting_report(
        data.meeting(BILINGUAL), [], [data.AHMED], BILINGUAL
    )
    assert "No action items were recorded" in rendered[0].text_body
    assert "لم تُسجَّل مهام" in rendered[0].text_body


# ------------------------------------------------------------------ subjects
def test_report_subject_is_paired_but_short(reports):
    """A fully paired subject would exceed what Gmail shows on a phone."""
    from nexa.reports.subject_builder import MAX_SUBJECT_LENGTH, meeting_report_subject

    subject = meeting_report_subject(
        data.meeting(BILINGUAL), BILINGUAL, reports.formatter(BILINGUAL)
    )
    assert "Meeting Action Report | تقرير مهام الاجتماع" in subject
    assert len(subject) <= MAX_SUBJECT_LENGTH


def test_reminder_subject_is_paired(reports):
    from nexa.reports.subject_builder import reminder_subject

    subject = reminder_subject(
        data.ACTION_NO_TIME, BILINGUAL, reports.formatter(BILINGUAL)
    )
    assert subject.startswith("[Nexa Reminder | تذكير]")
    assert "Due in 5 Days" in subject


def test_digest_subject_is_paired(reports):
    from nexa.reports.subject_builder import digest_subject

    subject = digest_subject(
        [data.ACTION_WITH_TIME, data.ACTION_NO_TIME],
        BILINGUAL,
        reports.formatter(BILINGUAL),
    )
    assert "2" in subject
    assert "Nexa" in subject


# ----------------------------------------------------------------- reminders
def test_reminder_carries_both_languages(reports):
    rendered = reports.build_reminder(
        data.AHMED, data.ACTION_WITH_TIME, data.meeting(BILINGUAL), BILINGUAL
    )
    body = rendered.text_body
    assert "This is a reminder that your assigned action item" in body
    assert "نود تذكيركم بأن المهمة المسندة إليكم" in body
    assert body.count(data.ACTION_WITH_TIME.task) >= 1


def test_reminder_urgency_is_in_each_language(reports):
    rendered = reports.build_reminder(
        data.AHMED, data.ACTION_WITH_TIME, data.meeting(BILINGUAL), BILINGUAL
    )
    assert "is due tomorrow" in rendered.text_body
    assert "مستحقة غداً" in rendered.text_body


def test_bilingual_mime_round_trips(reports):
    """Mixed-script subject and body must survive encoding."""
    from email import message_from_bytes

    from nexa.email import build_mime_message

    rendered = reports.build_reminder(
        data.AHMED, data.ACTION_WITH_TIME, data.meeting(BILINGUAL), BILINGUAL
    )
    message = build_mime_message(rendered, "nexa@example.com", "Nexa")
    parsed = message_from_bytes(message.as_bytes())
    text = parsed.get_payload()[0].get_payload(decode=True).decode("utf-8")
    assert "نود تذكيركم" in text
    assert "This is a reminder" in text
    assert parsed["Content-Language"] == "en"


def test_bilingual_sends_through_the_email_service(emails, fake_sender):
    summary = emails.send_meeting_report(
        data.meeting(BILINGUAL), data.APPROVED_ACTIONS, data.SENDABLE_EMPLOYEES,
        BILINGUAL,
    )
    assert summary.all_ok
    assert len(fake_sender.sent) == 3
    assert all(item.message.language == BILINGUAL for item in fake_sender.sent)
