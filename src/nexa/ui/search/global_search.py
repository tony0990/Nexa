from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QLineEdit, QVBoxLayout, QWidget

from nexa.ui.search.filters import SearchViewModel
from nexa.ui.search.results import format_employee_results, format_meeting_results, format_task_results
from nexa.ui.widgets.common import page_title
from nexa.ui.widgets.empty_states import EmptyState


class SearchPage(QWidget):
    def __init__(self, t, search_service) -> None:
        super().__init__()
        self.t = t
        self.vm = SearchViewModel(search_service)
        layout = QVBoxLayout(self)
        self.title = page_title("")
        self.query = QLineEdit()
        filters = QHBoxLayout()
        self.category = QComboBox()
        self.status = QComboBox()
        self.meeting_status = QComboBox()
        self.employee_active = QComboBox()
        for widget in (self.category, self.status, self.meeting_status, self.employee_active):
            filters.addWidget(widget)
        self.employees = QLabel()
        self.employees.setWordWrap(True)
        self.meetings = QLabel()
        self.meetings.setWordWrap(True)
        self.tasks = QLabel()
        self.tasks.setWordWrap(True)
        self.empty = EmptyState("")
        layout.addWidget(self.title)
        layout.addWidget(self.query)
        layout.addLayout(filters)
        for w in (self.employees, self.meetings, self.tasks, self.empty):
            layout.addWidget(w)
        layout.addStretch()
        self.query.textChanged.connect(self.reload)
        self.category.currentIndexChanged.connect(self._apply_filters)
        self.status.currentIndexChanged.connect(self._apply_filters)
        self.meeting_status.currentIndexChanged.connect(self._apply_filters)
        self.employee_active.currentIndexChanged.connect(self._apply_filters)
        self.retranslate()

    def _apply_filters(self) -> None:
        if self.category.count():
            self.vm.category = SearchViewModel.CATEGORIES[self.category.currentIndex()]
        if self.status.count():
            self.vm.task_status = SearchViewModel.TASK_STATUSES[self.status.currentIndex()]
        if self.meeting_status.count():
            self.vm.meeting_status = SearchViewModel.MEETING_STATUSES[self.meeting_status.currentIndex()]
        if self.employee_active.count():
            self.vm.employee_active = SearchViewModel.EMPLOYEE_ACTIVE[self.employee_active.currentIndex()]
        self.reload()

    def set_query(self, text: str) -> None:
        self.query.setText(text)

    def reload(self) -> None:
        result = self.vm.search(self.query.text())
        emp = result["employees"]
        meetings = result["meetings"]
        tasks = result["tasks"]
        empty = self.t("search.empty")
        self.employees.setText(f"{self.t('search.employees')} ({len(emp)})\n{format_employee_results(emp, empty)}")
        self.meetings.setText(f"{self.t('search.meetings')} ({len(meetings)})\n{format_meeting_results(meetings, empty)}")
        self.tasks.setText(f"{self.t('search.tasks')} ({len(tasks)})\n{format_task_results(tasks, empty)}")
        has_any = bool(emp or meetings or tasks)
        self.empty.setVisible(not has_any)
        self.empty.set_text(empty)

    def retranslate(self) -> None:
        self.title.setText(self.t("search.title"))
        self.query.setPlaceholderText(self.t("common.search"))
        cat = self.category.currentIndex() if self.category.count() else 0
        st = self.status.currentIndex() if self.status.count() else 0
        ms = self.meeting_status.currentIndex() if self.meeting_status.count() else 0
        ea = self.employee_active.currentIndex() if self.employee_active.count() else 0
        self.category.blockSignals(True)
        self.category.clear()
        self.category.addItems(
            [self.t("common.all"), self.t("search.employees"), self.t("search.meetings"), self.t("search.tasks")]
        )
        self.category.setCurrentIndex(cat)
        self.category.blockSignals(False)
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
        self.status.setCurrentIndex(st)
        self.status.blockSignals(False)
        self.meeting_status.blockSignals(True)
        self.meeting_status.clear()
        self.meeting_status.addItems(
            [
                self.t("filters.meetings_all"),
                self.t("filters.approved"),
                self.t("filters.pending_review"),
                self.t("filters.draft"),
            ]
        )
        self.meeting_status.setCurrentIndex(ms)
        self.meeting_status.blockSignals(False)
        self.employee_active.blockSignals(True)
        self.employee_active.clear()
        self.employee_active.addItems([self.t("common.all"), self.t("common.active"), self.t("common.inactive")])
        self.employee_active.setCurrentIndex(ea)
        self.employee_active.blockSignals(False)
        self.reload()
