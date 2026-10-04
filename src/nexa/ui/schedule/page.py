from PySide6.QtCore import QDate
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QInputDialog,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)

from nexa.ui.schedule.calendar import make_calendar, mark_dates
from nexa.ui.schedule.snooze_dialog import SnoozeDialog
from nexa.ui.schedule.viewmodel import ScheduleViewModel
from nexa.ui.widgets.common import ghost_button, page_title
from nexa.ui.widgets.tables import fill_table


class SchedulePage(QWidget):
    STATUS_FILTERS = ["all", "PENDING", "OVERDUE", "COMPLETED", "unassigned", "SNOOZED"]

    def __init__(self, t, reminders, morning: str = "08:00") -> None:
        super().__init__()
        self.t = t
        self.morning = morning
        self.vm = ScheduleViewModel(reminders)
        layout = QVBoxLayout(self)
        self.title = page_title("")
        layout.addWidget(self.title)
        toolbar = QHBoxLayout()
        self.mode = QComboBox()
        self.status = QComboBox()
        self.complete_btn = QPushButton()
        self.snooze_btn = ghost_button("")
        self.reschedule_btn = ghost_button("")
        self.test_btn = ghost_button("")
        for w in (self.mode, self.status, self.complete_btn, self.snooze_btn, self.reschedule_btn, self.test_btn):
            toolbar.addWidget(w)
        layout.addLayout(toolbar)
        self.stack = QStackedWidget()
        self.table = QTableWidget()
        self.calendar = make_calendar()
        self.calendar.setSelectedDate(QDate(2026, 9, 7))
        self.day_table = QTableWidget()
        calendar_wrap = QWidget()
        calendar_layout = QVBoxLayout(calendar_wrap)
        calendar_layout.setContentsMargins(0, 0, 0, 0)
        calendar_layout.addWidget(self.calendar)
        calendar_layout.addWidget(self.day_table, 1)
        self.stack.addWidget(self.table)
        self.stack.addWidget(calendar_wrap)
        layout.addWidget(self.stack, 1)
        self.mode.currentIndexChanged.connect(self.stack.setCurrentIndex)
        self.status.currentIndexChanged.connect(self._filter)
        self.calendar.selectionChanged.connect(self._reload_day)
        self.complete_btn.clicked.connect(self._complete)
        self.snooze_btn.clicked.connect(self._snooze)
        self.reschedule_btn.clicked.connect(self._reschedule)
        self.test_btn.clicked.connect(self._test)
        self.retranslate()

    def _selected_id(self) -> int | None:
        row = self.table.currentRow()
        if row < 0:
            return None
        item = self.table.item(row, 0)
        return int(item.text()) if item else None

    def _filter(self) -> None:
        self.vm.filter_status = self.STATUS_FILTERS[self.status.currentIndex()]
        self.reload()

    def _complete(self) -> None:
        action_id = self._selected_id()
        if action_id is None:
            return
        self.vm.reminders.mark_complete(action_id)
        self.reload()

    def _snooze(self) -> None:
        action_id = self._selected_id()
        if action_id is None:
            return
        dialog = SnoozeDialog(self.t, self, self.morning)
        if dialog.exec():
            self.vm.snooze(action_id, dialog.option, dialog.custom_text, self.morning)
            self.reload()

    def _reschedule(self) -> None:
        action_id = self._selected_id()
        if action_id is None:
            return
        text, ok = QInputDialog.getText(self, self.t("schedule.reschedule"), self.t("schedule.reschedule_prompt"), text="2026-09-10 16:00")
        if ok and text.strip():
            try:
                self.vm.reschedule(action_id, text)
            except ValueError:
                QMessageBox.warning(self, "Nexa", self.t("snooze.invalid"))
                return
            self.reload()

    def _test(self) -> None:
        action_id = self._selected_id()
        if action_id is None:
            return
        result = self.vm.reminders.send_test_reminder(action_id)
        QMessageBox.information(self, "Nexa", result.message_id)

    def _headers(self) -> list[str]:
        return [
            "ID",
            self.t("schedule.task"),
            self.t("schedule.owner"),
            self.t("schedule.deadline"),
            self.t("schedule.reminder"),
            self.t("schedule.status"),
        ]

    def _row(self, action) -> list:
        return [str(action.id), action.task, action.owner_name, action.due_display, action.reminder_display, action.status]

    def _reload_day(self) -> None:
        iso = self.calendar.selectedDate().toString("yyyy-MM-dd")
        fill_table(self.day_table, self._headers(), [self._row(a) for a in self.vm.rows_for_iso(iso)])

    def reload(self) -> None:
        fill_table(self.table, self._headers(), [self._row(a) for a in self.vm.rows()])
        mark_dates(self.calendar, self.vm.marked_dates())
        self._reload_day()

    def retranslate(self) -> None:
        self.title.setText(self.t("schedule.title"))
        self.mode.blockSignals(True)
        current_mode = self.mode.currentIndex() if self.mode.count() else 0
        self.mode.clear()
        self.mode.addItems([self.t("schedule.list"), self.t("schedule.calendar")])
        self.mode.setCurrentIndex(current_mode)
        self.mode.blockSignals(False)
        current_status = self.status.currentIndex() if self.status.count() else 0
        self.status.blockSignals(True)
        self.status.clear()
        self.status.addItems(
            [
                self.t("common.all"),
                self.t("filters.pending"),
                self.t("filters.overdue"),
                self.t("filters.completed"),
                self.t("filters.unassigned"),
                self.t("filters.snoozed"),
            ]
        )
        self.status.setCurrentIndex(current_status)
        self.status.blockSignals(False)
        self.complete_btn.setText(self.t("schedule.complete"))
        self.snooze_btn.setText(self.t("schedule.snooze"))
        self.reschedule_btn.setText(self.t("schedule.reschedule"))
        self.test_btn.setText(self.t("schedule.test_reminder"))
        self.reload()
