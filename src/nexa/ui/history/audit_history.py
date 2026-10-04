from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLineEdit, QTableWidget, QVBoxLayout, QWidget

from nexa.ui.history.filters import AUDIT_ENTITIES, filter_audit
from nexa.ui.widgets.common import page_title
from nexa.ui.widgets.tables import fill_table


class AuditHistoryPage(QWidget):
    def __init__(self, t, audit) -> None:
        super().__init__()
        self.t = t
        self.audit = audit
        layout = QVBoxLayout(self)
        self.title = page_title("")
        self.entity = QComboBox()
        self.text = QLineEdit()
        self.table = QTableWidget()
        layout.addWidget(self.title)
        bar = QHBoxLayout()
        bar.addWidget(self.text, 1)
        bar.addWidget(self.entity)
        layout.addLayout(bar)
        layout.addWidget(self.table)
        self.entity.currentIndexChanged.connect(self.reload)
        self.text.textChanged.connect(self.reload)
        self.retranslate()

    def reload(self) -> None:
        entity = AUDIT_ENTITIES[self.entity.currentIndex()] if self.entity.count() else "all"
        events = filter_audit(self.audit.history("all"), self.text.text(), entity)
        fill_table(
            self.table,
            [
                self.t("history.when"),
                self.t("audit.event"),
                self.t("audit.entity"),
                self.t("audit.actor"),
                self.t("audit.detail"),
            ],
            [[e.created_at, e.event_type, f"{e.entity_type}:{e.entity_id}", e.actor, e.detail] for e in events],
        )

    def retranslate(self) -> None:
        self.title.setText(self.t("audit.title"))
        self.text.setPlaceholderText(self.t("audit.filter_hint"))
        current = self.entity.currentIndex() if self.entity.count() else 0
        self.entity.blockSignals(True)
        self.entity.clear()
        self.entity.addItems([self.t("common.all"), "meeting", "action", "email"])
        self.entity.setCurrentIndex(current)
        self.entity.blockSignals(False)
        self.reload()
