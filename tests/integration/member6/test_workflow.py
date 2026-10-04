from nexa.ui.first_run import FirstRunDialog
from nexa.ui.main_window import MainWindow


def test_meeting_to_review_to_email_preview(qapp):
    window = MainWindow(skip_first_run=True)
    meeting = window.pages["meeting"]
    meeting._stop()
    review = window.pages["review"]
    assert window.stack.currentWidget() is review
    assert "أحمد يخلص الـdatabase before Monday" in review.cards[0].evidence.text()
    assert "الـpresentation تكون ready يوم الخميس الساعة three" in review.cards[1].evidence.text()
    review._approve()
    preview = window.pages["email_preview"]
    assert window.stack.currentWidget() is preview
    preview.language.setCurrentIndex(0)
    preview.refresh()
    assert "Meeting Action Report" in preview.subject.text()
    preview.language.setCurrentIndex(1)
    preview.refresh()
    assert "تقرير" in preview.subject.text()
    preview.language.setCurrentIndex(2)
    preview.refresh()
    assert "تقرير مهام الاجتماع" in preview.subject.text()
    window.close()


def test_schedule_complete_and_snooze_use_reminder_contract(qapp):
    window = MainWindow(skip_first_run=True)
    schedule = window.pages["schedule"]
    schedule.table.selectRow(0)
    action_id = schedule._selected_id()
    deadline = next(a.due_display for a in window.services.reminders.list_actions() if a.id == action_id)
    window.services.reminders.snooze(action_id, "in 30 minutes")
    snoozed = next(a for a in window.services.reminders.list_actions() if a.id == action_id)
    assert snoozed.due_display == deadline
    assert snoozed.reminder_display == "in 30 minutes"
    window.services.reminders.mark_complete(action_id)
    done = next(a for a in window.services.reminders.list_actions() if a.id == action_id)
    assert done.status == "COMPLETED"
    window.close()


def test_first_run_wizard_has_seven_steps(qapp):
    window = MainWindow(skip_first_run=True)
    dialog = FirstRunDialog(window.state, window.trans, window.services.email, window)
    assert dialog.stack.count() == 7
    dialog.retranslate()
    assert "Speech" in dialog.speech_ok.text() or "الكلام" in dialog.speech_ok.text()
    assert "AI" in dialog.llm_ok.text() or "الذكاء" in dialog.llm_ok.text()
    dialog.lang.setCurrentIndex(1)
    dialog._next()
    assert dialog.trans.language == "ar"
    assert dialog.step == 1
    dialog.close()
    window.close()


def test_approve_imports_actions_into_schedule(qapp):
    window = MainWindow(skip_first_run=True)
    before = len(window.services.reminders.list_actions())
    window.pages["meeting"]._stop()
    window.pages["review"]._approve()
    after = window.services.reminders.list_actions()
    assert len(after) == before + 3
    assert any(a.source_text == "أحمد يخلص الـdatabase before Monday" for a in after)
    window.close()


def test_schedule_calendar_lists_iso_due_date(qapp):
    from PySide6.QtCore import QDate

    window = MainWindow(skip_first_run=True)
    schedule = window.pages["schedule"]
    schedule.mode.setCurrentIndex(1)
    schedule.calendar.setSelectedDate(QDate(2026, 9, 7))
    schedule._reload_day()
    assert schedule.day_table.rowCount() == 1
    assert "database" in schedule.day_table.item(0, 1).text().lower()
    window.close()


def test_send_opens_email_history(qapp):
    window = MainWindow(skip_first_run=True)
    preview = window.pages["email_preview"]
    preview.refresh()
    preview.vm.email.send(preview.vm.rendered)
    preview.on_sent()
    assert window.stack.currentWidget() is window.pages["email_history"]
    window.close()
