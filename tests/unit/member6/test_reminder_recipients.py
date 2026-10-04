from nexa.contracts.models import ActionCandidate
from nexa.services.fakes import FakeEmailService, FakePeopleService
from nexa.ui.email_preview.viewmodel import EmailPreviewViewModel


def make_vm():
    vm = EmailPreviewViewModel(FakeEmailService(), FakePeopleService())
    vm.actions = [ActionCandidate(1, "Finish database", "Ahmed Hassan", 1, "", "", "", 0.9)]
    return vm


def test_reminders_default_to_assignee_independent_of_report():
    vm = make_vm()
    report = vm.recipients_for_mode("ALL")
    assert vm.reminder_recipients_for("ASSIGNEE", report_recipients=report) == ["Ahmed Hassan"]


def test_same_as_report_and_dedup():
    vm = make_vm()
    got = vm.reminder_recipients_for("SAME_AS_REPORT", report_recipients=["A", "B", "A"])
    assert got == ["A", "B"]


def test_assignee_plus_role_dedups_assignee():
    vm = make_vm()
    got = vm.reminder_recipients_for("ASSIGNEE_PLUS_ROLE", role="Developer")
    assert got.count("Ahmed Hassan") == 1 and "Ahmed Ali" in got


def test_custom_never_falls_back_to_everyone():
    assert make_vm().reminder_recipients_for("CUSTOM", custom=[]) == []
