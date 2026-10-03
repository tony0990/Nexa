"""Report rendering: languages, formatting, evidence, HTML and plain text.

Covers Section 39.3's rendering rows (Arabic, English, HTML, plain text) and the
Section 24.6 items about professional Arabic/English reports. Nothing here
touches the network, which is itself a requirement.
"""

from __future__ import annotations

from datetime import date, time

import pytest

from nexa.contracts.meetings import ActionItem, EmailLanguage
from nexa.reports import ReportFormatter, ReportService, resolve_language
from nexa.reports.models import is_rtl

from tests.fixtures import member4 as data


# ----------------------------------------------------------------- languages
@pytest.mark.parametrize(
    "given,expected",
    [
        ("AR", "AR"),
        ("ar", "AR"),
        ("EN", "EN"),
        ("english", "EN"),
        (EmailLanguage.EN, "EN"),
        (None, "AR"),
        ("", "AR"),
        ("BILINGUAL", "BILINGUAL"),
        ("bilingual", "BILINGUAL"),
        (EmailLanguage.BILINGUAL, "BILINGUAL"),
        # A stale settings row must not break a send; Arabic is the default.
        ("klingon", "AR"),
    ],
)
def test_resolve_language(given, expected):
    assert resolve_language(given) == expected


def test_three_modes_exist():
    """Section 24.1's "Three modes": ARABIC, ENGLISH, BILINGUAL."""
    assert {item.value for item in EmailLanguage} == {"AR", "EN", "BILINGUAL"}


def test_direction_follows_language():
    assert is_rtl("AR") is True
    assert is_rtl("EN") is False
    # Section 10.3's layout leads with English, so bilingual is LTR.
    assert is_rtl("BILINGUAL") is False


def test_every_mode_has_templates(reports):
    assert set(reports.available_languages()) == {"AR", "EN", "BILINGUAL"}


# ----------------------------------------------------------------- formatting
def test_arabic_date_is_formal_and_uses_ascii_digits(m4_clock):
    fmt = ReportFormatter("AR", m4_clock)
    assert fmt.format_date(date(2026, 9, 20)) == "الأحد 20 سبتمبر 2026"


def test_english_date_is_formal(m4_clock):
    fmt = ReportFormatter("EN", m4_clock)
    assert fmt.format_date(date(2026, 9, 20)) == "Sunday, 20 September 2026"


@pytest.mark.parametrize(
    "value,expected",
    [(time(15, 0), "3:00 PM"), (time(9, 30), "9:30 AM"), (time(0, 0), "12:00 AM"),
     (time(12, 0), "12:00 PM")],
)
def test_english_time_is_twelve_hour(m4_clock, value, expected):
    assert ReportFormatter("EN", m4_clock).format_time(value) == expected


def test_missing_time_says_time_not_specified(m4_clock):
    """Section 2.1: Nexa shows uncertainty instead of inventing a time."""
    assert ReportFormatter("EN", m4_clock).format_time(None) == "Time not specified"
    assert ReportFormatter("AR", m4_clock).format_time(None) == "الوقت غير محدد"


def test_deadline_uses_the_local_calendar_day(m4_clock):
    """A UTC instant late in the day is still the right Cairo date.

    21:00 UTC on 10 September is 23:00 Cairo on the same day, and 22:30 UTC is
    00:30 on the 11th. Formatting from UTC would report the wrong weekday.
    """
    from datetime import datetime, timezone

    fmt = ReportFormatter("EN", m4_clock)
    late = ActionItem(task="x", due_at=datetime(2026, 9, 10, 22, 30, tzinfo=timezone.utc))
    assert "11 September 2026" in fmt.format_deadline(late)


def test_no_deadline_says_not_specified(m4_clock):
    fmt = ReportFormatter("EN", m4_clock)
    assert fmt.format_deadline(data.ACTION_NO_OWNER_NO_DATE) == "Deadline not specified"
    assert fmt.days_until(data.ACTION_NO_OWNER_NO_DATE) is None


@pytest.mark.parametrize(
    "action,expected_days",
    [
        (data.ACTION_WITH_TIME, 1),
        (data.ACTION_NO_TIME, 5),
        (data.ACTION_OVERDUE, -1),
    ],
)
def test_days_until(m4_clock, action, expected_days):
    assert ReportFormatter("EN", m4_clock).days_until(action) == expected_days


# --------------------------------------------------------------------- owners
def test_resolved_owner_uses_the_employee_name(m4_clock):
    fmt = ReportFormatter("EN", m4_clock)
    by_id = {data.AHMED.id: data.AHMED}
    assert fmt.owner_name(data.ACTION_WITH_TIME, by_id) == data.AHMED.full_name


def test_unmatched_owner_keeps_the_spoken_name(m4_clock):
    """Section 2.2: the heard name is evidence and must not be discarded."""
    fmt = ReportFormatter("EN", m4_clock)
    assert fmt.owner_name(data.ACTION_UNMATCHED_OWNER, {}) == "محمد"


def test_no_owner_renders_unassigned(m4_clock):
    assert ReportFormatter("EN", m4_clock).owner_name(data.ACTION_NO_OWNER_NO_DATE, {}) == (
        "Unassigned"
    )
    assert ReportFormatter("AR", m4_clock).owner_name(data.ACTION_NO_OWNER_NO_DATE, {}) == (
        "غير مُسنَدة"
    )


