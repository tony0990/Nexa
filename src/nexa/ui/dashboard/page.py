from PySide6.QtWidgets import QGridLayout, QHBoxLayout, QVBoxLayout, QWidget

from nexa.ui.dashboard.viewmodel import DashboardViewModel
from nexa.ui.widgets.cards import Card
from nexa.ui.widgets.common import ghost_button, page_title


class DashboardPage(QWidget):
    def __init__(self, t, reminder_service, on_open_schedule, on_open_review, on_open_history=None) -> None:
        super().__init__()
        self.t = t
        self.vm = DashboardViewModel(reminder_service)
        self.on_open_schedule = on_open_schedule
        self.on_open_review = on_open_review
        self.on_open_history = on_open_history
        layout = QVBoxLayout(self)
        self.title = page_title("")
        layout.addWidget(self.title)
        grid = QGridLayout()
        self.cards = {}
        for i, key in enumerate(["upcoming", "reminders_today", "pending_review", "overdue", "email_failures", "completed"]):
            card = Card("", "0")
            self.cards[key] = card
            grid.addWidget(card, i // 3, i % 3)
        layout.addLayout(grid)
        row = QHBoxLayout()
        self.open_schedule = ghost_button("")
        self.open_review = ghost_button("")
        row.addWidget(self.open_schedule)
        row.addWidget(self.open_review)
        layout.addLayout(row)
        layout.addStretch()
        self.cards["upcoming"].clicked.connect(self.on_open_schedule)
        self.cards["reminders_today"].clicked.connect(self.on_open_schedule)
        self.cards["overdue"].clicked.connect(self.on_open_schedule)
        self.cards["pending_review"].clicked.connect(self.on_open_review)
        self.cards["email_failures"].clicked.connect(self._open_history)
        self.cards["completed"].clicked.connect(self.on_open_schedule)
        self.open_schedule.clicked.connect(self.on_open_schedule)
        self.open_review.clicked.connect(self.on_open_review)
        self.retranslate()

    def _open_history(self) -> None:
        if self.on_open_history:
            self.on_open_history()

    def retranslate(self) -> None:
        self.title.setText(self.t("dashboard.title"))
        self.open_schedule.setText(self.t("dashboard.open_schedule"))
        self.open_review.setText(self.t("dashboard.open_review"))
        counts = self.vm.counts()
        mapping = {
            "upcoming": ("dashboard.upcoming", counts["upcoming"]),
            "reminders_today": ("dashboard.reminders_today", counts["reminders_today"]),
            "pending_review": ("dashboard.pending_review", counts["pending_review"]),
            "overdue": ("dashboard.overdue", counts["overdue"]),
            "email_failures": ("dashboard.email_failures", counts["email_failures"]),
            "completed": ("dashboard.completed", counts.get("completed", 0)),
        }
        for key, (label, value) in mapping.items():
            self.cards[key].title_label.setText(self.t(label))
            self.cards[key].set_value(str(value))
