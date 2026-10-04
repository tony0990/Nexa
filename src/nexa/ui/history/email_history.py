from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLineEdit, QTableWidget, QVBoxLayout, QWidget

from nexa.ui.history.filters import DELIVERY_KINDS, DELIVERY_STATUSES, filter_deliveries
from nexa.ui.widgets.common import page_title
from nexa.ui.widgets.tables import fill_table


class EmailHistoryPage(QWidget):
    def __init__(self, t, email_service) -> None:
        super().__init__()
        self.t = t
        self.email = email_service
        layout = QVBoxLayout(self)
        self.title = page_title("")
        self.text = QLineEdit()
        self.status = QComboBox()
        self.kind = QComboBox()
        self.table = QTableWidget()
        layout.addWidget(self.title)
        bar = QHBoxLayout()
        for w in (self.text, self.status, self.kind):
            bar.addWidget(w)
        layout.addLayout(bar)
        layout.addWidget(self.table)
        self.text.textChanged.connect(self.reload)
        self.status.currentIndexChanged.connect(self.reload)
        self.kind.currentIndexChanged.connect(self.reload)
        self.retranslate()

    def reload(self) -> None:
        status = DELIVERY_STATUSES[self.status.currentIndex()] if self.status.count() else "all"
        kind = DELIVERY_KINDS[self.kind.currentIndex()] if self.kind.count() else "all"
        deliveries = filter_deliveries(self.email.deliveries, self.text.text(), status, kind)
        rows = [[d["when"], d["kind"], d["subject"], d["to"], d["status"], d["language"]] for d in deliveries]
        fill_table(
            self.table,
            [
                self.t("history.when"),
                self.t("history.kind"),
                self.t("history.subject"),
                self.t("history.to"),
                self.t("history.status"),
                self.t("history.language"),
            ],
            rows,
        )

    def retranslate(self) -> None:
        self.title.setText(self.t("history.title"))
        self.text.setPlaceholderText(self.t("common.search"))
        for combo, labels in (
            (self.status, [self.t("common.all"), "SENT", "FAILED", "PENDING"]),
            (self.kind, [self.t("common.all"), "REPORT", "REMINDER"]),
        ):
            current = combo.currentIndex() if combo.count() else 0
            combo.blockSignals(True)
            combo.clear()
            combo.addItems(labels)
            combo.setCurrentIndex(current)
            combo.blockSignals(False)
        self.reload()
