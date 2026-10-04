from nexa.services.models import ActionCandidate, Transcript
from nexa.services.fakes import FakeServiceContainer
from nexa.ui.email_preview.viewmodel import EmailPreviewViewModel
from nexa.ui.meeting.viewmodel import MeetingViewModel
from nexa.ui.review.viewmodel import ReviewViewModel
from nexa.ui.schedule.viewmodel import ScheduleViewModel
from nexa.ui.search.filters import SearchViewModel
from nexa.ui.settings.viewmodel import SettingsViewModel


def test_fake_extraction_keeps_original_evidence():
    services = FakeServiceContainer()
    transcript = services.transcription.transcribe("memory://demo")
    items = services.extraction.extract(transcript)
    assert transcript.confirmed_text.startswith("أحمد يخلص")
    assert items[0].source_text == "أحمد يخلص الـdatabase before Monday"
    assert items[1].source_text == "الـpresentation تكون ready يوم الخميس الساعة three"
    assert items[2].possible_duplicate_of == 1


def test_meeting_viewmodel_runs_through_public_fakes():
    services = FakeServiceContainer()
    vm = MeetingViewModel(services.audio, services.transcription, services.extraction)
    defaults = vm.apply_template("Weekly Team Meeting")
    assert defaults["source"] == "mic+computer"
    vm.start("mic")
    assert services.audio.running
    vm.pause()
    assert services.audio.paused
    vm.resume()
    transcript, candidates = vm.stop()
    assert not services.audio.running
    assert transcript.confirmed_text
    assert len(candidates) == 3


def test_review_merge_keeps_target_and_drops_duplicate():
    vm = ReviewViewModel()
    transcript = Transcript("raw", "confirmed")
    left = ActionCandidate(1, "A", "أحمد", 1, "before Monday", "Mon", "src-a", 0.9)
    right = ActionCandidate(2, "A copy", "أحمد", 1, "before Monday", "Mon", "src-a", 0.7, possible_duplicate_of=1)
    vm.set_result("Weekly", transcript, [left, right], ["Ahmed Hassan"])
    vm.merge(2, 1)
    assert [i.id for i in vm.items] == [1]
    assert vm.participants == ["Ahmed Hassan"]


def test_complete_cancels_future_reminders_via_contract():
    services = FakeServiceContainer()
    services.reminders.mark_complete(1)
    action = next(a for a in services.reminders.list_actions() if a.id == 1)
    reminder = next(r for r in services.reminders._reminders if r.action_item_id == 1)
    assert action.status == "COMPLETED"
    assert reminder.status == "SKIPPED_COMPLETED"


def test_snooze_changes_reminder_not_deadline():
    services = FakeServiceContainer()
    before = next(a for a in services.reminders.list_actions() if a.id == 1)
    deadline = before.due_display
    services.reminders.snooze(1, "Today 10:00")
    after = next(a for a in services.reminders.list_actions() if a.id == 1)
    assert after.due_display == deadline
    assert after.reminder_display == "Today 10:00"
    snoozed = services.reminders.list_actions({"status": "SNOOZED"})
    assert any(a.id == 1 for a in snoozed)


def test_schedule_unassigned_filter():
    services = FakeServiceContainer()
    vm = ScheduleViewModel(services.reminders)
    vm.filter_status = "unassigned"
    rows = vm.rows()
    assert rows and all(r.owner_name == "Unassigned" for r in rows)


def test_search_filters_by_category_and_task_status():
    services = FakeServiceContainer()
    vm = SearchViewModel(services.search)
    empty = vm.search("  ")
    assert empty == {"employees": [], "meetings": [], "tasks": []}
    vm.category = "employees"
    hits = vm.search("Ahmed")
    assert hits["employees"] and not hits["meetings"] and not hits["tasks"]
    vm.category = "all"
    vm.task_status = "OVERDUE"
    overdue = vm.search("API")
    assert overdue["tasks"] and all(t.status == "OVERDUE" for t in overdue["tasks"])
    vm.category = "meetings"
    vm.meeting_status = "PENDING_REVIEW"
    pending = vm.search("Review")
    assert pending["meetings"] and all(m.status == "PENDING_REVIEW" for m in pending["meetings"])
    assert not pending["employees"] and not pending["tasks"]


def test_email_preview_three_languages_and_deduped_recipients():
    services = FakeServiceContainer()
    vm = EmailPreviewViewModel(services.email, services.people)
    vm.actions = services.extraction.extract(services.transcription.transcribe("x"))
    vm.participants = ["Ahmed Hassan", "Maria Adel"]
    arabic = vm.build("ARABIC", vm.recipients_for_mode("ASSIGNEE"))
    english = vm.build("ENGLISH", vm.recipients_for_mode("ALL"))
    bilingual = vm.build("BILINGUAL", ["Ahmed Hassan", "Ahmed Hassan", "Maria Adel"])
    assert "تقرير" in arabic.rendered.subject
    assert "Meeting Action Report" in english.rendered.subject
    assert "تقرير مهام الاجتماع" in bilingual.rendered.subject
    assert bilingual.rendered.recipients == ["Ahmed Hassan", "Maria Adel"]
    managers = vm.recipients_for_mode("ROLE", "Manager")
    assert managers == ["Maria Adel"]
    combined = vm.recipients_for_mode("ASSIGNEE_PLUS_ROLE", "Manager")
    assert combined == ["أحمد", "Maria Adel"]


def test_settings_viewmodel_maps_ui_indexes():
    class DummyState:
        language = "en"
        theme = "light"
        email_language = "ENGLISH"
        audio_retention = "delete_after_approval"
        transcript_retention = "delete_after_approval"
        evening_reminder = "20:00"
        morning_reminder = "08:00"

        def persist(self) -> None:
            self.saved = True

    state = DummyState()
    vm = SettingsViewModel(state, FakeServiceContainer())
    vm.apply_from_ui(1, 1, 2, 1, 0, "21:00", "07:30")
    assert state.language == "ar"
    assert state.theme == "dark"
    assert state.email_language == "BILINGUAL"
    assert state.audio_retention == "keep"
    assert state.transcript_retention == "delete_after_approval"
    assert state.evening_reminder == "21:00"
    assert state.morning_reminder == "07:30"
    assert state.saved


def test_import_approved_adds_actions_without_dropping_existing():
    services = FakeServiceContainer()
    items = services.extraction.extract(services.transcription.transcribe("x"))
    before = len(services.reminders.list_actions())
    services.reminders.import_approved("Weekly Development Meeting", items)
    after = services.reminders.list_actions()
    assert len(after) == before + len(items)
    assert after[-1].meeting_title == "Weekly Development Meeting"
