from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QLineEdit

from nexa.contracts.models import ActionCandidate
from nexa.ui.widgets.badges import StatusBadge
from nexa.ui.widgets.cards import Card
from nexa.ui.widgets.common import ghost_button, muted


class ActionCard(Card):
    def __init__(self, t, item: ActionCandidate, people, on_delete, on_duplicate) -> None:
        super().__init__(item.task, f"{int(item.confidence * 100)}%")
        self.t = t
        self.item = item
        self.people = people
        self.on_delete = on_delete
        self.evidence = QLabel(item.source_text)
        self.evidence.setWordWrap(True)
        self.evidence.setStyleSheet("font-style: italic;")
        self.task_edit = QLineEdit(item.task)
        self.owner = QComboBox()
        self.due_edit = QLineEdit(item.due_display)
        self.confidence = muted("")
        kind = "ok" if item.confidence >= 0.9 else "warn" if item.confidence >= 0.75 else "bad"
        self.badge = StatusBadge(f"{int(item.confidence * 100)}%", kind)
        self.needs_review = muted("")
        self.evidence_caption = muted("")
        self.task_caption = muted("")
        self.owner_caption = muted("")
        self.due_caption = muted("")
        self.layout().addWidget(self.evidence_caption)
        self.layout().addWidget(self.evidence)
        self.layout().addWidget(self.task_caption)
        self.layout().addWidget(self.task_edit)
        self.layout().addWidget(self.owner_caption)
        self.layout().addWidget(self.owner)
        self.layout().addWidget(self.due_caption)
        self.layout().addWidget(self.due_edit)
        self.layout().addWidget(self.confidence)
        self.layout().addWidget(self.badge)
        self.layout().addWidget(self.needs_review)
        row = QHBoxLayout()
        self.delete_btn = ghost_button("")
        self.dup_btn = ghost_button("")
        row.addWidget(self.delete_btn)
        row.addWidget(self.dup_btn)
        self.layout().addLayout(row)
        self.delete_btn.clicked.connect(lambda: on_delete(item.id))
        if item.possible_duplicate_of:
            self.dup_btn.clicked.connect(lambda: on_duplicate(item))
        else:
            self.dup_btn.hide()
        self._fill_owners()
        self.retranslate()

    def _fill_owners(self) -> None:
        current = self.item.owner_raw_text
        employees = list(self.people.list_employees("", "active"))
        names = [e.full_name for e in employees]
        self.owner.clear()
        self.owner.addItem(self.t("review.unassigned"), None)
        if current and current not in names and current not in {"Unassigned", "غير معيّن"}:
            self.owner.addItem(current, self.item.owner_employee_id)
        for employee in employees:
            self.owner.addItem(employee.full_name, employee.id)
        if self.item.owner_employee_id:
            index = self.owner.findData(self.item.owner_employee_id)
            if index >= 0:
                self.owner.setCurrentIndex(index)
                return
        if current in names:
            self.owner.setCurrentText(current)
        elif current and current not in {"Unassigned", "غير معيّن"}:
            self.owner.setCurrentText(current)

    def sync(self) -> None:
        self.item.task = self.task_edit.text()
        self.item.owner_raw_text = self.owner.currentText()
        self.item.owner_employee_id = self.owner.currentData()
        self.item.due_display = self.due_edit.text()

    def retranslate(self) -> None:
        self.evidence_caption.setText(self.t("review.evidence"))
        self.task_caption.setText(self.t("review.task"))
        self.owner_caption.setText(self.t("review.owner"))
        self.due_caption.setText(self.t("review.datetime"))
        self.confidence.setText(f"{self.t('review.confidence')}: {int(self.item.confidence * 100)}%")
        self.delete_btn.setText(self.t("common.delete"))
        self.dup_btn.setText(self.t("review.duplicate"))
        self.title_label.setText(self.item.task)
        needs = self.item.confidence < 0.75 or not self.item.due_display or self.item.owner_employee_id is None
        self.needs_review.setVisible(needs)
        self.needs_review.setText(self.t("review.needs_review") if needs else "")
        current_data = self.owner.currentData()
        current_text = self.owner.currentText()
        self._fill_owners()
        if current_data is not None:
            index = self.owner.findData(current_data)
            if index >= 0:
                self.owner.setCurrentIndex(index)
        elif current_text:
            self.owner.setCurrentText(current_text)