# ------------------------------------------------------------------- bodies
@pytest.fixture
def rendered_en(reports):
    return reports.build_meeting_report(
        data.meeting("EN"), data.APPROVED_ACTIONS, data.SENDABLE_EMPLOYEES, "EN",
        employees=data.EMPLOYEES,
    )


@pytest.fixture
def rendered_ar(reports):
    return reports.build_meeting_report(
        data.meeting("AR"), data.APPROVED_ACTIONS, data.SENDABLE_EMPLOYEES, "AR",
        employees=data.EMPLOYEES,
    )


def test_one_rendered_email_per_recipient(rendered_en):
    assert [item.to_email for item in rendered_en] == [
        data.AHMED.email, data.SARAH.email, data.NADA.email
    ]


def test_html_and_text_are_both_produced(rendered_en):
    for item in rendered_en:
        assert item.html_body.strip()
        assert item.text_body.strip()


def test_english_report_is_professional(rendered_en):
    body = rendered_en[0].text_body
    assert "Dear Sarah Ali," in rendered_en[1].text_body
    assert "Please find below the action report" in body
    assert "Action Items" in body
    assert "Deadline:" in body
    assert "Regards," in body


def test_arabic_report_is_professional(rendered_ar):
    body = rendered_ar[0].text_body
    assert "السيد/السيدة أحمد حسن،" in body
    assert "نرفق إليكم تقرير اجتماع" in body
    assert "المهام" in body
    assert "الموعد النهائي:" in body
    assert "مع التحية،" in body


def test_arabic_html_is_rtl(rendered_ar):
    html = rendered_ar[0].html_body
    assert 'dir="rtl"' in html
    assert 'lang="ar"' in html
    # Tahoma leads the Arabic stack, or Arabic joins badly in Outlook.
    assert "Tahoma" in html


def test_english_html_is_ltr(rendered_en):
    html = rendered_en[0].html_body
    assert 'dir="ltr"' in html
    assert 'lang="en"' in html


def test_html_is_mobile_friendly(rendered_en):
    html = rendered_en[0].html_body
    assert "width=device-width" in html
    # Gmail strips <style> blocks, so styling has to be inline.
    assert "<style" not in html.lower()


def test_original_phrase_is_preserved_exactly(rendered_en, rendered_ar):
    """Section 2.2: the confirmed spoken sentence survives into the report."""
    evidence = data.ACTION_WITH_TIME.source_text
    assert evidence == "الـpresentation Thursday الساعة three"
    for item in (rendered_en[0], rendered_ar[0]):
        assert evidence in item.text_body
        assert evidence in item.html_body


def test_evidence_can_be_switched_off(reports):
    rendered = reports.build_meeting_report(
        data.meeting("EN"), data.APPROVED_ACTIONS, [data.AHMED], "EN",
        include_evidence=False,
    )
    assert data.ACTION_WITH_TIME.source_text not in rendered[0].text_body


def test_report_contains_no_raw_json_or_placeholders(rendered_en, rendered_ar):
    """Section 24.5: no raw JSON, and no unrendered template syntax."""
    for item in rendered_en + rendered_ar:
        for body in (item.html_body, item.text_body):
            assert "{{" not in body
            assert "{%" not in body
            assert "None" not in body.replace("None of", "")
            assert '"task":' not in body


def test_needs_review_is_flagged(rendered_en):
    body = rendered_en[0].text_body
    assert "Needs review" in body
    assert "flagged for review" in body


def test_zero_actions_still_renders(reports):
    """An approved meeting with nothing extracted must not send a broken mail."""
    rendered = reports.build_meeting_report(data.meeting("EN"), [], [data.AHMED], "EN")
    assert "No action items were recorded" in rendered[0].text_body
    assert rendered[0].html_body.strip()


def test_task_text_is_html_escaped(reports):
    """Transcribed text containing markup must appear literally, not as HTML."""
    hostile = ActionItem(
        id=1, task="Fix <b>the</b> & test", due_date=date(2026, 9, 21),
        source_text="fix <script>alert(1)</script> please",
    )
    rendered = reports.build_meeting_report(
        data.meeting("EN"), [hostile], [data.AHMED], "EN"
    )
    html = rendered[0].html_body
    assert "&lt;b&gt;the&lt;/b&gt;" in html
    assert "<script>" not in html
    # ...but the plain-text part is not escaped, or recipients see &amp;.
    assert "Fix <b>the</b> & test" in rendered[0].text_body


def test_invalid_recipient_is_skipped_not_rendered(reports):
    """Section 39.3's "invalid email" row."""
    rendered = reports.build_meeting_report(
        data.meeting("EN"), data.APPROVED_ACTIONS, data.EMPLOYEES, "EN"
    )
    assert data.BROKEN.email not in [item.to_email for item in rendered]


def test_single_recipient(reports):
    rendered = reports.build_meeting_report(
        data.meeting("EN"), data.APPROVED_ACTIONS, [data.AHMED], "EN"
    )
    assert len(rendered) == 1


def test_many_recipients_share_one_subject(reports):
    """Section 39.3's "many recipients" row."""
    many = [
        data.Employee(id=100 + i, full_name=f"Person {i}", email=f"p{i}@example.com")
        for i in range(50)
    ]
    rendered = reports.build_meeting_report(
        data.meeting("EN"), data.APPROVED_ACTIONS, many, "EN"
    )
    assert len(rendered) == 50
    assert len({item.subject for item in rendered}) == 1
